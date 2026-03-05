# DBMCP: Database MCP Server for SQL Server

[![CI](https://github.com/jesse-smith/dbmcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jesse-smith/dbmcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jesse-smith/dbmcp/graph/badge.svg?token=mmy1Rukgi3)](https://codecov.io/gh/jesse-smith/dbmcp)

MCP server that gives AI assistants full read-only access to SQL Server databases -- schema exploration, query execution, and structural analysis. Designed for legacy databases with undeclared foreign keys. All responses use TOON format for minimal token consumption.

## Features

- Schema exploration (schemas, tables, columns, indexes, constraints)
- Read-only query execution with CTE support and automatic row limiting
- Query validation via configurable denylist (sqlglot-based)
- Primary key candidate discovery
- Foreign key candidate inference
- Column statistics and analysis
- Azure AD integrated authentication
- TOON-formatted responses (token-efficient for LLM consumers)
- Async database execution with configurable query timeouts

## Requirements

- Python 3.11+
- SQL Server (via ODBC Driver 18)
- uv (Python package manager)
- MCP-compatible client (Claude Desktop, Claude Code, etc.)

## Installation

### 1. Global install (recommended for MCP clients)

```bash
uv tool install "dbmcp @ git+https://github.com/jesse-smith/dbmcp.git"
```

### 2. Local development

```bash
git clone https://github.com/jesse-smith/dbmcp.git
cd dbmcp
uv sync
```

### ODBC Driver 18

**macOS:**
```bash
brew tap microsoft/mssql-release https://github.com/Microsoft/homebrew-mssql-release
brew install msodbcsql18
```

**Linux (Ubuntu/Debian):**
```bash
curl https://packages.microsoft.com/keys/microsoft.asc | sudo apt-key add -
curl https://packages.microsoft.com/config/ubuntu/$(lsb_release -rs)/prod.list | sudo tee /etc/apt/sources.list.d/mssql-release.list
sudo apt-get update
sudo ACCEPT_EULA=Y apt-get install -y msodbcsql18
```

**Windows:**
Download from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server

## MCP Client Configuration

### Claude Desktop

Add to `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "dbmcp": {
      "command": "dbmcp"
    }
  }
}
```

### Claude Code

Add to `.mcp.json` or configure via CLI:

```json
{
  "mcpServers": {
    "dbmcp": {
      "command": "dbmcp",
      "type": "stdio"
    }
  }
}
```

> If installed locally (not via `uv tool`), use `uv run dbmcp` as the command and set `cwd` to the repo directory.

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `connect_database` | Connect to a SQL Server instance (Windows auth, SQL auth, or Azure AD) |
| `list_schemas` | List all schemas with table/view counts |
| `list_tables` | List tables with filtering, sorting, and pagination |
| `get_table_schema` | Get detailed table schema (columns, indexes, foreign keys) |
| `get_sample_data` | Retrieve sample rows from a table |
| `execute_query` | Execute read-only SQL queries (supports CTEs) |
| `get_column_info` | Get column-level statistics and value distributions |
| `find_pk_candidates` | Discover likely primary key columns via uniqueness analysis |
| `find_fk_candidates` | Infer potential foreign key relationships between tables |

## Development

```bash
uv sync --group dev
uv run pytest tests/
uv run ruff check src/
```

## Project Structure

```
dbmcp/
  src/
    mcp_server/    # FastMCP server, tool definitions
    db/            # Connection, metadata, query execution, validation
    analysis/      # PK discovery, FK inference, column stats
    models/        # Data models (schema, relationship, analysis)
  tests/
    unit/
    integration/
    compliance/
    performance/
  specs/           # Feature specifications
```

## License

MIT
