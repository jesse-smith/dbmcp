---
phase: quick
plan: 1
subsystem: db-connection, mcp-tools
tags: [performance, async, timeout, pyodbc]
dependency_graph:
  requires: []
  provides: [query-timeout, async-db-execution]
  affects: [src/db/connection.py, src/mcp_server/schema_tools.py, src/mcp_server/query_tools.py, src/mcp_server/analysis_tools.py]
tech_stack:
  added: [asyncio.to_thread]
  patterns: [sync-to-async-wrapping, pyodbc-attrs-before]
key_files:
  created:
    - tests/unit/test_query_timeout.py
    - tests/unit/test_async_tools.py
  modified:
    - src/db/connection.py
    - src/mcp_server/schema_tools.py
    - src/mcp_server/query_tools.py
    - src/mcp_server/analysis_tools.py
decisions:
  - "SQL_ATTR_QUERY_TIMEOUT (1005) used as ODBC constant for per-statement timeout"
  - "query_timeout validation: 0 (disabled) or 5-300 range, matching connection_timeout pattern"
  - "Parameter validation stays outside asyncio.to_thread for fast-path error returns"
  - "Error responses from sync work returned as dicts, encoded after to_thread returns"
metrics:
  duration: 7min
  completed: "2026-03-05"
  tasks_completed: 2
  tasks_total: 2
  tests_added: 22
  tests_total: 463
---

# Quick Task 1: Add Query Timeouts and Async DB Execution Summary

pyodbc SQL_ATTR_QUERY_TIMEOUT (default 30s) on all connections + asyncio.to_thread wrapping on all 9 MCP tools to prevent event loop blocking.

## What Was Done

### Task 1: Query Timeout on Connection Engine Creation

Added `query_timeout` parameter throughout the connection stack:

- `PoolConfig.query_timeout` field with default 30 seconds
- `ConnectionManager.connect()` accepts `query_timeout` with validation (0 = disabled, 5-300 = active)
- Standard auth path: `SQL_ATTR_QUERY_TIMEOUT` passed via `connect_args={"attrs_before": {...}}`
- Azure AD Integrated path: `SQL_ATTR_QUERY_TIMEOUT` added to existing `attrs_before` dict alongside `SQL_COPT_SS_ACCESS_TOKEN`

**Commit:** `4d81986` feat(quick-1): add query timeout to connection engine creation

### Task 2: Async DB Execution via asyncio.to_thread

Wrapped all 9 MCP tool functions to execute sync DB work in `asyncio.to_thread()`:

- **schema_tools.py** (4 tools): connect_database, list_schemas, list_tables, get_table_schema
- **query_tools.py** (2 tools): get_sample_data, execute_query
- **analysis_tools.py** (3 tools): get_column_info, find_pk_candidates, find_fk_candidates

Pattern applied: Parameter validation stays outside `to_thread` (fast path, no I/O). Sync DB work extracted to `_sync_work()` inner function. Error handling wraps the `await asyncio.to_thread()` call.

**Commit:** `99e3ca5` feat(quick-1): wrap all 9 MCP tools with asyncio.to_thread

## Deviations from Plan

None -- plan executed exactly as written.

## Verification Results

- 463 tests pass, 0 regressions (41 integration tests skipped)
- `ruff check src/mcp_server/` -- all checks passed
- All 3 tool modules use `asyncio.to_thread` (9 call sites)
- `SQL_ATTR_QUERY_TIMEOUT` configured in `src/db/connection.py` for both auth paths

## Self-Check: PASSED

All 6 key files verified present. All 4 commits verified in git log.
