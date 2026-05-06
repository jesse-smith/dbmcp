---
phase: 13
plan: 03
subsystem: test-infrastructure
tags: [pytest, dialect, test-migration, parallel-add]
requirements: [TEST-02]
dependency_graph:
  requires:
    - tests.conftest.dialect (from 13-01)
    - tests.conftest.dialect_inspector (from 13-01)
    - tests.conftest.ALL_DIALECTS (from 13-01)
    - tests.fixtures.sqlite_schema.load_sqlite_schema (from 13-01)
  provides:
    - tests.unit.test_metadata.TestSharedMetadataBehavior
    - tests.unit.test_metadata._build_metadata_service (module-local helper)
    - tests.unit.test_metadata._configure_magicmock_engine_dialect (module-local helper)
  affects:
    - Closes parallel-add portion of TEST-02 for tests/unit/test_metadata.py
    - Plan 13-04 (coverage gate) still outstanding
tech_stack:
  added: []
  patterns:
    - Parallel-add migration (D-17): new TestSharedMetadataBehavior class; legacy test_engine/TestListSchemas tree untouched
    - Branch-in-test dispatch on dialect_inspector.name for paths where MagicMock vs real-engine setup differs
    - Index-section presence keyed off dialect.supports_indexes (D-13 / META-04)
key_files:
  created: []
  modified:
    - tests/unit/test_metadata.py
decisions:
  - Kept TestListSchemas, TestListTables, TestSorting, TestAccessDenied, TestPagination, TestObjectTypeFiltering, TestErrorPaths, TestLimitEnforcement, TestOutputMode — they use test_engine and cover parameter/filter/error behavior not in TestSharedMetadataBehavior.
  - Kept TestCatalog* classes — dialect-exclusive SHOW SCHEMAS IN / SHOW TABLES IN SQL-shape assertions.
  - Kept TestDescribeExtended and TestDatabricksTableProperties — Databricks DTE parsing is dialect-exclusive per plan guidance.
  - Kept TestIndexGating::test_indexes_present_when_dialect_is_none (dialect=None backward-compat) and test_indexes_omitted_when_include_indexes_false (parameter override) — distinct from supports_indexes gating covered by the shared test.
  - Retired only TestIndexGating::test_indexes_omitted_when_supports_indexes_false and test_indexes_present_when_supports_indexes_true — both are directly subsumed by the shared test's supports_indexes assertion under [databricks] and [generic] respectively.
  - Used inline branch-on-dialect dispatch rather than @pytest.mark.dialects for the three shared tests, because the production code routes list_schemas/list_tables differently per dialect (DMV SQL for mssql, SHOW ... IN for databricks w/ catalog, inspector path otherwise) — each branch needs distinct fixture setup. Keeping one parametrized test per method yields [mssql]/[databricks]/[generic] node IDs, satisfying the acceptance criteria.
metrics:
  duration: ~8 min
  completed: 2026-04-27
  tasks: 2
  files: 1
---

# Phase 13 Plan 03: test_metadata.py Parallel-Add Migration Summary

**One-liner:** Added `TestSharedMetadataBehavior` to tests/unit/test_metadata.py exercising `list_schemas` / `list_tables` / `get_table_schema` under [mssql], [databricks], [generic] via the shared `dialect_inspector` fixture, and retired the two now-duplicate index-gating tests.

## What Shipped

### tests/unit/test_metadata.py (modified)

- Added two module-local helpers (`_configure_magicmock_engine_dialect`, `_build_metadata_service`) to paper over the fact that `MagicMock(spec=Engine)` does not auto-expose `.dialect`, which `MetadataService.__init__` reads for `dialect_name`.
- Added `TestSharedMetadataBehavior` class with three dialect-parametrized tests:
  - `test_list_schemas_returns_schema_objects[{mssql,databricks,generic}]` — MSSQL stubs the DMV SQL rows on `connection.execute`; Databricks (no catalog) uses the inspector fall-through path; generic exercises real SQLite.
  - `test_list_tables_returns_table_objects[{mssql,databricks,generic}]` — MSSQL stubs count + data queries; Databricks uses inspector path + patched `_get_row_count_generic`; generic exercises real SQLite.
  - `test_get_table_schema_returns_table_schema_object[{mssql,databricks,generic}]` — generic runs against real SQLite; others configure the MagicMock inspector's `get_columns` / `get_pk_constraint` / `get_foreign_keys` / `get_indexes`; Databricks additionally patches `_parse_databricks_table_properties` so the DTE call is out-of-scope. Asserts index-section presence matches `dialect.supports_indexes` (D-13).
- Retired two duplicates from `TestIndexGating`: `test_indexes_omitted_when_supports_indexes_false` and `test_indexes_present_when_supports_indexes_true`. Left a docstring pointer to `TestSharedMetadataBehavior` in the class docstring.
- All 63 pre-plan tests still present except those two; net test count 63 → 70 (+9 parametrized - 2 retired = +7).

## Verification

- `uv run pytest tests/unit/test_metadata.py::TestSharedMetadataBehavior -v` → **9 passed** ([mssql]/[databricks]/[generic] for each of the three methods).
- `uv run pytest tests/unit/test_metadata.py -q` → **70 passed**.
- `uv run pytest tests/ -q` → **872 passed, 78 skipped** (was 874 before Task 2's 2 retirements — math checks out).
- `grep -c "class TestSharedMetadataBehavior" tests/unit/test_metadata.py` → **1**.
- `grep -c "def test_engine" tests/unit/test_metadata.py` → **1** (preserved).
- `grep -c "class TestListSchemas" tests/unit/test_metadata.py` → **1** (preserved).
- `grep -ciE "DESCRIBE EXTENDED|catalog|INFORMATION_SCHEMA" tests/unit/test_metadata.py` → **55** (dialect-exclusive surface preserved).
- Collected node IDs with `[mssql]` / `[databricks]` / `[generic]` present in TestSharedMetadataBehavior: 3 of each.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Missing infrastructure] `MagicMock(spec=Engine).dialect` raises AttributeError**

