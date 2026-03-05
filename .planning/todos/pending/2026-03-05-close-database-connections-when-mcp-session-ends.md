---
created: 2026-03-05T18:48:39.347Z
title: Close database connections when MCP session ends
area: database
files:
  - src/db/connection.py
  - src/mcp_server/server.py
---

## Problem

Database connections persist in the ConnectionManager singleton but are never explicitly closed when the MCP session ends (e.g., when the client disconnects or the server shuts down). This means pooled pyodbc connections may linger, holding server-side resources unnecessarily.

Currently `ConnectionManager` has `_engines` and `_connections` dicts but no `close()` or `dispose()` method. SQLAlchemy engines should be disposed on shutdown to release all pooled connections.

## Solution

- Add a `close_all()` or `dispose()` method to `ConnectionManager` that calls `engine.dispose()` on all cached engines and clears the dicts
- Hook into MCP server lifecycle — FastMCP may support shutdown hooks, or use Python `atexit` module as fallback
- Consider whether individual `disconnect(connection_id)` tool should also be exposed to clients
