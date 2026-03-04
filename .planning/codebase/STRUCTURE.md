# Codebase Structure

**Analysis Date:** 2026-03-03

## Directory Layout

```
dbmcp/
├── src/                          # Main source code
│   ├── mcp_server/               # MCP tool implementations (tool layer)
│   │   ├── server.py             # Entry point, FastMCP setup, ConnectionManager singleton
│   │   ├── schema_tools.py        # connect_database, list_schemas, list_tables, get_table_schema
│   │   ├── query_tools.py         # get_sample_data, execute_query
│   │   └── analysis_tools.py      # get_column_info, find_pk_candidates, find_fk_candidates
│   │
│   ├── db/                        # Database service layer
│   │   ├── connection.py          # ConnectionManager, PoolConfig, ConnectionError
│   │   ├── metadata.py            # MetadataService (schema/table/column/index discovery)
│   │   ├── query.py               # QueryService (query execution, sampling, truncation)
│   │   ├── validation.py          # validate_query() pure function (AST-based denylist)
│   │   └── azure_auth.py          # AzureTokenProvider for azure_ad_integrated auth
│   │
│   ├── analysis/                  # Analysis modules for relationship/column profiling
│   │   ├── column_stats.py        # ColumnStatsCollector (numeric/datetime/string statistics)
│   │   ├── pk_discovery.py        # PKDiscovery (constraint-backed and structural PK candidates)
│   │   ├── fk_candidates.py       # FKCandidateSearch (foreign key relationship matching)
│   │   └── __init__.py
│   │
│   ├── models/                    # Domain data structures
│   │   ├── schema.py              # Connection, Schema, Table, Column, Index, Query, SampleData, ValidationResult
│   │   ├── analysis.py            # ColumnStatistics, PKCandidate, FKCandidateData (analysis result types)
│   │   ├── relationship.py        # Relationship (reserved for future use)
│   │   └── __init__.py
│   │
│   ├── logging_config.py          # Logging setup (file + stderr, CredentialFilter)
│   ├── metrics.py                 # Performance metrics placeholder
│   └── __init__.py
│
├── tests/                         # Test suite
│   ├── unit/                      # Unit tests (no DB required)
│   │   ├── test_connection.py     # ConnectionManager, PoolConfig
│   │   ├── test_metadata.py       # MetadataService discovery methods
│   │   ├── test_query.py          # QueryService, sampling methods
│   │   ├── test_validation.py     # validate_query() AST parsing
│   │   ├── test_azure_auth.py     # AzureTokenProvider
│   │   ├── test_analysis_models.py # Analysis model serialization
│   │   ├── test_pk_discovery.py   # PKDiscovery constraint/structural detection
│   │   ├── test_fk_candidates.py  # FKCandidateSearch matching logic
│   │   ├── test_column_stats.py   # ColumnStatsCollector statistics
│   │   └── __init__.py
│   │
│   ├── integration/               # Integration tests (uses live test database)
│   │   ├── conftest.py            # Fixtures for test database connection
│   │   ├── test_discovery.py      # Schema/table/column discovery
│   │   ├── test_get_column_info.py # Column statistics retrieval
│   │   ├── test_sample_data.py    # Sample data with various methods
│   │   ├── test_query_execution.py # Query execution and validation
│   │   ├── test_pk_discovery.py   # PK candidate finding
│   │   ├── test_fk_candidates.py  # FK candidate searching
│   │   ├── test_azure_ad_auth.py  # Azure AD integration (if available)
│   │   └── __init__.py
│   │
│   └── conftest.py                # Shared pytest fixtures
│
├── specs/                         # Feature specifications (reference)
│   ├── 001-db-schema-explorer/
│   ├── 002-example-notebooks/
│   ├── 003-allow-cte-queries/
│   ├── 004-azure-ad-integrated-auth/
│   ├── 005-denylist-query-validation/
│   ├── 006-codebase-refactor/
│   └── 007-analysis-tools/
│
├── .planning/                     # GSD planning documents (generated)
│   └── codebase/
│       ├── ARCHITECTURE.md        # (this file)
│       ├── STRUCTURE.md           # (this file)
│       └── ...
│
├── pyproject.toml                 # Python project config (uv, pytest, ruff)
├── uv.lock                        # Dependency lock file
└── dbmcp.log                       # Runtime log file (generated)
```