- **Found during:** Task 1, first test execution attempt (pre-commit).
- **Issue:** `MetadataService.__init__` reads `engine.dialect.name` for `self.dialect_name`. With `MagicMock(spec=Engine)` from the `dialect` fixture, `engine.dialect` raises `AttributeError('Mock object has no attribute dialect')` because `Engine.dialect` is a descriptor-style attribute not reflected in `spec`. The fixture therefore cannot be consumed directly by `MetadataService(dialect_ctx.engine, dialect=...)` without configuration.
- **Fix:** Added `_configure_magicmock_engine_dialect(dialect_ctx)` helper that sets `engine.dialect = MagicMock()` and `engine.dialect.name = dialect_ctx.name` before constructing the service. Real engines (generic via `dialect_inspector`) are detected by attribute-access success and skipped. Wrapped in `_build_metadata_service(dialect_ctx)` which also pre-populates `service._inspector = dialect_inspector.inspector` for the MagicMock path so the lazy `@property inspector` doesn't try to `inspect(engine)` on the mock.
- **Files modified:** `tests/unit/test_metadata.py` (helpers added inside the same commit as the TestSharedMetadataBehavior class).
- **Commit:** `bf81f2a` (Task 1).
- **Classification rationale:** Rule 3 (blocking) — fixture as-shipped from Plan 01 does not spec `.dialect`, which blocks Plan 03's stated goal of consuming it from `MetadataService`. The helpers are test-file-local (module-private with `_` prefix) so they do not widen Plan 01's fixture API and don't require a fixture change. An alternative was to extend the conftest `dialect` fixture to configure `.dialect.name` unconditionally, but per D-17's "parallel-add, isolate risk" principle I kept the workaround file-local rather than mutating shared fixtures mid-migration.

**2. [Rule 1 - Test design] Databricks shared list_schemas test exercises the inspector fallback, not SHOW SCHEMAS IN**

- **Found during:** Task 1, test-design stage.
- **Issue:** The Databricks-specific SHOW SCHEMAS IN path in `_list_schemas_databricks` requires a non-None `catalog` argument; calling `list_schemas()` with no catalog and a Databricks dialect routes through `_list_schemas_generic` (inspector path) because `has_fast_row_counts` is False for Databricks. Asserting SHOW SCHEMAS IN for the [databricks] shared test would cross into dialect-exclusive territory already covered by `TestCatalogListSchemas::test_list_schemas_with_catalog_executes_show_schemas`.
- **Fix:** Configured the [databricks] branch to stub the inspector (`get_schema_names` / `get_table_names` / `get_view_names`) and assert the generic inspector-path behavior. This is the correct shared semantic: "when no catalog is provided, list_schemas returns Schema objects regardless of dialect". The SHOW SCHEMAS IN shape remains exclusively tested by TestCatalogListSchemas.
- **Classification rationale:** Not strictly a bug — the plan's example used stubbed MSSQL responses and was permissive about the Databricks branch ("configure inspector responses per dialect, then call"). Documented here as a deviation because the plan sketch implied a single uniform assertion pattern, whereas the production routing requires two distinct setups (DMV SQL vs inspector) across the three dialects.
- **Files modified:** `tests/unit/test_metadata.py`.
- **Commit:** `bf81f2a` (Task 1, fix applied before commit).

No authentication gates. No architectural (Rule 4) questions. No threat-model flags — test infrastructure only.

## Commits

| Commit    | Scope   | Description                                                       |
| --------- | ------- | ----------------------------------------------------------------- |
| `bf81f2a` | Task 1  | Add TestSharedMetadataBehavior class (parallel-add, 9 node IDs)   |
| `dc12db0` | Task 2  | Retire duplicate index-gating tests (2 removed)                   |

## Known Stubs

None. All three shared tests exercise real code paths — either against real SQLAlchemy Inspector / in-memory SQLite (generic) or against real `DialectStrategy` instances with MagicMock execution surfaces (mssql/databricks). No tests were left as no-ops; no skipped-without-cause tests added.

## Self-Check: PASSED

- `tests/unit/test_metadata.py` — FOUND (TestSharedMetadataBehavior present; test_engine, TestListSchemas, TestCatalog*, TestDescribeExtended, TestDatabricksTableProperties all preserved)
- Commit `bf81f2a` — FOUND in `git log --oneline`
- Commit `dc12db0` — FOUND in `git log --oneline`
- Acceptance criteria:
  - `grep -c "class TestSharedMetadataBehavior" tests/unit/test_metadata.py` = 1 — PASS
  - `[mssql]` / `[databricks]` / `[generic]` node IDs collected in TestSharedMetadataBehavior — PASS (3 each)
  - `uv run pytest tests/unit/test_metadata.py::TestSharedMetadataBehavior -x -q` exits 0 — PASS
  - `grep -c "def test_engine"` = 1 — PASS
  - `grep -c "class TestListSchemas"` = 1 — PASS
  - Total test_metadata.py collected count 70 ≥ 80% of pre-plan 63 — PASS (70 > 50.4)
  - DESCRIBE EXTENDED / catalog / INFORMATION_SCHEMA greps still match (55 total) — PASS
  - `uv run pytest tests/ -q` exits 0 — PASS (872 passed, 78 skipped)
