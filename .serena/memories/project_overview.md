# dbmcp Project Overview

## Purpose
MCP server giving AI assistants read-only access to SQL databases — schema exploration, query execution, structural analysis. Designed for legacy databases with undeclared foreign keys. Responses use TOON format for token efficiency.

## Tech Stack
- **Python 3.11+** (development uses 3.13 in .venv, managed by `uv`)
- **MCP SDK**: `mcp[cli]>=1.27.0` (FastMCP)
- **SQLAlchemy 2.0+** for connection pooling and metadata introspection
- **sqlglot** for query validation (denylist-based)
- **toon-format** for token-efficient response serialization
- **Optional dialects**: pyodbc + azure-identity (mssql), databricks-sqlalchemy + databricks-sql-connector (databricks)
- **Dev**: pytest, pytest-asyncio, pytest-cov, ruff, pyright, complexipy, jupyter

## Multi-Dialect
Currently on branch `gsd/v2.0-multi-dialect-support` — expanding beyond SQL Server to Databricks and SQLite.

## Entry Point
`dbmcp` CLI command → `src.mcp_server.server:main`

## Active MCP Tools (9)
Registered via `@mcp.tool()` decorators in tool modules:
- **schema_tools.py**: connect_database, list_schemas, list_tables, get_table_schema, get_sample_data
- **query_tools.py**: execute_query
- **analysis_tools.py**: get_column_info, find_pk_candidates, find_fk_candidates
