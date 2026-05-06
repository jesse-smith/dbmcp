# Phase 10: GenericDialect & Tool Interface - Research

**Researched:** 2026-04-14
**Domain:** SQLAlchemy multi-dialect engine creation, optional dependency packaging, MCP tool interface refactoring
**Confidence:** HIGH

## Summary

This phase introduces three interconnected changes: (1) a GenericDialect class implementing the DialectStrategy protocol for any SQLAlchemy-supported database, (2) a simplified connect_database MCP tool accepting only `connection_name` or `sqlalchemy_url`, and (3) restructuring pyproject.toml to move pyodbc/azure-identity into optional extras while keeping core install driver-free.

The existing codebase is well-structured for this work. The DialectStrategy protocol (8 members), dialect registry, and config discrimination (MssqlConnectionConfig/DatabricksConnectionConfig/GenericConnectionConfig) are already in place from Phases 8-9. The primary implementation effort is: writing GenericDialect, refactoring ConnectionManager.connect() to accept a dialect+config pair instead of MSSQL-specific kwargs, rewriting the connect_database tool function, and restructuring pyproject.toml dependencies.

**Primary recommendation:** Implement bottom-up: GenericDialect class first (simplest, no refactoring), then ConnectionManager.connect() generalization, then connect_database tool rewrite, then pyproject.toml dependency restructuring. The Connection model in schema.py needs dialect-neutral fields.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** connect_database tool signature becomes two params only: `connection_name: str | None` and `sqlalchemy_url: str | None`. All MSSQL-specific params removed immediately -- clean break for v2.0, no deprecation period.
- **D-02:** When `sqlalchemy_url` is passed directly, dialect is auto-detected from URL scheme. A mapping dict handles known schemes.
- **D-03:** When `connection_name` is passed, the TOML config's `dialect` field determines the dialect (existing Phase 9 behavior).
- **D-04:** GenericDialect uses URL-scheme-to-sqlglot-dialect mapping. Unknown schemes pass `dialect=None` to sqlglot.
- **D-05:** GenericDialect uses ANSI double-quote identifier quoting (`"identifier"`). No engine-dependent quoting detection.
- **D-06:** GenericDialect capability flags: `supports_indexes=True`, `has_fast_row_counts=False`.
- **D-07:** GenericDialect.safe_procedures returns `frozenset()` (empty).
- **D-08:** GenericDialect.create_engine accepts the sqlalchemy_url and passes it to `sqlalchemy.create_engine()` with reasonable defaults.
- **D-09:** TOML config path: unknown dialect names raise ValueError (fail-fast). GenericDialect only activates for explicit `dialect = "generic"`.
- **D-10:** URL path: auto-detect from URL scheme. Unknown schemes route to GenericDialect with a warning log.
- **D-11:** Core install: mcp[cli], sqlalchemy, sqlglot, toon-format only. pyodbc + azure-identity to `[mssql]` extra. Databricks to `[databricks]` extra.
- **D-12:** Add `[all]` convenience extra combining mssql + databricks + examples.
- **D-13:** Missing dialect dependencies surface at connection time via lazy import with clear error messages. No registry-time checks.

### Claude's Discretion
- **D-14:** Internal URL-scheme-to-dialect mapping structure and placement.
- **D-15:** GenericDialect's create_engine pool configuration and engine kwargs defaults.
- **D-16:** connect_database tool internal routing logic between connection_name vs sqlalchemy_url paths.

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIAL-04 | GenericDialect accepts any SQLAlchemy URL and uses Inspector-only metadata with COUNT(*) fallback for row counts | GenericDialect implementation with `has_fast_row_counts=False`, `fast_row_counts()` returning empty dict, `create_engine()` delegating to `sqlalchemy.create_engine()` |
| CONF-03 | connect_database tool accepts connection_name or sqlalchemy_url (clean break) | Tool signature rewrite, new routing logic in schema_tools.py, ConnectionManager.connect() generalization |
| CONF-04 | pyodbc and azure-identity move to `mssql` optional extra; databricks packages to `databricks` extra | pyproject.toml `[project.optional-dependencies]` restructuring |
| CONF-05 | Dialect-specific dependencies use lazy imports with clear error messages when missing | Lazy import pattern in MssqlDialect (and later DatabricksDialect) with try/except ImportError |
</phase_requirements>

