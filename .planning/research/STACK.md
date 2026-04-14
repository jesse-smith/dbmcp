# Technology Stack: v1.1 Concern Handling

**Project:** dbmcp
**Researched:** 2026-03-06
**Scope:** Stack additions/changes for exception handling, token refresh, sqlglot pinning, config format, type handler registry

## Existing Stack (No Changes)

These are validated and working. Listed for reference only.

| Technology | Version (Installed) | Spec Range | Purpose |
|------------|-------------------|------------|---------|
| Python | 3.13.1 | >=3.11 | Runtime |
| FastMCP (mcp[cli]) | >=1.0.0 | >=1.0.0 | MCP server framework |
| SQLAlchemy | 2.0.47 | >=2.0.0 | Connection pooling, metadata introspection |
| pyodbc | 5.3.0 | >=5.0.0 | SQL Server ODBC driver |
| azure-identity | 1.25.2 | >=1.14.0 | Azure AD authentication |
| sqlglot | 29.0.1 | >=26.0.0,<30.0.0 | SQL AST validation |
| toon-format | 0.9.0-beta.1 | git pin | Response serialization |

## Recommended Changes

### 1. Exception Handling -- NO NEW DEPENDENCIES

**Recommendation:** Replace broad `except Exception:` with specific SQLAlchemy and pyodbc exception types. Zero new dependencies required.

**Confidence:** HIGH (verified against installed SQLAlchemy 2.0.47 and pyodbc 5.3.0)

There are 25 `except Exception` blocks across `src/`. The correct replacements group into three categories:

#### Category A: Database Operations (connection, query execution, metadata)

Use `sqlalchemy.exc` types. SQLAlchemy wraps pyodbc errors as DBAPI exceptions, so catching at the SQLAlchemy layer is sufficient when going through `engine.connect()` / `conn.execute()`.

| Exception | When It Fires | Replace In |
|-----------|---------------|------------|
| `sqlalchemy.exc.OperationalError` | Connection failure, timeout, network drop, query timeout | `connection.py`, `query.py`, `metadata.py` |
| `sqlalchemy.exc.ProgrammingError` | Bad SQL syntax, nonexistent table/column, permission denied | `query.py`, `metadata.py` |
| `sqlalchemy.exc.DatabaseError` | Generic DB-level error (superset of above two) | Catch as fallback after specific types |
| `sqlalchemy.exc.InterfaceError` | Driver-level failure (ODBC driver missing, corrupt connection) | `connection.py` |
| `sqlalchemy.exc.TimeoutError` | Pool checkout timeout (all connections busy) | `connection.py` pool operations |
| `sqlalchemy.exc.DisconnectionError` | Stale connection detected by pool_pre_ping | `connection.py` (log and let pool retry) |
| `sqlalchemy.exc.NoSuchTableError` | Table introspection on nonexistent table | `metadata.py` |
| `sqlalchemy.exc.NoInspectionAvailable` | Inspector can't introspect object | `metadata.py` |

#### Category B: Azure Authentication

Already handled specifically in `azure_auth.py` -- uses `CredentialUnavailableError` and `ClientAuthenticationError`. No changes needed there.

#### Category C: MCP Tool Layer (schema_tools.py, query_tools.py, analysis_tools.py)

These 10 `except Exception` blocks are catch-all wrappers that format errors for MCP responses. **Keep these broad but layer them**: catch specific types first for actionable error messages, then catch `Exception` as final fallback for unexpected errors. MCP tools must never raise -- they must always return a response.

**Pattern:**

```python
# In MCP tool handlers:
try:
    ...
except sqlalchemy.exc.OperationalError as e:
    return encode_response({"status": "error", "error": "Connection lost or query timed out", "detail": str(e)})
except sqlalchemy.exc.ProgrammingError as e:
    return encode_response({"status": "error", "error": "SQL error", "detail": str(e)})
except ValueError as e:
    return encode_response({"status": "error", "error": str(e)})
except Exception as e:
    logger.exception(f"Unexpected error in {tool_name}")
    return encode_response({"status": "error", "error": f"Unexpected error: {type(e).__name__}: {e}"})
```

**Why NOT catch pyodbc exceptions directly:** SQLAlchemy wraps all DBAPI exceptions. You only need raw pyodbc catches in the `creator()` function in `_create_engine()` where pyodbc is called directly (Azure AD token connection).

