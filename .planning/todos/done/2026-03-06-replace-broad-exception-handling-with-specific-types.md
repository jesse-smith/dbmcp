---
created: 2026-03-06T18:27:58.485Z
title: Replace broad exception handling with specific types
area: general
files:
  - src/db/metadata.py
  - src/metrics.py
  - src/mcp_server/schema_tools.py
  - src/mcp_server/query_tools.py
  - src/mcp_server/analysis_tools.py
---

## Problem

25 instances of `except Exception:` across the codebase mask specific failures. Breakdown:
- `src/db/metadata.py` — 10 instances (most concentrated)
- `src/metrics.py` — 1 instance (may be removed if metrics module is deleted)
- `src/mcp_server/*.py` — multiple instances across tool modules

Generic catches like "Table not found" or "Access denied" may hide actual database errors, permission issues, or connection problems. This makes debugging difficult and can silently swallow important failure information.

## Solution

Replace broad `except Exception:` with specific exception types:
- **Database operations**: `except (sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError)`
- **Lookup failures**: `except (KeyError, AttributeError)`
- **Connection issues**: `except (sqlalchemy.exc.DisconnectionError, pyodbc.OperationalError)`
- **Validation**: `except (ValueError, TypeError)`

Approach: audit each catch site individually — some may legitimately need broad catches (e.g., top-level MCP tool handlers that must return error messages). For those, log the specific exception type/message before returning the generic error.