## Directory Purposes

**src/mcp_server/:**
- Purpose: MCP tool adapters (HTTP/stdio interface to database services)
- Contains: Async tool functions decorated with `@mcp.tool()`, parameter validation, JSON serialization
- Key files: `server.py` (entry point), schema_tools.py, query_tools.py, analysis_tools.py
- Dependencies: Models, services, ConnectionManager

**src/db/:**
- Purpose: Core database service implementations
- Contains: Connection pooling, metadata discovery, query execution, validation
- Key files: connection.py (ConnectionManager), metadata.py (MetadataService), query.py (QueryService), validation.py (pure validation)
- Dependencies: SQLAlchemy, pyodbc, sqlglot, models

**src/analysis/:**
- Purpose: Complex analysis logic for table profiling and relationship discovery
- Contains: Column statistics, PK/FK candidate detection
- Key files: column_stats.py, pk_discovery.py, fk_candidates.py
- Dependencies: SQLAlchemy, models

**src/models/:**
- Purpose: Shared domain entities used across layers
- Contains: Dataclasses for schema, query, analysis results, enums for auth/query types
- Key files: schema.py (primary entities), analysis.py (analysis result types)
- Dependencies: None (only stdlib: dataclasses, datetime, enum)

**tests/unit/:**
- Purpose: Unit tests with no database required
- Contains: Mocked services, pure function tests, model serialization
- Key files: test_validation.py, test_analysis_models.py
- Runs: Via `uv run pytest tests/unit/` with no external DB

**tests/integration/:**
- Purpose: End-to-end tests against live test database (SVWTSTEM04, StemSoftClinic)
- Contains: Real database operations, discovery, sampling, analysis
- Key files: conftest.py (test DB fixtures), test_discovery.py, test_query_execution.py
- Runs: Via `uv run pytest tests/integration/` (requires live DB connection)

## Key File Locations

**Entry Points:**
- `src/mcp_server/server.py::main()`: MCP server startup (FastMCP, ConnectionManager init, tool registration)
- `src/mcp_server/server.py::get_connection_manager()`: Access singleton ConnectionManager from tools

**Configuration:**
- `pyproject.toml`: Python 3.11+, dependencies (mcp, sqlalchemy, pyodbc, sqlglot, azure-identity), test config, ruff
- `src/logging_config.py`: Logging setup (file + stderr), CredentialFilter, logger factory

**Core Logic:**
- `src/db/connection.py`: Connection lifecycle, ODBC string building, pool tuning
- `src/db/metadata.py`: Schema/table/column/index discovery, SQL Server DMV optimization
- `src/db/query.py`: Query execution, sampling strategies (TOP/TABLESAMPLE/MODULO), value truncation
- `src/db/validation.py`: Pure AST-based query validation, denylist categories

**Analysis:**
- `src/analysis/column_stats.py`: Per-column statistics (numeric/datetime/string)
- `src/analysis/pk_discovery.py`: PK candidate detection (constraint-backed and structural)
- `src/analysis/fk_candidates.py`: FK candidate search and overlap calculation

**Data Models:**
- `src/models/schema.py`: Connection, Schema, Table, Column, Index, Query, SampleData, enums
- `src/models/analysis.py`: ColumnStatistics, PKCandidate, FKCandidateData, analysis result types

**Testing:**
- `tests/conftest.py`: Shared pytest fixtures (logger setup, temp dirs)
- `tests/integration/conftest.py`: Test database connection fixture (SVWTSTEM04)
- `tests/unit/`: Individual unit test files (no DB dependency)
- `tests/integration/`: Individual integration test files (live DB dependency)

## Naming Conventions

**Files:**
- Module files: `lowercase_with_underscores.py` (e.g., connection.py, metadata.py)
- Test files: `test_*.py` (e.g., test_connection.py, test_metadata.py)
- Pattern: One primary class or cohesive module per file

**Directories:**
- Packages: `lowercase_with_underscores` (e.g., mcp_server, src/db, src/analysis)
- Feature specs: `NNN-kebab-case-name` (e.g., 001-db-schema-explorer, 007-analysis-tools)

