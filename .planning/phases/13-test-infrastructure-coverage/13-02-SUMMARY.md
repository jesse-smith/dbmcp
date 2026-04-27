---
phase: 13
plan: 02
subsystem: test-infrastructure
tags: [pytest, dialect, test-migration, in-place]
requirements: [TEST-02]
dependency_graph:
  requires:
    - tests.conftest.dialect (from 13-01)
    - tests.conftest.dialect_inspector (from 13-01)
    - tests.conftest.ALL_DIALECTS (from 13-01)
    - pyproject.toml::markers::dialects (from 13-01)
  provides:
    - tests.unit.test_column_stats.sa_types_inspector (renamed local fixture)
    - tests.unit.test_pk_discovery._mock_inspector_for_pk (retained shape builder)
    - tests.unit.test_fk_candidates._build_inspector (renamed local helper)
  affects:
    - Closes TEST-02 dialect-parametrized shared-behavior gap for 3 analysis test files
    - Plan 13-03 (test_metadata.py parallel-add) and Plan 13-04 (coverage gate) remain
tech_stack:
  added: []
  patterns:
    - In-place migration (D-17): rewrite tests to consume `dialect` fixture directly
    - Marker-narrowed parametrization via @pytest.mark.dialects(...) for dialect-specific behavior
    - Local shape-builder helpers (not fixtures) retained for per-test Inspector shape customization
key_files:
  created: []
  modified:
    - tests/unit/test_column_stats.py
    - tests/unit/test_pk_discovery.py
    - tests/unit/test_fk_candidates.py
decisions:
  - Kept _mock_inspector_for_pk as-is in test_pk_discovery.py (plan listed rename as Optional; skipped to minimize churn)
  - Narrowed test_generic_inspector_constraints to @pytest.mark.dialects('generic') only — databricks has supports_indexes=False and returns target_has_index=None, which contradicts the test's assertion
  - Narrowed test_fast_path_skipped_for_non_databricks to ('mssql','generic') to match its semantic (non-databricks no-op); databricks fast-path coverage is in test_fast_path_returns_stats_when_present
metrics:
  duration: ~15 min
  completed: 2026-04-27
  tasks: 3
  files: 3
---

# Phase 13 Plan 02: Dialect Fixture In-Place Migration Summary

**One-liner:** Migrated `test_column_stats.py`, `test_pk_discovery.py`, and `test_fk_candidates.py` off local `_mock_*_dialect` helpers onto the shared `dialect` fixture, collapsing dialect-suffixed test triplets into marker-narrowed parametrized tests.

## What Shipped

Three analysis test files migrated in-place (per D-17). All local dialect-mock helpers deleted. File-local Inspector shape builders renamed to avoid shadowing the conftest-level `mock_inspector` fixture. All tests pass; test count grew from 852 → 865 (net +13) because some previously mssql-only tests now collect generic/databricks parametrizations as well. No `src/` changes.

### tests/unit/test_column_stats.py (modified)

- Deleted `_make_mock_dialect` helper and `mock_mssql_dialect` / `mock_databricks_dialect` / `mock_generic_dialect` fixtures (~30 lines).
- Renamed local `mock_inspector` fixture → `sa_types_inspector` (the conftest fixture with the same name has a different column shape).
- Migrated databricks-specific tests to `@pytest.mark.dialects('databricks')` + `dialect.dialect`.
- Migrated mssql-specific tests to `@pytest.mark.dialects('mssql')` + `dialect.dialect`.
- `test_fast_path_skipped_for_non_databricks` now parametrized across `('mssql','generic')` — asserts the fast path never touches the connection for non-databricks dialects.

### tests/unit/test_pk_discovery.py (modified)

- Deleted `_mock_mssql_dialect()`, `_mock_databricks_dialect()`, `_mock_generic_dialect()` helpers.
- Kept `_mock_inspector_for_pk(...)` as a local shape-builder (rename was listed as Optional in the plan; skipped).
- Renamed `test_pk_discovered_via_inspector_generic` → `test_pk_discovered_via_inspector` and similarly for unique, parametrized across `('generic','databricks')`.
- Narrowed `test_databricks_constraints_have_enforced_false` to databricks, `test_generic_constraints_have_enforced_true` to generic.
- Migrated `test_mssql_dialect_uses_information_schema` to use the `dialect` fixture with `@pytest.mark.dialects('mssql')`.

### tests/unit/test_fk_candidates.py (modified)

