# External Integrations

**Analysis Date:** 2026-03-03

## APIs & External Services

**Model Context Protocol (MCP):**
- FastMCP server implementation - Enables Claude and other AI agents to use dbmcp as a tool server
  - SDK/Client: mcp[cli]>=1.0.0
  - Transport: stdio (JSON-RPC 2.0 over standard input/output)
  - Tools exposed: connect_database, list_schemas, list_tables, get_table_schema, get_sample_data, execute_query, find_pk_candidates, find_fk_candidates, get_column_info

**Azure Identity Services:**
- Azure AD token acquisition - Enables managed identity and service principal authentication
  - SDK/Client: azure-identity>=1.14.0
  - Auth methods: DefaultAzureCredential (credential chain: Environment, ManagedIdentity, AzureCliCredential, SharedTokenCacheCredential)
  - Scope: https://database.windows.net/.default (Azure SQL Database)
  - Token format: UTF-16LE encoded, packed for ODBC Driver 18

## Data Storage

**Databases:**
- SQL Server 2016+ / Azure SQL Database (primary target)
  - Connection: ODBC Driver 18 for SQL Server
  - Client: SQLAlchemy 2.0+ with pyodbc 5.0+
  - Authentication: SQL, Windows Integrated, Azure AD, Azure AD Integrated
  - Connection pooling: SQLAlchemy QueuePool with configurable pool size and recycling

**File Storage:**
- Local filesystem only - Log files and example notebooks
  - `dbmcp.log` - Application logs (file-based, rotated via OS)
  - `.ipynb` files - Jupyter example notebooks (in `examples/` directory)

**Caching:**
- In-memory connection cache - SQLAlchemy connection pooling
- No external caching service (Redis, Memcached, etc.)

## Authentication & Identity

**Auth Provider:**
- Azure AD (primary for cloud deployments)
  - Implementation: azure-identity DefaultAzureCredential
  - Credential chain (non-interactive only):
    1. Environment variables (AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, AZURE_TENANT_ID)
    2. Managed identity (VM/AKS)
    3. Azure CLI cached credentials (az login)
    4. Shared token cache (Service Principal)
  - Token format: Bearer token packed for ODBC SQL_COPT_SS_ACCESS_TOKEN (1256)

- SQL Server authentication (fallback)
  - Implementation: Plain text credentials in ODBC connection string
  - Security: Never logged per NFR-005; redacted by CredentialFilter

- Windows integrated authentication
  - Implementation: Trusted_Connection via ODBC

## Monitoring & Observability

**Error Tracking:**
- None integrated - Errors logged to file and stderr
- Expected usage: External log aggregation (Azure Log Analytics, Splunk, etc.)

**Logs:**
- Approach: Structured logging to file + stderr
  - File: `dbmcp.log` (default, configurable via Path parameter)
  - Stderr: WARNING and above (non-intrusive for stdout JSON-RPC)
  - Format: ISO 8601 timestamp, logger name, level, message
  - Redaction: Automatic credential filtering via CredentialFilter
  - Performance tracking: T105 metrics for metadata query times (target: <30s for 1000 tables)

## CI/CD & Deployment

**Hosting:**
- Stateless MCP server - Can run anywhere with Python 3.11+ and ODBC Driver 18
- Primary deployment: Claude desktop client, Claude web, or custom MCP clients
- Intended for: Single-user or small-team usage (no multi-tenancy features)

**CI Pipeline:**
- GitHub Actions configured in `.github/workflows/` (if present)
- Test pipeline: `uv run pytest tests/` (with markers for integration/performance tests)
- Linting: `uv run ruff check src/`
- Coverage: `uv run pytest --cov=src tests/`

## Environment Configuration

**Required env vars (for Azure AD authentication only):**
- `AZURE_CLIENT_ID` - Service principal client ID (for DefaultAzureCredential)
- `AZURE_CLIENT_SECRET` - Service principal secret (for DefaultAzureCredential)
- `AZURE_TENANT_ID` - Azure tenant ID (for DefaultAzureCredential)

**Optional env vars:**
- None for core operation; all other configuration is tool-parameter based

**Secrets location:**
- Sensitive data: Never stored in code or `.env` files
- Azure credentials: Azure CLI cache, environment variables, or managed identity (non-interactive sources only)
- SQL credentials: Passed as tool parameters; never persisted or logged

## Webhooks & Callbacks

**Incoming:**
- None - dbmcp is a query-response service, not an event-driven service

**Outgoing:**
- None - No external HTTP calls or webhooks initiated by dbmcp

## Data Flow

**Query Execution Pipeline:**
1. Client → MCP tool call (e.g., `execute_query`)
2. ConnectionManager.get_engine() → SQLAlchemy engine from pool
3. QueryService.execute_query() → sqlglot AST parse + validation
4. ValidationResult checked against denylist (DML/DDL/DCL/stored procedures)
5. If safe: execute via SQLAlchemy text() → SQL Server
6. Return JSON results to client

**Metadata Introspection Pipeline:**
1. Client → MCP tool call (e.g., `list_tables`)
2. MetadataService → SQLAlchemy inspector or SQL Server DMVs
3. Performance timing logged (T105) for NFR-001 compliance
4. Return JSON response to client

**Connection Lifecycle:**
1. Client calls `connect_database(server, database, ...)`
2. ConnectionManager generates connection_id (SHA256 hash)
3. ODBC connection string built → SQLAlchemy engine created
4. Test query executed (SELECT @@VERSION, DB_NAME())
5. Engine + metadata stored in module-level singleton
6. connection_id returned to client for subsequent tool calls
7. Client disconnects via `disconnect()` or connection auto-disposed on server shutdown

---

*Integration audit: 2026-03-03*
