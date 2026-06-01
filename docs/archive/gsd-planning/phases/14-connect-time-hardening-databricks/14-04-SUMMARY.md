---
phase: 14-connect-time-hardening-databricks
plan: 04
subsystem: tests.unit
tags: [databricks, ident-01, ident-02, test-01, test-02, regression-tests]
requires:
  - "14-01: DatabricksDialect.create_engine ValueError + list_catalogs"
  - "14-02: list_schemas no SHOW CATALOGS fallback"
  - "14-03: ConnectionManager._require_databricks_catalog enrichment helper"
provides:
  - "IDENT-01 regression coverage (D-14 a/b/c/d) via engine-spy SHOW CATALOGS pattern"
  - "IDENT-02 regression coverage (D-15) — list_schemas issues zero SHOW CATALOGS"
  - "TEST-01 (D-16) env-var substitution coverage for catalog and schema_name"
  - "TEST-02 (D-17) SQLAlchemyError → ConnectionError wrap coverage"
affects:
  - tests/unit/test_connect_with_config_databricks.py
  - tests/unit/test_metadata.py
tech_added: []
patterns:
  - "Engine-spy with SHOW CATALOGS routing — _make_engine_spy_with_catalogs(catalog_names)"
  - "Negative-assertion regression test (no SHOW CATALOGS during list_schemas)"
  - "Real dialect.list_catalogs path exercised via spy engine; only the engine boundary mocked"
key_files:
  created:
    - .planning/phases/14-connect-time-hardening-databricks/14-04-SUMMARY.md
  modified:
    - tests/unit/test_connect_with_config_databricks.py
    - tests/unit/test_metadata.py
decisions:
  - "Plan-3 already shipped overlapping IDENT-01 tests that patch list_catalogs directly. Plan-4 adds the engine-spy variant alongside them — they exercise complementary surfaces (the spy variant runs the real list_catalogs code through SHOW CATALOGS routing on a MagicMock engine)."
  - "Inserted IDENT-02 regression test inside the existing TestCatalogListSchemas class in test_metadata.py rather than creating a new module. Keeps Databricks list_schemas tests clustered."
  - "Promoted _make_engine_spy_with_catalogs to the same module as _make_engine_spy. No conftest extraction yet (Rule of Three not yet hit — only one consumer pattern across two tests)."
  - "All new tests use src.db.connection.ConnectionError (custom), not Python's built-in ConnectionError. Caught early on first run."
metrics:
  duration: ~20 minutes
  completed: 2026-05-13
---

# Phase 14 Plan 04: Phase 14 closure regression tests Summary

Landed six regression tests that lock the Phase 14 fixes (Plans 01-03) and close all four
phase requirements (IDENT-01, IDENT-02, TEST-01, TEST-02). The new tests exercise the
end-to-end shape — including the chained `__cause__ ValueError`, the `Accessible catalogs:`
listing, the both-problems probe-failure message, env-var substitution, and the
`SQLAlchemyError → ConnectionError` wrap — through a spy engine that routes `SHOW CATALOGS`
to a fixture catalog list. Full suite green at 987 passed, 78 skipped; coverage 91.14%.

## Tasks Executed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 | IDENT-02 regression test (no SHOW CATALOGS during list_schemas) | `d0deae9` | `tests/unit/test_metadata.py` |
| 2 | IDENT-01 closure tests (D-14 a/b/c/d) via engine-spy | `52af085` | `tests/unit/test_connect_with_config_databricks.py` |
| 3 | TEST-01 env-var substitution + TEST-02 SQLAlchemyError wrap | `3d9a197` | `tests/unit/test_connect_with_config_databricks.py` |

## Six New Test Functions

| Function | File | Requirement |
|---|---|---|
| `test_list_schemas_databricks_does_not_fall_back_to_show_catalogs` | `tests/unit/test_metadata.py` (in `TestCatalogListSchemas`) | IDENT-02 (D-15) |
| `test_connect_databricks_catalog_required_lists_accessible_catalogs` | `tests/unit/test_connect_with_config_databricks.py` | IDENT-01 (D-14 a/b/c) |
| `test_connect_databricks_catalog_required_surfaces_show_catalogs_failure` | `tests/unit/test_connect_with_config_databricks.py` | IDENT-01 (D-14 d) |
| `test_connect_with_url_databricks_requires_catalog` | `tests/unit/test_connect_with_config_databricks.py` | IDENT-01 (D-14 URL mode) |
| `test_env_var_substitution_for_catalog_and_schema` | `tests/unit/test_connect_with_config_databricks.py` | TEST-01 (D-16) |
| `test_sqlalchemy_error_wrapped_as_connection_error` | `tests/unit/test_connect_with_config_databricks.py` | TEST-02 (D-17) |

## Shared Helper

`_make_engine_spy_with_catalogs(catalog_names: list[str])` was added at the top of
`tests/unit/test_connect_with_config_databricks.py` next to the existing `_make_engine_spy`.
It returns a MagicMock engine whose `conn.execute()` routes:

- `SHOW CATALOGS` → fetchall returns `[(name,) for name in catalog_names]`
- everything else → MagicMock result with `fetchone -> (1,)` (so a SELECT 1 probe also works)

This lets the closure tests run the **real** `DatabricksDialect.list_catalogs` code path
against the probe engine constructed by `_require_databricks_catalog`, providing one extra
notch of coverage versus Plan 03's tests (which patched `list_catalogs` directly).

