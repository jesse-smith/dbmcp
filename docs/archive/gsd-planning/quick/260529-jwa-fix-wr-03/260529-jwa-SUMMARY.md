---
phase: quick-260529-jwa
plan: 01
subsystem: analysis
tags: [databricks, cross-catalog, nullability, pk-discovery, fk-candidates, WR-03]
requires:
  - CatalogAwareReflector (src/analysis/_sql.py)
  - cross-catalog info_schema reflection pattern (15.1)
provides:
  - CatalogAwareReflector.reflect_column_nullability (name->is_nullable map)
  - FK/PK reflection-layer nullability agreement on the cross-catalog branch
affects:
  - find_fk_candidates (all-columns target nullability)
  - find_pk_candidates (structural candidacy on all-nullable cross-catalog tables)
tech-stack:
  added: []
  patterns:
    - "reflect-and-report nullability, probe-only structural gate"
key-files:
  created: []
  modified:
    - src/analysis/_sql.py
    - src/analysis/fk_candidates.py
    - src/analysis/pk_discovery.py
    - tests/unit/test_analysis_sql.py
    - tests/unit/test_fk_candidates.py
    - tests/unit/test_pk_discovery.py
decisions:
  - "Source nullability from {catalog}.information_schema.columns (queryable cross-catalog), not DESCRIBE TABLE (which omits nullability)."
  - "Report declared nullability truthfully in BOTH tools; gate structural PK candidacy on the uniqueness probe ONLY on the cross-catalog branch (declared nullability does not exclude)."
  - "Default / MSSQL / Inspector paths keep the declared-nullable exclusion unchanged."
metrics:
  duration: "~12 min"
  completed: 2026-05-29
  tasks: 3
  files: 6
requirements: [WR-03]
---

# Quick Task 260529-jwa: Fix WR-03 (cross-catalog nullability contradiction) Summary

Eliminated the WR-03 contradiction where the Databricks cross-catalog branch fabricated opposite nullability defaults for the same column (FK hardcoded `is_nullable=True`, PK hardcoded `is_nullable=False`). Both tools now reflect real declared nullability from `{catalog}.information_schema.columns` and report it identically, while structural PK candidacy on all-nullable cross-catalog tables is preserved by gating on the uniqueness probe instead of declared nullability.

## What Was Built

- **`CatalogAwareReflector.reflect_column_nullability(catalog, schema, table) -> dict[str, bool]`** (`src/analysis/_sql.py`): queries `{qi(catalog)}.information_schema.columns` (catalog quoted via `dialect.quote_identifier`, which escapes backticks per CR-01; `schema`/`table` bound as `:params`), returns a `column_name -> is_nullable` map (`YES`/`NO` matched after `strip().upper()`). No `USE CATALOG` emitted — stateless over the pooled connection. `reflect_columns` is untouched.
- **FK `get_candidate_columns(pk_candidates_only=False)` cross-catalog branch** (`src/analysis/fk_candidates.py`): overlays `reflect_column_nullability` onto the reflected columns instead of hardcoding `is_nullable=True`. Columns absent from the map fall back to `True` (defensive, not the primary path).
- **PK `_list_all_columns` cross-catalog branch** (`src/analysis/pk_discovery.py`): reports the reflected `is_nullable` in the tuple's third slot instead of hardcoding `False`.
- **PK `get_structural_candidates` gate** (`src/analysis/pk_discovery.py`): the declared-nullable exclusion (`if ... or is_nullable: continue`) now only fires when `not self._cross_catalog`. On the cross-catalog branch the `_column_is_unique` probe is the sole structural gate (emitted candidates keep `is_non_null=True` because the probe proved non-null over the domain). Default / MSSQL / Inspector branches are byte-equivalent to before.

## Tasks Completed

| Task | Name | Commit | Files |
| ---- | ---- | ------ | ----- |
| 1 | Add `reflect_column_nullability` to `CatalogAwareReflector` (TDD RED→GREEN) | `67245ba` | `src/analysis/_sql.py`, `tests/unit/test_analysis_sql.py` |
| 2 | Report reflected nullability in both tools; preserve probe-only structural gate (TDD RED→GREEN) | `0bcb466` | `src/analysis/fk_candidates.py`, `src/analysis/pk_discovery.py`, `tests/unit/test_fk_candidates.py`, `tests/unit/test_pk_discovery.py` |
| 3 | Full unit suite + lint gate (verify-only) | (no code change) | — |

## TDD Evidence

- **Task 1 RED**: new `TestCatalogAwareReflectorColumnNullability` failed with `AttributeError: 'CatalogAwareReflector' object has no attribute 'reflect_column_nullability'`. **GREEN**: 17 passed after implementing the method.
- **Task 2 RED**: the reflection-layer agreement tests failed (PK `_list_all_columns` reported `patient_id=False`, FK reported `ssn=True` — the fabricated defaults). The regression-guard test passed pre-fix only because PK hardcoded `is_nullable=False`; making the reflected `YES` flow through is exactly what would have re-introduced the all-nullable-table regression, which the gate change prevents. **GREEN**: all FK+PK tests pass (89 passed, 52 skipped) after the source change.

## Verification

- AGREEMENT (`test_fk_and_pk_agree_on_reflected_nullability`): FK `get_candidate_columns(all)` and PK `_list_all_columns` report identical `is_nullable` (`patient_id=True`, `ssn=False`), both sourced from `information_schema.columns`.
- REGRESSION GUARD (`test_declared_nullable_probe_unique_still_structural_candidate`): a column declared `is_nullable=YES` whose uniqueness probe returns True still surfaces as a structural PK candidate with `is_non_null=True`, `is_constraint_backed=False`.
- PROBE-IS-SOLE-GATE (`test_declared_nullable_probe_nonunique_excluded`): a declared-nullable, non-unique column is excluded by the probe.
- DEFAULT-PATH UNCHANGED (`test_inspector_nullable_column_excluded`): on the `catalog=None` Inspector path a nullable column is still excluded from structural candidacy.
- Full unit suite: **1045 passed, 105 skipped** (`uv run pytest tests/unit/`).
- Coverage gate: **88.96% total**, ≥ 85% floor enforced (`--cov=src`). Per-file: `_sql.py` 94%, `fk_candidates.py` 90%, `pk_discovery.py` 94%.
- Lint: `uv run ruff check src/analysis/` — all checks passed (no new warnings).

## Threat Surface

No new threat surface beyond the plan's `<threat_model>`. The single new query (`reflect_column_nullability`) is covered by T-WR03-01 (catalog quoted via `dialect.quote_identifier`; `schema`/`table` bound as `:params` — never interpolated) and T-WR03-02 (no `USE CATALOG`; stateless over the pooled connection). Both mitigations are asserted by tests (`test_schema_and_table_bound_as_params_not_interpolated`, `test_never_emits_use_catalog`). No new dependencies (T-WR03-SC).

## Deviations from Plan

None — plan executed exactly as written. Rules 1-4 never triggered; no auto-fixes, no auth gates, no architectural decisions.

## Known Stubs

None.

## Out of Scope / Known-Environmental

- The 6 Azure AD integration tests in `tests/integration/test_azure_ad_auth.py` fail environmentally (live Azure SQL unreachable) — not run by the unit gate, not a regression, not in scope.
- Pre-existing ruff warning in `src/metrics.py` (`Generator` import from `typing`) — out of scope; `src/analysis/` lint is clean.

## Self-Check: PASSED

All 6 modified files present, SUMMARY present, both task commits (`67245ba`, `0bcb466`) found in git log, `reflect_column_nullability` present in `src/analysis/_sql.py`.
