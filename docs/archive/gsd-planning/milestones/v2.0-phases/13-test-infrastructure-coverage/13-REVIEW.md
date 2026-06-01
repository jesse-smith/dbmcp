---
phase: 13-test-infrastructure-coverage
reviewed: 2026-04-27T00:00:00Z
depth: standard
files_reviewed: 7
files_reviewed_list:
  - pyproject.toml
  - tests/conftest.py
  - tests/fixtures/sqlite_schema.py
  - tests/unit/test_column_stats.py
  - tests/unit/test_fk_candidates.py
  - tests/unit/test_metadata.py
  - tests/unit/test_pk_discovery.py
findings:
  critical: 0
  warning: 2
  info: 5
  total: 7
status: issues_found
---

# Phase 13: Code Review Report

**Reviewed:** 2026-04-27
**Depth:** standard
**Files Reviewed:** 7
**Status:** issues_found

## Summary

Phase 13 introduces a clean dialect/dialect_inspector fixture pair in `tests/conftest.py`, a minimal shared SQLite schema builder in `tests/fixtures/sqlite_schema.py`, and migrates three unit test modules onto the parametrized fixtures. Overall shape is sound: the `dialects` marker is correctly registered in `pyproject.toml`, the `dialects` opt-out marker works as designed, and generic/mssql/databricks surfaces are cleanly separated (real Inspector for generic only, MagicMock for the other two). Fixtures are function-scoped so cross-test state leakage is not a concern.

Two warnings worth fixing: the mock engine's `__exit__` returns a truthy MagicMock which could suppress exceptions in `with` blocks that rely on it, and `dialect_inspector` leaks a SQLite connection per generic-parametrized test. Remaining findings are info-level cleanups (dead code, brittle heuristics, iterator-based mocks).

No bugs in the test schema, no security issues, no correctness issues in the migrated assertions themselves. The coverage config in `pyproject.toml` (`fail_under=85`, `branch=true`, `source=["src"]`) is sensible and unchanged.

## Warnings

### WR-01: Mock `__exit__` returns truthy MagicMock, suppressing exceptions

**File:** `tests/conftest.py:64-65`

**Issue:** The `dialect` fixture wires
```python
engine.connect.return_value.__exit__ = MagicMock()
```
Calling this `__exit__(exc_type, exc, tb)` returns a fresh `MagicMock` object, which is truthy. Python's `with` protocol treats a truthy return from `__exit__` as "exception handled, suppress it." Any production code path under test that does `with engine.connect() as conn: ...` will silently swallow exceptions raised inside the `with` block, which can mask real bugs (e.g. an exception that should propagate out of `list_tables` would be suppressed and the test would see a spurious success).

The same pattern exists at `mock_engine` fixture line 98 (`engine.connect.return_value.__exit__ = MagicMock()`).

**Fix:**
```python
engine.connect.return_value.__exit__ = MagicMock(return_value=False)
```
Apply in both the `dialect` fixture and the `mock_engine` fixture.

### WR-02: `dialect_inspector` leaks SQLite connection per parametrized test

**File:** `tests/conftest.py:79-86`

