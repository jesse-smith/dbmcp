# Technology Stack

**Analysis Date:** 2026-03-03

## Languages

**Primary:**
- Python 3.11+ - Core application and MCP server implementation

## Runtime

**Environment:**
- Python 3.11+ (tested on 3.11, 3.12, 3.13.1)
- Virtual environment managed by `uv`

**Package Manager:**
- `uv` (projects tool) - Primary package and dependency manager
- Lockfile: `uv.lock` (present)

## Frameworks

**Core:**
- FastMCP 1.0.0+ - MCP server implementation (`mcp[cli]>=1.0.0`)
- SQLAlchemy 2.0.0+ - Database abstraction, connection pooling, and metadata introspection
- pyodbc 5.0.0+ - ODBC driver for SQL Server connectivity

**Authentication:**
- azure-identity 1.14.0+ - Azure AD integration for managed identities and service principals

**Query Processing:**
- sqlglot 26.0.0-<30.0.0 - SQL AST parsing and query validation (denylist enforcement)

**Testing:**
- pytest 7.0.0+ - Test runner
- pytest-asyncio 0.21.0+ - Async test support
- pytest-cov 4.0.0+ - Code coverage analysis

**Development Tools:**
- ruff 0.1.0+ - Fast Python linter and formatter (line-length: 120, target: py311)
- complexipy 5.2.0+ - Code complexity analysis

**Optional (Examples):**
- Jupyter 1.0.0+ - Notebook environment
- notebook 7.0.0+ - Jupyter web interface

## Key Dependencies

**Critical:**
- `mcp[cli]>=1.0.0` - MCP server framework and CLI transport
- `sqlalchemy>=2.0.0` - Connection pooling (QueuePool), metadata introspection, and cross-database compatibility
- `pyodbc>=5.0.0` - SQL Server ODBC driver (ODBC Driver 18 for SQL Server)

**Infrastructure:**
- `azure-identity>=1.14.0` - DefaultAzureCredential for Azure AD token acquisition
- `sqlglot>=26.0.0,<30.0.0` - SQL dialect parsing for query validation (T-SQL support required)

## Configuration

**Environment:**
- Configuration via tool parameters (no .env files required for core operation)
- Azure AD tenant_id configurable per-connection

**Build:**
- `pyproject.toml`: Build system configuration, dependencies, and tool settings
- Tool configuration sections: pytest, ruff, coverage

**Setup:**
- Entry point: `dbmcp = "src.mcp_server.server:main"` (defined in `pyproject.toml`)
- Configured to run on stdio transport (MCP spec requirement)

## Platform Requirements

**Development:**
- Python 3.11+
- ODBC Driver 18 for SQL Server (native on Windows; requires `odbcinst` on Linux/macOS)
- `uv` package manager installed

**Production:**
- Python 3.11+
- SQL Server 2016+ or Azure SQL Database (ODBC Driver 18 required)
- ODBC driver properly installed and configured
- Azure CLI (`az` command) or environment variables for Azure AD auth (optional)

## Database Connectivity

**Supported Authentication:**
- SQL authentication (username/password)
- Windows integrated authentication (Trusted_Connection)
- Azure AD password authentication
- Azure AD integrated (managed identity or service principal via DefaultAzureCredential)

**Connection Details:**
- Default port: 1433
- Certificate validation: Configurable (trust_server_cert parameter)
- Connection timeout: 5-300 seconds (configurable per-connection)
- Connection pooling: QueuePool (pool_size: 5, max_overflow: 10, pool_recycle: 3600s, pre_ping: True)

## Logging

**Framework:** Python standard library `logging` module

**Configuration:**
- Primary destination: `dbmcp.log` (file)
- Secondary destination: stderr (WARNING level and above)
- Formatter: ISO 8601 timestamps with module name and level
- Credential filtering: Automatic redaction of passwords, tokens, and secrets from logs (CredentialFilter class)

---

*Stack analysis: 2026-03-03*
