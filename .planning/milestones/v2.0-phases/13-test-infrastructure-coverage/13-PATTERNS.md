# Phase 13: Test Infrastructure & Coverage — Pattern Map

**Mapped:** 2026-04-27
**Files analyzed:** 7 (6 modified + 1 created)
**Analogs found:** 7 / 7

## File Classification

| File | New/Modified | Role | Data Flow | Closest Analog | Match Quality |
|------|--------------|------|-----------|----------------|---------------|
| `tests/conftest.py` | Modified | test fixture infra | fixture → multiple test files | existing fixtures in same file (`mock_engine`, `mock_inspector`) + `_make_mock_dialect` in `test_column_stats.py` | exact (same file, role-match) |
| `tests/fixtures/sqlite_schema.py` | Created | test fixture infra | schema builder → `dialect_inspector` fixture | `test_metadata.py::test_engine` lines 17–51 | exact (same pattern, extract-and-promote) |
| `tests/unit/test_column_stats.py` | Modified | test module | test setup → test body | self (lines 545–587) | in-place migration |
| `tests/unit/test_pk_discovery.py` | Modified | test module | test setup → test body | self (lines 444–491) | in-place migration |
| `tests/unit/test_fk_candidates.py` | Modified | test module | test setup → test body | self (lines 703–728) | in-place migration |
| `tests/unit/test_metadata.py` | Modified | test module | parametrized fixture → test body | existing class pattern (`TestListSchemas`) + `test_query.py` parametrize idiom | role-match (parallel addition) |
| `pyproject.toml` | Modified | config | config declaration | self lines 68–72 (markers) + line 101 (`fail_under`) | exact |

---

## Pattern Assignments

### `tests/conftest.py` (test fixture infra, fixture → multiple test files)

**Analogs:**
- Structural bundle fixture pattern: `tests/conftest.py::mock_inspector` (lines 242–310) — shows how a single fixture composes related mocks into a callable bundle via `side_effect`.
- Real-dialect bundle material: `tests/unit/test_column_stats.py::_make_mock_dialect` (lines 548–555) — the primitive that supplies `.name`, `.sqlglot_dialect`, `.supports_indexes`, `.quote_identifier`.
- Marker-registration plumbing: `tests/conftest.py::pytest_configure` (lines 318–325).

**Existing mock_engine pattern to mirror** (`tests/conftest.py` lines 29–35):
```python
@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine."""
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock()
    engine.connect.return_value.__exit__ = MagicMock()
    return engine
```

**Existing `_make_mock_dialect` primitive to promote** (`tests/unit/test_column_stats.py` lines 548–573):
```python
def _make_mock_dialect(name, sqlglot_dialect, supports_indexes=True):
    """Create a mock DialectStrategy."""
    dialect = Mock()
    dialect.name = name
    dialect.sqlglot_dialect = sqlglot_dialect
    dialect.supports_indexes = supports_indexes
    dialect.quote_identifier = Mock(side_effect=lambda x: f"`{x}`")
    return dialect

@pytest.fixture
def mock_mssql_dialect():
    return _make_mock_dialect("mssql", "tsql", supports_indexes=True)

@pytest.fixture
def mock_databricks_dialect():
    return _make_mock_dialect("databricks", "databricks", supports_indexes=False)

@pytest.fixture
def mock_generic_dialect():
    return _make_mock_dialect("generic", None, supports_indexes=True)
```

**Marker registration pattern** (`tests/conftest.py` lines 318–325):
```python
def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests requiring database"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
```