### 2. Azure AD Token Refresh -- NO NEW DEPENDENCIES

**Recommendation:** Use SQLAlchemy `pool_events.checkout` to validate token expiry before each connection use. The `AccessToken.expires_on` field (Unix timestamp) is already available from azure-identity.

**Confidence:** HIGH (verified `AccessToken` is a NamedTuple with `token: str, expires_on: int`; verified SQLAlchemy pool has `checkout` event)

**Current problem:** The `creator()` function in `_create_engine()` calls `provider.get_token()` on every new raw connection, but pooled connections reuse the same pyodbc connection without re-acquiring tokens. Azure AD tokens expire after ~60-90 minutes, so long-running sessions will fail silently.

**Solution architecture:**

```python
# In AzureTokenProvider, cache the token with expiry:
def get_token(self) -> str:
    if self._cached_token and self._expires_on > time.time() + 300:  # 5-min buffer
        return self._cached_token
    access_token = self._credential.get_token(_AZURE_SQL_SCOPE)
    self._cached_token = access_token.token
    self._expires_on = access_token.expires_on
    return self._cached_token

def is_token_expiring_soon(self, buffer_seconds: int = 300) -> bool:
    return self._expires_on <= time.time() + buffer_seconds
```

Then in `ConnectionManager._create_engine()` for Azure AD Integrated:

```python
@event.listens_for(engine, "checkout")
def _check_token_expiry(dbapi_connection, connection_record, connection_proxy):
    if provider.is_token_expiring_soon():
        # Invalidate this pooled connection; pool will create a new one via creator()
        raise sqlalchemy.exc.DisconnectionError("Azure AD token expiring, reconnecting")
```

**Why `checkout` not `connect`:** The `connect` event fires only when a *new* raw connection is created. `checkout` fires every time a connection is borrowed from the pool, which is where we need to validate token freshness.

**Why `DisconnectionError`:** SQLAlchemy's pool treats this as "connection is stale, create a new one" -- exactly the behavior we want. The `creator()` function will be called again, which calls `get_token()`, which acquires a fresh token.

**No new dependencies.** Uses `time` (stdlib), `sqlalchemy.event` (existing), `azure.core.credentials.AccessToken.expires_on` (existing).

### 3. sqlglot Version Pinning -- TIGHTEN EXISTING RANGE

**Recommendation:** Pin to `>=29.0.0,<30.0.0` (tighten from current `>=26.0.0,<30.0.0`).

**Confidence:** MEDIUM (based on observed API surface; sqlglot does not follow semver strictly)

**Rationale:**

- **Current installed:** 29.0.1
- **Current spec:** `>=26.0.0,<30.0.0` -- too wide. The validation module depends on `exp.Execute`, `exp.ExecuteSql`, `exp.Kill`, `exp.IfBlock`, `exp.WhileBlock`, which may not exist in all versions 26-29.
- The codebase has explicit comments: `"Execute/ExecuteSql (sqlglot >=29)"` and `"Command: EXEC/EXECUTE (sqlglot <29)"` -- confirming API breakage between major versions.
- sqlglot releases frequently (multiple minor versions per month) but major versions can rearrange expression types.
- The `_check_command` and `_check_execute` paths handle both old and new sqlglot behavior, but testing should anchor to a known-working major.

**Action:** Change `pyproject.toml` to `sqlglot>=29.0.0,<30.0.0`. Add a test fixture that explicitly verifies all expression types used in `DENIED_TYPES` and the control flow types exist in the installed sqlglot version, so CI catches breakage on upgrade.

### 4. Config File Format -- USE TOML (stdlib)

**Recommendation:** Use TOML via `tomllib` (Python 3.11+ stdlib). No new dependencies.

**Confidence:** HIGH (verified `tomllib` available in Python 3.13.1 runtime)

| Format | Pros | Cons | Verdict |
|--------|------|------|---------|
| **TOML** | Stdlib `tomllib` (read), human-friendly, supports nested tables, standard for Python projects (pyproject.toml) | Write requires `tomli-w` (3rd party) | **Use this** |
| YAML | Human-friendly, widely used | Requires `pyyaml` (new dependency), security footguns with `yaml.load` | No |
| JSON | Stdlib `json`, machine-friendly | No comments, poor human ergonomics | No |
| INI | Stdlib `configparser` | No nested structures, limited types | No |

