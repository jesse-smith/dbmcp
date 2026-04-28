---
status: complete
phase: 11-databricksdialect
source:
  - .planning/phases/11-databricksdialect/11-01-SUMMARY.md
  - .planning/phases/11-databricksdialect/11-02-SUMMARY.md
started: 2026-04-28T00:00:00Z
updated: 2026-04-28T17:00:00Z
---

## Current Test

none — UAT complete

## Tests

### 1. MSSQL regression — list_schemas with no catalog
expected: Connect to StemSoftClinic via connect_database. Call list_schemas — returns schemas list with table_count and view_count. Identical behavior to pre-phase-11.
result: pass
notes: Tested against SVWTSTEM04/StemSoftClinicTest (substituted for StemSoftClinic). Returned 2 schemas (dbo: 246 tables / 92 views; reporting: 1 table). No errors, no Databricks-specific keys.

### 2. MSSQL regression — list_tables with no catalog
expected: On same MSSQL connection, call list_tables (or with schema_filter=['dbo']) — returns tables with row counts. No regression from prior behavior.
result: pass
notes: list_tables(schema_filter=['dbo'], limit=5) returned 5 of 338 tables with correct row counts, primary-key flags, timestamps, pagination metadata (has_more=true).

### 3. MSSQL regression — get_table_schema includes indexes
expected: Call get_table_schema on a real MSSQL table with include_indexes=true. Response includes `indexes` key (populated or empty list) because MSSQL supports indexes. Index gating logic does NOT strip the key for MSSQL.
result: pass
notes: get_table_schema(PerformedActs, include_indexes=true) returned 21 columns, 8 indexes, 3 foreign keys. `indexes` key present and populated.

### 4. MSSQL ignores catalog parameter (backward compat)
expected: Call list_schemas on the MSSQL connection with catalog="ignored_value". Behaves identically to calling without catalog — MSSQL dialect ignores the parameter. No error, no behavior change.
result: pass
notes: list_schemas(catalog="ignored_value") returned byte-identical result to no-catalog call. Parameter silently ignored for MSSQL.

### 5. Databricks dialect registered
expected: Inspect the dialect registry (e.g., via src/db/dialects/__init__.py imports or a direct DIALECT_REGISTRY lookup). 'databricks' key resolves to DatabricksDialect class. Also reachable via resolve_dialect_from_url("databricks://...").
result: pass
notes: Registry at src/db/dialects/registry.py::_REGISTRY contains keys ['databricks', 'generic', 'mssql']. resolve_dialect_from_url("databricks://...") returns a DatabricksDialect instance.

### 6. Missing databricks packages → helpful error
expected: With databricks-sqlalchemy NOT installed, attempting to connect using a DatabricksConnectionConfig (or databricks:// URL) raises an ImportError (or similar) with a clear install hint pointing to the `databricks` extras (e.g., `pip install 'dbmcp[databricks]'` or equivalent). Not a generic ModuleNotFoundError buried in a stack trace.
result: pass
notes: |
  databricks-sqlalchemy not installed in .venv. connect_database(sqlalchemy_url="databricks://...") returned:
    "Unexpected error: ImportError: Databricks support requires databricks-sqlalchemy. Install with: pip install dbmcp[databricks]"
  Message is clear and actionable. Minor nit: the "Unexpected error:" prefix makes it read like an internal bug rather than a user-actionable missing-dependency message. Worth a follow-up polish but not a blocker.

### 7. Live Databricks connection (if available)
expected: If a Databricks workspace is configured (host + http_path + token), connect_database with a Databricks URL or config succeeds, then list_schemas with a catalog param returns schemas via SHOW SCHEMAS IN, and get_table_schema on a Databricks table omits the `indexes` key (absent, not empty list) and includes DESCRIBE EXTENDED properties (owner, storage_format, location, etc.) in a `properties` or similar field.
result: skipped
notes: No Databricks workspace configured; databricks-sqlalchemy not installed. Skipped per the expected-value gating clause ("if available").

## Summary

total: 7
passed: 6
issues: 0
pending: 0
skipped: 1

## Gaps

1. Minor wording polish on the missing-databricks-package error — strip the "Unexpected error:" prefix so it reads as a user-actionable install hint rather than an internal bug. Non-blocking; capture as a todo.
2. Test 7 (live Databricks) remains uncovered — requires either a Databricks workspace for manual verification or an end-to-end integration test suite gated behind a `--databricks` flag. Recommend deferring to a separate phase unless a workspace becomes available.