**Classes:**
- Service classes: `PascalCase` + suffix (e.g., MetadataService, QueryService, ConnectionManager)
- Model classes: `PascalCase` (e.g., Connection, Table, Column, PKCandidate)
- Enum classes: `PascalCase` (e.g., AuthenticationMethod, TableType, QueryType)
- Exception classes: `PascalCase` + "Error" or "Exception" (e.g., ConnectionError)

**Functions:**
- Tool functions (MCP): `snake_case`, decorated with `@mcp.tool()` (e.g., connect_database, list_schemas)
- Service methods: `snake_case` (e.g., get_table_schema, list_tables)
- Pure/utility functions: `snake_case` (e.g., validate_query, get_logger)
- Helper functions: `_snake_case` (leading underscore, e.g., _build_table_entry, _validate_list_tables_params)

**Variables:**
- Constants (module level): `UPPERCASE_WITH_UNDERSCORES` (e.g., NFR_001_THRESHOLD_MS, DEFAULT_LOG_FILE)
- Parameters: `snake_case` (e.g., connection_id, schema_name, sample_size)
- Private instance: `_snake_case` (leading underscore, e.g., _engines, _connections, _inspector)

**Enums:**
- Values: `UPPERCASE_WITH_UNDERSCORES` (e.g., TableType.TABLE, AuthenticationMethod.SQL)
- Pattern: Use StrEnum for serialization-friendly enums

## Where to Add New Code

**New Feature (SQL Server operation):**
- Primary code: `src/db/{new_module}.py` (new service class)
- Test (unit): `tests/unit/test_{new_module}.py` (mock SQLAlchemy)
- Test (integration): `tests/integration/test_{feature}.py` (live DB)
- MCP tool: Add tool function in `src/mcp_server/{tool_category}.py` with `@mcp.tool()` decorator

**New MCP Tool (exposes existing service):**
- Add function in `src/mcp_server/{category}_tools.py` (schema_tools, query_tools, or analysis_tools)
- Use pattern:
  ```python
  @mcp.tool()
  async def tool_name(...) -> str:
      try:
          # param validation
          service = SomeService(engine)
          result = service.method(...)
          return json.dumps({"status": "success", "data": ...})
      except ValueError as e:
          return json.dumps({"status": "error", "error_message": str(e)})
      except Exception as e:
          logger.exception("Error in tool_name")
          return json.dumps({"status": "error", "error_message": str(e)})
  ```
- Register: Function automatically registers via `@mcp.tool()` decorator
- Import: Add import in `src/mcp_server/server.py` (after mcp instance, before main())

**New Model (domain entity):**
- Add to `src/models/schema.py` or `src/models/analysis.py` depending on category
- Use dataclass decorator: `@dataclass`
- Include docstring for each field
- Pattern: Keep models data-only (no methods except to_dict() for serialization)

**Utilities/Helpers:**
- Shared helpers: `src/{category}/{utility_name}.py` or directly in module if <50 lines
- Logging: Use `get_logger(__name__)` and configure in `src/logging_config.py`
- Constants: Define at module top with `UPPERCASE_WITH_UNDERSCORES` naming

**Tests:**
- Unit: `tests/unit/test_{module}.py` - Mock all DB calls, test logic in isolation
- Integration: `tests/integration/test_{feature}.py` - Use live DB fixture from conftest.py
- Fixtures: Add to `tests/conftest.py` (shared) or `tests/integration/conftest.py` (DB-specific)

## Special Directories

**specs/:**
- Purpose: Feature specifications (reference only, not runtime)
- Generated: Via /speckit commands (feature planning)
- Committed: Yes (version-controlled planning docs)
- Structure: Each feature has NNN-name/ with spec.md, plan.md, tasks.md, checklists/

**.planning/codebase/:**
- Purpose: GSD-generated codebase analysis docs
- Generated: Yes (via /gsd:map-codebase command)
- Committed: Yes (reference for implementation)
- Contains: ARCHITECTURE.md, STRUCTURE.md, CONVENTIONS.md, TESTING.md, CONCERNS.md, etc.

**src/__pycache__/ and tests/__pycache__/:**
- Purpose: Python bytecode cache (gitignored)
- Generated: Yes (auto-generated by Python)
- Committed: No
- Safety: Never commit __pycache__ directories

**dbmcp.egg-info/:**
- Purpose: Package metadata (generated by uv/setuptools)
- Generated: Yes (auto-generated)
- Committed: No (should be .gitignored)

