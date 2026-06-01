# Architecture Patterns: Multi-Dialect Integration

**Domain:** Multi-dialect database MCP tool server
**Researched:** 2026-04-13
**Confidence:** HIGH (based on direct codebase analysis, SQLAlchemy/sqlglot documentation knowledge)

## Recommended Architecture

### Design Principle: Narrow the Dialect Seam

The existing codebase already has a two-path pattern (`is_mssql` checks in MetadataService, `dialect_name` checks in QueryService). The refactor replaces these ad-hoc conditionals with a single protocol-based dispatch point. The key insight: **most code does not need to know about dialects at all** -- only a thin layer at the boundary does.

### Component Boundaries

| Component | Responsibility | Communicates With |
|-----------|---------------|-------------------|
| `src/db/dialect.py` (NEW) | DialectStrategy protocol + registry, dialect detection | ConnectionManager, MetadataService, QueryService, validation |
| `src/db/dialects/` (NEW package) | MssqlDialect, DatabricksDialect, GenericDialect implementations | dialect.py (via protocol) |
| `src/db/connection.py` (MODIFIED) | Engine creation delegated to dialect; stores dialect alongside engine | dialect.py |
| `src/db/metadata.py` (MODIFIED) | Receives dialect, replaces `is_mssql` branches with dialect method calls | dialect.py |
| `src/db/query.py` (MODIFIED) | Receives dialect for SQL generation (TOP vs LIMIT, identifier quoting) | dialect.py |
| `src/db/validation.py` (MODIFIED) | Receives sqlglot dialect name from strategy instead of hardcoding `"tsql"` | dialect.py |
| `src/config.py` (MODIFIED) | Discriminated ConnectionConfig with `dialect` field | connection.py |
| `src/analysis/` (MODIFIED) | Receives dialect for SQL function adaptation | dialect.py |
| `src/mcp_server/` (UNCHANGED interfaces) | Tool signatures unchanged; internal wiring passes dialect through | All db modules |

### New Module: `src/db/dialect.py`

```python
from typing import Protocol, runtime_checkable
from sqlalchemy.engine import Engine

@runtime_checkable
class DialectStrategy(Protocol):
    """Three-tier dialect abstraction.

    Tier 1: SQLAlchemy Inspector (universal) -- not in strategy, used directly
    Tier 2: Standard SQL with dialect-aware transpilation
    Tier 3: Dialect-specific optimizations
    """

    @property
    def name(self) -> str:
        """Human-readable dialect name (e.g., 'mssql', 'databricks')."""
        ...

    @property
    def sqlglot_dialect(self) -> str | None:
        """sqlglot dialect string for parsing/transpilation. None = auto-detect."""
        ...

    def create_engine(self, config: "DialectConnectionConfig") -> Engine:
        """Tier 3: Dialect-specific engine construction."""
        ...

    def fast_row_count_sql(self, schema: str, table: str) -> str | None:
        """Tier 3: Optimized row count query, or None to fall back to COUNT(*)."""
        ...

    def list_schemas_sql(self) -> str | None:
        """Tier 3: Optimized schema listing query, or None for Inspector."""
        ...

    def list_tables_sql(self, **filters) -> str | None:
        """Tier 3: Optimized table listing query, or None for Inspector."""
        ...

    def quote_identifier(self, name: str) -> str:
        """Tier 2: Dialect-appropriate identifier quoting."""
        ...

    def qualify_table(self, schema: str, table: str) -> str:
        """Tier 2: Fully qualified table reference."""
        ...

    def top_n_sql(self, query_core: str, n: int) -> str:
        """Tier 2: Apply row limit to a query."""
        ...

    def test_connection_sql(self) -> str:
        """Tier 3: Connection validation query (SELECT @@VERSION vs SELECT 1)."""
        ...
```

### New Package: `src/db/dialects/`

```
src/db/dialects/
    __init__.py          # Re-exports, dialect registry function
    mssql.py             # MssqlDialect -- extracts existing MSSQL-specific code
    databricks.py        # DatabricksDialect -- new
    generic.py           # GenericDialect -- fallback for any SQLAlchemy database
```