**Issue:** The generic branch opens `connection = engine.connect()` and builds an `Inspector`, but never closes either. Since this fixture runs once per generic-parametrized test (and `ALL_DIALECTS` includes `"generic"` for every `dialect_inspector`-using test), each such test leaks one SQLAlchemy `Connection` and one `Engine` (the engine is GC'd, but the explicit connection is not tied to the fixture teardown). With 50+ tests migrated, this accumulates during a run. More subtly, nothing owns the lifecycle — if a future test mutates state on `connection`, the next test's connection is a different object but points at a new `:memory:` DB, so correctness is not impacted today, but the leak is real.

**Fix:** Convert to a yielding fixture with teardown:
```python
@pytest.fixture
def dialect_inspector(dialect):
    if dialect.name != "generic":
        yield dialect
        return
    engine = create_engine("sqlite:///:memory:", echo=False)
    load_sqlite_schema(engine)
    connection = engine.connect()
    try:
        inspector = sa_inspect(engine)
        yield DialectTestContext(
            name=dialect.name, dialect=dialect.dialect,
            engine=engine, connection=connection, inspector=inspector,
        )
    finally:
        connection.close()
        engine.dispose()
```

## Info

### IN-01: `pytest_configure` re-registers markers already in `pyproject.toml`

**File:** `tests/conftest.py:382-389`

**Issue:** `integration` and `slow` markers are already registered in `pyproject.toml:69-73` under `[tool.pytest.ini_options] markers`. The `pytest_configure` hook re-adds them, which is harmless but dead code. The `dialects` marker (used heavily by this phase) is correctly registered in pyproject.toml and does not need a duplicate here.

**Fix:** Delete the `pytest_configure` block, or (if intentional for redundancy) add a comment noting the pyproject.toml registration is authoritative.

### IN-02: Brittle real-engine detection in `_configure_magicmock_engine_dialect`

**File:** `tests/unit/test_metadata.py:1046-1061`

**Issue:** The function tries to distinguish `MagicMock(spec=Engine)` from a real `Engine` with a `hasattr + isinstance` check, then a `try/except AttributeError` fallback. `MagicMock(spec=Engine)` DOES expose `.dialect` as an auto-generated Mock (because `Engine` has that attribute in its spec), so the first branch's condition evaluates to `True` for spec'd engines and the try/except path is effectively unreachable in the current fixture setup. The logic works by accident — if someone later builds a non-spec'd MagicMock engine, the try/except path would fire in a surprising way.

**Fix:** Use the `DialectTestContext.name` to branch explicitly:
```python
def _configure_magicmock_engine_dialect(dialect_ctx):
    if dialect_ctx.name == "generic":
        return  # real Engine — don't touch
    dialect_ctx.engine.dialect = MagicMock()
    dialect_ctx.engine.dialect.name = dialect_ctx.name
```
This is the actual contract the fixture enforces and is easier to reason about.

### IN-03: `iter(...)` rows in mssql mocks break if code iterates twice

**File:** `tests/unit/test_metadata.py:1101, 1139`

**Issue:** `dialect_inspector.connection.execute.return_value = iter(mssql_rows)` returns a one-shot iterator. If the implementation (now or later) calls `.fetchall()` then also iterates the result, or retries, the second consumption yields nothing and the test fails opaquely. Works today because `list_schemas` iterates the result exactly once.

**Fix:** Use a list or a `MagicMock` with both `__iter__` and `fetchall` configured:
```python
mock_result = MagicMock()
mock_result.__iter__ = lambda self: iter(mssql_rows)
mock_result.fetchall.return_value = mssql_rows
dialect_inspector.connection.execute.return_value = mock_result
```
Low priority — flag for the next time this test needs to change.

### IN-04: `sqlite_schema.load_sqlite_schema` does not validate engine is SQLite

**File:** `tests/fixtures/sqlite_schema.py:15`

**Issue:** The function signature accepts `Engine` but the DDL is SQLite-specific (`INTEGER PRIMARY KEY` auto-increments, `REFERENCES` syntax). Passing a non-SQLite engine would silently fail in confusing ways. A one-line assertion would surface the contract.

**Fix:**
```python
def load_sqlite_schema(engine: Engine) -> None:
    assert engine.dialect.name == "sqlite", (
        f"load_sqlite_schema requires a SQLite engine, got {engine.dialect.name!r}"
    )
    ...
```

### IN-05: `sqlite_schema` inserts sample data but no test in this phase asserts on it

**File:** `tests/fixtures/sqlite_schema.py:48-50`

**Issue:** The docstring promises "sample data for row-count assertions," and the inserted rows (2 customers, 2 orders, 1 product) do match the counts asserted in `test_metadata.py::TestSharedMetadataBehavior::test_list_tables_returns_table_objects` generic branch. That linkage is invisible — if someone changes row counts here to "clean up," unrelated tests break. Consider either (a) centralizing the expected counts as a module-level dict that tests import, or (b) adding a brief comment in the DDL block listing which tests depend on these counts.

**Fix (option a):**
```python
SAMPLE_ROW_COUNTS = {"customers": 2, "orders": 2, "products": 1}
```
and import from tests that assert on counts.

---

_Reviewed: 2026-04-27_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
