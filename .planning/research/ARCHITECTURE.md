# Architecture Patterns

**Domain:** MCP server concern-handling improvements (v1.1)
**Researched:** 2026-03-06
**Confidence:** HIGH (based on direct codebase analysis)

## Current Architecture Overview

```
Entry Point: src/mcp_server/server.py
  - Creates FastMCP instance, singleton ConnectionManager
  - Imports tool modules (schema_tools, query_tools, analysis_tools)
  - Tool modules register via @mcp.tool() decorators

Request Flow:
  MCP Client -> FastMCP (stdio) -> @mcp.tool() handler (async)
    -> asyncio.to_thread(_sync_work)
      -> ConnectionManager.get_engine(connection_id)
      -> Service layer (MetadataService / QueryService / ColumnStatsCollector / etc.)
        -> SQLAlchemy Engine -> pyodbc -> SQL Server
    -> encode_response(result_dict) -> TOON string -> MCP Client

Exception Flow (current):
  Service layer raises -> _sync_work propagates -> to_thread propagates
    -> tool handler catches (ValueError | Exception) -> encode_response({status: "error"})
```

### Component Map

| Component | File | Responsibility | Dependencies |
|-----------|------|----------------|--------------|
| Server bootstrap | `server.py` | FastMCP, singleton CM, tool registration | ConnectionManager, logging_config |
| Schema tools | `schema_tools.py` | connect, list_schemas, list_tables, get_table_schema | server.py (mcp, CM, logger), MetadataService |
| Query tools | `query_tools.py` | get_sample_data, execute_query | server.py (mcp, CM, logger), QueryService |
| Analysis tools | `analysis_tools.py` | get_column_info, find_pk_candidates, find_fk_candidates | server.py (mcp, CM), ColumnStatsCollector, PKDiscovery, FKCandidateSearch |
| Connection mgmt | `connection.py` | Engine creation, pooling, connect/disconnect | AzureTokenProvider, SQLAlchemy, pyodbc |
| Query execution | `query.py` | Query running, row limit injection, value truncation | validation.py, sqlglot, SQLAlchemy |
| Query validation | `validation.py` | AST denylist, SP allowlist | sqlglot |
| Metadata | `metadata.py` | Schema/table/column/index introspection | SQLAlchemy inspector, DMVs |
| Serialization | `serialization.py` | Pre-serialize Python types, encode to TOON | toon_format |
| Azure auth | `azure_auth.py` | Token acquisition and packing | azure-identity |
| Metrics (dead) | `metrics.py` | Performance tracking (unused) | stdlib only |

## Concern Integration Analysis

### 1. Removing metrics.py -- Clean Delete

**Impact assessment:** NONE. No hidden imports or side effects.

Evidence:
- `grep` for `from src.metrics` and `import.*metrics` found only the self-reference in `metrics.py` line 7 (docstring usage example)
- No `__init__.py` re-exports metrics
- No other source file imports it
- No test file imports it (it has its own tests but those can be deleted too)
- No entry point references it
- It is a standalone singleton with no side effects on import

**Integration point:** Delete `src/metrics.py` and any corresponding test file. No other files change.

**Files to modify:** 1 deleted (`src/metrics.py`), plus test cleanup
**Files affected:** 0

### 2. Exception Handling -- 25 Broad `except Exception` Blocks

**Current exception flow** (three distinct patterns):

**Pattern A: MCP tool handlers (9 occurrences in schema_tools, query_tools, analysis_tools)**
```python
try:
    result = await asyncio.to_thread(_sync_work)
    return encode_response(result)
except ValueError as e:
    return encode_response({"status": "error", ...})
except Exception as e:          # <-- BROAD
    logger.exception("Error in ...")
    return encode_response({"status": "error", ...})
```
These are the outermost boundary. The broad `except Exception` here is actually *partially justified* -- it is the last line of defense preventing unhandled errors from crashing the MCP server. However, it should be narrowed to catch known database/connection errors specifically, with `Exception` retained only as a true last-resort fallback.

**Recommended replacement:**
```python
except ValueError as e:
    return encode_response(...)
except (ConnectionError, sqlalchemy.exc.OperationalError, sqlalchemy.exc.DatabaseError) as e:
    return encode_response(...)  # known DB errors
except Exception as e:
    logger.exception("Unexpected error in ...")  # keep as safety net, but now it's the THIRD handler
    return encode_response(...)
```

