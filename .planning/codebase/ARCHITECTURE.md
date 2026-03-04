# Architecture

**Analysis Date:** 2026-03-03

## Pattern Overview

**Overall:** Model-Control-Service (MCS) pattern with MCP protocol adapter layer

**Key Characteristics:**
- **MCP-first design**: Tools are FastMCP decorated functions in `src/mcp_server/` that act as HTTP/stdio adapters
- **Layered service architecture**: Domain logic (connection, metadata, query, analysis) isolated in `src/db/` and `src/analysis/`
- **Data-model driven**: Core domain entities in `src/models/` are exchanged between services (no ORM, plain dataclasses)
- **Singleton ConnectionManager**: Shared connection pooling across all tool invocations for a single server lifetime
- **Pure validation functions**: Query validation is stateless (sqlglot AST parsing, no database connection required)
- **Separation of concerns**: Tool layers handle parameter validation and JSON serialization; services handle business logic

## Layers

**MCP Server Layer (Tool Adapters):**
- Purpose: Expose database operations as MCP tools over stdio/HTTP transport
- Location: `src/mcp_server/`
- Contains: `@mcp.tool()` decorated async functions (server.py, schema_tools.py, query_tools.py, analysis_tools.py)
- Depends on: ConnectionManager, MetadataService, QueryService, analysis modules, logging
- Used by: Claude via MCP protocol
- Responsibilities: Parameter validation, error catching, JSON serialization, logging tool invocations

**Service Layer (Business Logic):**
- Purpose: Implement core database operations and domain logic
- Location: `src/db/` and `src/analysis/`
- Contains:
  - `ConnectionManager`: Connection pooling, lifecycle, credential handling (no logging passwords)
  - `MetadataService`: Schema/table/column/index discovery via SQLAlchemy inspector + SQL Server DMVs
  - `QueryService`: Query execution, sample data retrieval, data truncation
  - `PKDiscovery`, `FKCandidateSearch`, `ColumnStatsCollector`: Analysis modules for relationship and column profiling
  - `validate_query()`: Pure function for AST-based query validation
- Depends on: SQLAlchemy, pyodbc, sqlglot, models
- Used by: Tool layer, tests
- Responsibilities: Database interaction, business rule enforcement, performance logging (NFR-001 tracking)

**Model Layer (Domain Entities):**
- Purpose: Define core data structures for schemas, tables, columns, queries, analysis results
- Location: `src/models/`
- Contains:
  - `schema.py`: Connection, Schema, Table, Column, Index, Query, SampleData, ValidationResult, enum types
  - `analysis.py`: ColumnStatistics, PKCandidate, FKCandidateData (for relationship analysis)
  - `relationship.py`: Relationship tracking (reserved for future use)
- Depends on: dataclasses, datetime, enums (stdlib only)
- Used by: Services and tools
- Responsibilities: Type safety, documentation of domain concepts, JSON serialization support

**Infrastructure Layer:**
- Purpose: Cross-cutting concerns
- Location: `src/logging_config.py`, `src/metrics.py`
- Contains:
  - Logging setup (file + stderr, never stdout to avoid corrupting JSON-RPC)
  - Credential filtering to prevent password logging
  - Metrics placeholder (currently unused but available for performance tracking)
- Used by: All layers
- Responsibilities: Structured logging, security (redaction), observability hooks

## Data Flow

**Connection Establishment Flow:**

1. User calls `connect_database` MCP tool
2. Tool layer validates parameters, parses authentication method enum
3. Tool calls `ConnectionManager.connect()` with connection parameters
4. ConnectionManager:
   - Generates connection_id hash (excludes password for security)
   - Checks connection cache (reuses if exists)
   - Builds ODBC connection string (varies by auth method)
   - Creates SQLAlchemy engine with QueuePool pooling config
   - Tests connection with probe query (SELECT @@VERSION)
   - Stores engine and metadata in _engines and _connections dicts
5. Tool gets MetadataService, lists schemas for response
6. Tool returns JSON with connection_id and schema count

**Schema Discovery Flow:**

1. User calls `list_schemas` with connection_id
2. Tool layer retrieves ConnectionManager and gets engine for connection_id
3. Tool creates MetadataService(engine)
4. MetadataService.list_schemas():
   - If SQL Server: Uses DMV query (sys.schemas) for efficiency
   - Falls back to SQLAlchemy inspector for other databases
   - Returns Schema objects sorted by table_count descending
5. Tool serializes schemas to JSON with status="success"

