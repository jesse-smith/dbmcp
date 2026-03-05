---
created: 2026-03-04T21:12:06.381Z
title: Add query timeouts and investigate hanging MCP tool calls
area: database
files:
  - src/mcp_server/analysis_tools.py
  - src/mcp_server/schema_tools.py
  - src/mcp_server/query_tools.py
---

## Problem

During Phase 1 UAT, `get_column_info` on table `A_ACUTEGVHD` with datetime columns (`Date of Assessment`, `SignatureDate`, `DOT`) hung for 2+ minutes without returning. The same call on `A_Transplant_Info_Rpt` returned quickly.

The critical issue: sync SQLAlchemy DB calls block the async MCP event loop. One hung query blocks ALL subsequent tool calls (confirmed: `list_tables`, `execute_query SELECT 1` all queued behind the stuck call). Interrupting the MCP tool call from the client does NOT cancel the server-side query.

Two sub-issues:
1. **No query timeout** — sync DB calls can block indefinitely with no safety net
2. **A_ACUTEGVHD specifically** — unclear if it's a view, has missing indexes, or the stats queries (DISTINCT, MIN/MAX on datetime) are expensive on that table

User confirmed `get_column_info` worked on this table prior to the TOON migration, but the serialization code itself is not the cause (confirmed: `A_Transplant_Info_Rpt` with datetime columns returns fine via TOON). May be coincidental timing or a transient DB issue.

## Solution

1. Add `connect_args` timeout to SQLAlchemy engine creation (pyodbc supports `timeout` and `attrs_before` for `SQL_ATTR_QUERY_TIMEOUT`)
2. Consider wrapping sync DB calls in `asyncio.to_thread()` so they don't block the event loop
3. Investigate `A_ACUTEGVHD` — check if it's a view, check row count, check indexes on datetime columns
4. Ensure MCP tool call interruption propagates cancellation to the DB connection