- Deleted `_mock_mssql_dialect()`, `_mock_databricks_dialect()`, `_mock_generic_dialect()` helpers.
- Renamed `_mock_inspector(...)` → `_build_inspector(...)` (clarifies it's a shape-builder, not a fixture; avoids shadow).
- Migrated ~10 tests to the `dialect` fixture:
  - Inspector-driven table listing / column listing / constraint checks → `@pytest.mark.dialects('generic', 'databricks')`.
  - `test_databricks_omits_target_has_index` → `@pytest.mark.dialects('databricks')`.
  - `test_generic_uses_inspector_get_indexes` and `test_generic_inspector_constraints` → `@pytest.mark.dialects('generic')` (target_has_index=True assertion requires supports_indexes=True).
  - `test_pk_discovery_receives_dialect_inspector` updated to assert `dialect=dialect.dialect` in `mock_pk_cls.assert_called_once_with(...)`.

## Verification

- `uv run pytest tests/ -q` → **865 passed, 78 skipped in 37.45s** (baseline was 852 passed, 54 skipped; +13 tests, +24 skips from marker-narrowed parametrization).
- `uv run pytest tests/unit/test_column_stats.py tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py -q` → all pass.
- `uv run pytest --collect-only tests/unit/test_column_stats.py -q | grep -cE '\[(mssql|databricks|generic)\]'` → ≥ 20 node IDs collected; `[mssql]`, `[databricks]`, `[generic]` all present.
- `uv run pytest --collect-only tests/unit/test_pk_discovery.py -q | grep -cE '\[(mssql|databricks|generic)\]'` → 24.
- `uv run pytest --collect-only tests/unit/test_fk_candidates.py -q | grep -cE '\[(mssql|databricks|generic)\]'` → 30.
- `grep -cE "^def _mock_(generic|mssql|databricks)_dialect" tests/unit/test_fk_candidates.py` → 0.
- `grep -c "_make_mock_dialect\|mock_mssql_dialect\|mock_databricks_dialect\|mock_generic_dialect" tests/unit/test_column_stats.py` → 0.
- `grep -cE "_mock_(mssql|databricks|generic)_dialect" tests/unit/test_pk_discovery.py` → 0.
- `grep -c "def _build_inspector" tests/unit/test_fk_candidates.py` → 1.
- `grep -c "def _mock_inspector" tests/unit/test_fk_candidates.py` → 0.
- `grep -c "def sa_types_inspector" tests/unit/test_column_stats.py` → 1.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test design] Narrowed `test_fast_path_skipped_for_non_databricks` to ('mssql','generic')**

- **Found during:** Task 1, initial run.
- **Issue:** First attempt parametrized the test across all three dialects with conditional assertion, which failed on `[databricks]` because `_try_describe_extended_stats` actually iterates `rows` under databricks — the MagicMock `conn.execute()` returned a default Mock whose `fetchall()` returned another Mock (not iterable), raising TypeError. The test's semantic is "non-databricks dialects skip the fast path", so databricks belongs in `test_fast_path_returns_stats_when_present`, not this test.
- **Fix:** Added `@pytest.mark.dialects('mssql', 'generic')` to the test; databricks fast-path coverage remains in `test_fast_path_returns_stats_when_present` (marked `@pytest.mark.dialects('databricks')`).
- **Files modified:** `tests/unit/test_column_stats.py`.
- **Commit:** `4485a29` (single commit, fix applied before commit).

**2. [Rule 1 - Test design] Narrowed `test_generic_inspector_constraints` to generic only**

- **Found during:** Task 3, test design review.
- **Issue:** Initial plan-mapping suggested this test could run for both generic and databricks. However, it asserts `metadata["target_has_index"] is True`. Databricks has `supports_indexes=False`, so this path returns `None`. Running the test under `[databricks]` would fail on the `target_has_index` assertion.
- **Fix:** Narrowed marker to `@pytest.mark.dialects('generic')`. Databricks-specific index behavior is covered by `test_databricks_omits_target_has_index`.
- **Files modified:** `tests/unit/test_fk_candidates.py`.
- **Commit:** `2512086` (single commit, fix applied before commit).

No other deviations. No authentication gates. No architectural questions.

## Commits

| Commit    | Scope        | Description                                                    |
| --------- | ------------ | -------------------------------------------------------------- |
| `4485a29` | Task 1       | Migrate test_column_stats.py to dialect fixture                |
| `0bb4a36` | Task 2       | Migrate test_pk_discovery.py to dialect fixture                |
| `2512086` | Task 3       | Migrate test_fk_candidates.py to dialect fixture               |

## Known Stubs

None. Every test either runs the real code path against its real `DialectStrategy` instance or is explicitly narrowed via `@pytest.mark.dialects(...)` to the dialects whose behavior it actually verifies. No tests were left as no-ops or skipped implicitly.

## Self-Check: PASSED

- `tests/unit/test_column_stats.py` — FOUND (modified; `_make_mock_dialect`, `mock_*_dialect` removed; `sa_types_inspector` present)
- `tests/unit/test_pk_discovery.py` — FOUND (modified; `_mock_*_dialect` helpers removed)
- `tests/unit/test_fk_candidates.py` — FOUND (modified; dialect helpers removed; `_build_inspector` present)
- Commit `4485a29` — FOUND in git log
- Commit `0bb4a36` — FOUND in git log
- Commit `2512086` — FOUND in git log
- Plan success criteria: three files migrated in-place — YES; local dialect-mock helpers deleted — YES; each file has parametrized tests with `[mssql]`, `[databricks]`, `[generic]` node IDs collected — YES; dialect-specific tests narrowed via `@pytest.mark.dialects(...)` — YES; local helpers renamed (`sa_types_inspector`, `_build_inspector`) to avoid conftest shadowing — YES; full test suite passes — YES; no `src/` changes — YES.