**Query Validation & Execution Flow:**

1. User calls `execute_query` with connection_id and SQL text
2. Tool layer validates query via `validate_query(sql)` (pure function)
   - Parses SQL into sqlglot AST
   - Walks AST checking for denied operation types (DML, DDL, DCL, etc.)
   - Returns ValidationResult with is_safe bool and denial reasons
3. If not safe: Returns error JSON immediately (no DB connection)
4. If safe:
   - Gets engine and creates QueryService(engine)
   - Executes query via SQLAlchemy text()
   - Truncates large values (>1000 chars text, binary to 32 bytes hex)
   - Returns Query object with execution_time_ms and rows_affected
5. Tool serializes to JSON

**Sample Data Retrieval Flow:**

1. User calls `get_sample_data` with table_name, schema_name, sampling_method
2. Tool creates QueryService and calls get_sample_data()
3. QueryService builds sampling query based on method:
   - TOP N: Simple SELECT TOP N (fast, not representative)
   - TABLESAMPLE: SQL Server TABLESAMPLE SYSTEM percentage (statistical)
   - MODULO: WHERE ROW_NUMBER() % interval = 0 (deterministic, repeatable)
4. Executes query, truncates large values, returns SampleData object
5. Tool serializes rows and metadata to JSON

**Analysis Flow (Column Stats/PK-FK Discovery):**

1. User calls `get_column_info`, `find_pk_candidates`, or `find_fk_candidates`
2. Tool validates table/column existence via MetadataService
3. Tool creates analysis module instance (ColumnStatsCollector, PKDiscovery, FKCandidateSearch)
4. Analysis module:
   - Opens raw database connection via engine
   - Executes targeted SQL queries (aggregation, uniqueness, overlap checking)
   - Returns analysis models (ColumnStatistics, PKCandidate, FKCandidateData)
5. Tool collects results, serializes to JSON with metadata

**Error Handling Flow:**

1. Any layer encounters error
2. Logs via get_logger() (file + stderr, never stdout)
3. CredentialFilter redacts sensitive keywords in error messages
4. Tool layer catches exceptions and returns JSON with status="error" and error_message
5. User receives structured error response via MCP

## State Management

**Connection State:**
- Managed by singleton `ConnectionManager` in `src/mcp_server/server.py`
- State: _engines dict (SQLAlchemy engines) and _connections dict (Connection metadata)
- Lifetime: Server startup to shutdown (no hot reload of connections)
- Thread safety: SQLAlchemy QueuePool handles connection acquisition/release

**Query Validation State:**
- Stateless: `validate_query()` is pure function (no side effects, no DB connection)
- State: None (sqlglot AST parsing is deterministic)
- Cacheable: Results could be cached by caller if needed

**Analysis Results State:**
- Ephemeral: Analysis modules compute statistics on-demand
- No persistence: Results returned directly to user, not cached
- Deterministic: Same query on same table always produces same results (assuming table unchanged)

## Key Abstractions

**Connection Abstraction:**
- Purpose: Isolates credential handling, pooling config, ODBC string building
- Examples: `src/db/connection.py` (ConnectionManager class)
- Pattern: Singleton manager with dict-based caching and reuse by connection_id
- Benefits: Prevents credential leaks, enables pool tuning, supports hot connection reuse

**MetadataService Abstraction:**
- Purpose: Provides unified interface for schema discovery across databases
- Examples: `src/db/metadata.py` (MetadataService class)
- Pattern: Adapter over SQLAlchemy inspector + SQL Server DMV optimizations
- Benefits: Hides SQL Server specifics, makes queries testable, enables performance optimization

**QueryService Abstraction:**
- Purpose: Encapsulates query execution, sampling strategies, data truncation logic
- Examples: `src/db/query.py` (QueryService class)
- Pattern: Stateless service with pluggable sampling methods (TOP, TABLESAMPLE, MODULO)
- Benefits: Reusable across tools, testable truncation logic, supports multiple sampling strategies

**ValidationService Abstraction:**
- Purpose: Pure AST-based query validation without database access
- Examples: `src/db/validation.py` (validate_query function)
- Pattern: Pure function accepting SQL string, returns ValidationResult
- Benefits: No DB connection required, fast, deterministic, cacheable

**Analysis Modules Abstraction:**
- Purpose: Isolate complex analysis logic (PK discovery, FK matching, column profiling)
- Examples: `src/analysis/{pk_discovery, fk_candidates, column_stats}.py`
- Pattern: Classes that take connection/schema/table parameters, expose query methods
- Benefits: Modular, testable, separates statistical computation from tool layer

