---
phase: 13
plan: 01
subsystem: test-infrastructure
tags: [pytest, fixtures, dialect, test-infrastructure]
requirements: [TEST-02]
dependency_graph:
  requires:
    - src.db.dialects.get_dialect (existing)
    - src.db.dialects.protocol.DialectStrategy (existing)
  provides:
    - tests.conftest.ALL_DIALECTS
    - tests.conftest.DialectTestContext
    - tests.conftest.dialect (parametrized fixture)
    - tests.conftest.dialect_inspector (hybrid fixture)
    - tests.fixtures.sqlite_schema.load_sqlite_schema
    - pyproject.toml::markers::dialects
  affects:
    - Plans 13-02 and 13-03 (test migration consumers)
tech_stack:
  added: []
  patterns:
    - Parametrized pytest fixture with per-dialect node-ID suffixes
    - Hybrid real-vs-MagicMock Inspector via fixture composition
    - Marker-based opt-out pattern (@pytest.mark.dialects)
key_files:
  created:
    - tests/fixtures/sqlite_schema.py
  modified:
    - tests/conftest.py
    - pyproject.toml
decisions:
  - Execute Task 2 before Task 1 to resolve forward import dependency (tests/conftest.py imports load_sqlite_schema from tests/fixtures/sqlite_schema.py)
metrics:
  duration: ~4 min
  completed: 2026-04-27
  tasks: 2
  files: 3
---

# Phase 13 Plan 01: Dialect Test Fixture Infrastructure Summary

**One-liner:** Shared `dialect` / `dialect_inspector` pytest fixtures over `('mssql','databricks','generic')` with SQLite-backed real Inspector for generic, enabling Wave 2 test de-triplication.

## What Shipped

Test infrastructure prerequisites for Plans 13-02 and 13-03. Three files changed, no `src/` touched, existing 852-test baseline preserved.

### tests/conftest.py (modified)

- `ALL_DIALECTS = ("mssql", "databricks", "generic")` — module-level constant.
- `DialectTestContext` dataclass with `name`, `dialect` (real `DialectStrategy`), `engine`, `connection`, `inspector`.
- `dialect` fixture — parametrized with `params=ALL_DIALECTS, ids=ALL_DIALECTS`. Resolves real strategy via `get_dialect(name)()`, wires MagicMock engine/connection/inspector with `engine.connect().__enter__()` chain. Honors `@pytest.mark.dialects(...)` opt-out via `pytest.skip`.
- `dialect_inspector` fixture — delegates to `dialect` unchanged for mssql/databricks; for `generic`, creates `sqlite:///:memory:` engine, loads schema via `load_sqlite_schema`, returns real `sa_inspect(engine)` Inspector.
- Existing `mock_engine`, `mock_connection`, `mock_inspector`, sample-data fixtures, and `pytest_configure` untouched.

### tests/fixtures/sqlite_schema.py (created)

- `load_sqlite_schema(engine)` — creates `customers(customer_id PK, name NOT NULL, email UNIQUE)`, `orders(order_id PK, customer_id FK→customers, total)`, `products(product_id PK, name NOT NULL, sku UNIQUE, price)`, and seeds minimal data.
- No MSSQL-specific syntax (no IDENTITY, GO, NVARCHAR, IF NOT EXISTS EXEC). `tests/fixtures/test_db_schema.sql` intentionally not reused (documented in module docstring).

### pyproject.toml (modified)

- Appended `"dialects(*names): ..."` entry to `[tool.pytest.ini_options].markers`. No duplicate registration in `pytest_configure` (single source of truth per plan D-16).

## Verification

- `uv run pytest tests/ -q` → **852 passed, 41 skipped** (matches pre-plan baseline — no regressions).
- `uv run pytest --collect-only tests/ 2>&1 | grep -c PytestUnknownMarkWarning` → **0**.
- `uv run python -c "from tests.conftest import ALL_DIALECTS, DialectTestContext, dialect, dialect_inspector; assert ALL_DIALECTS == ('mssql','databricks','generic')"` → exits 0.
- Direct SQLite Inspector verification: tables `['customers','orders','products']` present, FK `orders.customer_id → customers.customer_id` detected, UNIQUE constraint on `products.sku` detected.
- Acceptance grep counts all return `1`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocker] Reordered task execution**

- **Found during:** Pre-execution dependency analysis.
- **Issue:** Task 1 (conftest.py edits) imports `load_sqlite_schema` from the module Task 2 creates. Committing Task 1 first would leave the working tree with a broken import between commits.
- **Fix:** Executed Task 2 first (create `tests/fixtures/sqlite_schema.py`), committed, then Task 1 (conftest.py + pyproject.toml), committed. Final commit graph is linear; each commit leaves the test suite green.
- **Files modified:** None beyond what the plan specified.
- **Commits:** `fb6d9fa` (Task 2, reordered to first), `90da635` (Task 1, reordered to second).

No other deviations. No authentication gates. No architectural questions.

## Commits

| Commit    | Scope   | Description                                                        |
| --------- | ------- | ------------------------------------------------------------------ |
| `fb6d9fa` | Task 2  | Add SQLite schema builder for generic-dialect Inspector tests      |
| `90da635` | Task 1  | Add dialect/dialect_inspector fixtures; register dialects marker   |

## Known Stubs

None. Both fixtures are fully wired; marker is fully registered. Plans 13-02 and 13-03 will consume them unchanged.

## Self-Check: PASSED

- `tests/conftest.py` — FOUND (modified, imports and fixtures present)
- `tests/fixtures/sqlite_schema.py` — FOUND
- `pyproject.toml` — FOUND (marker appended)
- Commit `fb6d9fa` — FOUND in git log
- Commit `90da635` — FOUND in git log
