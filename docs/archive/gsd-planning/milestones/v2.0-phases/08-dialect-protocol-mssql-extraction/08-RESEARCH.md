# Phase 8: Dialect Protocol & MSSQL Extraction - Research

**Researched:** 2026-04-13
**Domain:** Python typing.Protocol, Strategy pattern, refactoring extraction
**Confidence:** HIGH

## Summary

Phase 8 introduces the first abstract pattern in the codebase: a `typing.Protocol`-based DialectStrategy that encapsulates all dialect-specific behavior, then extracts the existing SQL Server code into an `MssqlDialect` implementation. The codebase currently has MSSQL-specific code scattered across 6 files (`connection.py`, `metadata.py`, `query.py`, `validation.py`, `azure_auth.py`, `config.py`) plus 3 analysis modules that use bracket quoting and DMV queries.

The critical constraint is **zero behavior regression** -- all 680 existing tests must pass unchanged after extraction. This means the refactoring must be purely structural: moving code behind a protocol interface while keeping all call sites producing identical results. No new features, no new dialects, no interface changes visible to MCP tool consumers.

**Primary recommendation:** Define `DialectStrategy` as a `typing.Protocol` in `src/db/dialects/protocol.py`, implement `MssqlDialect` in `src/db/dialects/mssql.py` (moving `azure_auth.py` alongside), create a module-level dict registry in `src/db/dialects/registry.py`, and wire the dialect into `ConnectionManager` and `MetadataService` via constructor injection -- all behind the existing public API so callers are unaware of the change.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Use `typing.Protocol` (structural subtyping) for DialectStrategy. No ABC. This is the first abstract pattern in the codebase -- Protocol fits the existing dataclass-oriented, lightweight style.
- **D-02:** Capability flags are bool properties on the protocol (e.g., `supports_indexes: bool`, `has_fast_row_counts: bool`). Not an enum set.
- **D-03:** Protocol methods match ROADMAP spec: `name`, `sqlglot_dialect`, `create_engine`, `fast_row_counts`, `quote_identifier`, plus capability flag properties. No additions at this stage.
- **D-04:** `azure_auth.py` moves into the dialect package, co-located with MssqlDialect code.
- **D-05:** Simple dict registry mapping dialect name strings to DialectStrategy classes. Module-level dict with `register_dialect()` and `get_dialect()` functions.
- **D-06:** Unknown dialect names raise an error in Phase 8. GenericDialect fallback will be added in Phase 10. Fail-fast over silent misconfiguration.

### Claude's Discretion
- **D-07:** How optional features signal "not supported" (return None vs guard with capability flag)
- **D-08:** How ConnectionManager splits with dialect (dialect owns engine creation vs ConnectionManager delegates to dialect)
- **D-09:** How DMV queries survive extraction (move to MssqlDialect vs stay in MetadataService behind dialect checks)
- **D-10:** Module layout within `src/db/dialects/` -- subpackage (`mssql/`) vs flat files
- **D-11:** Whether dialect files live at `src/db/dialects/` (under db package, recommended) or `src/dialects/` (top-level)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| DIAL-01 | DialectStrategy protocol with name, sqlglot_dialect, create_engine, fast_row_counts, quote_identifier, and capability flags | Protocol design pattern in Architecture Patterns; code example in Code Examples section |
| DIAL-02 | MssqlDialect extracts all existing MSSQL-specific code (ODBC strings, Azure AD, DMV queries) behind the protocol | MSSQL-specific code inventory in Architecture Patterns; extraction boundary analysis |
| DIAL-05 | Dialect registry maps dialect names to strategy implementations with fallback path | Registry pattern in Architecture Patterns; fail-fast in Phase 8 per D-06 |
| META-05 | Dialect-appropriate identifier quoting in all generated SQL (brackets/backticks/double-quotes) | quote_identifier method on protocol; current bracket usage inventory in Common Pitfalls |
| TEST-01 | All existing MSSQL tests pass unchanged (zero behavior regression) | Zero-regression strategy in Common Pitfalls; test infrastructure in Validation Architecture |
</phase_requirements>