## Standard Stack

### Core (already installed, no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlalchemy | >=2.0.0 | Engine creation, URL parsing via `make_url()` | Already in use; `make_url()` provides `get_backend_name()` for scheme detection |
| sqlglot | >=30.4.2,<31.0.0 | Query validation with dialect-specific parsing | Already in use; accepts `dialect=None` for generic SQL |
| mcp[cli] | >=1.27.0 | MCP tool registration | Already in use |
| toon-format | v0.9.0-beta.1 | Response encoding | Already in use |

### No New Dependencies
This phase adds zero new runtime dependencies. It restructures existing ones into optional extras.

## Architecture Patterns

### URL-Scheme-to-Dialect Mapping

SQLAlchemy's `make_url(url).get_backend_name()` returns the backend portion of the URL scheme. Verified mappings: [VERIFIED: local Python REPL]

| URL Example | `get_backend_name()` | Target Dialect | sqlglot dialect |
|-------------|---------------------|----------------|-----------------|
| `mssql+pyodbc://...` | `mssql` | MssqlDialect | `tsql` |
| `databricks://...` | `databricks` | DatabricksDialect | `databricks` |
| `postgresql://...` | `postgresql` | GenericDialect | `postgres` |
| `postgresql+psycopg2://...` | `postgresql` | GenericDialect | `postgres` |
| `mysql+pymysql://...` | `mysql` | GenericDialect | `mysql` |
| `sqlite:///...` | `sqlite` | GenericDialect | `sqlite` |
| `oracle+cx_oracle://...` | `oracle` | GenericDialect | `None` (generic) |

**Critical finding:** sqlglot uses `postgres` (not `postgresql`), while SQLAlchemy returns `postgresql` from `get_backend_name()`. The mapping must handle this translation. [VERIFIED: local Python REPL -- `sqlglot.parse('SELECT 1', dialect='postgresql')` raises error, `dialect='postgres'` works]

### Recommended Mapping Structure (D-14 discretion)

```python
# URL scheme (from get_backend_name()) -> registered dialect name
_URL_SCHEME_TO_DIALECT: dict[str, str] = {
    "mssql": "mssql",
    "databricks": "databricks",
    # All others fall through to GenericDialect
}

# URL scheme -> sqlglot dialect name (for GenericDialect)
_URL_SCHEME_TO_SQLGLOT: dict[str, str] = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
    # Unknown schemes -> None (generic SQL)
}
```

Place in `src/db/dialects/registry.py` alongside the existing registry functions. The scheme-to-dialect mapping is registry-level concern. The scheme-to-sqlglot mapping belongs in GenericDialect since only it needs it.

### GenericDialect Implementation

```python
# Source: project DialectStrategy protocol + verified sqlglot/SQLAlchemy behavior
class GenericDialect:
    def __init__(self, sqlglot_dialect_name: str | None = None):
        self._sqlglot_dialect = sqlglot_dialect_name

    @property
    def name(self) -> str:
        return "generic"

    @property
    def sqlglot_dialect(self) -> str:
        # Protocol returns str, but sqlglot accepts None for generic parsing
        # Return empty string "" for None case; validate_query handles "" -> None
        return self._sqlglot_dialect or ""

    @property
    def supports_indexes(self) -> bool:
        return True  # D-06

    @property
    def has_fast_row_counts(self) -> bool:
        return False  # D-06

    @property
    def safe_procedures(self) -> frozenset[str]:
        return frozenset()  # D-07

    def quote_identifier(self, identifier: str) -> str:
        return f'"{identifier}"'  # D-05: ANSI double-quote

    def create_engine(self, **kwargs) -> Engine:
        url = kwargs["sqlalchemy_url"]
        return sa_create_engine(url, pool_pre_ping=True, echo=False)

    def fast_row_counts(self, engine, schema_name=None) -> dict[str, int]:
        return {}  # No fast path; callers use COUNT(*) fallback
```

