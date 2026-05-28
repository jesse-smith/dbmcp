---
phase: 15-unified-identifier-resolver-cross-dialect
plan: 02
subsystem: db
tags: [identifier-resolution, schema-default, dialect, refactor]
requires:
  - "DialectStrategy protocol (v2.0)"
provides:
  - "MetadataService methods with schema_name: str | None = None (no dbo default)"
  - "QueryService.get_sample_data with schema_name: str | None = None (no dbo default)"
affects:
  - "MCP tools in Plans 04/05/06 (must pass resolved schema explicitly)"
tech-stack:
  added: []
  patterns:
    - "None schema_name flows to SQLAlchemy inspector default schema (D-10), no synthetic 'dbo' injection"
key-files:
  created: []
  modified:
    - src/db/metadata.py
    - src/db/query.py
    - tests/unit/test_query.py
decisions:
  - "table_id in get_sample_data guarded against None schema to avoid literal 'None.' prefix (Rule 1 bug fix)"
metrics:
  duration: "~6 min"
  completed: "2026-05-28"
  tasks: 2
  files_changed: 3
requirements: [IDENT-07]
---

# Phase 15 Plan 02: Sweep `dbo` Signature Defaults from Service Layer Summary

Removed every hardcoded `schema_name="dbo"` default from `MetadataService` and `QueryService` method signatures (D-11), making `None` the new default so the resolver/connection-default-schema becomes the single source of the schema default — SQLite/Databricks no longer silently inherit a SQL-Server schema name.

## What Was Done

### Task 1 — Remove `dbo` signature defaults (commit `7dc780b`)
Changed `schema_name: str = "dbo"` to `schema_name: str | None = None` at all seven sites:
- `src/db/metadata.py`: `get_columns`, `get_indexes`, `get_foreign_keys`, `get_primary_key`, `get_table_schema`, `table_exists`
- `src/db/query.py`: `get_sample_data`

Docstrings updated from `Schema name (default: 'dbo')` to `Schema name (None = connection default schema)`. Method body SQL logic left unchanged — `query.py` `quote_identifier(schema_name)` remains the SQL-safety boundary (resolver does NOT sanitize, per RESEARCH §Security).

### Task 2 — Tests for the None-default behavior (commit `690720c`)
Added `TestSampleDataSchemaDefault` to `tests/unit/test_query.py`:
- `test_get_sample_data_schema_name_default_is_none` — asserts `inspect.signature(QueryService.get_sample_data).parameters['schema_name'].default is None`.
- `test_get_sample_data_none_schema_builds_unqualified_reference` — with no dialect (`_dialect is None`) and `schema_name=None`, the built SQL contains the bare table name with no `dbo.`/schema prefix, and `table_id` equals the unqualified table name.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] `table_id` emitted literal `"None."` prefix under the new None default**
- **Found during:** Task 2 (writing the unqualified-reference assertion)
- **Issue:** `src/db/query.py` set `table_id = f"{schema_name}.{table_name}"` unconditionally. With the new `schema_name=None` default, this produced `"None.Customers"` — a latent bug exposed by the signature change. The SQL `full_table_name` path already handled `None` correctly (no-prefix branch), but `table_id` did not.
- **Fix:** `table_id = f"{schema_name}.{table_name}" if schema_name else table_name`.
- **Files modified:** `src/db/query.py`
- **Commit:** `690720c`
- **Verification:** Full suite (1015 passed, 78 skipped) confirms no consumer of `table_id` relied on the `"None."` form; new test asserts the unqualified `table_id`.

### Plan-vs-actual file scope

`tests/unit/test_metadata.py` was listed in the plan's `files_modified` but is **unchanged**. No existing metadata test relied on the implicit `dbo` default — every call already passed `schema_name` explicitly (positional `"dbo"` or keyword). After the signature change all 102 metadata tests still pass without edits, so no modification was required (plan Task 2 explicitly framed test updates as conditional: "Find any existing test ... that relies on the implicit default").

## Out-of-Scope Flag Recorded (per plan)

`src/db/metadata.py:919` `fk.get("referred_schema", "dbo")` is a **result-mapping default** (FK target-schema display), NOT a signature default. It was deliberately left untouched (RESEARCH.md Pitfall 4 / A2). Confirmed unchanged via `grep -n 'referred_schema'`. Flagged here for a future `dbo` audit.

## Verification

- `grep -nE 'schema_name: str = "dbo"' src/db/metadata.py src/db/query.py` → no matches (zero signature defaults remain).
- `grep -n 'referred_schema' src/db/metadata.py` → line 919 unchanged (out-of-scope confirmation).
- `uv run pytest tests/unit/test_metadata.py tests/unit/test_query.py` → 163 passed.
- `uv run pytest tests/` → 1015 passed, 78 skipped.
- `uv run ruff check src/db/ tests/unit/test_query.py tests/unit/test_metadata.py` → All checks passed.

## Success Criteria

- [x] No `schema_name: str = "dbo"` signature default remains in `src/db/metadata.py` or `src/db/query.py`.
- [x] `metadata.py:919` result-mapping default left intact and noted for future audit.
- [x] Service tests green; no new ruff warnings.

## Self-Check: PASSED

- FOUND: src/db/metadata.py
- FOUND: src/db/query.py
- FOUND: tests/unit/test_query.py
- FOUND: commit 7dc780b
- FOUND: commit 690720c