## Project Constraints (from CLAUDE.md)

- **Always use `uv run`** for pytest, ruff, python invocations
- **Python 3.11+** target
- **Ruff** for linting (rules: E, W, F, I, B, C4, UP)
- **Dataclasses** for data models (not Pydantic)
- **Google-style docstrings** with Args/Returns/Raises
- **Absolute imports** from `src.*`
- 120 char line length
- No `from module import *`

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| typing (stdlib) | Python 3.11+ | `Protocol` for structural subtyping | Built-in, no dependency; runtime_checkable available [VERIFIED: Python 3.11 stdlib] |
| sqlalchemy | >=2.0.0 | Engine creation, Inspector, connection pooling | Already in project dependencies [VERIFIED: pyproject.toml] |
| pyodbc | >=5.0.0 | MSSQL ODBC connectivity | Already in project dependencies [VERIFIED: pyproject.toml] |
| azure-identity | >=1.14.0 | Azure AD token auth | Already in project dependencies [VERIFIED: pyproject.toml] |
| sqlglot | >=30.4.2,<31.0.0 | Query parsing with dialect parameter | Already in project dependencies [VERIFIED: pyproject.toml] |

### Supporting
No new dependencies required for Phase 8. This is a pure refactoring phase.

## Architecture Patterns

### Recommended Project Structure
```
src/db/dialects/
    __init__.py          # Exports: DialectStrategy, MssqlDialect, register_dialect, get_dialect
    protocol.py          # DialectStrategy Protocol definition
    registry.py          # Dict registry + register/get functions
    mssql.py             # MssqlDialect implementation
    azure_auth.py        # Moved from src/db/azure_auth.py (D-04)
```

**Rationale for flat files (D-10):** The MSSQL-specific code that needs extraction fits comfortably in two files (`mssql.py` ~200-300 lines, `azure_auth.py` ~90 lines). A `mssql/` subpackage adds import depth for no benefit. Future dialects (Generic, Databricks) will each be a single file too. [ASSUMED]

**Rationale for `src/db/dialects/` (D-11):** Dialects are part of the database layer, not a cross-cutting concern. All consumers are in `src/db/`. Placing under `src/db/` maintains the existing layered architecture. [VERIFIED: ARCHITECTURE.md service layer organization]

### Pattern 1: DialectStrategy Protocol (D-01, D-02, D-03)

**What:** A `typing.Protocol` defining the contract all dialects must satisfy.
**When to use:** Any code that currently branches on `dialect_name == "mssql"` or `self.is_mssql`.

```python
# Source: typing.Protocol docs + project conventions
from typing import Protocol, runtime_checkable
from sqlalchemy.engine import Engine

@runtime_checkable
class DialectStrategy(Protocol):
    """Abstract protocol for database dialect-specific behavior.

    Implementations encapsulate all dialect-specific logic: engine creation,
    identifier quoting, fast metadata queries, and capability advertisement.
    """

    @property
    def name(self) -> str:
        """Dialect identifier string (e.g., 'mssql', 'databricks', 'generic')."""
        ...

    @property
    def sqlglot_dialect(self) -> str:
        """Sqlglot dialect name for query parsing (e.g., 'tsql', 'databricks')."""
        ...

    @property
    def supports_indexes(self) -> bool:
        """Whether this dialect supports traditional index metadata."""
        ...

    @property
    def has_fast_row_counts(self) -> bool:
        """Whether this dialect has DMV/system-table-based fast row counts."""
        ...

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine with dialect-specific configuration.

        Args:
            **kwargs: Dialect-specific connection parameters.

        Returns:
            Configured SQLAlchemy Engine.
        """
        ...

    def fast_row_counts(self, engine: Engine, schema_name: str | None = None) -> dict[str, int]:
        """Get row counts using dialect-optimized system queries.

        Args:
            engine: SQLAlchemy engine to query against.
            schema_name: Optional schema filter.

        Returns:
            Dict mapping 'schema.table' to approximate row count.
            Returns empty dict if dialect doesn't support fast row counts.
        """
        ...

    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier using dialect-appropriate quoting.

        Args:
            identifier: Raw SQL identifier (table name, column name, etc.)

        Returns:
            Quoted identifier (e.g., '[name]' for MSSQL, '"name"' for generic).
        """
        ...
```