**Design note on sqlglot_dialect return type:** The protocol defines `sqlglot_dialect -> str`, but GenericDialect may need `None` for unknown schemes. Two options: (1) return `""` and have validation layer convert empty string to `None`, or (2) change protocol to `str | None`. Option 2 is cleaner but touches the protocol. Recommend option 2 since it's a one-line change and more honest. [ASSUMED -- Claude's discretion per D-14]

### ConnectionManager Refactoring

Current `ConnectionManager.connect()` takes 10 MSSQL-specific kwargs. It needs a new method or refactored signature:

```python
def connect_with_url(
    self,
    sqlalchemy_url: str,
    dialect: DialectStrategy,
    query_timeout: int = 30,
) -> Connection:
    """Connect using a SQLAlchemy URL with the given dialect."""

def connect_with_config(
    self,
    config: ConnectionConfig,
    dialect: DialectStrategy,
    query_timeout: int = 30,
) -> Connection:
    """Connect using a typed config with the given dialect."""
```

The existing `connect()` method can be preserved internally for backward compatibility during refactoring, but the tool layer will call the new methods.

### Connection Model Generalization

The `Connection` dataclass in `schema.py` has MSSQL-specific fields (`server`, `database`, `port`, `authentication_method`). For generic connections, some of these are meaningless. Options:

1. **Make fields optional with defaults** -- `server` becomes `str = ""`, `port` becomes `int = 0`, etc.
2. **Replace with generic fields** -- `connection_label: str` (human-readable summary) instead of individual MSSQL fields.
3. **Keep fields, populate from URL parsing** -- SQLAlchemy's `make_url()` provides host/database/port.

Recommend option 3: populate from `make_url()` for URL connections. The fields are useful for display regardless of dialect. `authentication_method` could default to a generic value or be made Optional. [ASSUMED]

### connect_database Tool Routing Logic (D-16 discretion)

```
connect_database(connection_name=None, sqlalchemy_url=None):
    if both provided: error
    if neither provided: error

    if connection_name:
        config = lookup from AppConfig
        dialect_cls = get_dialect(config.dialect)
        dialect = instantiate(dialect_cls, config)
        engine_kwargs from config

    if sqlalchemy_url:
        backend = make_url(url).get_backend_name()
        if backend in _URL_SCHEME_TO_DIALECT:
            dialect_cls = get_dialect(_URL_SCHEME_TO_DIALECT[backend])
        else:
            sqlglot_name = _URL_SCHEME_TO_SQLGLOT.get(backend)
            dialect = GenericDialect(sqlglot_dialect_name=sqlglot_name)
            if sqlglot_name is None:
                logger.warning(f"No optimized dialect for '{backend}' -- using generic fallback.")

    # Route to ConnectionManager with dialect + url/config
```

### Lazy Import Pattern for CONF-05

MssqlDialect currently has top-level `import pyodbc` and `from src.db.dialects.azure_auth import ...`. These must become lazy:

```python
class MssqlDialect:
    def create_engine(self, **kwargs) -> Engine:
        try:
            import pyodbc  # noqa: F811
        except ImportError:
            raise ImportError(
                "MSSQL support requires pyodbc. Install with: pip install dbmcp[mssql]"
            ) from None
        # ... rest of engine creation
```

The azure_auth module import also needs lazy handling since it imports `azure.identity`.

### pyproject.toml Restructuring