## Verification Results

- `uv run pytest tests/unit/test_metadata.py::TestCatalogListSchemas::test_list_schemas_databricks_does_not_fall_back_to_show_catalogs -x -v` → **1 passed**
- All three IDENT-01 tests → **3 passed**
- TEST-01 + TEST-02 → **2 passed**
- `uv run pytest tests/ -q` → **987 passed, 78 skipped** (was 974+78 pre-Plan-04; +13 includes the 6 new tests + Plan-03 tests already present in the baseline; +6 net new in this plan)
- `uv run pytest tests/ --cov=src --cov-fail-under=85` → **91.14%** total coverage (well above the 85% floor)
- `uv run ruff check tests/unit/test_connect_with_config_databricks.py tests/unit/test_metadata.py` → **All checks passed**

### Acceptance-criteria greps

- `grep -n "test_list_schemas_databricks_does_not_fall_back_to_show_catalogs" tests/unit/test_metadata.py` → 1 match
- `grep -n "SHOW CATALOGS" tests/unit/test_metadata.py` → matches the new test's negative assertion
- `grep -n "test_connect_databricks_catalog_required_lists_accessible_catalogs\|test_connect_databricks_catalog_required_surfaces_show_catalogs_failure\|test_connect_with_url_databricks_requires_catalog\|test_env_var_substitution_for_catalog_and_schema\|test_sqlalchemy_error_wrapped_as_connection_error" tests/unit/test_connect_with_config_databricks.py` → 5 matches (all expected)
- `grep -n "_make_engine_spy_with_catalogs" tests/unit/test_connect_with_config_databricks.py` → 3 matches (definition + 2 uses)
- `grep -n "Accessible catalogs:" tests/unit/test_connect_with_config_databricks.py` → 2 matches in the new tests' assertions
- `grep -n "SHOW CATALOGS failed" tests/unit/test_connect_with_config_databricks.py` → 1 match (probe-failure test)

## Deviations from Plan

### [Rule 1 — Bug] First test run failed because tests used Python's built-in `ConnectionError`

- **Found during:** Task 2 first run
- **Issue:** The plan's task skeletons used `pytest.raises(ConnectionError)`. `src.db.connection`
  defines its own `ConnectionError` class (custom exception), and the existing tests in this
  file consistently import it as `from src.db.connection import ConnectionError as DBConnectionError`.
  The first run of the new IDENT-01 tests printed the right error type (`src.db.connection.ConnectionError`)
  but the test itself was using Python's `builtins.ConnectionError`, so `pytest.raises` did not match.
- **Fix:** Imported `from src.db.connection import ConnectionError as DBConnectionError` inside
  each new test (matching the existing file convention) and switched the three `pytest.raises`
  contexts to use it. TEST-02 was written correctly from the start (added after the fix landed).
- **Files modified:** `tests/unit/test_connect_with_config_databricks.py`
- **Commit:** Bundled into `52af085` (same RED→GREEN cycle).

No other deviations. Plan executed as written.

## Authentication Gates

None.

## Known Stubs

None — every new test exercises live code paths and asserts concrete invariants.

## TDD Gate Compliance

This plan creates regression-locking tests against production code that already shipped in
Plans 01-03. There is no RED phase in the strict sense — the tests pass on first run because
the upstream fixes are already in place. Each task is a single `test(14-04)` commit (no
matching `feat`), which is the appropriate gate shape for a "lock the fix" plan.

The plan-level type was `execute` with all three tasks marked `tdd="true"`; per the TDD
reference, tests-only commits for regression-locking are valid output for `tdd="true"`
when the production fix is already landed and the test purpose is to lock it in place.

## Discretionary Decisions

1. **Engine-spy helper placement** — kept in the same module as the existing `_make_engine_spy`
   rather than promoted to `conftest.py`. Two consumers, both in this file. Will revisit if a
   third consumer appears (Rule of Three).
2. **Test coexistence with Plan 03** — Plan 03 already shipped IDENT-01 tests with similar
   names that patch `list_catalogs` directly. Plan 04's tests use the engine-spy variant.
   Both shapes valuable: the patch variant guards against the helper being deleted; the
   engine-spy variant guards against `list_catalogs` regressing to a different SQL statement.
3. **IDENT-02 regression test inserted in `TestCatalogListSchemas` class** — clusters with
   the seven other Databricks list_schemas tests. Method form preserves the test class style.
4. **Negative assertion shape for IDENT-02** — `assert not any("SHOW CATALOGS" in s.upper()
   for s in executed_statements)`. Case-insensitive on the statement side (already upper),
   case-sensitive on the literal substring. Matches the plan's `must_haves.truths` exact
   wording.

## Self-Check

### Files claimed to be created/modified

- `tests/unit/test_metadata.py` — **FOUND** (modified)
- `tests/unit/test_connect_with_config_databricks.py` — **FOUND** (modified)
- `.planning/phases/14-connect-time-hardening-databricks/14-04-SUMMARY.md` — **FOUND** (this file)

### Commits claimed

- `d0deae9` test(14-04): add IDENT-02 regression test asserting no SHOW CATALOGS in list_schemas — **FOUND**
- `52af085` test(14-04): add IDENT-01 closure tests with engine-spy SHOW CATALOGS coverage — **FOUND**
- `3d9a197` test(14-04): add TEST-01 env-var substitution and TEST-02 SQLAlchemyError wrap tests — **FOUND**

## Self-Check: PASSED
