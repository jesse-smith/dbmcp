# Phase 6: Serialization & Configuration - Research

**Researched:** 2026-03-10
**Domain:** Python type handler registry, TOML configuration loading, MCP tool parameter injection
**Confidence:** HIGH

## Summary

Phase 6 addresses two independent concerns: (1) unifying the duplicate type-conversion pipelines (`_truncate_value()` in `query.py` and `_pre_serialize()` in `serialization.py`) into a single type handler registry, and (2) adding optional TOML configuration file support for named connections, default parameters, and SP allowlist extensions.

The type handler registry is a straightforward refactor -- both existing functions handle overlapping types (datetime, date, Decimal) with slightly different behavior. The registry must combine conversion AND truncation into a single pass, returning `(value, was_truncated)` tuples. The key complexity is that `_truncate_value` handles types `_pre_serialize` doesn't (bytes, time, large strings) and `_pre_serialize` handles types `_truncate_value` doesn't (StrEnum, tuple, recursive dict/list). The unified registry must cover the union.

The config system uses Python 3.11+ stdlib `tomllib` (confirmed available in project environment). The main design challenge is the precedence chain: explicit MCP tool args > config file values > hardcoded defaults. This requires the config module to expose defaults that callers can use as sentinel-detected fallbacks rather than hard overrides.