```toml
[project]
dependencies = [
    "mcp[cli]>=1.27.0",
    "sqlalchemy>=2.0.0",
    "sqlglot>=30.4.2,<31.0.0",
    "toon-format @ git+https://github.com/toon-format/toon-python.git@v0.9.0-beta.1",
]

[project.optional-dependencies]
mssql = [
    "pyodbc>=5.0.0",
    "azure-identity>=1.14.0",
]
databricks = [
    # Phase 11 will populate; placeholder for now
    # "databricks-sqlalchemy>=...",
    # "databricks-sql-connector>=...",
]
examples = [
    "jupyter>=1.0.0",
    "notebook>=7.0.0",
]
all = [
    "dbmcp[mssql]",
    "dbmcp[databricks]",
    "dbmcp[examples]",
]
```

**Self-referencing extras:** The `all` extra uses `dbmcp[mssql]` syntax which is valid in PEP 508 and supported by pip/uv. [VERIFIED: PEP 508 spec, common pattern in major packages like `httpx[http2]`]

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| URL scheme parsing | Regex on URL strings | `sqlalchemy.engine.url.make_url()` | Handles `+driver` suffixes, edge cases, query params correctly |
| Engine creation for generic DBs | Custom connection string builders | `sqlalchemy.create_engine(url)` | SQLAlchemy handles driver loading, connection args, pooling |
| Dependency availability checks | `importlib.util.find_spec()` | `try: import X except ImportError` | Simpler, standard Python pattern, catches broken installs too |

## Common Pitfalls

### Pitfall 1: sqlglot dialect naming mismatch
**What goes wrong:** Passing `"postgresql"` (from SQLAlchemy) to sqlglot causes an error; it expects `"postgres"`.
**Why it happens:** Different projects use different names for the same database.
**How to avoid:** Explicit mapping dict from SQLAlchemy backend names to sqlglot dialect names. Verified: sqlglot uses `postgres`, `mysql`, `sqlite`, `tsql`, `databricks`. [VERIFIED: local REPL]
**Warning signs:** Query validation failures on otherwise valid SQL.

### Pitfall 2: Top-level imports breaking core install
**What goes wrong:** `from src.db.dialects.mssql import MssqlDialect` at module init (in `__init__.py`) triggers `import pyodbc` which fails on core-only install.
**Why it happens:** MssqlDialect currently has `import pyodbc` at module level. The `__init__.py` imports it and registers it.
**How to avoid:** Two options: (1) lazy import inside MssqlDialect methods, OR (2) deferred registration that doesn't import the class until needed. Recommend option 1 (lazy imports inside create_engine) since registration just stores the class reference -- the import only fires when `create_engine` is called. However, `__init__.py` currently does `from src.db.dialects.mssql import MssqlDialect` which WILL trigger the module-level pyodbc import. Must change to lazy registration or conditional import.
**Warning signs:** ImportError on `import src.db.dialects` in core-only environment.

### Pitfall 3: Connection model MSSQL assumptions
**What goes wrong:** The `Connection` dataclass has required `server: str` and `database: str` fields. Generic URL connections may not have distinct server/database values (e.g., SQLite).
**Why it happens:** Model was designed for MSSQL-only usage.
**How to avoid:** Extract host/database from `make_url()` for URL connections. SQLite can use `server=""` and `database=<path>`. The `authentication_method` field needs a generic default.
**Warning signs:** Test failures when creating Connection objects for non-MSSQL connections.

### Pitfall 4: _test_connection uses SQL Server-specific query
**What goes wrong:** `ConnectionManager._test_connection()` runs `SELECT @@VERSION AS version, DB_NAME() AS database_name` which is MSSQL-specific.
**Why it happens:** Hardcoded probe query.
**How to avoid:** Make test query dialect-aware, or use a universal probe like `SELECT 1`. The version/database info is nice-to-have for logging but not essential for connection validation.
**Warning signs:** Connection test fails for PostgreSQL/MySQL/SQLite despite valid credentials.

