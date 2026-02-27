# DBMCP: Database Schema Explorer MCP Server

[![CI](https://github.com/jesse-smith/dbmcp/actions/workflows/ci.yml/badge.svg)](https://github.com/jesse-smith/dbmcp/actions/workflows/ci.yml)
[![codecov](https://codecov.io/gh/jesse-smith/dbmcp/graph/badge.svg?token=mmy1Rukgi3)](https://codecov.io/gh/jesse-smith/dbmcp)

A Model Context Protocol (MCP) server that enables AI assistants like Claude to explore and understand SQL Server database schemas. Designed for legacy databases with undeclared foreign keys and cryptic column names.

## Features

- **Database Discovery**: List schemas, tables, and views with row counts and metadata
- **Table Inspection**: Get detailed schema info including columns, indexes, and constraints
- **Relationship Inference**: Automatically detect likely foreign key relationships using name similarity, type compatibility, and structural hints
- **Sample Data**: Retrieve representative data samples using multiple sampling strategies
- **Column Analysis**: Infer column purposes (ID, enum, status, flag, amount, timestamp) from data patterns
- **Documentation Cache**: Export and cache database documentation as markdown files
- **Schema Drift Detection**: Detect changes between cached docs and current database state
- **Query Execution**: Execute read-only SQL queries with automatic row limiting

## Requirements

- Python 3.11+
- SQL Server database access (via ODBC Driver 18)
- Claude for Desktop (or other MCP-compatible client)

## Installation

1. Clone the repository:
```bash
git clone https://github.com/your-org/dbmcp.git
cd dbmcp
```

2. Create and activate a virtual environment:
```bash
python3.11 -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -e .
# Or install directly:
pip install "mcp[cli]" sqlalchemy pyodbc
```

4. Install ODBC Driver 18 for SQL Server:

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

## Configuration

### Claude for Desktop

Add the server to your Claude Desktop configuration (`~/.claude/claude_desktop_config.json`):

```json
{
  "mcpServers": {
    "dbmcp": {
      "command": "python",
      "args": ["-m", "src.mcp_server.server"],
      "cwd": "/path/to/dbmcp",
      "env": {
        "PYTHONPATH": "/path/to/dbmcp"
      }
    }
  }
}
```

See `docs/claude_config.json` for a template.

## Usage

Once configured, interact with your database through Claude:

### Connect to a Database
```
Connect to SQL Server at localhost, database AdventureWorks,
username sa, password MyPassword123.
```

### Explore Schema
```
List all schemas in the database.
Show me the top 20 tables by row count.
Get the schema for the Orders table.
```

### Infer Relationships
```
What foreign key relationships can you infer for the OrderDetails table?
```

### Sample Data
```
Show me 5 sample rows from the Customers table.
```

### Analyze Columns
```
Analyze the STATUS_CD column in the Orders table.
```

### Execute Queries
```
Execute: SELECT TOP 10 * FROM Orders WHERE Status = 'Pending'
```

## MCP Tools Reference

| Tool | Description |
|------|-------------|
| `connect_database` | Connect to a SQL Server database |
| `list_schemas` | List all schemas with table/view counts |
| `list_tables` | List tables with filtering, sorting, pagination |
| `get_table_schema` | Get detailed table schema (columns, indexes, FKs) |
| `infer_relationships` | Infer potential foreign key relationships |
| `get_sample_data` | Retrieve sample rows from a table |
| `analyze_column` | Analyze column to infer purpose |
| `export_documentation` | Export database docs to markdown files |
| `load_cached_docs` | Load previously cached documentation |
| `check_drift` | Detect schema changes since last cache |
| `execute_query` | Execute read-only SQL queries |

## Non-Functional Requirements

The server is designed to meet the following performance targets:

| NFR | Requirement | Threshold |
|-----|-------------|-----------|
| NFR-001 | Metadata retrieval | <30s for 1000 tables |
| NFR-002 | Sample data retrieval | <10s per request |
| NFR-003 | Documentation size | <1MB for 500 tables |
| NFR-004 | Read-only enforcement | Block all writes by default |
| NFR-005 | Credential security | Never log passwords |

## Development

### Running Tests
```bash
# All tests
pytest

# Unit tests only
pytest tests/unit/

# Integration tests
pytest tests/integration/

# Performance tests (slow)
pytest tests/performance/ -m slow

# NFR compliance suite
pytest tests/compliance/
```

### Code Quality
```bash
# Linting
ruff check .

# Type checking
mypy src/
```

### Project Structure
```
dbmcp/
├── src/
│   ├── mcp_server/     # FastMCP server and tools
│   ├── db/             # Database connection, metadata, queries
│   ├── inference/      # FK and column inference algorithms
│   ├── cache/          # Documentation caching and drift detection
│   └── models/         # Data models (Schema, Table, Column, etc.)
├── tests/
│   ├── unit/           # Unit tests
│   ├── integration/    # Integration tests
│   ├── performance/    # Performance and NFR validation
│   ├── compliance/     # NFR compliance suite
│   └── fixtures/       # Test fixtures and utilities
├── docs/               # Documentation and examples
├── examples/           # Example notebooks
└── specs/              # Feature specifications
```

## License

[Your License Here]

## Contributing

[Your Contributing Guidelines Here]