**Why a package, not a single file:** Each dialect implementation will be 100-200 lines (MSSQL has the most due to DMV queries, Azure auth, ODBC string building). Keeping them separate avoids a 500+ line monolith and makes it easy to add dialects without touching existing ones.

## Integration Points: Module-by-Module Analysis

### 1. ConnectionManager (`src/db/connection.py`)

**Current state:** Hardcodes `mssql+pyodbc://` URL construction, ODBC connection string building, `@@VERSION` test query, pyodbc-specific timeout setting, Azure AD token injection.

**Changes needed:**
- `connect()` signature simplified: accepts `DialectConnectionConfig` (discriminated union) or `sqlalchemy_url: str`
- Engine creation delegated to `dialect.create_engine(config)`
- Connection test delegated to `dialect.test_connection_sql()`
- `_engines` dict stores `(Engine, DialectStrategy)` tuples instead of bare engines
- New `get_dialect(connection_id) -> DialectStrategy` method
- `_build_odbc_connection_string()` and `_create_engine()` move to `MssqlDialect`
- `PoolConfig` stays in connection.py (shared across dialects)
- `_classify_db_error()` stays (error classification is useful for all dialects, SQLSTATE codes are standard)

**What moves out:**
- `_build_odbc_connection_string()` -> `MssqlDialect`
- ODBC driver selection -> `MssqlDialect`
- Azure AD token injection -> `MssqlDialect` (it is pyodbc-specific)
- `@@VERSION` test -> `MssqlDialect.test_connection_sql()`

**What stays:**
- Engine/connection lifecycle management
- Pool configuration
- Connection ID generation (needs dialect in hash input)
- `disconnect()`, `disconnect_all()`, `list_connections()`

**New helper:**
```python
def get_dialect(self, connection_id: str) -> DialectStrategy:
    """Get dialect strategy for a connection."""
    if connection_id not in self._dialects:
        raise ValueError(f"Connection '{connection_id}' not found.")
    return self._dialects[connection_id]
```

### 2. MetadataService (`src/db/metadata.py`)

**Current state:** Has `is_mssql` property and dual-path methods (`_list_schemas_mssql` / `_list_schemas_generic`, `_list_tables_mssql` / `_list_tables_generic`). Generic path already uses SQLAlchemy Inspector.

**Recommended refactoring -- delegation, not separate layer:**

The MetadataService should accept a `DialectStrategy` at construction and delegate Tier 3 operations to it. Do NOT create a separate metadata layer -- the existing MetadataService is already the right abstraction.

```python
class MetadataService:
    def __init__(self, engine: Engine, dialect: DialectStrategy | None = None):
        self.engine = engine
        self._dialect = dialect
        self._inspector = None

    def list_schemas(self, connection_id: str = "") -> list[Schema]:
        # Tier 3: Try dialect-specific optimized query
        if self._dialect:
            sql = self._dialect.list_schemas_sql()
            if sql is not None:
                return self._execute_schema_query(sql, connection_id)
        # Tier 1: Fall back to Inspector
        return self._list_schemas_inspector(connection_id)
```

**Key insight:** The existing `_list_schemas_generic` and `_list_tables_generic` methods become the Tier 1 fallback (they already use Inspector). The `_list_schemas_mssql` and `_list_tables_mssql` methods move into `MssqlDialect` as the SQL they return from Tier 3 methods. MetadataService executes whatever SQL the dialect provides, or falls back to Inspector.

**What changes:**
- Constructor accepts optional `DialectStrategy`
- `is_mssql` property removed
- `_list_schemas_mssql()` -> SQL moves to `MssqlDialect.list_schemas_sql()`
- `_list_tables_mssql()` -> SQL moves to `MssqlDialect.list_tables_sql()`
- `_list_schemas_generic()` renamed to `_list_schemas_inspector()`
- `_list_tables_generic()` renamed to `_list_tables_inspector()`
- `_get_row_count_generic()` stays (Tier 2, uses COUNT(*) which is universal)
- `get_columns()`, `get_indexes()`, `get_foreign_keys()` stay unchanged (already Tier 1 via Inspector)

### 3. QueryService (`src/db/query.py`)

**Current state:** Checks `self.engine.dialect.name` repeatedly for SQL generation (TOP vs LIMIT, bracket quoting vs bare identifiers, TABLESAMPLE syntax).

