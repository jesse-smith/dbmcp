---
created: 2026-03-06T18:56:27.892Z
title: Add type handler registry for query result JSON serialization
area: database
files:
  - src/db/query.py:600-750
  - src/mcp_server/query_tools.py:97-107
---

## Problem

Query result formatting in `src/db/query.py:600-750` assumes all column values are JSON-serializable. Custom Python types returned by SQL Server (Decimal, datetime, UUID, bytes) require explicit conversion. If a new or unexpected SQL column type appears (e.g., geography, geometry, hierarchyid, xml), JSON serialization fails silently or throws an error.

The MCP tool layer (`query_tools.py:97-107`) passes these results directly to JSON response without a safety net.

## Solution

1. **Add a type handler registry** — a dict mapping Python types to serialization functions:
   ```python
   TYPE_HANDLERS = {
       Decimal: str,
       datetime: lambda d: d.isoformat(),
       bytes: lambda b: b.hex(),
       UUID: str,
   }
   ```
2. **Apply handlers during result formatting** — iterate result values through the registry before building the response dict
3. **Add a fallback** for unknown types (`str(value)`) with a warning log so new types are visible rather than failing silently
4. **Test with real SQL Server types** — geography, geometry, hierarchyid, xml, datetimeoffset, sql_variant need integration test coverage