**Pattern B: Service layer methods (metadata.py ~10 occurrences, query.py ~3, connection.py ~1)**
```python
except Exception:           # swallows all errors silently
    return []  # or return False, or pass
```
These are the *most dangerous*. They hide real errors (permission denied, network timeout, OOM) behind empty results. The user gets no feedback that something went wrong.

**Recommended replacement (varies by call site):**
- `metadata.py` inspector calls: Catch `sqlalchemy.exc.NoSuchTableError`, `sqlalchemy.exc.OperationalError`, `sqlalchemy.exc.ProgrammingError`. Log warning. Return empty collection.
- `query.py` count query: Catch `sqlalchemy.exc.OperationalError`. Silently return None (this is truly best-effort).
- `connection.py` connect: Already correctly catches `ConnectionError` first, but the fallback `except Exception` should narrow to `(sqlalchemy.exc.OperationalError, pyodbc.Error)`.

**Pattern C: Query execution error capture (query.py `_run_query`)**
```python
except Exception as e:
    error_message = f"Query execution failed: {type(e).__name__}: {str(e)}"
```
This one captures the error message to return to the user. It needs to catch `sqlalchemy.exc.OperationalError` (timeout), `sqlalchemy.exc.ProgrammingError` (syntax), `pyodbc.Error` specifically. Keep a final `Exception` catch but log it as unexpected.

**Integration points:**
- Changes are spread across 6 files but are self-contained per file
- No cross-module interface changes -- each file's catch blocks are internal
- The exception *types* to catch come from sqlalchemy and pyodbc (already dependencies)

**Build order consideration:** Do this BEFORE connection lifecycle changes, since you need to understand which exceptions propagate to handle Azure AD token refresh correctly.

### 3. Connection Lifecycle -- Azure AD Token Refresh and Session Cleanup

**Current state of Azure AD token flow:**

```
ConnectionManager.connect()
  -> _create_engine(authentication_method=AZURE_AD_INTEGRATED)
    -> Creates AzureTokenProvider(tenant_id)
    -> Defines creator() closure that calls provider.get_token() on EVERY new raw connection
    -> create_engine("mssql+pyodbc://", creator=creator, ...)
```

**Key insight:** The `creator` closure is called by SQLAlchemy's QueuePool whenever it needs a *new physical connection*. The token is fetched fresh each time. However, there is a critical gap:

**Problem 1: Token expiry on pooled connections.** Azure AD tokens are typically valid for 60-90 minutes. A pooled connection that was created with a valid token and then sits idle will have a valid *pyodbc connection* but the underlying token is expired. The next query on that connection will fail with an auth error from SQL Server. `pool_pre_ping=True` (currently enabled) will detect the dead connection and discard it, triggering `creator()` again with a fresh token. **This partially mitigates the issue** but has a race window and generates noisy errors.

**Problem 2: No proactive refresh.** The `pool_recycle=3600` (1 hour) recycles connections by age, which roughly aligns with token lifetime. But there is no coordination between token TTL and pool recycle. If a token has 5 minutes left and a connection is checked out, it may fail mid-query.

**Recommended approach:**
- Add token expiry tracking to `AzureTokenProvider` (the `azure.core.credentials.AccessToken` returned by `get_token()` includes an `expires_on` field)
- Set `pool_recycle` to be shorter than token lifetime (e.g., 45 minutes vs 60-minute token)
- Add a pool event listener (`checkout`) that checks token expiry and invalidates stale connections proactively
- This stays entirely within `connection.py` and `azure_auth.py` -- no interface changes

**Problem 3: No session cleanup.** The MCP server has no lifecycle hook for when a client disconnects. `ConnectionManager.disconnect_all()` exists but is never called. The `FastMCP` class does not expose a shutdown hook in the current API.

**Recommended approach:**
- Register an `atexit` handler in `server.py` that calls `_connection_manager.disconnect_all()`
- Check if FastMCP supports a `shutdown` or `on_close` callback (needs verification against current mcp SDK version)
- This is a 5-line change in `server.py`

**Integration points:**
- `azure_auth.py`: Add `expires_on` tracking to `get_token()`, add `is_token_fresh()` method
- `connection.py`: Add pool checkout event listener for Azure AD engines, adjust `pool_recycle`
- `server.py`: Add atexit handler
- No changes to tool modules or serialization

### 4. Identifier Sanitization -- Metadata Validation in Query Pipeline