**Changes needed:**
- Constructor accepts optional `DialectStrategy`
- `_build_top_query()` delegates to `dialect.top_n_sql()`
- `_build_tablesample_query()` uses dialect for syntax variation
- `_build_modulo_query()` uses dialect for `ROW_NUMBER()` syntax
- `_sanitize_identifier()` delegates to `dialect.quote_identifier()`
- `inject_row_limit()` delegates to dialect for TOP/LIMIT injection
- `parse_query_type()` uses `dialect.sqlglot_dialect` instead of hardcoded `"tsql"`

**Critical:** The `validate_query()` call in `execute_query()` currently hardcodes `dialect="tsql"` in the validation module. This must pass through `dialect.sqlglot_dialect`.

### 4. Query Validation (`src/db/validation.py`)

**Current state:** Hardcodes `sqlglot.parse(sql, dialect="tsql")` and has MSSQL-specific safe stored procedure lists.

**Changes needed:**
- `validate_query()` accepts optional `dialect: str | None` parameter (the sqlglot dialect name)
- `SAFE_PROCEDURES` should be dialect-aware (SP concepts are MSSQL-specific; Databricks has no stored procedures)
- For non-MSSQL dialects, stored procedure checking can be skipped entirely

**Minimal change:** Add `dialect` parameter defaulting to `"tsql"` for backward compatibility:
```python
def validate_query(sql: str, allow_write: bool = False, dialect: str = "tsql") -> ValidationResult:
    statements = sqlglot.parse(sql, dialect=dialect)
    ...
```

### 5. Config (`src/config.py`)

**Current state:** `ConnectionConfig` has MSSQL-specific fields (server, port, trust_server_cert, authentication_method, tenant_id).

**Recommended: Discriminated union via `dialect` field:**

```python
@dataclass(frozen=True)
class BaseConnectionConfig:
    """Common fields for all connection types."""
    dialect: str = "mssql"  # discriminator

@dataclass(frozen=True)
class MssqlConnectionConfig(BaseConnectionConfig):
    dialect: str = "mssql"
    server: str = ""
    database: str = ""
    port: int = 1433
    authentication_method: str = "sql"
    username: str | None = None
    password: str | None = None
    trust_server_cert: bool = False
    connection_timeout: int = 30
    tenant_id: str | None = None

@dataclass(frozen=True)
class DatabricksConnectionConfig(BaseConnectionConfig):
    dialect: str = "databricks"
    host: str = ""            # Databricks workspace hostname
    http_path: str = ""       # SQL warehouse HTTP path
    catalog: str = "main"     # Unity Catalog catalog name
    schema: str = "default"   # Default schema
    access_token: str | None = None  # PAT or ${ENV_VAR}

@dataclass(frozen=True)
class GenericConnectionConfig(BaseConnectionConfig):
    dialect: str = "generic"
    sqlalchemy_url: str = ""  # Full SQLAlchemy URL
    connect_args: dict | None = None

# Type alias for the union
DialectConnectionConfig = MssqlConnectionConfig | DatabricksConnectionConfig | GenericConnectionConfig
```

**TOML format:**
```toml
[connections.my_mssql]
dialect = "mssql"
server = "myserver"
database = "mydb"
authentication_method = "windows"

[connections.my_databricks]
dialect = "databricks"
host = "adb-1234567890.azuredatabricks.net"
http_path = "/sql/1.0/warehouses/abc123"
catalog = "analytics"
access_token = "${DATABRICKS_TOKEN}"

[connections.my_postgres]
dialect = "generic"
sqlalchemy_url = "postgresql://user:pass@host/db"
```

**Parser change:** `_parse_connections()` reads `dialect` field first, then dispatches to the appropriate config dataclass. Missing `dialect` defaults to `"mssql"` for backward compatibility.

### 6. Analysis Modules (`src/analysis/`)

