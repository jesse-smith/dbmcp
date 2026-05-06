# Phase 13: Test Infrastructure & Coverage — Research

**Researched:** 2026-04-27
**Status:** Ready for planning
**Requirements addressed:** TEST-02, TEST-03

## Executive Summary

Phase 13 delivers a `dialect` pytest fixture parametrized over `['mssql','databricks','generic']`, with opt-out via a `dialects(*names)` marker. A hybrid mocking strategy (real SQLAlchemy + in-memory SQLite for Inspector-driven generic paths; MagicMock + canned Row objects for SQL-execution paths) exercises all three dialect code paths without live connections. Parameterization targets the shared-behavior subset of `test_column_stats.py`, `test_pk_discovery.py`, `test_fk_candidates.py`, and `test_metadata.py`. Coverage floor ratchets from 70% to 85% (current measured: 89.11% on 852 passing tests). The relevant mocking primitives (`_make_mock_dialect`, `_mock_generic_dialect`, `mock_inspector`) already exist in the target test files and can be promoted/unified rather than invented.

The main design decision for planning is **how the hybrid SQLite-vs-MagicMock selection is expressed** for the `generic` path (D-16 is Claude's discretion): a single `dialect` fixture that always yields MagicMock vs. a second `dialect_real` (or `dialect_sqlite`) fixture for tests that genuinely need Inspector-driven reads. Recommendation below: a single `dialect` fixture that yields a bundle; tests that need a real SQLite Inspector request a narrower fixture `dialect_inspector` that constructs a real SQLAlchemy Inspector against an in-memory SQLite engine while preserving dialect identity via the yielded `DialectStrategy`.

## Existing State (surveyed)

**Test count:** 893 tests collected; 852 passing, 41 skipped.
**Coverage:** 89.11% line/branch (pytest --cov=src). `fail_under = 70` in `[tool.coverage.report]`.
**Registered markers:** `integration`, `performance`, `slow` — `dialects` is NOT yet registered.

**Existing dialect mock helpers already in the codebase** (to be unified into a single `dialect` fixture, NOT re-invented):

- `tests/unit/test_column_stats.py` (lines ~547–580): `_make_mock_dialect(name, sqlglot_dialect, supports_indexes)` + three fixtures `mock_mssql_dialect`, `mock_databricks_dialect`, `mock_generic_dialect`. Each returns `Mock()` with `.name`, `.sqlglot_dialect`, `.supports_indexes`, `.quote_identifier` (side_effect=lambda x: f"\`{x}\`").
- `tests/unit/test_pk_discovery.py` (lines 448–470): same three helpers, inline (not fixtures) — `_mock_mssql_dialect`, `_mock_databricks_dialect`, `_mock_generic_dialect`.
- `tests/unit/test_fk_candidates.py` (near line 1025+): `_mock_generic_dialect()` plus `_mock_inspector(columns=...)` helper.
- `tests/conftest.py` (root): `mock_engine`, `mock_connection`, `mock_inspector` (builds a full Inspector-like Mock with `sample_columns`/`sample_indexes`), `sample_columns`, `sample_indexes`, `sample_schemas`, `sample_tables`, `connection_manager`.
- `tests/unit/test_metadata.py` (lines 18–49): `test_engine` fixture constructs an in-memory SQLite database (`sqlite:///:memory:`) with `customers`, `orders`, `products` tables and sample rows — proof that the real-SQLAlchemy+SQLite pattern already works in this codebase and passes the MetadataService tests unchanged.

**Dialect registry** (`src/db/dialects/__init__.py`, `registry.py`): `register_dialect`/`get_dialect` lookup with three pre-registered names (`mssql`, `generic`, `databricks`). Real instances can be constructed in the fixture via `get_dialect(name)()`.

**Fixture organization:** root `tests/conftest.py` (325 lines, 9 fixtures) + `tests/integration/conftest.py` (smaller, for live-connection tests). No existing `tests/fixtures/` python module — `tests/fixtures/test_db_schema.sql` is a MSSQL DDL file used by integration tests.

## Technical Approach

### 1. `dialect` Fixture Design (D-01, D-02, D-03)

Place the fixture in `tests/conftest.py` (top-level, visible everywhere). Single fixture with indirect parameterization:

```python
# tests/conftest.py
from dataclasses import dataclass
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.inspection import inspect as sa_inspect
from unittest.mock import MagicMock, Mock

from src.db.dialects import get_dialect
from src.db.dialects.protocol import DialectStrategy

ALL_DIALECTS = ("mssql", "databricks", "generic")


@dataclass
class DialectTestContext:
    name: str
    dialect: DialectStrategy
    engine: object        # MagicMock (default) — swap to real Engine in dialect_inspector
    connection: object    # MagicMock — tests configure .execute().fetchall() etc.
    inspector: object     # MagicMock by default


@pytest.fixture(params=ALL_DIALECTS, ids=ALL_DIALECTS)
def dialect(request) -> DialectTestContext:
    name = request.param

    # Honor opt-out marker
    marker = request.node.get_closest_marker("dialects")
    if marker and name not in marker.args:
        pytest.skip(f"dialect={name} excluded by @pytest.mark.dialects{marker.args}")

    dialect_obj = get_dialect(name)()  # real strategy instance
    engine = MagicMock(spec=Engine)
    connection = MagicMock()
    inspector = MagicMock()
    engine.connect.return_value.__enter__.return_value = connection
    return DialectTestContext(
        name=name,
        dialect=dialect_obj,
        engine=engine,
        connection=connection,
        inspector=inspector,
    )
```

**Node IDs:** `test_foo[mssql]` / `test_foo[databricks]` / `test_foo[generic]` — directly from `ids=ALL_DIALECTS`.

**Opt-out via marker:** `@pytest.mark.dialects('mssql')` on a test → only the mssql param runs (others skip). Skip is intentional rather than deselect — keeps the skip count visible and discoverable.

**Why real `DialectStrategy` + mock Engine:** the dialect object has real capability flags (`supports_indexes`, `sqlglot_dialect`, `quote_identifier`), so tests exercising `if dialect.supports_indexes:` or `dialect.quote_identifier("foo")` get real behavior — only the SQL execution/inspection surface is mocked.

### 2. Hybrid SQLite Path (D-04, D-07, D-16)

For tests that genuinely drive `Inspector.get_columns()` / `get_pk_constraint()` / `get_unique_constraints()` against the generic dialect (the Phase 10 + Phase 12 isinstance-based type classification code paths), a second fixture yields a real SQLAlchemy Inspector against in-memory SQLite:

```python
@pytest.fixture
def dialect_inspector(dialect) -> DialectTestContext:
    """Augments the `dialect` fixture with a real Inspector + SQLite engine
    for tests that drive Inspector calls. Only swaps the generic path —
    mssql/databricks tests keep the MagicMock inspector (SQLite can't impersonate
    DESCRIBE EXTENDED or sys.indexes). Skip MagicMock-only assertions when the
    backing is real."""
    if dialect.name != "generic":
        return dialect  # MagicMock inspector — unchanged

    engine = create_engine("sqlite:///:memory:")
    _load_sqlite_schema(engine)
    inspector = sa_inspect(engine)
    return DialectTestContext(
        name=dialect.name,
        dialect=dialect.dialect,
        engine=engine,
        connection=engine.connect().__enter__(),  # real connection
        inspector=inspector,
    )
```

**SQLite schema source (D-07):** A new helper `tests/fixtures/sqlite_schema.py` with a small Python-driven SQLAlchemy Core builder. Recommendation: do NOT adapt `tests/fixtures/test_db_schema.sql` — that file has MSSQL-specific syntax (`IDENTITY(1,1)`, `GO` batch separators, `IF NOT EXISTS EXEC('CREATE SCHEMA ...')`, `NVARCHAR`). A Python builder is ~30 lines, avoids maintaining two DDL dialects, and matches the pattern already in `test_metadata.py::test_engine`:

```python
# tests/fixtures/sqlite_schema.py
from sqlalchemy import text

def load_sqlite_schema(engine):
    """Minimal schema for generic-dialect Inspector tests:
    customers(id PK, name, email), orders(id PK, customer_id FK, total),
    products(id PK, name, sku UNIQUE, price)."""
    with engine.connect() as conn:
        conn.execute(text("CREATE TABLE customers (id INTEGER PRIMARY KEY, name TEXT, email TEXT UNIQUE)"))
        conn.execute(text("CREATE TABLE orders (id INTEGER PRIMARY KEY, customer_id INTEGER REFERENCES customers(id), total NUMERIC)"))
        conn.execute(text("CREATE TABLE products (id INTEGER PRIMARY KEY, name TEXT, sku TEXT UNIQUE, price NUMERIC)"))
        conn.commit()
```

Tests that need different schema shapes (e.g., multi-column PK, composite uniques) can call `load_sqlite_schema()` followed by extra `CREATE TABLE` statements, or define local `CREATE TABLE` inline — same pattern as `test_metadata.py`.

### 3. MagicMock Path for SQL Execution (D-05, D-06)

For tests asserting specific SQL execution (Tier 2 aggregates via `connection.execute()`, MSSQL `sys.indexes` DMV queries, Databricks `DESCRIBE EXTENDED` parsing, INFORMATION_SCHEMA responses), use the default `dialect` fixture (MagicMock) and configure canned Row-like objects inline:

```python
def test_bar(dialect):
    if dialect.name == "mssql":
        dialect.connection.execute.return_value.fetchall.return_value = [
            _row(schema_name="dbo", table_name="orders", row_count=100, last_modified=None),
        ]
    # ... assertions that use dialect.dialect (real strategy), dialect.connection (mock)
```

**Row helper (inline or in a small fixtures module):**

```python
def _row(**kwargs):
    """Build a MagicMock that mimics SQLAlchemy Row: both attribute access
    (row.column_name) and mapping access (row._mapping['column_name'])."""
    row = MagicMock()
    for k, v in kwargs.items():
        setattr(row, k, v)
    row._mapping = kwargs
    row.__iter__ = lambda self: iter(kwargs.values())
    return row
```

No JSON/YAML fixture files up front (D-06). If a `DESCRIBE EXTENDED` response block starts repeating across >2 tests, extract then.

### 4. Parameterization Scope (D-08, D-09, D-10)

**Files to parameterize (shared-behavior subset):**
- `tests/unit/test_column_stats.py` — the `ColumnStatsCollector` behavior (type classification, null counts, tier decisions) is shared across dialects. The 3 existing fixture helpers `mock_{mssql,databricks,generic}_dialect` should be REPLACED by the new `dialect` fixture. Tests currently parameterized manually over the three helpers (via multiple test methods) collapse into one body run 3x.
- `tests/unit/test_pk_discovery.py` — Inspector-driven discovery for generic/databricks, INFORMATION_SCHEMA for mssql. Shared-behavior: "find candidates for table T" returns expected columns regardless of backing.
- `tests/unit/test_fk_candidates.py` — candidate column discovery via Inspector for non-MSSQL, INFORMATION_SCHEMA for MSSQL. Shared behavior: "get_candidate_columns with pk_candidates_only=True returns PK cols."
- `tests/unit/test_metadata.py` — the `list_schemas`/`list_tables`/`get_table_schema` subset. Note: `test_engine` already uses SQLite. Parameterize the shared-behavior classes to run under all three dialects (mssql and databricks variants use MagicMock; generic variant keeps the SQLite-backed path).

**Files NOT to parameterize (per D-09, D-10):**
- `tests/unit/test_query.py` — already parametrized via sqlglot; no new signal.
- `tests/unit/test_validation.py` — dialect-aware via sqlglot.
- `tests/unit/test_mssql_dialect.py`, `test_databricks_dialect.py`, `test_generic_dialect.py` — these test the dialect implementations themselves; running the MSSQL test under the generic dialect is nonsense.

**In-place vs parallel migration (D-17):** Recommendation — **in-place for the 3 dialect-mock-helper files** (`test_column_stats.py`, `test_pk_discovery.py`, `test_fk_candidates.py`): their existing `_mock_*_dialect` helpers and the 3 duplicated test methods collapse into single parameterized tests, producing a net code reduction and clearer diff. **Parallel + retire for `test_metadata.py`**: its existing `test_engine` SQLite fixture is used extensively and its dialect is implicitly `generic`; add new parameterized tests under a `class TestSharedMetadataBehavior:` that uses `dialect_inspector`, then retire any now-duplicate tests in a follow-up commit. This minimizes risk in the most-trafficked metadata test file.

### 5. Marker Registration (pyproject.toml)

Add to `[tool.pytest.ini_options].markers`:
```toml
"dialects(*names): restrict a test to specific dialect params (e.g., 'mssql')",
```

Unknown markers currently emit `PytestUnknownMarkWarning` — registering silences these and documents intent.

### 6. Coverage Ratchet (D-11, D-12, D-13)

Change `[tool.coverage.report].fail_under` from `70` to `85` in `pyproject.toml` — single-line edit. No per-module floors (D-12). No CI/GitHub Actions (D-13).

**Rationale:** measured 89.11% → 85% floor leaves ~4 points of headroom for normal churn but blocks a silent ~19-point regression the current 70 floor permits. TEST-03 originally says "70%+ maintained" — D-11 deliberately exceeds this; plans should note the effective floor going forward is 85%.

### 7. Order of Operations (for planner)

1. Register `dialects` marker (pyproject.toml).
2. Add `DialectTestContext`, `ALL_DIALECTS`, `dialect`, `dialect_inspector` fixtures to `tests/conftest.py`. Add `tests/fixtures/sqlite_schema.py` helper.
3. Migrate `test_column_stats.py` — replace `_make_mock_dialect` + 3 fixtures with `dialect`. Collapse triplet tests.
4. Migrate `test_pk_discovery.py` — replace inline `_mock_*_dialect` helpers with `dialect`. Collapse triplet tests. Use `dialect_inspector` where Inspector-driven tests exist.
5. Migrate `test_fk_candidates.py` — same pattern.
6. Add new parameterized shared-behavior class to `test_metadata.py`, retire duplicates in a separate commit/plan.
7. Raise `fail_under` from 70 to 85 (after steps 1–6 land and tests pass).
8. Delete now-unused local `_mock_*_dialect` helpers from the three migrated test files.

Step 7 is a gate: it only lands after all migrated tests pass. Steps 1–6 are independent in logic but touch `conftest.py` (shared) + one test file each, so they should be sequenced, not parallelized.

## Validation Architecture

**Testable contract for this phase** (what a retroactive audit should verify exists in `tests/`):

### Fixture Surface
- `tests/conftest.py` defines `ALL_DIALECTS = ("mssql", "databricks", "generic")`.
- `tests/conftest.py` defines a parametrized `dialect` fixture with `params=ALL_DIALECTS` and `ids=ALL_DIALECTS`.
- `tests/conftest.py` defines a `dialect_inspector` fixture that swaps in a real SQLAlchemy Inspector + SQLite engine for the `generic` case.
- `tests/conftest.py` defines a `DialectTestContext` dataclass (or equivalent bundle) with fields: `name`, `dialect`, `engine`, `connection`, `inspector`.
- The `dialect` fixture honors `@pytest.mark.dialects(*names)` to skip non-listed dialects.

### Marker Registration
- `pyproject.toml` `[tool.pytest.ini_options].markers` registers `dialects(*names): restrict a test to specific dialect params`.

### Parameterization Coverage (per-module)
- `tests/unit/test_column_stats.py` — at least one test class or module-level parameterized test uses the `dialect` fixture (node IDs contain `[mssql]`, `[databricks]`, `[generic]`).
- `tests/unit/test_pk_discovery.py` — same.
- `tests/unit/test_fk_candidates.py` — same.
- `tests/unit/test_metadata.py` — a shared-behavior test class uses the `dialect` (or `dialect_inspector`) fixture and produces the three dialect-suffixed node IDs.

### Preserved Files (no dialect fixture usage required)
- `tests/unit/test_mssql_dialect.py`, `test_databricks_dialect.py`, `test_generic_dialect.py` — remain dialect-specific; NOT expected to use the `dialect` fixture.
- `tests/unit/test_query.py`, `test_validation.py` — remain as-is.

### Coverage Floor
- `pyproject.toml` `[tool.coverage.report].fail_under` is `85` (exact numeric value).
- `uv run pytest --cov=src` exits 0 (i.e., total coverage ≥ 85%). Currently 89.11% so the ratchet is non-disruptive.

### SQLite Schema Helper
- A Python-driven schema builder exists (recommended location: `tests/fixtures/sqlite_schema.py`) that constructs the generic-dialect test schema. The `dialect_inspector` fixture uses it for the generic case. The existing MSSQL DDL file `tests/fixtures/test_db_schema.sql` is NOT modified.

### Regression Ratchet (Dimension 8 audit)
- Running `uv run pytest` after the phase produces ≥ 852 passing tests (current baseline) plus the new parameterized tests. Expected net: ~852 + (3 dialects − 1 original) × (tests collapsed) − (retired duplicates) ≈ comparable or slightly higher test count at much higher effective coverage per dialect.
- No new test uses a live database connection (no `connect_database` or live URL in test code outside `tests/integration/`).

## Risks & Landmines

1. **SQLAlchemy Inspector on SQLite returns different shapes than MSSQL Inspector.** Phase 10/12 code paths were designed around this (Inspector returns `{"type": sa_types.Integer(), ...}` dicts), but any test that asserts a specific `type` string (e.g., `"VARCHAR(100)"`) will break when running under generic/SQLite. Mitigation: assert on `sa_types` class via `isinstance(col["type"], sa_types.Integer)` rather than string equality.

2. **`connection.execute().fetchall()` mocking is brittle.** The three different invocation patterns in the codebase (`connection.execute(stmt).fetchall()`, `connection.execute(stmt).scalar()`, `connection.execute(stmt).mappings().all()`) each need distinct MagicMock configuration. The `_row()` helper addresses the fetchall shape; tests asserting `.scalar()` or `.mappings()` need per-test setup. This is existing complexity, not new — the `dialect` fixture doesn't amplify it.

3. **Databricks doesn't support `IDENTITY`/`PRIMARY KEY` enforcement.** `DatabricksDialect.supports_indexes = False`. Tests running under `[databricks]` that assert "PK discovery returns the declared PK" must rely on INFORMATION_SCHEMA.TABLE_CONSTRAINTS + `ENFORCED='NO'` handling (Phase 11). If a migrated test assumes all dialects return PKs identically, it will fail under databricks — by design. Use `@pytest.mark.dialects(...)` to narrow.

4. **`pytest.skip` inside a fixture based on marker.** `request.node.get_closest_marker("dialects")` on a fixture-level skip is safe but emits a skip record per-param. If the skip count becomes noisy, switch to `pytest_collection_modifyitems` hook to deselect before collection. Low priority — the skip is the clearer UX.

5. **Coverage floor raise lands AFTER migrations.** If raised first, an intermediate commit (after step 3, before step 6) could drop below 85% transiently during refactor. Plans must sequence this: floor change is the LAST step.

6. **41 currently-skipped tests.** These are mostly `integration`/`slow` markers; the migration must not change their skip behavior. Verify `uv run pytest -m integration` still selects them.

## Open Questions for Planner

1. **Single `dialect` fixture vs two fixtures** for the hybrid selection? Recommendation above: two fixtures (`dialect` default MagicMock; `dialect_inspector` swaps in real SQLite Inspector for generic only). Rationale: tests opt into Inspector backing by fixture name — clearest signal at the call site. The planner may override this in favor of a marker-based selection if call-site readability would benefit — both are acceptable under D-16.

2. **Migrate `test_metadata.py` in-place or parallel?** Recommendation above: parallel (add new `TestSharedMetadataBehavior` class, retire duplicates in a follow-up). Planner can override if diff noise is acceptable.

3. **Plan granularity.** Three tightly-coupled deliverables (conftest + marker, per-file migrations, coverage floor). Recommendation: 2–3 plans — (a) conftest fixtures + SQLite helper + marker registration, (b) test file migrations (one plan covering all four, or split 3+1 with metadata as its own), (c) coverage floor ratchet + cleanup of local `_mock_*_dialect` helpers. Planner decides based on context budget.

## RESEARCH COMPLETE
