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

## Configuration

dbmcp loads optional configuration from a TOML file. No config file is required — all settings have sensible defaults.

### Config file locations

dbmcp searches for a config file in this order (first match wins):

| Priority | Path | Use case |
|----------|------|----------|
| 1 | `./dbmcp.toml` | Project-level config, committed to repo or kept local |
| 2 | `~/.dbmcp/config.toml` | User-level config, shared across all projects |

### Setting up a project-level config

Create `dbmcp.toml` in the directory where the MCP server runs (usually your project root):

```toml
[defaults]
query_timeout = 60          # seconds (5–300, default: 30)
row_limit = 5000            # max rows returned (1–10000, default: 1000)
sample_size = 10            # default sample rows (1–1000, default: 5)
text_truncation_limit = 2000  # chars before truncation (100–10000, default: 1000)

[connections.dev]
server = "localhost"
database = "mydb"
authentication_method = "sql"
username = "sa"
password = "${SA_PASSWORD}"   # resolved from env var at connection time
trust_server_cert = true

[connections.prod]
server = "prod-server.example.com"
database = "proddb"
port = 1434
authentication_method = "windows"

allowed_stored_procedures = ["sp_custom_report", "dbo.my_proc"]
```

### Setting up a user-level config

Create `~/.dbmcp/config.toml` for connections and defaults you want available everywhere:

```bash
mkdir -p ~/.dbmcp
```

```toml
# ~/.dbmcp/config.toml

[defaults]
query_timeout = 60

[connections.staging]
server = "staging-db.internal"
database = "app_staging"
authentication_method = "azure_ad_integrated"
tenant_id = "your-tenant-id"

[connections.local]
server = "localhost"
database = "devdb"
authentication_method = "sql"
username = "sa"
password = "${SA_PASSWORD}"
trust_server_cert = true
```

> **Tip:** If both files exist, the project-level `dbmcp.toml` takes precedence and the user-level file is ignored entirely.

### Using named connections

Once configured, pass the connection name to `connect_database` instead of individual parameters:

```
connect_database(connection_name="dev")
```

Explicit parameters override config values, so you can use a named connection as a base and override specific fields:

```
connect_database(connection_name="dev", database="other_db")
```

### Connection fields reference

| Field | Type | Default | Description |
|-------|------|---------|-------------|
| `server` | string | *(required)* | SQL Server hostname or IP |
| `database` | string | *(required)* | Database name |
| `port` | int | `1433` | SQL Server port |
| `authentication_method` | string | `"sql"` | `sql`, `windows`, `azure_ad`, or `azure_ad_integrated` |
| `username` | string | — | For SQL or Azure AD auth |
| `password` | string | — | Supports `${ENV_VAR}` references |
| `trust_server_cert` | bool | `false` | Trust server certificate without validation |
| `connection_timeout` | int | `30` | Connection timeout in seconds |
| `tenant_id` | string | — | Azure AD tenant ID (for `azure_ad_integrated`) |

### Environment variable references

Credential fields support `${VAR_NAME}` syntax. Variables are resolved at connection time (not when the config is loaded), so the environment variable must be set when you call `connect_database`:

```toml
[connections.prod]
server = "prod-server"
database = "proddb"
password = "${PROD_DB_PASSWORD}"
```

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