**Current state:** All three modules (column_stats.py, fk_candidates.py, pk_discovery.py) use raw SQL with MSSQL-specific syntax:
- Bracket quoting: `[{column_name}]`, `[{schema}].[{table}]`
- INFORMATION_SCHEMA queries (actually standard SQL, mostly portable)
- `sys.indexes` / `sys.index_columns` / `sys.tables` / `sys.schemas` (MSSQL-specific, used in fk_candidates.py)
- `DATEDIFF()` (MSSQL-specific, in column_stats.py)
- `LEN()` vs `LENGTH()` (MSSQL vs standard)
- `SELECT TOP N` (MSSQL-specific, in column_stats.py)
- `STRING_SPLIT()` (MSSQL-specific, in fk_candidates.py)

**Recommended approach: sqlglot transpilation for Tier 2 queries**

Rather than rewriting every query, use sqlglot to transpile from a "canonical" dialect to the target:

```python
def transpile_query(sql: str, source_dialect: str = "tsql", target_dialect: str | None = None) -> str:
    if target_dialect is None or source_dialect == target_dialect:
        return sql
    return sqlglot.transpile(sql, read=source_dialect, write=target_dialect)[0]
```

**What this handles automatically:**
- `LEN()` -> `LENGTH()` (most dialects)
- `TOP N` -> `LIMIT N` (most dialects)
- Bracket quoting -> backtick/double-quote quoting
- `DATEDIFF()` -> dialect-appropriate equivalent
- `ISNULL()` -> `COALESCE()` (standard)

**What needs manual handling:**
- `INFORMATION_SCHEMA` queries: Available in MSSQL, Postgres, MySQL. Databricks uses `information_schema` in Unity Catalog (similar structure but different column names in some cases). Can be kept as-is for most dialects.
- `sys.*` DMV queries in fk_candidates.py: These are MSSQL-only. The index check query needs a dialect-specific alternative or must fall back to Inspector.
- `STRING_SPLIT()`: MSSQL-specific. Replace with parameterized IN clause or Inspector-based approach.

**Practical refactoring for analysis modules:**

1. **ColumnStatsCollector**: Accept a `DialectStrategy` for quoting and function adaptation. Write queries in standard SQL, use sqlglot transpilation. The `NUMERIC_TYPES`, `DATETIME_TYPES`, `STRING_TYPES` sets need to be dialect-aware (Databricks uses different type names like `DOUBLE`, `TIMESTAMP`, `STRING`).

2. **FKCandidateSearch**: The `sys.indexes` query in `get_column_metadata()` is the hardest to port. For non-MSSQL, replace with `Inspector.get_indexes()` check. The INFORMATION_SCHEMA queries are mostly portable.

3. **PKDiscovery**: Similar to FKCandidateSearch -- INFORMATION_SCHEMA queries are mostly portable. Databricks Unity Catalog supports `information_schema.table_constraints` so this should work.

**Build order implication:** Analysis module refactoring should come AFTER the core dialect/connection/metadata work is stable.

## Data Flow: Before and After

### Current Flow (MSSQL-only)
```
MCP Tool -> ConnectionManager.get_engine(id) -> Engine
         -> MetadataService(engine) -> Inspector / raw MSSQL SQL
         -> QueryService(engine) -> engine.dialect.name checks
         -> validation.validate_query(sql) -> hardcoded "tsql"
```

### Proposed Flow (Multi-dialect)
```
MCP Tool -> ConnectionManager.get_engine(id) -> Engine
         -> ConnectionManager.get_dialect(id) -> DialectStrategy
         -> MetadataService(engine, dialect) -> dialect.tier3_sql() || Inspector
         -> QueryService(engine, dialect) -> dialect.quote/top_n/etc.
         -> validation.validate_query(sql, dialect=dialect.sqlglot_dialect)
```

### Key change: Dialect flows through the system as a companion to Engine

The `get_metadata_service()` helper in `schema_tools.py` currently creates `MetadataService(engine)`. It will change to:

```python
def _get_metadata_service(connection_id: str) -> MetadataService:
    conn_manager = get_connection_manager()
    engine = conn_manager.get_engine(connection_id)
    dialect = conn_manager.get_dialect(connection_id)
    return MetadataService(engine, dialect)
```

Similarly, QueryService and analysis tool constructors gain a `dialect` parameter.

## Patterns to Follow

