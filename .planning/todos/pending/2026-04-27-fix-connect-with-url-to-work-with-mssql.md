---
created: 2026-04-27T20:38:36.837Z
title: Fix connect_with_url to work with MSSQL
area: database
files:
  - src/db/connection.py:321-374
  - src/db/dialects/mssql.py:129-203
  - src/mcp_server/schema_tools.py:81-194
---

## Problem

`connect_database` with the `sqlalchemy_url` path fails for MSSQL with `KeyError: 'server'`. `ConnectionManager.connect_with_url` (src/db/connection.py:321) calls `dialect.create_engine(sqlalchemy_url=..., query_timeout=...)`, but `MSSQLDialect.create_engine` (src/db/dialects/mssql.py:129) requires separate `server`, `database`, `authentication_method`, `trust_server_cert`, etc. kwargs — it never parses the URL. Result: the URL path is silently broken for MSSQL; only the named-connection path (`connect_with_config`) works. Generic dialects (SQLite/Postgres) are unaffected because they accept `sqlalchemy_url` directly.

Surfaced during Phase 12 UAT: attempted `mcp__dbmcp__connect_database(sqlalchemy_url="mssql+pyodbc://...")` against the SVWTSTEM04/StemSoftClinic test DB, got `Unexpected error: KeyError: 'server'` from the MSSQL create_engine call.

## Solution

TBD. Options:

1. Have `MSSQLDialect.create_engine` parse `sqlalchemy_url` via `make_url()` when present and derive `server`/`database`/`username`/`password`/query params (`authentication_method`, `trust_server_cert`) — matches the `connect_with_url` contract.
2. Normalize in `ConnectionManager.connect_with_url`: detect MSSQL URLs and unpack to kwargs before calling `dialect.create_engine`.
3. Document that `sqlalchemy_url` is generic-dialect-only and reject MSSQL URLs with a clear error in `connect_database` or `resolve_dialect_from_url`.

Option 1 keeps the URL path a first-class MSSQL connection method and matches the tool's documented contract ("Connect directly with a SQLAlchemy URL"); needs a convention for `authentication_method` in the URL (query param like `?authentication_method=windows`).