### Pitfall 5: Self-referencing extras with uv
**What goes wrong:** Some older package managers don't resolve self-referencing extras (`dbmcp[mssql]` inside `dbmcp`'s own `[all]` extra).
**Why it happens:** PEP 508 allows it but not all resolvers handle it.
**How to avoid:** Test with `uv pip install -e ".[all]"`. uv handles self-refs correctly. [ASSUMED -- verify during implementation]
**Warning signs:** Resolution errors when installing `[all]` extra.

## Code Examples

### SQLAlchemy URL Parsing (verified)
```python
# Source: verified in local REPL
from sqlalchemy.engine.url import make_url

url = make_url("postgresql+psycopg2://user:pass@host:5432/mydb")
url.get_backend_name()  # "postgresql"
url.host                # "host"
url.port                # 5432
url.database            # "mydb"
url.drivername          # "postgresql+psycopg2"
```

### Lazy Import Pattern
```python
# Source: standard Python pattern
class MssqlDialect:
    def create_engine(self, **kwargs) -> Engine:
        try:
            import pyodbc
        except ImportError:
            raise ImportError(
                "MSSQL support requires pyodbc. Install with: pip install dbmcp[mssql]"
            ) from None
        # ... proceed with pyodbc
```

### Generic Engine Creation (D-15 discretion)
```python
# Source: SQLAlchemy docs pattern
from sqlalchemy import create_engine as sa_create_engine

def create_engine(self, **kwargs) -> Engine:
    url = kwargs["sqlalchemy_url"]
    return sa_create_engine(
        url,
        pool_pre_ping=True,     # Validate stale connections
        pool_size=5,            # Reasonable default
        max_overflow=10,        # Match MSSQL defaults
        pool_recycle=3600,      # Recycle hourly
        echo=False,             # No SQL logging
    )
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.x + pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIAL-04 | GenericDialect implements all 8 protocol members | unit | `uv run pytest tests/unit/test_generic_dialect.py -x` | Wave 0 |
| DIAL-04 | GenericDialect.create_engine creates engine from URL | unit | `uv run pytest tests/unit/test_generic_dialect.py::test_create_engine -x` | Wave 0 |
| DIAL-04 | GenericDialect.fast_row_counts returns empty dict | unit | `uv run pytest tests/unit/test_generic_dialect.py::test_fast_row_counts_empty -x` | Wave 0 |
| CONF-03 | connect_database accepts connection_name only | unit | `uv run pytest tests/unit/test_connect_tool.py::test_connection_name_path -x` | Wave 0 |
| CONF-03 | connect_database accepts sqlalchemy_url only | unit | `uv run pytest tests/unit/test_connect_tool.py::test_url_path -x` | Wave 0 |
| CONF-03 | connect_database rejects both params | unit | `uv run pytest tests/unit/test_connect_tool.py::test_both_params_error -x` | Wave 0 |
| CONF-03 | connect_database rejects neither param | unit | `uv run pytest tests/unit/test_connect_tool.py::test_no_params_error -x` | Wave 0 |
| CONF-04 | Core install works without pyodbc | unit | `uv run pytest tests/unit/test_optional_deps.py::test_core_import -x` | Wave 0 |
| CONF-05 | MssqlDialect.create_engine raises clear ImportError when pyodbc missing | unit | `uv run pytest tests/unit/test_optional_deps.py::test_mssql_import_error -x` | Wave 0 |
| CONF-05 | URL auto-detection routes known schemes to correct dialect | unit | `uv run pytest tests/unit/test_url_routing.py -x` | Wave 0 |
| CONF-05 | Unknown URL scheme routes to GenericDialect with warning | unit | `uv run pytest tests/unit/test_url_routing.py::test_unknown_scheme_warning -x` | Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v --tb=short`
- **Phase gate:** Full suite green + `uv run ruff check src/` clean

