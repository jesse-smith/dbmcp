---
phase: quick-260428-mwr
plan: "01"
subsystem: db/query + db/metadata
tags: [databricks, bugfix, tdd]
dependency_graph:
  requires: []
  provides: [DATABRICKS-SHOW-QUERY, DATABRICKS-CROSS-CATALOG-COLUMNS]
  affects: [src/db/query.py, src/db/metadata.py]
tech_stack:
  added: []
  patterns: [safe_operational_commands result materialization, DESCRIBE TABLE cross-catalog column fetch]
key_files:
  created: []
  modified:
    - src/db/query.py
    - src/db/metadata.py
    - tests/unit/test_query.py
    - tests/unit/test_metadata.py
decisions:
  - "SHOW/DESCRIBE routed through _process_select_results without conn.commit() — pure reads need no transaction"
  - "_get_databricks_columns issues DESCRIBE TABLE (not EXTENDED) for simpler column-only output"
  - "Stop parsing at blank row or '#' section marker — matches DESCRIBE TABLE output format"
  - "get_table_schema cross-catalog branch guarded by catalog AND dialect.name == databricks — zero impact on MSSQL/generic"
metrics:
  duration: ~10min
  completed: "2026-04-28T21:38:41Z"
  tasks_completed: 2
  files_modified: 4
---

# Quick Task 260428-mwr: Fix Databricks SHOW/DESCRIBE Result Materialization and Cross-Catalog Column Fetch

**One-liner:** Two targeted Databricks fixes — SHOW/DESCRIBE rows materialized via safe_operational_commands check in `_run_query`, cross-catalog columns fetched via DESCRIBE TABLE in new `_get_databricks_columns`.

## Tasks Completed

| Task | Name | Commit | Files |
|------|------|--------|-------|
| 1 | Fix execute_query to materialize rows for safe operational commands | 6d37227 | src/db/query.py, tests/unit/test_query.py |
| 2 | Fix get_table_schema cross-catalog column fetch for Databricks | 3abcbc1 | src/db/metadata.py, tests/unit/test_metadata.py |

## What Was Fixed

### Task 1: SHOW/DESCRIBE Result Materialization

**Root cause:** `_run_query` had two branches — `QueryType.SELECT` went through `_process_select_results`, everything else went straight to `rowcount + commit()`, discarding result sets. Databricks SHOW/DESCRIBE/EXPLAIN are result-producing reads that aren't typed as SELECT.

**Fix:** After the SELECT branch, extract the query verb and check membership in `self._dialect.safe_operational_commands`. When the verb matches (SHOW, DESCRIBE, etc.), call `_process_select_results` and return — no commit. The write/DDL path is unchanged.

**Key invariants preserved:**
- Queries only reach this path if they passed `validate_query` (which gates on `safe_operational_commands`)
- No row limit injection for operational commands (already guarded by `query_type == QueryType.SELECT`)
- Non-Databricks dialects have empty `safe_operational_commands`, so SHOW remains blocked

### Task 2: Cross-Catalog Column Fetch

**Root cause:** `get_table_schema` called `get_columns` → `inspector.get_columns()`. The SQLAlchemy Inspector is created from the engine's connection which is bound to the default catalog. For tables in other catalogs (e.g., `bmtct` when connected to `main`), `inspector.get_columns` silently returns [].

**Fix:** New private method `_get_databricks_columns(table_name, schema_name, catalog)` issues `DESCRIBE TABLE \`catalog\`.\`schema\`.\`table\`` using the engine's `connect()` directly. Parses column rows (row[0]=col_name, row[1]=data_type) and stops at the first blank row or "#" section marker. All identifiers backtick-quoted via `dialect.quote_identifier()` (T-mwr-02).

`get_table_schema` branches: when `catalog` is provided and dialect is Databricks, use `_get_databricks_columns`; otherwise use the existing `get_columns` path. Zero impact on MSSQL/generic/no-dialect paths.

## Deviations from Plan

None — plan executed exactly as written. The stale `mock_insp` line in the test (auto-fixed: [Rule 1 - Bug]) was a copy/paste artifact from writing the initial RED tests; removed in the same task before commit.

## Known Stubs

None.

## Threat Flags

None — both fixes are read-only paths with no new network endpoints or trust boundary crossings. Injection mitigations for T-mwr-02 (backtick-quoting in `_get_databricks_columns`) are implemented as specified.

## Self-Check: PASSED

- `src/db/query.py` — modified, committed in 6d37227
- `src/db/metadata.py` — modified, committed in 3abcbc1
- `tests/unit/test_query.py` — modified, committed in 6d37227
- `tests/unit/test_metadata.py` — modified, committed in 3abcbc1
- `git log --oneline` confirms both commits exist
- Full test suite: 903 passed, 78 skipped, 0 failures
- ruff: all checks passed on both source files
