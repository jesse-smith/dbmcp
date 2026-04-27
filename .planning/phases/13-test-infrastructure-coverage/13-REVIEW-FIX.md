---
phase: 13-test-infrastructure-coverage
fixed_at: 2026-04-27T00:00:00Z
review_path: .planning/phases/13-test-infrastructure-coverage/13-REVIEW.md
iteration: 1
findings_in_scope: 7
fixed: 7
skipped: 0
status: all_fixed
---

# Phase 13: Code Review Fix Report

**Fixed at:** 2026-04-27
**Source review:** .planning/phases/13-test-infrastructure-coverage/13-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 7 (2 Warning + 5 Info)
- Fixed: 7
- Skipped: 0

All fixes verified by running the full test suite (`uv run pytest tests/`) after each change — 872 passed, 78 skipped, no regressions across all seven fixes.

## Fixed Issues

### WR-01: Mock `__exit__` returns truthy MagicMock, suppressing exceptions

**Files modified:** `tests/conftest.py`
**Commit:** 53d8088
**Applied fix:** Set `return_value=False` on both `dialect` fixture (line 65) and `mock_engine` fixture (line 98) `__exit__` MagicMocks, so `with` blocks do not silently swallow exceptions raised within.

### WR-02: `dialect_inspector` leaks SQLite connection per parametrized test

**Files modified:** `tests/conftest.py`
**Commit:** a3f5316
**Applied fix:** Converted `dialect_inspector` from a return-fixture to a yielding fixture with `try/finally` teardown that calls `connection.close()` and `engine.dispose()`. Non-generic branch also yields (instead of return) to remain consistent.

### IN-01: `pytest_configure` re-registers markers already in `pyproject.toml`

**Files modified:** `tests/conftest.py`
**Commit:** 401f1af
**Applied fix:** Removed the `pytest_configure(config)` hook entirely and replaced it with a comment noting that pyproject.toml registration is authoritative. All markers (integration, slow, performance, dialects) remain registered there.

### IN-02: Brittle real-engine detection in `_configure_magicmock_engine_dialect`

**Files modified:** `tests/unit/test_metadata.py`
**Commit:** 779e06a
**Applied fix:** Replaced the hasattr+isinstance+try/except logic with an explicit `if dialect_ctx.name == "generic": return` check — matches the actual fixture contract and removes unreachable code paths.

### IN-03: `iter(...)` rows in mssql mocks break if code iterates twice

**Files modified:** `tests/unit/test_metadata.py`
**Commit:** 073ddef
**Applied fix:** Replaced both `iter(mssql_rows)` / `iter(data_rows)` one-shot iterators with MagicMock result objects that configure both `__iter__` and `fetchall.return_value`, so implementation changes that call fetchall or re-iterate will continue to work.

### IN-04: `sqlite_schema.load_sqlite_schema` does not validate engine is SQLite

**Files modified:** `tests/fixtures/sqlite_schema.py`
**Commit:** 836d0cc
**Applied fix:** Added an early `assert engine.dialect.name == "sqlite"` with a descriptive error message so non-SQLite engines fail fast with a clear contract violation rather than silently misbehaving on SQLite-specific DDL.

### IN-05: `sqlite_schema` inserts sample data but no test in this phase asserts on it

**Files modified:** `tests/fixtures/sqlite_schema.py`
**Commit:** 5ef2784
**Applied fix:** Added module-level `SAMPLE_ROW_COUNTS = {"customers": 2, "orders": 2, "products": 1}` constant with a comment directing future tests to import rather than hard-code the values. Existing tests were not updated in this pass to avoid scope creep; tests can adopt the constant on next touch.

---

_Fixed: 2026-04-27_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
