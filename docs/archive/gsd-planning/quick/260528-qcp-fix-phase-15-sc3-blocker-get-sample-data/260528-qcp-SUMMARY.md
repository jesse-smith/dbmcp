---
phase: quick-260528-qcp
plan: 01
subsystem: db/query
tags: [bugfix, identifier-resolution, sc3, dialect, security]
requires:
  - "src/db/query.py get_sample_data full_table_name construction"
  - "src/db/dialects (Generic/Mssql/Databricks quote_identifier)"
provides:
  - "Schema-guarded full_table_name construction in get_sample_data (no synthetic 'None' namespace)"
  - "Real-dialect regression coverage for None schema_name in get_sample_data"
affects:
  - "Phase 15 SC3 verification (unblocked)"
tech-stack:
  added: []
  patterns:
    - "Guard identifier-segment emission on presence; never quote_identifier(None)"
key-files:
  created: []
  modified:
    - "src/db/query.py"
    - "tests/unit/test_query.py"
decisions:
  - "Omit the schema segment (rather than emit quote_identifier(None)) for both the 2-part else branch and the Databricks 3-part branch when schema_name is falsy."
metrics:
  duration: "~6 min"
  completed: "2026-05-28"
  tasks: 3
  files: 2
---

# Phase quick-260528-qcp Plan 01: Fix Phase 15 SC3 Blocker (get_sample_data None schema) Summary

Guarded `get_sample_data`'s `full_table_name` construction so a falsy `schema_name` yields an unqualified quoted table reference instead of a synthetic `"None"` schema segment, closing the Phase 15 SC3 verification blocker exposed when the hardcoded `dbo` default was removed (SC4).

## What Was Done

- **Task 1 (RED, commit `8263dc0`):** Added two tests to `TestSampleDataSchemaDefault`:
  - `test_get_sample_data_none_schema_real_generic_dialect_unqualified` — real `GenericDialect` + `schema_name=None`, asserts the built SQL contains the bare quoted table (`"Customers"`) and **no** `None.` / `"None"` segment, and `table_id == "Customers"`. This failed RED on `"None"."Customers"`.
  - `test_get_sample_data_mssql_two_part_reference_preserved` — no-regression guard; `MssqlDialect` + `schema_name="sales"` must still emit `[sales].[Customers]`. Passed from the start (exercises the unchanged correct path).
- **Task 2 (GREEN, commit `b303326`):** In `src/db/query.py get_sample_data`, split the trailing branch into a `schema_name`-guarded 2-part path and an unqualified else path, and hardened the Databricks 3-part `elif` branch to omit the schema segment (`catalog.table`) when `schema_name` is None. Every emitted segment is still quoted via `quote_identifier` — the injection defense is preserved (T-qcp-01).
- **Task 3 (gate):** Full `tests/unit/test_query.py` (85 tests) passes; `ruff check` clean on both touched files. No behavior change in this task.

## Verification

- RED → GREEN confirmed: the generic-dialect test went from FAILED (`"None"."Customers"`) to PASSED (`"Customers"`).
- Cross-dialect manual cross-check (via `uv run python`):
  - Databricks, schema present: `` `c`.`s`.`t` `` (unchanged 3-part).
  - Databricks, schema None: `` `c`.`t` `` (no synthetic `` `None` `` segment).
  - MSSQL, schema present: `[sales].[Customers]` (unchanged 2-part).
  - SQLite/no-dialect path: unchanged (`self._dialect is None` branch untouched).
- `uv run pytest tests/unit/test_query.py` → 85 passed.
- `uv run ruff check src/db/query.py tests/unit/test_query.py` → All checks passed.

## Deviations from Plan

The plan's `<interfaces>` note stated that `GenericDialect.quote_identifier` escapes via `str.replace`, so `quote_identifier(None)` would raise `AttributeError`. In the actual code, only `MssqlDialect.quote_identifier` uses `.replace()`; `GenericDialect` and `DatabricksDialect` use plain f-strings. Therefore the chosen RED test (GenericDialect) does **not** raise `AttributeError` — it produces a synthetic `"None"."Customers"` reference, which the test's `None.` / `"None"` assertions catch (FAILED). The Task 1 verify grep accepts `FAILED`, so the RED gate behaved as specified. No code or test design change was needed; the underlying bug (T-qcp-02 wrong-namespace) and the guard fix are exactly as the plan intended. Documented here for accuracy rather than treated as a defect.

No Rule 1–4 deviations. No auth gates. No architectural changes.

## TDD Gate Compliance

- RED commit present: `8263dc0` (`test(...)`).
- GREEN commit present: `b303326` (`fix(...)`).
- No REFACTOR commit — the GREEN implementation was already clean (ruff passed, no duplication introduced).

## Known Stubs

None.

## Threat Flags

None. The change only alters whether the schema identifier segment is emitted; all emitted segments remain quoted via `dialect.quote_identifier`. No new network endpoints, auth paths, file access, or schema changes introduced. T-qcp-01 (tampering) and T-qcp-02 (info disclosure / wrong namespace) are both mitigated as planned.

## Self-Check: PASSED

- `src/db/query.py` — FOUND
- `tests/unit/test_query.py` — FOUND
- `260528-qcp-SUMMARY.md` — FOUND
- Commit `8263dc0` (RED) — FOUND
- Commit `b303326` (GREEN) — FOUND