**Design decisions for D-07 (optional feature signaling):**
- `has_fast_row_counts` property guards whether `fast_row_counts()` returns useful data
- `fast_row_counts()` returns empty dict when unsupported (not None) -- callers always get a dict, never need None checks
- `supports_indexes` guards whether MetadataService should call `get_indexes()`
- This keeps call sites clean: check flag, then call method. No try/except NotImplementedError patterns.
[ASSUMED -- based on cleanest call-site analysis]

### Pattern 2: MssqlDialect Implementation (DIAL-02)

**What:** Concrete implementation that encapsulates all current MSSQL-specific code.

**MSSQL-specific code inventory (extraction targets):**

| Current Location | What | Moves To |
|-----------------|------|----------|
| `connection.py::_build_odbc_connection_string()` | ODBC string building with auth variants | `MssqlDialect.create_engine()` (internally calls private `_build_odbc_string`) |
| `connection.py::_create_engine()` | `mssql+pyodbc://` URL, Azure AD creator, pool_recycle tuning | `MssqlDialect.create_engine()` |
| `connection.py::_test_connection()` | `SELECT @@VERSION` probe query | `MssqlDialect` (MSSQL-specific probe; generic would use `SELECT 1`) |
| `connection.py::_classify_db_error()` | SQLSTATE classification + Azure AD token messages | `MssqlDialect` private helper |
| `azure_auth.py` | Entire module (AzureTokenProvider, token packing) | `src/db/dialects/azure_auth.py` (unchanged, just relocated) |
| `metadata.py::_list_schemas_mssql()` | DMV query for schema listing | `MssqlDialect` or stay in MetadataService (see D-09) |
| `metadata.py::_list_tables_mssql()` | DMV query for table listing with row counts | `MssqlDialect` or stay in MetadataService (see D-09) |
| `metadata.py::is_mssql` property | Dialect branching flag | Replaced by dialect protocol checks |
| `query.py` | `dialect_name == "sqlite"` branches for TOP vs LIMIT, bracket quoting | `quote_identifier()` on dialect; sampling queries stay in QueryService but use dialect for quoting |
| `query.py::_sanitize_identifier()` | `[identifier]` bracket quoting | Replaced by `dialect.quote_identifier()` |
| `query.py::parse_query_type()` | Hardcoded `dialect="tsql"` | Uses `dialect.sqlglot_dialect` |
| `validation.py::validate_query()` | Hardcoded `dialect="tsql"` | Phase 9 scope (VALID-01), but protocol prepares for it |
| `analysis/pk_discovery.py` | `f"[{schema}].[{table}]"` bracket quoting | Uses `dialect.quote_identifier()` (Phase 12 scope for analysis, but protocol enables it) |
| `analysis/column_stats.py` | `f"[{schema}].[{table}]"` bracket quoting | Same as above |
| `analysis/fk_candidates.py` | `sys.*` DMV queries + bracket quoting | Same as above |

**Design decision for D-08 (ConnectionManager split):**
- Dialect owns engine creation entirely via `create_engine(**kwargs)`.
- ConnectionManager becomes dialect-agnostic: it receives a dialect instance, delegates `create_engine()` to it, and manages the engine lifecycle (caching, disposal, connection testing).
- ConnectionManager still owns `_engines` dict, `_connections` dict, `connect()`/`disconnect()` lifecycle.
- This is clean separation: dialect knows HOW to connect, ConnectionManager knows WHEN to connect/disconnect.
[ASSUMED -- based on separation of concerns analysis]