### Pattern 1: Tier Fallback Chain
**What:** Every metadata/query operation tries Tier 3 (dialect-specific), then Tier 2 (standard SQL), then Tier 1 (Inspector).
**When:** Any operation that has both fast and slow paths.
**Example:**
```python
def list_schemas(self, connection_id: str = "") -> list[Schema]:
    # Tier 3: Dialect-optimized
    if self._dialect:
        sql = self._dialect.list_schemas_sql()
        if sql is not None:
            return self._run_schema_sql(sql, connection_id)
    # Tier 1: Inspector fallback
    return self._list_schemas_inspector(connection_id)
```

### Pattern 2: Dialect Registry with Auto-Detection
**What:** Map dialect names to strategy classes, with fallback to GenericDialect.
**When:** At connection time, resolving config `dialect` field to implementation.
**Example:**
```python
_DIALECT_REGISTRY: dict[str, type[DialectStrategy]] = {}

def register_dialect(name: str, cls: type[DialectStrategy]) -> None:
    _DIALECT_REGISTRY[name] = cls

def get_dialect_strategy(name: str) -> DialectStrategy:
    cls = _DIALECT_REGISTRY.get(name, GenericDialect)
    return cls()
```

### Pattern 3: Backward-Compatible Defaults
**What:** Every new parameter defaults to MSSQL behavior so existing configs work unchanged.
**When:** config.py parsing, validation.py dialect parameter, ConnectionManager.connect().
**Example:** Config files without `dialect` field default to `"mssql"`. `validate_query()` defaults `dialect="tsql"`.

## Anti-Patterns to Avoid

### Anti-Pattern 1: Dialect Checks in MCP Tools
**What:** Putting `if dialect == "databricks":` in schema_tools.py, analysis_tools.py, etc.
**Why bad:** Scatters dialect knowledge across the codebase. Every new dialect requires changes in multiple tool files.
**Instead:** All dialect-specific behavior lives in `src/db/dialects/*.py`. Tools are dialect-agnostic.

### Anti-Pattern 2: Separate MetadataService Per Dialect
**What:** Creating `MssqlMetadataService`, `DatabricksMetadataService`, etc.
**Why bad:** The existing MetadataService already handles the dual-path pattern well. Most methods (get_columns, get_indexes, get_foreign_keys) use Inspector and are already universal. Creating subclasses would duplicate the shared logic.
**Instead:** Single MetadataService with dialect delegation for the 2-3 methods that need Tier 3 optimization.

### Anti-Pattern 3: Putting Engine Construction Logic in ConnectionManager
**What:** Adding Databricks/generic engine construction as more conditionals in `_create_engine()`.
**Why bad:** ConnectionManager becomes a god class that knows about every database driver.
**Instead:** Each DialectStrategy owns its `create_engine()` method. ConnectionManager just calls it.

### Anti-Pattern 4: Transpiling Everything Through sqlglot
**What:** Writing all queries in one dialect and transpiling to the target.
**Why bad:** sqlglot transpilation is imperfect -- it handles common patterns well but can break on complex DMV queries or dialect-specific features. Over-reliance leads to subtle bugs.
**Instead:** Use transpilation for Tier 2 standard SQL queries. Tier 3 queries are written natively per dialect. Inspector (Tier 1) needs no SQL at all.

## Suggested Build Order

The ordering is designed to minimize MSSQL regression risk by establishing the abstraction layer first, then migrating existing code behind it, then adding new dialects.

### Phase 1: Dialect Protocol + MSSQL Extraction (Foundation)
**Goal:** Introduce the abstraction without changing behavior.

1. Create `src/db/dialect.py` with `DialectStrategy` protocol
2. Create `src/db/dialects/__init__.py` with registry
3. Create `src/db/dialects/mssql.py` -- extract existing MSSQL code from:
   - `ConnectionManager._build_odbc_connection_string()` -> `MssqlDialect.create_engine()`
   - `ConnectionManager._create_engine()` -> `MssqlDialect.create_engine()`
   - `ConnectionManager._test_connection()` SQL -> `MssqlDialect.test_connection_sql()`
   - `MetadataService._list_schemas_mssql()` SQL -> `MssqlDialect.list_schemas_sql()`
   - `MetadataService._list_tables_mssql()` SQL -> `MssqlDialect.list_tables_sql()`