**Current sanitization in `query.py`:**
```python
def _sanitize_identifier(self, identifier: str) -> str:
    if not re.match(r'^[a-zA-Z0-9_\s]+$', identifier):
        raise ValueError(f"Invalid identifier: {identifier}")
    return f"[{identifier}]"  # brackets for SQL Server
```

**Where it is called:** Only in `get_sample_data()` for user-supplied column names. Table names and schema names are passed directly into f-strings with brackets: `f"[{schema_name}].[{table_name}]"` -- this is bracket-quoting but without regex validation.

**The concern:** The current regex allows any alphanumeric + underscore + space but does NOT validate that the identifier actually exists in the database. A crafted identifier like `]; DROP TABLE Students; --` would be caught by the regex, but `valid_looking_column` that does not exist would generate a SQL error at runtime rather than a clear validation error.

**Where metadata validation should fit:**

```
Current:  MCP tool handler -> QueryService.get_sample_data(columns=[...])
                                -> _sanitize_identifier(col)  # regex only
                                -> builds SQL string

Proposed: MCP tool handler -> QueryService.get_sample_data(columns=[...])
                                -> _validate_identifiers(columns, table_name, schema_name)
                                   -> MetadataService.get_columns(table, schema)
                                   -> compare requested columns against actual columns
                                   -> raise ValueError for unknown columns
                                -> _sanitize_identifier(col)  # regex (belt-and-suspenders)
                                -> builds SQL string
```

**Integration challenge:** `QueryService` currently takes only an `Engine` in its constructor. It does not have access to `MetadataService`. Options:

**Option A (recommended): Pass metadata service to QueryService.**
Change `QueryService.__init__(self, engine, metadata_service=None)`. When metadata_service is provided, use it for identifier validation. This preserves backward compatibility.

**Option B: Validate in the tool handler layer.**
The tool handlers already have access to both services. Move validation to `query_tools.py` and `schema_tools.py` before calling into QueryService. This avoids changing QueryService's interface but scatters validation logic.

**Option A is better** because it keeps validation close to the SQL building code, following defense-in-depth.

**Also needed:** Apply the same regex validation to `schema_name` and `table_name` parameters in `get_sample_data()` and throughout `metadata.py` methods that accept user-supplied identifiers. Currently these are passed raw into bracket-quoted SQL.

**Integration points:**
- `query.py`: Add MetadataService as optional dependency, add identifier validation
- `query_tools.py` and `schema_tools.py`: Pass MetadataService when constructing QueryService
- `metadata.py`: Add a lightweight `validate_identifier()` or `column_exists()` method

### 5. Type Handler Registry -- Serialization Chain

**Current serialization chain:**

```
Tool handler builds result dict (may contain datetime, Decimal, StrEnum, bytes, etc.)
  |
  v
Two separate type-handling paths:
  Path 1: query.py _truncate_value() handles bytes, datetime, date, time, Decimal
           (converts to str/float BEFORE putting into result dict)
  Path 2: serialization.py _pre_serialize() handles datetime, date, Decimal, StrEnum
           (converts AFTER result dict is built, during TOON encoding)

  Both paths handle overlapping types with slightly different behavior:
    - query.py converts Decimal -> float, datetime -> isoformat string
    - serialization.py converts Decimal -> float, datetime -> isoformat string
    (same behavior, but duplicated logic)

  query.py additionally handles: bytes -> hex preview string, time -> isoformat
  serialization.py additionally handles: StrEnum -> str value, tuple -> list

  Neither handles: uuid.UUID (used in query_id generation but stored as string already)
```

**The concern from PROJECT.md:** "Add type handler registry for query result serialization"

**Where the registry plugs in:**

The type handler registry should replace the ad-hoc isinstance chains in BOTH `query.py._truncate_value()` and `serialization.py._pre_serialize()` with a single registry that maps `type -> handler_function`.

**Recommended design:**