**Design decision for D-09 (DMV queries):**
- DMV-based `_list_schemas_mssql()` and `_list_tables_mssql()` should move to `MssqlDialect` as methods like `list_schemas_fast()` and `list_tables_fast()`.
- MetadataService checks `dialect.has_fast_row_counts` (and a similar flag for schema/table listing) to decide whether to call dialect-specific fast paths or fall back to Inspector.
- Alternative: Keep DMV queries in MetadataService but behind `isinstance(dialect, MssqlDialect)` checks. This is simpler but leaks dialect knowledge into the service.
- **Recommendation:** Move DMV queries into `MssqlDialect`. Add protocol methods `fast_list_schemas()` and `fast_list_tables()` if needed -- but this risks protocol bloat. Better approach: Add a single method like `get_table_metadata_fast()` that returns the DMV result, and let MetadataService call it when `has_fast_row_counts` is True.
- **Simplest approach for Phase 8 (zero behavior change):** Keep DMV methods in MetadataService for now, but replace `self.is_mssql` checks with `self.dialect.has_fast_row_counts` (or a more general `has_fast_metadata` flag). The DMV SQL stays in MetadataService. This minimizes code movement and risk. Phase 11+ can move them if needed.
[ASSUMED -- based on minimizing risk for zero-regression constraint]

### Pattern 3: Registry (D-05, D-06)

**What:** Module-level dict mapping dialect names to classes, with registration/lookup functions.

```python
# Source: project conventions (module-level constants, simple functions)
from src.db.dialects.protocol import DialectStrategy

_REGISTRY: dict[str, type[DialectStrategy]] = {}


def register_dialect(name: str, dialect_class: type[DialectStrategy]) -> None:
    """Register a dialect strategy implementation.

    Args:
        name: Dialect identifier (e.g., 'mssql', 'generic').
        dialect_class: Class implementing DialectStrategy protocol.
    """
    _REGISTRY[name] = dialect_class


def get_dialect(name: str) -> type[DialectStrategy]:
    """Look up a dialect strategy class by name.

    Args:
        name: Dialect identifier.

    Returns:
        The dialect strategy class.

    Raises:
        ValueError: If dialect name is not registered (Phase 8: fail-fast).
    """
    if name not in _REGISTRY:
        registered = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ValueError(
            f"Unknown dialect '{name}'. Registered dialects: {registered}"
        )
    return _REGISTRY[name]
```

Auto-registration in `__init__.py`:
```python
from src.db.dialects.mssql import MssqlDialect
from src.db.dialects.registry import register_dialect

register_dialect("mssql", MssqlDialect)
```

### Anti-Patterns to Avoid
- **Premature protocol expansion:** Don't add methods to DialectStrategy that aren't needed until Phase 10+. Keep it to what ROADMAP specifies: `name`, `sqlglot_dialect`, `create_engine`, `fast_row_counts`, `quote_identifier`, plus capability flags.
- **Double dispatch:** Don't have MetadataService call `dialect.do_metadata()` which calls back into MetadataService. Keep the call direction one-way: service calls dialect for primitive operations.
- **Isinstance checks on protocol:** Avoid `isinstance(dialect, MssqlDialect)` in service code -- that defeats the purpose of the protocol. Use capability flags instead.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Structural subtyping | Custom ABC or interface class | `typing.Protocol` | Built into Python 3.11+; structural (duck-typed), not nominal [VERIFIED: Python stdlib] |
| Identifier quoting | Per-callsite bracket/backtick logic | `dialect.quote_identifier()` method | Centralizes quoting logic, eliminates scattered f-string bracket patterns |
| Registry pattern | Class decorators or metaclass magic | Simple dict + register/get functions | Matches project's lightweight, explicit style (D-05) |

## Common Pitfalls