### Wave 0 Gaps
- [ ] `tests/unit/test_generic_dialect.py` -- GenericDialect protocol compliance, property values, create_engine, fast_row_counts
- [ ] `tests/unit/test_connect_tool.py` -- New connect_database routing (replaces MSSQL-specific tests for the tool signature)
- [ ] `tests/unit/test_optional_deps.py` -- Lazy import behavior, clear error messages
- [ ] `tests/unit/test_url_routing.py` -- URL scheme to dialect mapping, sqlglot dialect mapping

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Connection model can be generalized by populating fields from make_url() for URL connections | Architecture Patterns | Connection objects for generic DBs may have empty/misleading fields; downstream code that relies on server/database may break |
| A2 | Self-referencing extras (`dbmcp[mssql]` in `[all]`) work with uv | Pitfall 5 | `[all]` extra may not install correctly; easy to fix by inlining dependencies |
| A3 | Protocol change `sqlglot_dialect -> str | None` is preferable to empty-string workaround | Architecture Patterns | Minimal risk; one-line protocol change, affects downstream dialect implementations |

## Open Questions

1. **Connection model generalization strategy**
   - What we know: Connection has MSSQL-specific required fields (server, database, port, authentication_method)
   - What's unclear: Whether to make fields optional, add a display_name field, or keep and populate from URL parsing
   - Recommendation: Populate from `make_url()` -- most backwards compatible, provides useful info for all dialects

2. **azure_auth module lazy loading**
   - What we know: `src/db/dialects/azure_auth.py` is imported at module level in mssql.py; it imports `azure.identity`
   - What's unclear: Whether azure_auth has module-level side effects that make lazy loading tricky
   - Recommendation: Move the azure_auth import inside the create_engine method alongside pyodbc

3. **Existing test suite impact**
   - What we know: 607 tests exist, many test the current connect_database signature
   - What's unclear: How many tests directly test the MSSQL-specific params of connect_database
   - Recommendation: Run test suite early, identify failures from signature change, update affected tests

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | Credentials handled by SQLAlchemy URL -- no custom auth logic |
| V5 Input Validation | yes | `make_url()` validates URL structure; sqlglot validates queries |
| V6 Cryptography | no | No custom crypto; SSL handled by database drivers |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Credential leakage in URL logging | Information Disclosure | Never log raw sqlalchemy_url; redact credentials before logging |
| SQL injection via URL params | Tampering | URL is passed to create_engine only, not to query execution; query validation is separate |

**NFR-005 compliance:** The `sqlalchemy_url` parameter may contain embedded credentials. Must ensure it is never logged, stored in Connection model, or returned in error messages. Use `make_url(url).render_as_string(hide_password=True)` for safe logging. [VERIFIED: SQLAlchemy API -- `render_as_string(hide_password=True)` replaces password with `***`]

## Sources

### Primary (HIGH confidence)
- SQLAlchemy `make_url()` behavior -- verified in local Python REPL with multiple URL schemes
- sqlglot dialect names (`postgres`, `mysql`, `sqlite`, `tsql`) -- verified in local Python REPL
- Existing codebase: `src/db/dialects/protocol.py`, `registry.py`, `mssql.py`, `__init__.py`, `config.py`, `connection.py`, `schema_tools.py`

### Secondary (MEDIUM confidence)
- PEP 508 self-referencing extras syntax -- common pattern, widely used [ASSUMED]
- pyproject.toml optional-dependencies structure -- standard setuptools/PEP 621 [CITED: https://packaging.python.org/en/latest/guides/writing-pyproject-toml/]

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, verified existing APIs
- Architecture: HIGH -- clear patterns from existing MssqlDialect reference implementation
- Pitfalls: HIGH -- verified key gotchas (sqlglot naming, top-level imports) in local REPL

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable domain, no fast-moving dependencies)
