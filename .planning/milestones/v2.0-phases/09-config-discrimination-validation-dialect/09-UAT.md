---
status: complete
phase: 09-config-discrimination-validation-dialect
source:
  - 09-01-SUMMARY.md
  - 09-02-SUMMARY.md
started: 2026-04-30T16:12:20Z
updated: 2026-04-30T16:30:00Z
---

## Current Test

[testing complete]

## Tests

### 1. TOML config requires dialect field
expected: Loading a connection from dbmcp.toml that omits `dialect` fails with a clear error naming the missing field. Valid TOML with `dialect = "mssql"` parses into MssqlConnectionConfig.
result: pass

### 2. Unknown TOML fields produce warning (not silent ignore)
expected: A TOML connection entry containing an unrecognized field (e.g. `dialectt = "mssql"` typo or `foo = "bar"`) still parses successfully but emits a WARNING log identifying the unknown field name. No silent drop.
result: pass

### 3. Backward-compatible T-SQL validation still works
expected: An existing MSSQL connection (`stemsoftclinictest`) still validates and executes SELECT queries end-to-end via `execute_query`. Safe system procedures (sp_help, sp_helptext, etc.) still pass validation when invoked via EXEC.
result: pass

### 4. Dialect-aware validation rejects EXEC outside T-SQL
expected: Running a query containing `EXEC ...` against a Databricks-dialect connection fails validation with a parse/validation error (EXEC is T-SQL-only). The same EXEC against an MSSQL connection still validates normally.
result: pass

### 5. validate_query requires explicit dialect argument
expected: Internal callers must pass `dialect=` as a keyword argument; there is no hardcoded default. Safe procedures are composed at the QueryService level from `dialect.safe_procedures | config.allowed_stored_procedures`, not from a module-level constant.
result: pass
verified_by: code inspection (src/db/validation.py:45, src/db/query.py:540-549)

## Summary

total: 5
passed: 5
issues: 0
pending: 0
skipped: 0

## Gaps

[none yet]