```python
# New file: src/type_handlers.py (or add to serialization.py)

class TypeHandlerRegistry:
    """Registry mapping Python types to serialization handlers."""

    def __init__(self):
        self._handlers: dict[type, Callable[[Any], Any]] = {}

    def register(self, python_type: type, handler: Callable[[Any], Any]):
        self._handlers[python_type] = handler

    def convert(self, value: Any) -> tuple[Any, bool]:
        """Convert value using registered handler. Returns (converted, was_converted)."""
        for type_, handler in self._handlers.items():
            if isinstance(value, type_):
                return handler(value), True
        return value, False

# Default registry with all known types
DEFAULT_REGISTRY = TypeHandlerRegistry()
DEFAULT_REGISTRY.register(bytes, lambda v: f"<binary: {v[:32].hex()}{'...' if len(v) > 32 else ''} ({len(v)} bytes)>")
DEFAULT_REGISTRY.register(datetime, lambda v: v.isoformat())
DEFAULT_REGISTRY.register(date, lambda v: v.isoformat())
DEFAULT_REGISTRY.register(Decimal, lambda v: float(v))
DEFAULT_REGISTRY.register(StrEnum, lambda v: str(v.value))
# etc.
```

**Integration:**
- `serialization.py._pre_serialize()` delegates to registry for non-primitive types
- `query.py._truncate_value()` delegates to registry, then applies truncation rules on top
- Truncation (bytes preview, long string trim) remains in `query.py` as it is query-context-specific, not a type conversion concern

**Key distinction:** The registry handles *type conversion* (Decimal -> float). Truncation (1000-char limit, binary preview) is a separate concern that stays in QueryService.

**Integration points:**
- New: `src/type_handlers.py` (or extend `serialization.py`)
- Modified: `serialization.py` to use registry
- Modified: `query.py._truncate_value()` to use registry for type conversion, keep truncation logic

### 6. Config File Loading -- Server Startup

**Current state:** All configuration is hardcoded or passed as function arguments:
- `PoolConfig` defaults in `connection.py`
- Log file path hardcoded as `"dbmcp.log"` in `server.py`
- SP allowlist hardcoded as `SAFE_PROCEDURES` frozenset in `validation.py`
- No connection presets

**Where config loading fits in the startup sequence:**

```
Current startup:
  server.py module load:
    1. setup_logging(log_file="dbmcp.log")
    2. FastMCP("dbmcp")
    3. ConnectionManager()  (with default PoolConfig)
    4. Import tool modules
  main():
    5. mcp.run(transport="stdio")

Proposed startup:
  server.py module load:
    1. load_config()  # <-- NEW: reads dbmcp.toml or similar
    2. setup_logging(log_file=config.log_file)  # from config
    3. FastMCP("dbmcp")
    4. ConnectionManager(pool_config=config.pool_config)  # from config
    5. Import tool modules (which read config.safe_procedures, config.validation)
  main():
    6. mcp.run(transport="stdio")
```

**Config file format recommendation:** TOML (Python 3.11+ has `tomllib` in stdlib, zero new dependencies).

**Recommended config structure:**
```toml
[server]
log_file = "dbmcp.log"
log_level = "INFO"

[pool]
pool_size = 5
max_overflow = 10
pool_timeout = 30
pool_recycle = 3600
query_timeout = 30

[validation]
# Additional safe stored procedures beyond the built-in 22
safe_procedures = ["my_custom_sp", "another_safe_sp"]

[connections.mydb]
server = "myserver.example.com"
database = "mydb"
authentication_method = "windows"
trust_server_cert = true
```

**Config file discovery order:**
1. `--config` CLI argument (if added)
2. `./dbmcp.toml` (project-local)
3. `~/.config/dbmcp/config.toml` (user-level)
4. Built-in defaults (current behavior, always works)

**Integration points:**
- New: `src/config.py` -- loads and validates TOML config, returns typed config object
- Modified: `server.py` -- calls `load_config()` at top, passes config to components
- Modified: `connection.py` -- accepts PoolConfig from config (already does this via constructor)
- Modified: `validation.py` -- `SAFE_PROCEDURES` becomes configurable: built-in set UNION config additions
- The connect_database tool could optionally accept a connection preset name

## Recommended Architecture Changes

### New Components

| Component | File | Purpose |
|-----------|------|---------|
| Config loader | `src/config.py` | TOML config loading, validation, defaults |
| Type handler registry | `src/type_handlers.py` | Centralized type conversion registry |

### Modified Components