**Transformation notes:**
1. Replace the three `_make_mock_dialect`-derived fixtures with a single `dialect` fixture (`params=ALL_DIALECTS`, `ids=ALL_DIALECTS`) that constructs a **real** `DialectStrategy` via `get_dialect(name)()` rather than a `Mock()` — real capability flags, mocked execution surface.
2. Wrap `mock_engine`'s `engine.connect().__enter__` chain into the new `DialectTestContext` bundle so `dialect.connection` is pre-wired the way `mock_engine` already pre-wires `__enter__`/`__exit__`.
3. Add `dialect_inspector` as a **second** fixture that *depends on* `dialect` and swaps in a real SQLite engine/Inspector for `name == "generic"` only (returns `dialect` unchanged otherwise). Mirrors the "fixtures request fixtures" pattern already in `mock_inspector(sample_columns, sample_indexes)`.
4. Preserve `pytest_configure` structure; append a `config.addinivalue_line("markers", "dialects(*names): restrict a test to specific dialect params")` line — but prefer the `pyproject.toml` markers list (the existing `integration`/`performance`/`slow` are already there). Keep the single source of truth consistent.
5. Honor `@pytest.mark.dialects(...)` inside the `dialect` fixture via `request.node.get_closest_marker("dialects")` + `pytest.skip(...)` — new primitive; no codebase analog for in-fixture skip, but the `request.node` pattern is standard pytest.

---

### `tests/fixtures/sqlite_schema.py` (test fixture infra, created)

**Analog:** `tests/unit/test_metadata.py::test_engine` fixture (lines 17–51)

**Full excerpt to adapt:**
```python
@pytest.fixture
def test_engine():
    """Create an in-memory SQLite database with test tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    with engine.connect() as conn:
        # Create test tables
        conn.execute(text("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                total DECIMAL(10,2)
            )
        """))
        conn.execute(text("""
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price DECIMAL(10,2)
            )
        """))

        # Insert sample data for row count testing
        conn.execute(text("INSERT INTO customers VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Carol')"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1, 100.00), (2, 1, 200.00)"))
        conn.execute(text("INSERT INTO products VALUES (1, 'Widget', 10.00)"))
        conn.commit()

    return engine
```