4. Modify `ConnectionManager` to store and provide dialect
5. Modify `MetadataService.__init__()` to accept dialect
6. **All existing tests must pass unchanged** -- this phase is pure refactoring

**Risk:** LOW. Extract-and-delegate refactoring with existing test coverage as safety net.

### Phase 2: Config Discrimination + Validation Dialect
**Goal:** Config supports multiple dialect types; validation uses dialect-aware parsing.

1. Add `dialect` field to `ConnectionConfig` (default: `"mssql"`)
2. Create discriminated config dataclasses (`MssqlConnectionConfig`, etc.)
3. Update `_parse_connections()` to dispatch on `dialect` field
4. Add `dialect` parameter to `validate_query()` (default: `"tsql"`)
5. Wire `dialect.sqlglot_dialect` through `QueryService.execute_query()`

**Risk:** LOW. Backward-compatible defaults mean existing configs work unchanged.

### Phase 3: GenericDialect + QueryService Refactoring
**Goal:** Any SQLAlchemy database works with Inspector-only (Tier 1) metadata.

1. Create `src/db/dialects/generic.py` -- GenericDialect implementation
2. Refactor QueryService to delegate SQL generation to dialect
3. Add `GenericConnectionConfig` with `sqlalchemy_url` field
4. Wire `connect_database` tool to support `sqlalchemy_url` parameter
5. Test with SQLite (already partially supported in current codebase)

**Risk:** MEDIUM. The `connect_database` tool interface changes. Need to ensure backward compatibility.

### Phase 4: DatabricksDialect
**Goal:** Full Databricks support with optimized paths.

1. Create `src/db/dialects/databricks.py`
2. Add `databricks-sql-connector` and `sqlalchemy-databricks` as optional deps
3. Implement Databricks-specific engine construction (HTTP path, token auth, Unity Catalog)
4. Add Databricks Tier 3 optimizations (if any provide meaningful speedup over Inspector)
5. Test Databricks-specific type mappings for analysis modules

**Risk:** MEDIUM. New external dependency; Databricks SQL connector has its own quirks.

### Phase 5: Analysis Module Adaptation
**Goal:** Column stats, PK discovery, FK candidates work across dialects.

1. Add `DialectStrategy` parameter to analysis constructors
2. Replace bracket quoting with `dialect.quote_identifier()`
3. Replace `sys.*` queries with Inspector fallbacks for non-MSSQL
4. Add type category mappings per dialect (NUMERIC_TYPES, etc.)
5. Use sqlglot transpilation for standard SQL queries where appropriate
6. Test analysis tools against Databricks

**Risk:** MEDIUM-HIGH. The analysis modules have the most MSSQL-specific SQL. Need careful testing.

### Phase 6: connect_database Simplification
**Goal:** Simplified tool interface (connection_name or sqlalchemy_url).

1. Simplify `connect_database` tool signature
2. Remove per-field MSSQL params from tool interface (they stay in config)
3. Add `sqlalchemy_url` parameter for ad-hoc generic connections
4. Update tool docstrings

**Risk:** HIGH (breaking change). This is the v2.0 interface change noted in PROJECT.md. Must be the last step.

## Scalability Considerations

| Concern | Current (MSSQL only) | At 3-5 dialects | At 10+ dialects |
|---------|----------------------|------------------|-----------------|
| Code per dialect | N/A | ~150-200 lines per dialect file | Same -- protocol keeps it bounded |
| Test matrix | 682 tests, MSSQL + SQLite | ~800 tests, parameterized per dialect | Parameterized fixtures scale linearly |
| Config complexity | Flat TOML | Discriminated union, still readable | May need config validation tool |
| sqlglot coverage | Good for TSQL | Good for major dialects | Some obscure dialects may need custom parsing |

## Sources

- Direct codebase analysis of all `src/` modules (PRIMARY source, HIGH confidence)
- SQLAlchemy Inspector API documentation (HIGH confidence -- well-established, stable API)
- sqlglot transpilation capabilities (MEDIUM confidence -- version-dependent, known edge cases with complex queries)
- Databricks SQL Connector documentation (MEDIUM confidence -- based on training data, needs verification at implementation time)