**Why TOML:** The project constraint is "minimize new dependencies; prefer stdlib solutions." `tomllib` is stdlib since Python 3.11 (the project's minimum). TOML is already the project's config format (pyproject.toml). Config files are read-only at runtime -- no need for `tomli-w`.

**Config file structure (proposed):**

```toml
# dbmcp.toml

[connection.defaults]
port = 1433
trust_server_cert = false
connection_timeout = 30
query_timeout = 30

[pool]
size = 5
max_overflow = 10
timeout = 30
recycle = 3600
pre_ping = true

[validation]
safe_procedures = [
    "sp_help",
    "sp_helptext",
    # ... user can extend the allowlist
]

[serialization]
max_text_length = 1000
max_binary_preview = 32
```

**Reading pattern:**

```python
import tomllib
from pathlib import Path

def load_config(path: Path | None = None) -> dict:
    if path is None:
        path = Path("dbmcp.toml")
    if not path.exists():
        return {}  # All defaults are in code; config is optional
    with open(path, "rb") as f:
        return tomllib.load(f)
```

**No write support needed.** Users create/edit config manually. The server only reads it.

### 5. Type Handler Registry -- NO NEW DEPENDENCIES

**Recommendation:** Implement a registry pattern using a dict mapping `type -> callable` in `src/serialization.py`. No new dependencies.

**Confidence:** HIGH (this is a pure Python pattern)

**Current problem:** `_pre_serialize()` in `serialization.py` and `_truncate_value()` in `query.py` both handle type conversion with hardcoded `isinstance` chains. Adding new types requires editing both functions. SQL Server returns types not currently handled:

| SQL Server Type | Python Type | Current Handling | Needed |
|----------------|-------------|-----------------|--------|
| `uniqueidentifier` | `uuid.UUID` | **TypeError** (crash) | `str(value)` |
| `time` | `datetime.time` | **Missing in serialization.py** (handled only in query.py) | `.isoformat()` |
| `datetimeoffset` | `datetime.datetime` (tz-aware) | Works (datetime handler) | OK |
| `varbinary` | `bytes` | **TypeError** in serialization.py | hex repr |
| `sql_variant` | varies | Depends on actual value | Passthrough or str() |
| `hierarchyid` | `str` | Works | OK |

**Registry pattern:**

```python
from typing import Any, Callable

# Type -> serializer function
_TYPE_HANDLERS: dict[type, Callable[[Any], Any]] = {}

def register_type_handler(type_: type, handler: Callable[[Any], Any]) -> None:
    _TYPE_HANDLERS[type_] = handler

def _pre_serialize(value: Any) -> Any:
    # Primitives first (fast path)
    if value is None or isinstance(value, (bool, int, float, str)) and not isinstance(value, StrEnum):
        return value
    # Check registry before hardcoded handlers
    for type_, handler in _TYPE_HANDLERS.items():
        if isinstance(type_, type) and isinstance(value, type_):
            return handler(value)
    # ... existing hardcoded handlers as fallback ...
    raise TypeError(f"Cannot serialize type {type(value).__name__}")
```

**Default registrations (at module load):**

```python
import uuid
from datetime import date, datetime, time as dt_time
from decimal import Decimal

register_type_handler(StrEnum, lambda v: str(v.value))
register_type_handler(dict, lambda v: {k: _pre_serialize(val) for k, val in v.items()})
register_type_handler(list, lambda v: [_pre_serialize(item) for item in v])
register_type_handler(tuple, lambda v: [_pre_serialize(item) for item in v])
register_type_handler(datetime, lambda v: v.isoformat())
register_type_handler(date, lambda v: v.isoformat())
register_type_handler(dt_time, lambda v: v.isoformat())
register_type_handler(Decimal, lambda v: float(v))
register_type_handler(uuid.UUID, lambda v: str(v))
register_type_handler(bytes, lambda v: f"<binary: {v[:32].hex()}{'...' if len(v) > 32 else ''} ({len(v)} bytes)>")
```

**Why a dict registry, not a Protocol/ABC:** The project constraint says "prefer stdlib solutions" and "current dataclasses work fine." A dict registry is simple, extensible (config file could add custom handlers later), and testable. No need for an abstract interface when there are fewer than 15 types.

**Important:** The registry uses `isinstance` ordering, so subclass relationships matter. `StrEnum` must be checked before `str`, `bool` before `int`. The implementation should either maintain insertion order (dict preserves order in Python 3.7+) or use explicit priority.

## Dependencies Summary

### New Dependencies: NONE

The entire v1.1 concern handling milestone requires **zero new dependencies**. Everything is achievable with:

- `sqlalchemy.exc` (existing) -- specific exception types
- `sqlalchemy.event` (existing) -- pool checkout for token refresh
- `azure.core.credentials.AccessToken.expires_on` (existing) -- token expiry check
- `tomllib` (stdlib since 3.11) -- config file parsing
- `time` (stdlib) -- token expiry comparison
- `uuid` (stdlib) -- UUID serialization handler

### Dependency Changes

| Dependency | Current Spec | Proposed Spec | Reason |
|------------|-------------|---------------|--------|
| sqlglot | `>=26.0.0,<30.0.0` | `>=29.0.0,<30.0.0` | Tighten to known-working major; codebase uses >=29 expression types |

### Explicitly NOT Adding

| Library | Why Considered | Why Rejected |
|---------|---------------|-------------|
| `pyyaml` | Config file format | TOML is stdlib; YAML is not |
| `tomli-w` | TOML writing | Config is read-only at runtime |
| `pydantic` | Config validation | PROJECT.md says "Pydantic migration -- current dataclasses work fine" |
| `tenacity` | Retry logic for token refresh | `DisconnectionError` + pool retry is simpler; one retry mechanism |
| `structlog` | Structured exception logging | Existing `logging` module is sufficient |

## Integration Points

### Exception Types and MCP Tool Layer

The MCP tool handlers (`schema_tools.py`, `query_tools.py`, `analysis_tools.py`) are the boundary between database errors and user-facing responses. They must:
1. Catch specific SQLAlchemy exceptions for actionable messages
2. Keep a final `except Exception` for unexpected errors (MCP tools must never raise)
3. Always return `encode_response(...)` -- never let exceptions propagate to FastMCP

### Token Refresh and Connection Pool

The `checkout` event integrates with SQLAlchemy's existing pool lifecycle. The `creator()` callable already calls `get_token()`, so forcing a reconnect via `DisconnectionError` triggers token reacquisition naturally. No changes to the connection creation path -- only adding an event listener.

### Config File and Existing Defaults

Config must be optional. All current defaults live in code (`PoolConfig` dataclass, `SAFE_PROCEDURES` frozenset, etc.). The config file only overrides. Pattern: `config_value = config.get("key", code_default)`.

### Type Registry and TOON Serialization

The registry replaces the hardcoded `isinstance` chain in `_pre_serialize()`. The `encode_response()` public API does not change. The `_truncate_value()` in `query.py` remains separate (it handles display truncation, not serialization).

## MCP Session Cleanup Note

FastMCP does not expose session lifecycle hooks (no `on_disconnect` or `on_shutdown` callback). For connection cleanup when the MCP session ends, use Python's `atexit` module to call `ConnectionManager.disconnect_all()`. This fires when the process exits (stdio transport = process lifetime = session lifetime).

```python
import atexit
atexit.register(_connection_manager.disconnect_all)
```

## Sources

- SQLAlchemy 2.0 exception hierarchy: verified via `sqlalchemy.exc` introspection on installed 2.0.47
- SQLAlchemy pool events: verified via `sqlalchemy.pool.events.PoolEvents` introspection (checkout, connect, checkin, etc.)
- pyodbc exception hierarchy: verified via runtime inspection of installed 5.3.0
- `azure.core.credentials.AccessToken`: verified as `NamedTuple(token: str, expires_on: int)` via source inspection
- `tomllib` stdlib availability: verified in Python 3.13.1 runtime
- sqlglot expression types: verified `Execute`, `ExecuteSql`, `Kill`, `IfBlock`, `WhileBlock` all present in 29.0.1
- FastMCP lifecycle: verified `run()`, `session_manager` via introspection; no built-in shutdown hook (use `atexit` for cleanup)