**Transformation notes:**
1. Extract the DDL body into a module-level function `load_sqlite_schema(engine) -> None` (no fixture decorator — that's done in `conftest.py::dialect_inspector`).
2. Add FK + UNIQUE constraints the existing `test_engine` lacks, so PK/FK/unique discovery tests under the `generic` dialect have real Inspector signal:
   - `customers.email TEXT UNIQUE`
   - `orders.customer_id INTEGER REFERENCES customers(customer_id)`
   - `products.sku TEXT UNIQUE`
3. Keep the same `text(...)` + `conn.commit()` idiom — no SQLAlchemy Core `Table`/`MetaData` objects (the plain-SQL form is consistent with the analog and with `test_db_schema.sql`'s style).
4. Do NOT adapt `tests/fixtures/test_db_schema.sql` — it has MSSQL-specific syntax (`IDENTITY(1,1)`, `GO`, `NVARCHAR`, `IF NOT EXISTS EXEC('CREATE SCHEMA ...')`) per RESEARCH.md.
5. `test_engine` in `test_metadata.py` stays untouched (D-17: parallel addition). `load_sqlite_schema` is available to the new `TestSharedMetadataBehavior` class via `dialect_inspector`.

---

### `tests/unit/test_column_stats.py` (test module, in-place migration)

**Analog:** self — lines 545–587 (the block being replaced).

**Block to retire** (imports stay; fixtures/helper go):
```python
# Lines 548–555: helper
def _make_mock_dialect(name, sqlglot_dialect, supports_indexes=True): ...

# Lines 558–573: three parallel fixtures
@pytest.fixture
def mock_mssql_dialect(): ...
@pytest.fixture
def mock_databricks_dialect(): ...
@pytest.fixture
def mock_generic_dialect(): ...

# Lines 577–587: local mock_inspector (name-shadows conftest's mock_inspector!)
@pytest.fixture
def mock_inspector():
    inspector = Mock()
    inspector.get_columns.return_value = [
        {"name": "id", "type": sa_types.Integer()},
        ...
    ]
    return inspector
```

**Call-site pattern currently in file** (triplicated tests — grep for `mock_mssql_dialect`, `mock_databricks_dialect`, `mock_generic_dialect`):
Each behavior test exists three times, once per fixture. These collapse into one test body that takes `dialect` and asserts the shared behavior.

**Transformation notes:**
1. Delete `_make_mock_dialect` + the three `mock_{mssql,databricks,generic}_dialect` fixtures — replaced by `dialect` in `conftest.py`.
2. Rename local `mock_inspector` (lines 577–587) to something like `sa_types_inspector` to avoid shadowing the conftest-level `mock_inspector`, OR move it into a local `_make_sa_types_inspector()` helper (it's sa-types-specific, not generic-inspector-mocking).
3. Collapse triplicated test methods into single methods taking `dialect` (and `dialect_inspector` where the generic Inspector path is relevant). Node IDs become `test_foo[mssql]` / `test_foo[databricks]` / `test_foo[generic]`.
4. Where a test genuinely only applies to one dialect (e.g., MSSQL `sys.indexes` DMV), use `@pytest.mark.dialects('mssql')`.

---

### `tests/unit/test_pk_discovery.py` (test module, in-place migration)

**Analog:** self — lines 444–491 (the helpers being replaced).

**Block to retire** (lines 448–491):
```python
def _mock_mssql_dialect():
    d = MagicMock()
    d.name = "mssql"
    d.sqlglot_dialect = "tsql"
    d.supports_indexes = True
    return d

def _mock_databricks_dialect():
    d = MagicMock()
    d.name = "databricks"
    d.sqlglot_dialect = "databricks"
    d.supports_indexes = False
    return d

def _mock_generic_dialect():
    d = MagicMock()
    d.name = "generic"
    d.sqlglot_dialect = None
    d.supports_indexes = True
    return d

def _mock_inspector_for_pk(
    pk_columns=None, unique_constraints=None, columns=None, pk_name=None,
):
    insp = MagicMock()
    pk_info = {"constrained_columns": pk_columns or [], "name": pk_name}
    insp.get_pk_constraint.return_value = pk_info
    insp.get_unique_constraints.return_value = unique_constraints or []
    insp.get_columns.return_value = columns or []
    return insp
```

**Call-site pattern in file** (sample, line 501–519):
```python
def test_pk_discovered_via_inspector_generic(self):
    """PK discovered via Inspector for generic dialect."""
    dialect = _mock_generic_dialect()
    inspector = _mock_inspector_for_pk(
        pk_columns=["id"],
        columns=[
            {"name": "id", "type": MagicMock(__str__=lambda s: "INTEGER"), "nullable": False},
            ...
        ],
    )
    conn = MagicMock()
    discovery = PKDiscovery(conn, "public", "users", dialect=dialect, inspector=inspector)
    ...
```

**Transformation notes:**
1. Delete three `_mock_*_dialect` helpers — replaced by `dialect` fixture.
2. Keep `_mock_inspector_for_pk` as a local helper (it's pk-specific shape-builder; not a fixture). Or have it take `dialect` and return inspector attached to the context.
3. Tests that use `_mock_generic_dialect()` + inline MagicMock inspector become parametrized over `dialect` (MagicMock inspector) OR `dialect_inspector` (real SQLite Inspector) depending on whether they assert on SQL-text/mock calls vs. real Inspector return shapes.
4. Tests currently named `..._generic`, `..._mssql`, `..._databricks` suffixes collapse into a single test per behavior — the suffix moves to the pytest node ID.

---

### `tests/unit/test_fk_candidates.py` (test module, in-place migration)

**Analog:** self — lines 703–728 (the helpers being replaced).

**Block to retire** (lines 703–728):
```python
def _mock_generic_dialect():
    """Create a mock generic dialect."""
    d = MagicMock()
    d.name = "generic"
    d.sqlglot_dialect = None
    d.supports_indexes = True
    return d

def _mock_inspector(
    table_names=None,
    columns=None,
    pk_constraint=None,
    unique_constraints=None,
    indexes=None,
):
    """Create a mock Inspector."""
    insp = MagicMock()
    insp.get_table_names.return_value = table_names or []
    insp.get_columns.return_value = columns or []
    insp.get_pk_constraint.return_value = pk_constraint or {
        "constrained_columns": [], "name": None,
    }
    insp.get_unique_constraints.return_value = unique_constraints or []
    insp.get_indexes.return_value = indexes or []
    return insp
```

**Call-site pattern** (20 call sites per grep, e.g. line 740–743):
```python
dialect = _mock_generic_dialect()
inspector = _mock_inspector(table_names=["Customers", "Products", "Orders"])
conn = MagicMock()
```

**Transformation notes:**
1. Delete `_mock_generic_dialect` — replaced by `dialect` fixture.
2. Delete `_mock_mssql_dialect` / `_mock_databricks_dialect` if present earlier in file (the file also has the three-dialect helpers per RESEARCH.md line 23).
3. Keep `_mock_inspector(...)` as a **local** shape-builder helper — it's shape-customization-per-test (column lists, pk dicts, etc.) and inlining its logic would bloat tests. Rename to something like `_build_inspector(...)` to distinguish from the conftest `mock_inspector` fixture.
4. At call sites, replace `dialect = _mock_generic_dialect()` with the fixture-injected `dialect` parameter; use `dialect.inspector` for the default MagicMock or construct a custom shape via `_build_inspector(...)` where needed.
5. Narrow tests that are genuinely generic-only (Inspector-driven FK discovery) with `@pytest.mark.dialects('generic')`, since MSSQL FK discovery uses INFORMATION_SCHEMA, not Inspector.

---

### `tests/unit/test_metadata.py` (test module, parallel + retire)

**Analogs:**
- Existing class pattern in same file: `class TestListSchemas:` (line 54) uses the shared `test_engine` fixture.
- Parametrize idiom: `tests/unit/test_query.py::TestCTEQueryParsing` (lines 335–380+).

**Existing class pattern to parallel** (`test_metadata.py` lines 54–60):
```python
class TestListSchemas:
    """Tests for MetadataService.list_schemas() - T012A"""

    def test_list_schemas_returns_schema_objects(self, test_engine):
        """T012A: Verify list_schemas returns Schema objects with correct fields."""
        service = MetadataService(test_engine)
        ...
```

**Parametrize idiom** (`test_query.py` lines 335–352):
```python
@pytest.mark.parametrize(
    "sql,expected",
    [
        ("WITH cte AS (SELECT 1 AS val) SELECT * FROM cte", QueryType.SELECT),
        ...
    ],
)
```

**Transformation notes:**
1. **Do NOT modify** `test_engine` fixture (lines 17–51) — it stays; `TestListSchemas` and friends continue to use it unchanged. This is the parallel-addition path (D-17).
2. Add a new class `class TestSharedMetadataBehavior:` below the existing classes. Methods take `dialect` (for MagicMock-backed assertions) or `dialect_inspector` (for real-Inspector assertions on the generic path).
3. Follow the existing naming convention (`test_<behavior>_<dialect_distinction>`) but let the node ID carry the dialect suffix instead: `test_list_schemas_returns_schema_objects[mssql]` etc.
4. The parametrize idiom from `test_query.py` is NOT applied directly at the class level — parameterization comes from the `dialect` fixture (indirect). Use `@pytest.mark.parametrize` only for per-test sub-cases (e.g., "integer types", "string types") within a dialect-parametrized test.
5. Retire duplicates in a **follow-up commit** after verifying parity — don't couple retirement to the addition.

---

### `pyproject.toml` (config)

**Analogs within same file:**
- Marker list: lines 68–72.
- Coverage floor: line 101.

**Existing markers block** (lines 68–72):
```toml
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "performance: marks tests as performance tests (deselect with '-m \"not performance\"')",
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]
```

**Existing coverage floor** (line 101):
```toml
[tool.coverage.report]
fail_under = 70
```

**Transformation notes:**
1. Append one line to the `markers` array:
   ```toml
   "dialects(*names): restrict a parametrized dialect test to specific dialect params (e.g., 'mssql')",
   ```
   Match the existing `"<name>: <description>"` string-form style exactly — preserve trailing-comma + double-quote conventions (note: `'` inside `"..."` per the `integration` example).
2. Single-line change: `fail_under = 70` → `fail_under = 85`.
3. Both changes are trivial; the sequencing (raise floor LAST, per RESEARCH risk #5) is a plan-ordering concern, not a pattern concern.
4. Note: `pytest_configure` in `tests/conftest.py` also registers `integration`/`slow` via `addinivalue_line`. The `pyproject.toml` markers list is the authoritative source (TOML form); `pytest_configure` is redundant but harmless. Do NOT add `dialects` to `pytest_configure` — TOML registration alone is sufficient, and mixing the two would create drift risk.

---

## Shared Patterns

### Dialect Strategy Construction
**Source:** `src/db/dialects/__init__.py` + `registry.py` (`get_dialect(name) -> type[DialectStrategy]`)
**Apply to:** `tests/conftest.py::dialect` fixture
**Usage:**
```python
from src.db.dialects import get_dialect
dialect_obj = get_dialect(name)()   # real DialectStrategy instance
```
Real object preferred over `Mock()` — gives tests real `supports_indexes`, `quote_identifier`, `sqlglot_dialect` behavior. Only engine/connection/inspector are mocked.

### MagicMock Engine Connection Chain
**Source:** `tests/conftest.py::mock_engine` (lines 29–35)
**Apply to:** `dialect` fixture default path
**Pattern:**
```python
engine = MagicMock(spec=Engine)
connection = MagicMock()
engine.connect.return_value.__enter__.return_value = connection
```
Wires up `with engine.connect() as conn:` to yield the mock connection so tests can configure `connection.execute(...).fetchall()` etc.

### In-Memory SQLite Engine Construction
**Source:** `tests/unit/test_metadata.py::test_engine` (line 20)
**Apply to:** `dialect_inspector` fixture (generic path only) + `tests/fixtures/sqlite_schema.py`
**Pattern:**
```python
engine = create_engine("sqlite:///:memory:", echo=False)
with engine.connect() as conn:
    conn.execute(text("CREATE TABLE ..."))
    conn.commit()
```

### Marker Skip in Fixture
**Source:** Standard pytest idiom (no exact codebase analog); closest is the `pytest_configure` registration pattern (lines 318–325) + marker consumption usually in test bodies.
**Apply to:** `dialect` fixture's opt-out path
**Pattern:**
```python
marker = request.node.get_closest_marker("dialects")
if marker and name not in marker.args:
    pytest.skip(f"dialect={name} excluded by @pytest.mark.dialects{marker.args}")
```

### Local Shape-Builder Helpers (keep, don't promote)
**Source:** `tests/unit/test_pk_discovery.py::_mock_inspector_for_pk` (lines 475–491), `tests/unit/test_fk_candidates.py::_mock_inspector` (lines 712–728)
**Apply to:** Retained **local** helpers after migration — these are per-test-file shape customization (pk dicts, column lists with specific types), not dialect construction. Rename to `_build_inspector(...)` to disambiguate from the conftest `mock_inspector` fixture.

---

## No Analog Found

None. Every file has a concrete existing analog — this phase is primarily **promotion + unification** of patterns already present in the codebase, not invention.

---

## Metadata

**Analog search scope:**
- `tests/conftest.py` (root — 325 lines, 9 fixtures)
- `tests/unit/test_column_stats.py` (dialect fixture block)
- `tests/unit/test_pk_discovery.py` (dialect helper block)
- `tests/unit/test_fk_candidates.py` (dialect helper block)
- `tests/unit/test_metadata.py` (test_engine + TestListSchemas)
- `tests/unit/test_query.py` (parametrize idioms)
- `pyproject.toml` (markers + coverage config)

**Files scanned:** 7
**Pattern extraction date:** 2026-04-27

## PATTERN MAPPING COMPLETE
