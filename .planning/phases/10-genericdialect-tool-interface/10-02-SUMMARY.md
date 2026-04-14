---
phase: 10-genericdialect-tool-interface
plan: 02
subsystem: database
tags: [connect-database, multi-dialect, connection-manager, url-routing]

# Dependency graph
requires:
  - phase: 10-genericdialect-tool-interface
    plan: 01
    provides: GenericDialect, resolve_dialect_from_url, get_dialect registry
provides:
  - Two-param connect_database tool (connection_name | sqlalchemy_url)
  - ConnectionManager.connect_with_url for URL-based connections
  - ConnectionManager.connect_with_config for config-based routing
  - Generalized Connection model with optional MSSQL fields
  - Dialect-neutral _test_connection using SELECT 1
affects: [10-03, schema-tools-consumers, staleness-tests]

# Tech tracking
tech-stack:
  added: []
  patterns: [two-param-mutual-exclusive, url-credential-hiding, config-dialect-routing]

# Files
key-files:
  created:
    - tests/unit/test_connection_manager.py
    - tests/unit/test_connect_tool.py
  modified:
    - src/models/schema.py
    - src/db/connection.py
    - src/mcp_server/schema_tools.py
    - tests/unit/test_async_tools.py
    - tests/staleness/tool_invoker.py

# Decisions
decisions:
  - Connection model fields (server, database) default to empty string for generic connections
  - port defaults to 0 (not 1433) for dialect-agnostic connections
  - dialect_name field added to Connection for display/response purposes
  - _test_connection uses SELECT 1 instead of @@VERSION for dialect neutrality
  - ResolvedConnectionParams removed (no longer needed after simplification)
  - connect_with_config raises NotImplementedError for DatabricksConnectionConfig (Phase 11)

# Metrics
metrics:
  duration_seconds: 598
  completed: 2026-04-14T20:28:33Z
  tasks_completed: 2
  tasks_total: 2
  files_changed: 7
  tests_added: 18
  tests_total_after: 750
---

# Phase 10 Plan 02: Rewrite connect_database Tool Interface Summary

Two-param connect_database with generalized ConnectionManager and Connection model for multi-dialect support.

## What Was Done

### Task 1: Generalize Connection model and ConnectionManager

**Connection model** (`src/models/schema.py`):
- `server` and `database` now default to `""` (were required positional args)
- `port` defaults to `0` (was `1433`)
- Added `dialect_name: str = "mssql"` field
- Removed `ResolvedConnectionParams` dataclass (dead after schema_tools rewrite)
- Full backward compatibility: existing code passing keyword args still works

**ConnectionManager** (`src/db/connection.py`):
- `connect_with_url(sqlalchemy_url, dialect, query_timeout)`: Creates engine via dialect, extracts host/db/port from parsed URL, stores dialect, returns Connection
- `connect_with_config(config, dialect, query_timeout)`: Routes MssqlConnectionConfig to existing `connect()`, GenericConnectionConfig to `connect_with_url()`, DatabricksConnectionConfig raises NotImplementedError
- `_generate_url_connection_id(url)`: Credential-free deterministic hash from backend+host+port+database
- `_test_connection`: Now uses `SELECT 1` instead of `SELECT @@VERSION` (dialect-neutral)
- Error messages use `render_as_string(hide_password=True)` to prevent credential leakage (T-10-04)

### Task 2: Rewrite connect_database tool with two-param interface

**connect_database** (`src/mcp_server/schema_tools.py`):
- New signature: `connect_database(connection_name=None, sqlalchemy_url=None)`
- Mutual exclusivity: both params -> error, neither -> error
- `connection_name` path: looks up config, resolves dialect via `get_dialect(config.dialect)`, routes through `connect_with_config`
- `sqlalchemy_url` path: auto-detects dialect via `resolve_dialect_from_url`, routes through `connect_with_url`
- Response now includes `dialect` field
- No raw URLs in response (T-10-03)

**Removed MSSQL-specific helpers**: `_pick`, `_resolve_env_field`, `_merge_with_config`, `_defaults_only`, `_resolve_connection_params` -- all replaced by the cleaner connect_with_config/connect_with_url routing.

**Test updates**: staleness tool_invoker and async_tools tests updated for new signature.

## Commits

| # | Hash | Message |
|---|------|---------|
| 1 | 4ba6e12 | test(10-02): add failing tests for Connection model and ConnectionManager generalization |
| 2 | 0390e62 | feat(10-02): generalize Connection model and ConnectionManager for multi-dialect |
| 3 | 0fba3cd | test(10-02): add failing tests for two-param connect_database interface |
| 4 | db94e54 | feat(10-02): rewrite connect_database with two-param interface |

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added TYPE_CHECKING import for ConnectionConfig**
- **Found during:** Task 2 (ruff check)
- **Issue:** `connect_with_config` type annotation `"ConnectionConfig"` flagged as F821 undefined name
- **Fix:** Added `from __future__ import annotations` and `TYPE_CHECKING` import block
- **Files modified:** src/db/connection.py

No other deviations -- plan executed as written.

## Verification Results

- `uv run pytest tests/unit/test_connect_tool.py -v`: 6/6 passed
- `uv run pytest tests/unit/test_connection_manager.py -v`: 12/12 passed
- `uv run pytest tests/ -x -q`: 750 passed, 41 skipped, 0 failed
- `uv run ruff check src/`: All checks passed

## Known Stubs

None -- all code paths are fully wired.

## Self-Check: PASSED

All 5 key files exist. All 4 commit hashes verified in git log.