### Pitfall 1: Import Cycle Between Dialect and ConnectionManager
**What goes wrong:** `MssqlDialect` imports from `connection.py` (e.g., `PoolConfig`), and `connection.py` imports from dialects. Circular import.
**Why it happens:** `PoolConfig` is currently defined in `connection.py` but is dialect-agnostic. `MssqlDialect.create_engine()` needs pool configuration.
**How to avoid:** Keep `PoolConfig` in `connection.py` (it's not dialect-specific). `MssqlDialect.create_engine()` accepts pool config as a parameter, not an import dependency. Or move `PoolConfig` to a shared module if needed.
**Warning signs:** `ImportError` at module load time.

### Pitfall 2: Backward-Incompatible ConnectionManager.connect() Signature
**What goes wrong:** Changing `connect()` parameters breaks all 680 tests and the MCP tool layer.
**Why it happens:** Eagerness to make `connect()` dialect-aware in Phase 8 when that's Phase 10 scope (CONF-03).
**How to avoid:** In Phase 8, `connect()` signature stays EXACTLY as-is. Internally, it creates an `MssqlDialect` instance and delegates to it. The dialect is an implementation detail, not a public API change.
**Warning signs:** Test failures in `test_connection.py`, `test_async_tools.py`.

### Pitfall 3: Breaking Analysis Module Quoting
**What goes wrong:** Analysis modules (`pk_discovery.py`, `column_stats.py`, `fk_candidates.py`) use `f"[{schema}].[{table}]"` hardcoded. Changing these breaks analysis tests.
**Why it happens:** Trying to make analysis modules dialect-aware in Phase 8 when that's Phase 12 scope.
**How to avoid:** Leave analysis modules UNTOUCHED in Phase 8. They still use bracket quoting. Phase 12 will inject dialect into analysis modules. The protocol just needs to exist and be ready.
**Warning signs:** Test failures in `test_column_stats.py`, `test_pk_discovery.py`, `test_fk_candidates.py`.

### Pitfall 4: Scattered Bracket Quoting Not Fully Inventoried
**What goes wrong:** Some bracket-quoting call sites get missed, leading to inconsistent behavior.
**Current bracket quoting locations (META-05 inventory):**
- `query.py::_sanitize_identifier()` -- returns `f"[{identifier}]"` for non-sqlite
- `query.py::_validate_identifier()` -- returns `f"[{actual_name}]"` for non-sqlite
- `query.py::get_sample_data()` -- `f"[{schema_name}].[{table_name}]"` for non-sqlite
- `metadata.py::_get_row_count_generic()` -- uses `"` double-quotes (generic path)
- `analysis/pk_discovery.py` -- `f"[{schema_name}].[{table_name}]"`
- `analysis/column_stats.py` -- `f"[{schema_name}].[{table_name}]"`
- `analysis/fk_candidates.py` -- `f"[{self.source_schema}].[{self.source_table}]"` and target tables
**How to avoid:** Only convert quoting in `query.py` and `metadata.py` in Phase 8 (modules already being touched). Leave analysis modules for Phase 12.

### Pitfall 5: `validation.py` Hardcoded `dialect="tsql"`
**What goes wrong:** Temptation to make `validate_query()` dialect-aware in Phase 8.
**Why it happens:** The function uses `sqlglot.parse(sql, dialect="tsql")` -- obviously MSSQL-specific.
**How to avoid:** Leave it alone. This is explicitly Phase 9 scope (VALID-01). The DialectStrategy protocol provides `sqlglot_dialect` property which Phase 9 will use.

### Pitfall 6: `_test_connection()` Uses MSSQL-Specific SQL
**What goes wrong:** `SELECT @@VERSION AS version, DB_NAME() AS database_name` is T-SQL syntax.
**How to avoid:** In Phase 8 this is fine -- we're only extracting MSSQL code, not adding new dialects. The probe query can be a method on MssqlDialect (e.g., `get_probe_query()`), or simply left in ConnectionManager since only MssqlDialect exists. Keep it simple.

## Code Examples

### DialectStrategy Protocol Definition
```python
# src/db/dialects/protocol.py
# Source: typing.Protocol stdlib + project conventions
from typing import Protocol, runtime_checkable

from sqlalchemy.engine import Engine


@runtime_checkable
class DialectStrategy(Protocol):
    """Protocol for database dialect-specific behavior."""

    @property
    def name(self) -> str: ...

    @property
    def sqlglot_dialect(self) -> str: ...

    @property
    def supports_indexes(self) -> bool: ...

    @property
    def has_fast_row_counts(self) -> bool: ...

    def create_engine(self, **kwargs) -> Engine: ...

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None,
    ) -> dict[str, int]: ...

    def quote_identifier(self, identifier: str) -> str: ...
```

### MssqlDialect Skeleton
```python
# src/db/dialects/mssql.py
# Source: extracted from src/db/connection.py + src/db/metadata.py
from sqlalchemy.engine import Engine

from src.db.dialects.azure_auth import AzureTokenProvider, SQL_COPT_SS_ACCESS_TOKEN
from src.logging_config import get_logger

logger = get_logger(__name__)


class MssqlDialect:
    """SQL Server dialect implementation.

    Encapsulates MSSQL-specific behavior: ODBC connection strings,
    Azure AD authentication, DMV-based fast metadata, bracket quoting.
    """

    @property
    def name(self) -> str:
        return "mssql"

    @property
    def sqlglot_dialect(self) -> str:
        return "tsql"

    @property
    def supports_indexes(self) -> bool:
        return True

    @property
    def has_fast_row_counts(self) -> bool:
        return True

    def create_engine(self, **kwargs) -> Engine:
        """Create MSSQL engine with ODBC + optional Azure AD."""
        # Extract from ConnectionManager._build_odbc_connection_string()
        # and ConnectionManager._create_engine()
        ...

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None,
    ) -> dict[str, int]:
        """Get row counts from sys.dm_db_partition_stats."""
        ...

    def quote_identifier(self, identifier: str) -> str:
        """Quote using SQL Server brackets."""
        return f"[{identifier}]"
```

### Registry Usage
```python
# src/db/dialects/registry.py
from src.db.dialects.protocol import DialectStrategy

_REGISTRY: dict[str, type[DialectStrategy]] = {}

def register_dialect(name: str, dialect_class: type[DialectStrategy]) -> None:
    _REGISTRY[name] = dialect_class

def get_dialect(name: str) -> type[DialectStrategy]:
    if name not in _REGISTRY:
        registered = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ValueError(f"Unknown dialect '{name}'. Registered dialects: {registered}")
    return _REGISTRY[name]
```

### Wiring Into ConnectionManager (Backward Compatible)
```python
# In ConnectionManager.connect() -- internal change only, signature unchanged
def connect(self, server, database, ...) -> Connection:
    # ... existing validation ...

    # Phase 8: always use MssqlDialect (only dialect available)
    dialect = MssqlDialect()

    # Delegate engine creation to dialect
    engine = dialect.create_engine(
        server=server, database=database, port=port,
        username=username, password=password,
        authentication_method=authentication_method,
        trust_server_cert=trust_server_cert,
        connection_timeout=connection_timeout,
        tenant_id=tenant_id,
        query_timeout=query_timeout,
        pool_config=self._pool_config,
        connection_id=connection_id,
        disconnect_callback=self.disconnect,
    )
    # ... rest unchanged ...
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.3+ with pytest-asyncio |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -v --tb=short` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DIAL-01 | DialectStrategy protocol exists with required methods | unit | `uv run pytest tests/unit/test_dialect_protocol.py -x` | Wave 0 |
| DIAL-02 | MssqlDialect implements protocol correctly | unit | `uv run pytest tests/unit/test_mssql_dialect.py -x` | Wave 0 |
| DIAL-05 | Registry resolves names, raises on unknown | unit | `uv run pytest tests/unit/test_dialect_registry.py -x` | Wave 0 |
| META-05 | quote_identifier produces correct quoting | unit | `uv run pytest tests/unit/test_mssql_dialect.py::TestQuoteIdentifier -x` | Wave 0 |
| TEST-01 | All existing tests pass unchanged | regression | `uv run pytest tests/ -v --tb=short` | Existing (680 tests) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q` (fast, unit only)
- **Per wave merge:** `uv run pytest tests/ -v --tb=short` (full suite)
- **Phase gate:** Full suite green + `uv run ruff check src/` clean before verification

### Wave 0 Gaps
- [ ] `tests/unit/test_dialect_protocol.py` -- covers DIAL-01 (protocol structural typing checks)
- [ ] `tests/unit/test_mssql_dialect.py` -- covers DIAL-02, META-05 (implementation correctness)
- [ ] `tests/unit/test_dialect_registry.py` -- covers DIAL-05 (registration, lookup, error on unknown)

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | yes | Azure AD token handling stays encapsulated in MssqlDialect; no credential exposure changes |
| V3 Session Management | no | N/A -- no session state changes |
| V4 Access Control | no | Read-only enforcement unchanged |
| V5 Input Validation | yes | `quote_identifier()` prevents SQL injection in identifier quoting |
| V6 Cryptography | no | No crypto changes |

### Known Threat Patterns for This Refactoring

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via identifier quoting | Tampering | `quote_identifier()` must properly escape embedded brackets/quotes |
| Credential leak during extraction | Information Disclosure | Azure AD tokens never logged (CredentialFilter); verify no new log statements expose tokens |
| Registry poisoning | Elevation of Privilege | Registry only populated at module import time, not from user input |

## Sources

### Primary (HIGH confidence)
- **Codebase analysis** -- direct reading of all 6 extraction-target source files and 3 analysis modules
- **CONTEXT.md** -- locked decisions D-01 through D-06
- **ROADMAP.md** -- Phase 8 success criteria and requirement mapping
- **REQUIREMENTS.md** -- DIAL-01, DIAL-02, DIAL-05, META-05, TEST-01 definitions
- **ARCHITECTURE.md** -- MCS pattern, layered service architecture
- **CONVENTIONS.md** -- naming, imports, docstring style

### Secondary (MEDIUM confidence)
- **Python typing.Protocol** -- stdlib documentation for structural subtyping [VERIFIED: Python 3.11 stdlib]

### Tertiary (LOW confidence)
None -- all findings based on direct codebase analysis and locked decisions.

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | Flat files under `src/db/dialects/` is sufficient (no subpackages needed) | Architecture Patterns (D-10) | Low -- easy to restructure later |
| A2 | `fast_row_counts()` returns empty dict (not None) for unsupported dialects | Architecture Patterns (D-07) | Low -- call-site preference, easy to change |
| A3 | Dialect owns engine creation, ConnectionManager delegates | Architecture Patterns (D-08) | Medium -- affects ConnectionManager refactoring scope |
| A4 | DMV queries stay in MetadataService for Phase 8, guarded by capability flags | Architecture Patterns (D-09) | Medium -- moving them later is more work but minimizes Phase 8 regression risk |
| A5 | Analysis modules left untouched in Phase 8 (Phase 12 scope) | Common Pitfalls | Low -- explicitly out of scope per roadmap |

## Open Questions

1. **`create_engine()` parameter signature**
   - What we know: MssqlDialect needs server, database, port, auth_method, credentials, pool_config, and Azure AD parameters
   - What's unclear: Whether to use `**kwargs` (flexible but untyped) or a typed parameter object (safer but more boilerplate)
   - Recommendation: Use `**kwargs` for the protocol definition, but MssqlDialect internally validates expected keys. This keeps the protocol generic for future dialects with very different connection parameters.

2. **ConnectionManager auto-disconnect callback**
   - What we know: Current `_create_engine()` passes `connection_id` and calls `self.disconnect()` on Azure AD token failure
   - What's unclear: How to give MssqlDialect the ability to trigger disconnect without creating a circular dependency
   - Recommendation: Pass a `disconnect_callback: Callable[[str], None] | None` parameter to `create_engine()`. MssqlDialect uses it for the Azure AD token failure path.

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, pure refactoring
- Architecture: HIGH -- all extraction targets identified from direct code reading
- Pitfalls: HIGH -- based on actual code inventory and regression risk analysis

**Research date:** 2026-04-13
**Valid until:** 2026-05-13 (stable -- internal refactoring, no external dependency risk)