**Primary recommendation:** Implement the type handler registry first (INFRA-01) since it's self-contained, then build the config system (INFRA-02) which touches more integration points (server.py, schema_tools.py, validation.py, connection.py).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Single registry mapping Python types to handler functions -- each handler does BOTH conversion and truncation in one pass
- Every handler returns `(converted_value, was_truncated)` tuple -- callers that don't need truncation tracking ignore the flag
- TypeError raised on unknown types (strict) -- no silent str() fallback
- Registry is internal-only (Python code) -- not extensible via config file
- Replaces both `_truncate_value()` in query.py and `_pre_serialize()` in serialization.py
- Fallback logging for unknown types is not needed since TypeError is raised (strict mode)
- Check project-local `dbmcp.toml` first, then `~/.dbmcp/config.toml` -- local overrides global
- Use Python 3.11+ stdlib `tomllib` -- no new dependency
- Missing config file is normal -- no warning, just no config loaded
- Malformed config file: log warning with parse error, skip entire config, continue with defaults
- New optional `connection_name` parameter on `connect_database` MCP tool
- Other explicitly provided params override config values (tool args > config > hardcoded defaults)
- Env var references for credentials (syntax: Claude's discretion)
- Unresolved env vars produce a clear error at connection time, not at config load time
- `[defaults]` section sets fallback values; named connections inherit and override
- Configurable defaults: query_timeout, text_truncation_limit, sample_size, row_limit
- Pool settings stay hardcoded
- All configurable values validated with min/max bounds
- SP allowlist: additive only, union of hardcoded + config-provided
- SP names validated with identifier pattern
- Schema-qualified names supported
- Hardcoded system SPs remain non-overridable

### Claude's Discretion
- Env var reference syntax choice ($VAR vs ${VAR})
- Exact min/max bounds for each configurable default
- Type handler registry internal structure (dict, class, or module-level functions)
- Config loading architecture (module-level singleton vs passed-through parameter)
- TOML section naming conventions for connections and defaults

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| INFRA-01 | Type handler registry unifies `_truncate_value()` and `_pre_serialize()` into single conversion pipeline with fallback logging for unknown types | Type union analysis below; registry pattern; test mapping for all type handlers |
| INFRA-02 | Optional TOML config file (`~/.dbmcp/config.toml` or `dbmcp.toml`) supporting named connections, default parameters, and SP allowlist extensions | tomllib stdlib confirmed; TOML schema design; precedence chain architecture; env var expansion pattern |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| tomllib | stdlib (3.11+) | Parse TOML config files | Zero-dependency, read-only TOML parser in stdlib |
| os | stdlib | Environment variable expansion | `os.environ.get()` for credential env var references |
| re | stdlib | SP name identifier validation | Already used in project for pattern matching |
| pathlib | stdlib | Config file discovery | Already used throughout project |
| logging | stdlib | Config warning logging | Already used via `src/logging_config.py` |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| dataclasses | stdlib | Config data models | For `AppConfig`, `ConnectionConfig` dataclasses |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| tomllib (read-only) | tomli-w | Only if writing TOML is needed -- it's not |
| dataclass config | pydantic | Overkill for simple validation; adds dependency |
| dict registry | class-based registry | Class adds ceremony without benefit for ~10 handlers |

**Installation:**
```bash
# No new dependencies required -- all stdlib
```

## Architecture Patterns

### Recommended Project Structure
```
src/
├── type_registry.py          # NEW: Unified type handler registry (INFRA-01)
├── config.py                 # NEW: TOML config loading + validation (INFRA-02)
├── serialization.py          # MODIFIED: calls registry instead of _pre_serialize
├── db/
│   ├── query.py              # MODIFIED: calls registry instead of _truncate_value
│   ├── connection.py         # MODIFIED: accepts config-driven defaults
│   └── validation.py         # MODIFIED: merges config SP allowlist
├── mcp_server/
│   ├── server.py             # MODIFIED: loads config at startup
│   └── schema_tools.py       # MODIFIED: connection_name parameter
```

### Pattern 1: Dict-Based Type Handler Registry
**What:** A module-level dict mapping Python types to handler callables, with ordered isinstance checks for subclass correctness.
**When to use:** When the type set is fixed and internal-only.
**Example:**
```python
# src/type_registry.py
from datetime import date, datetime
from datetime import time as dt_time
from decimal import Decimal
from enum import StrEnum
from typing import Any

# Each handler: (value, truncation_limit) -> (converted, was_truncated)
# truncation_limit is passed through for text; ignored by most handlers.

def _handle_none(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return None, False

def _handle_bool(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return value, False

def _handle_int(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return value, False

def _handle_float(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return value, False

def _handle_str(value: Any, trunc_limit: int) -> tuple[str, bool]:
    if len(value) > trunc_limit:
        return value[:trunc_limit] + f"... ({len(value)} chars total)", True
    return value, False

def _handle_bytes(value: Any, trunc_limit: int) -> tuple[str, bool]:
    if len(value) > 32:
        return f"<binary: {value[:32].hex()}... ({len(value)} bytes)>", True
    return f"<binary: {value.hex()} ({len(value)} bytes)>", True

def _handle_datetime(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return value.isoformat(), False

def _handle_date(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return value.isoformat(), False

def _handle_time(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return value.isoformat(), False

def _handle_decimal(value: Any, trunc_limit: int) -> tuple[float, bool]:
    return float(value), False

def _handle_strenum(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return str(value.value), False

def _handle_dict(value: Any, trunc_limit: int) -> tuple[dict, bool]:
    any_truncated = False
    result = {}
    for k, v in value.items():
        converted, was_truncated = convert(v, trunc_limit)
        result[k] = converted
        any_truncated = any_truncated or was_truncated
    return result, any_truncated

def _handle_list(value: Any, trunc_limit: int) -> tuple[list, bool]:
    any_truncated = False
    result = []
    for item in value:
        converted, was_truncated = convert(item, trunc_limit)
        result.append(converted)
        any_truncated = any_truncated or was_truncated
    return result, any_truncated

def _handle_tuple(value: Any, trunc_limit: int) -> tuple[list, bool]:
    return _handle_list(list(value), trunc_limit)

# Ordered check list -- order matters for subclass correctness:
# 1. None check (not isinstance-based)
# 2. bool before int (bool is subclass of int)
# 3. StrEnum before str (StrEnum is subclass of str)
# 4. datetime before date (datetime is subclass of date)
_HANDLER_CHAIN: list[tuple[type | None, callable]] = [
    # None handled specially in convert()
    (bool, _handle_bool),
    (StrEnum, _handle_strenum),   # before str
    (int, _handle_int),           # after bool
    (float, _handle_float),
    (str, _handle_str),           # after StrEnum
    (bytes, _handle_bytes),
    (datetime, _handle_datetime), # before date
    (date, _handle_date),
    (dt_time, _handle_time),
    (Decimal, _handle_decimal),
    (dict, _handle_dict),
    (list, _handle_list),
    (tuple, _handle_tuple),
]

DEFAULT_TRUNCATION_LIMIT = 1000

def convert(value: Any, trunc_limit: int = DEFAULT_TRUNCATION_LIMIT) -> tuple[Any, bool]:
    """Convert a value through the type handler registry.

    Returns (converted_value, was_truncated).
    Raises TypeError for unrecognized types.
    """
    if value is None:
        return None, False

    for type_check, handler in _HANDLER_CHAIN:
        if isinstance(value, type_check):
            return handler(value, trunc_limit)

    raise TypeError(f"Cannot serialize type {type(value).__name__}")
```

### Pattern 2: Config Loading with Graceful Degradation
**What:** A config module that discovers, loads, validates TOML, and exposes a frozen dataclass.
**When to use:** At server startup, before ConnectionManager is created.
**Example:**
```python
# src/config.py
import os
import re
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from src.logging_config import get_logger

logger = get_logger(__name__)

_ENV_VAR_PATTERN = re.compile(r'\$\{([^}]+)\}')

@dataclass(frozen=True)
class DefaultsConfig:
    query_timeout: int = 30
    text_truncation_limit: int = 1000
    sample_size: int = 5
    row_limit: int = 1000

@dataclass(frozen=True)
class ConnectionConfig:
    server: str
    database: str
    port: int = 1433
    authentication_method: str = "sql"
    username: str | None = None
    password: str | None = None
    trust_server_cert: bool = False
    connection_timeout: int = 30
    tenant_id: str | None = None

@dataclass(frozen=True)
class AppConfig:
    defaults: DefaultsConfig = field(default_factory=DefaultsConfig)
    connections: dict[str, ConnectionConfig] = field(default_factory=dict)
    allowed_stored_procedures: frozenset[str] = field(default_factory=frozenset)

def load_config() -> AppConfig:
    """Load config from project-local or user-global TOML file."""
    config_path = _find_config_file()
    if config_path is None:
        return AppConfig()

    try:
        with open(config_path, "rb") as f:
            raw = tomllib.load(f)
    except (tomllib.TOMLDecodeError, OSError) as e:
        logger.warning(f"Config file {config_path} is malformed: {e} -- using defaults")
        return AppConfig()

    return _parse_config(raw)

def resolve_env_vars(value: str) -> str:
    """Resolve ${VAR_NAME} references in a string value."""
    # ...
```

### Pattern 3: Precedence Chain with Sentinel Values
**What:** Use `None` as sentinel in MCP tool args to detect "not explicitly provided" vs. "provided".
**When to use:** When tool args must override config which must override hardcoded defaults.
**Key insight:** Python MCP tools already use `None` defaults for optional params. For params with non-None defaults (like `row_limit=1000`), the tool layer needs to distinguish "user passed 1000" from "user didn't pass anything." The simplest approach: change MCP tool defaults to `None` for configurable params, then apply the precedence chain.
```python
# In schema_tools.py connect_database:
async def connect_database(
    server: str | None = None,       # None = check config
    database: str | None = None,     # None = check config
    connection_name: str | None = None,  # NEW: named connection lookup
    # ... other params with None defaults for configurable ones
) -> str:
    config = get_app_config()

    # If connection_name provided, load base from config
    if connection_name:
        conn_config = config.connections.get(connection_name)
        if not conn_config:
            return encode_response({"status": "error", ...})

    # Precedence: explicit arg > config connection > config defaults > hardcoded
    effective_server = server or (conn_config.server if connection_name else None)
    # ...
```

### Anti-Patterns to Avoid
- **Merging truncation and serialization into one call site only:** Both `encode_response` (serialization path) and `_process_rows` (query path) must use the registry. Don't optimize away the truncation tracking for the serialization path -- keep the uniform API.
- **Validating env vars at config load time:** Per decision, env vars are resolved lazily at connection time. Don't eagerly resolve `${VAR}` during `load_config()`.
- **Making config mutable:** Use frozen dataclass. Config is loaded once at startup. Mutations would create confusing state.
- **Changing `SAFE_PROCEDURES` from frozenset to set:** The hardcoded set must remain immutable. Create a new merged set for runtime use.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML parsing | Custom parser | `tomllib` (stdlib 3.11+) | Standard, well-tested, read-only |
| Env var expansion | String replace hacks | `re.sub` with `os.environ.get` | Handles missing vars, nested refs |
| Identifier validation for SP names | Ad-hoc string checks | `re.match(r'^[a-zA-Z_][\w.]*$')` | Same pattern used elsewhere in project |
| Config file discovery | Recursive search | Two fixed paths: `./dbmcp.toml`, `~/.dbmcp/config.toml` | Per decision, no search needed |

**Key insight:** The TOML config is intentionally simple -- two fixed locations, one-time load, frozen result. Don't over-engineer discovery or hot-reloading.

## Common Pitfalls

### Pitfall 1: isinstance Order for Subclasses
**What goes wrong:** `bool` is a subclass of `int`; `datetime` is a subclass of `date`; `StrEnum` is a subclass of `str`. If checked in wrong order, values get wrong handlers.
**Why it happens:** Natural alphabetical or "simple first" ordering puts parent before child.
**How to avoid:** The handler chain MUST check: bool before int, StrEnum before str, datetime before date. Document the ordering requirement in the registry code.
**Warning signs:** Tests pass for direct types but fail for subclass types (e.g., `True` serializes as `1`).

### Pitfall 2: Breaking _pre_serialize Callers That Don't Need Truncation
**What goes wrong:** `encode_response()` currently calls `_pre_serialize()` which has no truncation concept. After unification, the registry always returns `(value, was_truncated)`. If `encode_response` doesn't adapt, it passes tuples to TOON encoder.
**Why it happens:** Forgetting to update the call site in `serialization.py`.
**How to avoid:** `encode_response` must call the registry and discard the `was_truncated` flag. Create a thin wrapper like `serialize(value)` that returns only the converted value.
**Warning signs:** TOON encoding errors with tuple values, or `encode_response` tests failing.

### Pitfall 3: Config Precedence for `connection_name` + Explicit Params
**What goes wrong:** Named connection loads `server=X` from config, but user also passes `server=Y` explicitly. If precedence isn't clean, config silently wins.
**Why it happens:** Using `or` chaining where the first truthy value wins, but `0` or `False` are falsy yet valid.
**How to avoid:** Use `None` as the sentinel for "not provided." Apply precedence: `if explicit_arg is not None: use it; elif config has it: use config; else: hardcoded default`.
**Warning signs:** User passes `port=0` or `trust_server_cert=False` but config value is used instead.

### Pitfall 4: Circular Import Between config.py and server.py
**What goes wrong:** If `config.py` imports from `server.py` (e.g., for logging), and `server.py` imports from `config.py` (for config loading), circular import occurs.
**Why it happens:** server.py is the central module that many things import from.
**How to avoid:** `config.py` should only import from `logging_config.py` (not `server.py`). Config is loaded in `server.py` and passed to `ConnectionManager` / stored as module-level state.
**Warning signs:** `ImportError` at startup, or `AttributeError` on partially-initialized modules.

### Pitfall 5: TOML Type Coercion Surprises
**What goes wrong:** TOML has native types (int, bool, string). A port written as `port = "1433"` is a string, not int. `trust_server_cert = "true"` is string, not bool.
**Why it happens:** Config file authors may quote values unnecessarily.
**How to avoid:** Validate types strictly during `_parse_config()`. Log a warning with the exact field and expected type. Don't silently coerce.
**Warning signs:** `TypeError` deep in connection logic when string appears where int is expected.

### Pitfall 6: SP Allowlist Injection via Config
**What goes wrong:** A malicious config adds `"; DROP TABLE--"` as an SP name.
**Why it happens:** No validation of SP names from config.
**How to avoid:** Validate each SP name against identifier pattern `^[a-zA-Z_][\w.]*$` before merging. Reject and warn on invalid names.
**Warning signs:** SQL injection through SP allowlist config values.

## Code Examples

### Current Type Overlap Analysis (verified from source)

| Type | `_pre_serialize()` | `_truncate_value()` | Unified Registry |
|------|-------------------|---------------------|------------------|
| None | passthrough | return (None, False) | (None, False) |
| bool | passthrough | fall-through (return as-is) | (value, False) |
| int | passthrough | fall-through | (value, False) |
| float | passthrough | fall-through | (value, False) |
| str | passthrough | truncate if >1000 chars | truncate if >limit, (value, was_truncated) |
| bytes | NOT HANDLED | hex preview + truncate | (hex_repr, True) |
| datetime | .isoformat() | .isoformat() | (.isoformat(), False) |
| date | .isoformat() | .isoformat() | (.isoformat(), False) |
| time | NOT HANDLED | .isoformat() | (.isoformat(), False) |
| Decimal | float() | float() | (float(value), False) |
| StrEnum | str(value.value) | NOT HANDLED | (str(value.value), False) |
| dict | recurse values | NOT HANDLED | recurse with convert() |
| list | recurse items | NOT HANDLED | recurse with convert() |
| tuple | convert to list, recurse | NOT HANDLED | convert to list, recurse |
| Unknown | TypeError | return as-is | TypeError |

**Key difference:** `_truncate_value` returns unknown types as-is (permissive); `_pre_serialize` raises TypeError (strict). The unified registry uses strict mode per decision.

### TOML Config Schema Design
```toml
# ~/.dbmcp/config.toml or ./dbmcp.toml

[defaults]
query_timeout = 30           # 5-300, default 30
text_truncation_limit = 1000 # 100-10000, default 1000
sample_size = 5              # 1-1000, default 5
row_limit = 1000             # 1-10000, default 1000

[connections.production]
server = "sql-prod.example.com"
database = "AppDB"
port = 1433
authentication_method = "azure_ad_integrated"
tenant_id = "${AZURE_TENANT_ID}"
trust_server_cert = false

[connections.dev]
server = "localhost"
database = "DevDB"
authentication_method = "sql"
username = "sa"
password = "${DB_PASSWORD}"

[stored_procedures]
allow = [
    "dbo.my_custom_report",
    "reporting.get_monthly_stats",
]
```

### Env Var Syntax Recommendation: `${VAR_NAME}`
**Rationale:** `${VAR_NAME}` is the more explicit syntax. `$VAR` alone is ambiguous in TOML because `$` has no special meaning -- a bare `$VAR` could be a literal string. The `${...}` delimiters make the intent explicit and are the common convention in Docker Compose, shell scripts, and config files. It's also easier to parse with a regex (`\$\{([^}]+)\}`).

### Validation Bounds Recommendation

| Parameter | Min | Max | Default | Rationale |
|-----------|-----|-----|---------|-----------|
| query_timeout | 5 | 300 | 30 | Matches existing `_validate_connect_params` in connection.py |
| text_truncation_limit | 100 | 10000 | 1000 | <100 is useless; >10000 risks token bloat |
| sample_size | 1 | 1000 | 5 | Matches existing validation in query_tools.py |
| row_limit | 1 | 10000 | 1000 | Hard cap at 10000 per MCP tool contract |

### Config Loading Architecture Recommendation: Module-Level Singleton
**Rationale:** Config is loaded once at startup and never changes. A module-level `_config` variable in `config.py` with a `get_config() -> AppConfig` accessor follows the same pattern as `server.py`'s `_connection_manager` singleton. The `load_config()` function is called once in `server.py:main()` (or at module level), and `get_config()` returns the cached result. This avoids threading config through every function signature.

```python
# src/config.py
_config: AppConfig | None = None

def init_config() -> AppConfig:
    """Load config and store as module singleton. Call once at startup."""
    global _config
    _config = load_config()
    return _config

def get_config() -> AppConfig:
    """Get the loaded config. Returns empty defaults if init_config not called."""
    if _config is None:
        return AppConfig()
    return _config
```

### Registry Internal Structure Recommendation: Module-Level Handler Chain
**Rationale:** A dict keyed by type doesn't work here because isinstance ordering matters (subclass checks). An ordered list of `(type, handler)` tuples is the simplest correct structure. A class would add unnecessary ceremony for what is essentially a lookup table with ~13 entries.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `configparser` (INI) | `tomllib` (TOML) | Python 3.11 (Oct 2022) | Native TOML support, no dependency needed |
| `json` for config | TOML for config | Industry trend ~2020+ | Comments, better readability, typed values |
| Separate serialize/truncate | Unified type registry | This phase | Eliminates duplicate type handling |

**Deprecated/outdated:**
- `toml` (PyPI package): Superseded by stdlib `tomllib` for reading. Only needed if writing TOML.

## Open Questions

1. **How should `encode_response` interact with the registry's truncation?**
   - What we know: `encode_response` currently has no truncation. After unification, it calls the same registry that truncates.
   - What's unclear: Should serialization-only callers get a different truncation limit (e.g., no truncation)?
   - Recommendation: Pass `trunc_limit=float('inf')` (effectively no truncation) from `encode_response`, and the configurable limit from `_process_rows`. The registry API handles both cases.

2. **Should `connection_name` be the only required param when provided?**
   - What we know: Named connections load all params from config. Server and database could come from config.
   - What's unclear: If `connection_name` is provided, are `server`/`database` still required MCP params?
   - Recommendation: When `connection_name` is provided, `server` and `database` become optional. The config must supply them. Validation happens after merging.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ with pytest-asyncio 0.21+ |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-01a | Registry handles all current `_pre_serialize` types | unit | `uv run pytest tests/unit/test_type_registry.py -x` | No - Wave 0 |
| INFRA-01b | Registry handles all current `_truncate_value` types | unit | `uv run pytest tests/unit/test_type_registry.py -x` | No - Wave 0 |
| INFRA-01c | Subclass ordering correct (bool/int, datetime/date, StrEnum/str) | unit | `uv run pytest tests/unit/test_type_registry.py::test_subclass_ordering -x` | No - Wave 0 |
| INFRA-01d | Unknown types raise TypeError | unit | `uv run pytest tests/unit/test_type_registry.py::test_unknown_type_raises -x` | No - Wave 0 |
| INFRA-01e | encode_response still works after refactor | unit | `uv run pytest tests/unit/test_serialization.py -x` | Yes |
| INFRA-01f | _process_rows uses registry with truncation tracking | unit | `uv run pytest tests/unit/test_query.py -x` | Yes |
| INFRA-02a | Config loaded from project-local dbmcp.toml | unit | `uv run pytest tests/unit/test_config.py::test_local_config -x` | No - Wave 0 |
| INFRA-02b | Config loaded from ~/.dbmcp/config.toml | unit | `uv run pytest tests/unit/test_config.py::test_global_config -x` | No - Wave 0 |
| INFRA-02c | Local config takes precedence over global | unit | `uv run pytest tests/unit/test_config.py::test_local_overrides_global -x` | No - Wave 0 |
| INFRA-02d | Missing config returns defaults | unit | `uv run pytest tests/unit/test_config.py::test_missing_config -x` | No - Wave 0 |
| INFRA-02e | Malformed config logs warning, returns defaults | unit | `uv run pytest tests/unit/test_config.py::test_malformed_config -x` | No - Wave 0 |
| INFRA-02f | Named connection loads from config | unit | `uv run pytest tests/unit/test_config.py::test_named_connection -x` | No - Wave 0 |
| INFRA-02g | Env var ${VAR} resolved at connection time | unit | `uv run pytest tests/unit/test_config.py::test_env_var_resolution -x` | No - Wave 0 |
| INFRA-02h | Unresolved env var produces clear error | unit | `uv run pytest tests/unit/test_config.py::test_unresolved_env_var -x` | No - Wave 0 |
| INFRA-02i | Defaults section validates bounds | unit | `uv run pytest tests/unit/test_config.py::test_bounds_validation -x` | No - Wave 0 |
| INFRA-02j | SP allowlist additive merge | unit | `uv run pytest tests/unit/test_config.py::test_sp_allowlist_merge -x` | No - Wave 0 |
| INFRA-02k | SP names validated against identifier pattern | unit | `uv run pytest tests/unit/test_config.py::test_sp_name_validation -x` | No - Wave 0 |
| INFRA-02l | Hardcoded SPs non-overridable | unit | `uv run pytest tests/unit/test_config.py::test_hardcoded_sp_preserved -x` | No - Wave 0 |
| INFRA-02m | Precedence: tool args > config > defaults | unit | `uv run pytest tests/unit/test_config.py::test_precedence -x` | No - Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_type_registry.py` -- covers INFRA-01a through INFRA-01d
- [ ] `tests/unit/test_config.py` -- covers INFRA-02a through INFRA-02m
- [ ] No new framework install needed -- pytest already configured

## Sources

### Primary (HIGH confidence)
- Source code: `src/serialization.py` (70 lines) -- full `_pre_serialize` implementation
- Source code: `src/db/query.py:340-380` -- full `_truncate_value` implementation
- Source code: `src/db/validation.py` -- `SAFE_PROCEDURES` frozenset, SP name handling
- Source code: `src/db/connection.py` -- `PoolConfig` dataclass, `connect()` param validation
- Source code: `src/mcp_server/server.py` -- server startup, singleton pattern
- Source code: `src/mcp_server/schema_tools.py` -- `connect_database` MCP tool interface
- Source code: `src/mcp_server/query_tools.py` -- `execute_query` and `get_sample_data` defaults
- Python docs: `tomllib` -- stdlib TOML parser, read-only, returns dict

### Secondary (MEDIUM confidence)
- TOML spec: `${VAR}` is not a TOML-native feature; it's an application-level convention (Docker Compose, etc.)

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all stdlib, confirmed available in project Python 3.13.1
- Architecture: HIGH -- patterns derived directly from existing codebase conventions
- Pitfalls: HIGH -- derived from actual source code analysis of type handling overlap

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable domain, no external dependencies changing)