| Component | Change Type | Scope |
|-----------|------------|-------|
| `server.py` | Config integration, atexit handler | Small (5-10 lines) |
| `connection.py` | Azure AD token lifecycle, pool events | Medium (30-50 lines) |
| `azure_auth.py` | Token expiry tracking | Small (10-15 lines) |
| `query.py` | MetadataService integration, type registry, exception narrowing | Medium (20-30 lines) |
| `validation.py` | Configurable SP allowlist, no broad exceptions here currently | Small (5-10 lines) |
| `metadata.py` | Exception narrowing across ~10 catch blocks | Medium (scattered but mechanical) |
| `serialization.py` | Delegate to type registry | Small (10 lines) |
| `schema_tools.py` | Exception narrowing | Small (mechanical) |
| `query_tools.py` | Exception narrowing, pass MetadataService | Small |
| `analysis_tools.py` | Exception narrowing | Small (mechanical) |

### Removed Components

| Component | File | Reason |
|-----------|------|--------|
| Dead metrics | `src/metrics.py` | Zero imports, zero usage |

## Data Flow Changes

### Before (query execution path):
```
Tool handler -> QueryService(engine) -> _sanitize_identifier (regex) -> SQL string -> execute
```

### After (query execution path):
```
Tool handler -> QueryService(engine, metadata_svc) -> _validate_identifiers (DB lookup) -> _sanitize_identifier (regex) -> SQL string -> execute
```

### Before (serialization):
```
query.py: _truncate_value (isinstance chain) -> result dict
serialization.py: _pre_serialize (isinstance chain) -> TOON
```

### After (serialization):
```
type_handlers.py: TypeHandlerRegistry (centralized)
query.py: registry.convert(value) + truncation logic -> result dict
serialization.py: registry.convert(value) -> TOON
```

## Suggested Build Order

Based on dependency analysis and risk:

| Order | Concern | Rationale |
|-------|---------|-----------|
| 1 | Remove metrics.py | Zero risk, zero dependencies, immediate cleanup |
| 2 | Exception handling narrowing | Foundation for all other changes -- you need to understand error paths before modifying connection lifecycle or adding new components |
| 3 | Type handler registry | Self-contained, tests can verify parity with existing behavior |
| 4 | Config file support | Foundation for connection presets and SP allowlist customization |
| 5 | Identifier sanitization | Requires MetadataService wiring into QueryService (moderate coupling change) |
| 6 | Connection lifecycle (Azure AD + cleanup) | Highest risk, most complex, benefits from exception handling being clean first |

**Rationale for this order:**
- Items 1-2 are pure cleanup with no new features -- they reduce noise and clarify the codebase
- Item 3 is additive and testable in isolation
- Item 4 provides infrastructure that items 5-6 can optionally consume
- Item 5 introduces cross-service coupling (QueryService -> MetadataService) which is easier to reason about after exceptions are clean
- Item 6 is the riskiest change (connection pooling behavior, token lifecycle, async pool events) and benefits from a clean foundation

## Anti-Patterns to Avoid

### Anti-Pattern 1: Catching Exception Where You Mean OperationalError
**What:** Using `except Exception` as shorthand for "database errors"
**Why bad:** Swallows TypeError, KeyError, AttributeError -- real bugs become silent empty results
**Instead:** Catch `(sqlalchemy.exc.OperationalError, sqlalchemy.exc.ProgrammingError, pyodbc.Error)` for database errors. Keep `Exception` only at the outermost MCP tool boundary.

### Anti-Pattern 2: Duplicating Type Conversion Logic
**What:** Both query.py and serialization.py have isinstance chains for the same types
**Why bad:** Divergent behavior (one handles `time`, the other handles `StrEnum`), maintenance burden
**Instead:** Single TypeHandlerRegistry used by both paths

### Anti-Pattern 3: Validating Identifiers After Building SQL
**What:** Current code brackets identifiers then hopes they are valid
**Why bad:** Invalid identifiers produce SQL errors that are hard to distinguish from other failures
**Instead:** Validate against metadata BEFORE building SQL, fail with clear ValueError

### Anti-Pattern 4: Config via Code Changes
**What:** Modifying `SAFE_PROCEDURES` frozenset or `PoolConfig` defaults requires code changes
**Why bad:** Operators cannot customize without forking
**Instead:** TOML config file with sane defaults, config augments (not replaces) built-in values

## Scalability Considerations

Not applicable for this milestone -- these are internal quality improvements, not scaling changes. The connection pool configuration becoming configurable (via config file) does enable future scaling tuning without code changes.

## Sources

- Direct codebase analysis (all findings are HIGH confidence)
- SQLAlchemy 2.0 pool event documentation (for checkout listener pattern)
- Python 3.11 tomllib documentation (for config file loading)
- azure-identity AccessToken.expires_on field (for token lifecycle tracking)