## Entry Points

**MCP Server Startup:**
- Location: `src/mcp_server/server.py::main()`
- Triggers: `uv run python -m src.mcp_server.server`
- Responsibilities:
  1. Configure logging (file + stderr, never stdout)
  2. Create FastMCP instance
  3. Initialize singleton ConnectionManager
  4. Import tool modules to register @mcp.tool() decorators
  5. Start server on stdio transport

**Tool Invocation Entry Points:**
- `connect_database`: User initiates database connection
- `list_schemas`, `list_tables`, `get_table_schema`: User explores schema
- `get_sample_data`: User retrieves table data sample
- `execute_query`: User runs ad-hoc SQL (validated against denylist)
- `get_column_info`, `find_pk_candidates`, `find_fk_candidates`: User analyzes table structure

## Error Handling

**Strategy:** Layered error catching with JSON-RPC safe responses

**Patterns:**

**Tool Layer:**
```python
@mcp.tool()
async def some_tool(...) -> str:
    try:
        # validation, service calls
    except SpecificError as e:
        logger.error(f"Specific: {e}")
        return json.dumps({"status": "error", "error_message": str(e)})
    except Exception as e:
        logger.exception("Unexpected error")
        return json.dumps({"status": "error", "error_message": f"Unexpected: {type(e).__name__}"})
```

**Service Layer:**
```python
def service_method(...):
    if not valid:
        raise ValueError("Validation failed")  # Caught by tool
    try:
        # DB operation
    except SomeException as e:
        logger.error(f"Operation failed: {e}")
        raise  # Re-raise to tool layer
```

**Connection Errors:**
- ConnectionManager.connect() raises ConnectionError on failure
- Tool catches and returns user-friendly JSON error
- Logs do NOT include passwords (CredentialFilter redacts)

**Query Execution Errors:**
- Validation phase: validate_query() returns ValidationResult with denial_reasons
- Execution phase: QueryService.execute_query() catches SQL errors, returns Query object with error_message
- Tool serializes both to JSON with status="error"

**Validation Failures:**
- Input parameter validation in tool layer (limit ranges, enum parsing, etc.)
- Returns JSON error immediately (no service call)
- Example: "limit must be between 1 and 1000"

## Cross-Cutting Concerns

**Logging:**
- Framework: Python logging module
- Configuration: `src/logging_config.py` sets up file handler (dbmcp.log) + stderr handler
- Severity levels:
  - DEBUG: Detailed metadata queries, performance timing
  - INFO: Connection success, tool invocations
  - WARNING: Slow queries (>5s connection), NFR-001 threshold breaches
  - ERROR: Connection/query failures, validation errors
- Credential safety: CredentialFilter redacts keywords (password, token, key, etc.)
- MCP safety: Never uses stdout (would corrupt JSON-RPC); only file + stderr

**Authentication:**
- Supported methods: SQL, Windows, Azure AD, Azure AD Integrated (via azure-identity package)
- Credential flow:
  1. Tool parameter validation
  2. ODBC string building (auth-method-specific)
  3. ConnectionManager creates engine
  4. Token provider (AzureTokenProvider) injected for azure_ad_integrated
  5. Credentials never stored in Connection object (only username, not password)
  6. Credentials never logged (CredentialFilter)

**Performance Monitoring (NFR-001/NFR-002):**
- Tools: `src/metrics.py` (currently unused but available)
- Tracking: MetadataService logs query timing for list_schemas, list_tables against 30s threshold
- Threshold: NFR_001_THRESHOLD_MS = 30000 (30 seconds for 1000+ tables)
- Warning level: Logged as WARNING if exceeded
- Per-query timing: All service methods record time.time() start/end, compute elapsed_ms

**Query Validation & Safety:**
- Pure validation: `validate_query()` in `src/db/validation.py` is a pure function
- AST parsing: sqlglot parses SQL to abstract syntax tree
- Denylist categories: DML (INSERT/UPDATE/DELETE/MERGE), DDL (CREATE/ALTER/DROP), DCL (GRANT/REVOKE), operational
- Safe procedures: 22 known-safe SQL Server system stored procedures (sp_help, sp_columns, etc.)
- Nested write detection: Walks AST to detect DML/DDL nested in CTEs or control flow
- CTE writes: Detects SELECT INTO wrapped in CTE (CTE_WRAPPED_WRITE category)

