# Phase 9: Config Discrimination & Validation Dialect - Research

**Researched:** 2026-04-14
**Domain:** TOML config parsing, dataclass modeling, sqlglot dialect-aware validation
**Confidence:** HIGH

## Summary

Phase 9 adds dialect discrimination to TOML config parsing and makes query validation dialect-aware. The work is entirely in-memory Python -- no new dependencies, no external services, no data migrations. The codebase already has the dialect protocol (`DialectStrategy`), registry, and `MssqlDialect` from Phase 8, so this phase extends those foundations.

The core technical challenges are: (1) replacing the flat `ConnectionConfig` dataclass with per-dialect typed dataclasses dispatched by a `dialect` field in TOML, (2) threading a `dialect` parameter through `validate_query()` and its 44 test call sites, and (3) moving `SAFE_PROCEDURES` from a module-level constant into `MssqlDialect.safe_procedures`. All three are mechanically straightforward with the current codebase structure.

**Primary recommendation:** Implement config discrimination first (CONF-01/CONF-02), then validation dialect plumbing (VALID-01/VALID-02/VALID-03). Config changes are self-contained; validation changes touch more files but are uniform (add `dialect=` parameter everywhere).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Separate frozen dataclasses per dialect: `MssqlConnectionConfig`, `DatabricksConnectionConfig`, `GenericConnectionConfig`. No base class or inheritance.
- **D-02:** The `dialect` field in TOML is always required for every connection. This overrides CONF-01's original "default to mssql" spec.
- **D-03:** Parse function reads `dialect` from each TOML connection table, then instantiates the correct typed config class.
- **D-04:** When `dialect` is omitted, raise `ValueError` with actionable message.
- **D-05:** connect_database MCP tool signature stays unchanged in Phase 9.
- **D-06:** Unrecognized fields produce a warning log, silently ignored.
- **D-07:** Add `safe_procedures` property to `DialectStrategy` protocol. `MssqlDialect` returns sp_ frozenset; others return empty.
- **D-08:** Config-level SP allowlist extensions remain global, merged with `dialect.safe_procedures` at validation time.
- **D-09:** `validate_query()` accepts `dialect` as a required sqlglot dialect string. No default value.
- **D-10:** All 44 existing test calls updated to pass `dialect="tsql"` explicitly.
- **D-11:** Safe procedure checking accepts `safe_procedures` parameter (frozenset) rather than reading from global state.

### Claude's Discretion
- **D-12:** Internal structure of per-dialect config dataclass fields.
- **D-13:** Whether `validate_query` takes `safe_procedures` as a separate param or bundles it.
- **D-14:** How `_parse_connections()` dispatches to per-dialect parsers (match/case, dict, if/elif).

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope.

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| CONF-01 | TOML config supports `dialect` discriminator field (updated: now required, not defaulting) | Config parsing dispatch pattern; per-dialect dataclass fields documented |
| CONF-02 | Typed config models validate dialect-specific fields | Per-dialect field sets researched; frozen dataclass patterns established |
| VALID-01 | validate_query accepts dialect parameter and passes it to sqlglot.parse() | Confirmed sqlglot 30.4.2 dialect parameter works for tsql/databricks; AST types identical |
| VALID-02 | Safe procedure list is dialect-aware (MSSQL sp_ list; empty for others) | `safe_procedures` property on DialectStrategy; EXEC parsing is MSSQL-only (confirmed) |
| VALID-03 | Denylist validation works unchanged across all sqlglot dialects | Verified: INSERT/DROP/SELECT produce identical AST types in tsql and databricks |

</phase_requirements>

## Standard Stack

### Core (existing -- no new dependencies)
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlglot | 30.4.2 | Query parsing with dialect parameter | Already installed; `sqlglot.parse(sql, dialect=X)` is the dialect entry point [VERIFIED: installed version check] |
| tomllib | stdlib | TOML config parsing | Already used in `src/config.py` [VERIFIED: codebase] |
| dataclasses | stdlib | Frozen config models | Already used for `ConnectionConfig` [VERIFIED: codebase] |

### Supporting (existing)
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy | >=2.0.0 | Engine types in config | Type annotations only in this phase |

**Installation:** No new packages required.

## Architecture Patterns

### Recommended Project Structure (changes only)
```
src/
  config.py              # Add per-dialect config dataclasses + dispatch in _parse_connections
  db/
    validation.py         # Add dialect + safe_procedures params to validate_query
    dialects/
      protocol.py         # Add safe_procedures property to DialectStrategy
      mssql.py            # Add safe_procedures property returning SAFE_PROCEDURES frozenset
```

### Pattern 1: Per-Dialect Config Dataclass Dispatch
**What:** `_parse_connections()` reads `dialect` from TOML, dispatches to a dialect-specific parser function that returns the correct typed dataclass.
**When to use:** Every config load.
**Example:**
```python
# Follows existing frozen dataclass pattern [VERIFIED: src/config.py]

@dataclass(frozen=True)
class MssqlConnectionConfig:
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
class DatabricksConnectionConfig:
    dialect: str = "databricks"
    host: str = ""
    http_path: str = ""
    catalog: str = "main"
    schema_name: str = "default"
    token: str | None = None  # ${ENV_VAR} pattern

@dataclass(frozen=True)
class GenericConnectionConfig:
    dialect: str = "generic"
    sqlalchemy_url: str = ""

# Type alias for callers
ConnectionConfig = MssqlConnectionConfig | DatabricksConnectionConfig | GenericConnectionConfig
```

### Pattern 2: Dict-Based Dispatch (D-14 recommendation)
**What:** Use a dict mapping dialect name to parser function.
**Why recommended over match/case:** Matches the existing `_REGISTRY` dict pattern in `registry.py`, is extensible without code changes. [VERIFIED: src/db/dialects/registry.py]
**Example:**
```python
_DIALECT_PARSERS: dict[str, Callable[[str, dict], ConnectionConfig]] = {
    "mssql": _parse_mssql_connection,
    "databricks": _parse_databricks_connection,
    "generic": _parse_generic_connection,
}

def _parse_connections(raw_connections: dict) -> dict[str, ConnectionConfig]:
    connections: dict[str, ConnectionConfig] = {}
    for name, params in raw_connections.items():
        if not isinstance(params, dict):
            logger.warning("Config: connection '%s' is not a table, skipping", name)
            continue
        dialect = params.get("dialect")
        if dialect is None:
            raise ValueError(
                f"Connection '{name}' missing required 'dialect' field. "
                f"Add dialect = \"mssql\" for SQL Server connections."
            )
        parser = _DIALECT_PARSERS.get(dialect)
        if parser is None:
            raise ValueError(
                f"Connection '{name}' has unknown dialect '{dialect}'. "
                f"Supported: {', '.join(sorted(_DIALECT_PARSERS))}"
            )
        connections[name] = parser(name, params)
    return connections
```

### Pattern 3: Pure validate_query with Explicit Dependencies
**What:** `validate_query()` takes `dialect` and `safe_procedures` as explicit parameters, eliminating global state reads.
**Why:** Per D-09 and D-11 -- makes the function pure and testable without mocking.
**Example:**
```python
def validate_query(
    sql: str,
    *,
    dialect: str,
    safe_procedures: frozenset[str] = frozenset(),
    allow_write: bool = False,
) -> ValidationResult:
    # ...
    statements = sqlglot.parse(sql, dialect=dialect)
    # ...
```

### Anti-Patterns to Avoid
- **Inheriting from a base config class:** D-01 explicitly forbids this. Keep dataclasses flat and independent.
- **Default dialect parameter:** D-09 requires every caller to pass dialect explicitly. No `dialect="tsql"` default.
- **Reading SAFE_PROCEDURES from module-level in validation.py:** Move to `MssqlDialect.safe_procedures` per D-07. The module-level constant stays temporarily for backward compatibility during migration but should be removed.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOML parsing | Custom parser | `tomllib` (stdlib) | Already used, handles edge cases [VERIFIED: codebase] |
| SQL dialect detection | String matching on SQL | `sqlglot.parse(dialect=X)` | sqlglot handles dialect-specific syntax [VERIFIED: runtime test] |
| Config field validation | Custom type checking | Dataclass `__post_init__` or explicit validation functions | Matches existing `_validate_defaults` pattern [VERIFIED: codebase] |

## Common Pitfalls

### Pitfall 1: EXEC Parsing is MSSQL-Only
**What goes wrong:** `EXEC sp_help` parses as `Alias` (garbage) in Databricks dialect, not as `Execute`.
**Why it happens:** EXEC is T-SQL syntax; sqlglot doesn't recognize it in other dialects.
**How to avoid:** Safe procedure checking only applies when dialect is "tsql". For other dialects, EXEC statements will be caught as garbage parse (unrecognized statement) and denied -- which is correct behavior.
**Warning signs:** Tests that pass `EXEC` queries with `dialect="databricks"` expecting `STORED_PROCEDURE` denial category. They'll get `PARSE_FAILURE` instead.
[VERIFIED: runtime test -- `sqlglot.parse('EXEC sp_help', dialect='databricks')` returns `Alias` type]

### Pitfall 2: ConnectionConfig Union Type Breaks Existing Callers
**What goes wrong:** Code that accesses `connection.server` will fail on `DatabricksConnectionConfig` (no `server` field).
**Why it happens:** Union types don't guarantee shared fields.
**How to avoid:** Phase 9 keeps the `connect_database` tool unchanged (D-05). The per-dialect config classes are only consumed by Phase 10's new connection logic. Existing code paths continue using `MssqlConnectionConfig` which has all the same fields as the old `ConnectionConfig`.
**Warning signs:** Type checker errors in `connection.py` when accessing connection config fields without narrowing.

### Pitfall 3: Test Count Is High (44 Call Sites)
**What goes wrong:** Missing a `validate_query` call site leads to test failures.
**Why it happens:** 44 calls across 4 test files need `dialect="tsql"` added.
**How to avoid:** Mechanical update -- grep for all `validate_query(` in tests/, add `dialect="tsql"`. No logic changes needed in test assertions.
**Warning signs:** Any test calling `validate_query` without `dialect=` will get a TypeError at runtime.
[VERIFIED: grep found exactly 44 occurrences across 4 files]

### Pitfall 4: get_allowed_procedures() Reads Global Config
**What goes wrong:** `get_allowed_procedures()` currently merges `SAFE_PROCEDURES | get_config().allowed_stored_procedures`. After refactoring, the dialect's safe_procedures replaces `SAFE_PROCEDURES`, but config-level SPs (D-08) still come from `get_config()`.
**Why it happens:** The function's responsibilities are split across two sources.
**How to avoid:** The production caller (QueryService.execute_query) should compose `dialect.safe_procedures | config.allowed_stored_procedures` and pass the merged set to `validate_query(safe_procedures=...)`. This keeps `validate_query` pure.
**Warning signs:** Tests that mock `get_config()` expecting it to affect validation results.

## Code Examples

### validate_query Signature Change
```python
# Current (src/db/validation.py line 88) [VERIFIED: codebase]
def validate_query(sql: str, allow_write: bool = False) -> ValidationResult:
    statements = sqlglot.parse(sql, dialect="tsql")

# New
def validate_query(
    sql: str,
    *,
    dialect: str,
    safe_procedures: frozenset[str] = frozenset(),
    allow_write: bool = False,
) -> ValidationResult:
    statements = sqlglot.parse(sql, dialect=dialect)
```

### Production Caller Update
```python
# Current (src/db/query.py line 539) [VERIFIED: codebase]
validation = validate_query(query_text, allow_write=allow_write)

# New -- QueryService already has self._dialect [VERIFIED: codebase, line 67]
dialect_str = self._dialect.sqlglot_dialect if self._dialect else "tsql"
safe_procs = (
    self._dialect.safe_procedures if self._dialect else MSSQL_SAFE_PROCEDURES
) | get_config().allowed_stored_procedures
validation = validate_query(
    query_text,
    dialect=dialect_str,
    safe_procedures=safe_procs,
    allow_write=allow_write,
)
```

### DialectStrategy Protocol Extension
```python
# Add to src/db/dialects/protocol.py [VERIFIED: codebase]
@property
def safe_procedures(self) -> frozenset[str]:
    """Known-safe stored procedures for this dialect."""
    ...
```

### MssqlDialect Implementation
```python
# Add to src/db/dialects/mssql.py [VERIFIED: codebase]
@property
def safe_procedures(self) -> frozenset[str]:
    """22 known-safe SQL Server system stored procedures."""
    return frozenset({
        "sp_column_privileges", "sp_columns", "sp_databases",
        "sp_fkeys", "sp_pkeys", "sp_server_info",
        "sp_special_columns", "sp_sproc_columns", "sp_statistics",
        "sp_stored_procedures", "sp_table_privileges", "sp_tables",
        "sp_help", "sp_helptext", "sp_helpindex", "sp_helpconstraint",
        "sp_who", "sp_who2", "sp_spaceused",
        "sp_describe_first_result_set", "sp_describe_undeclared_parameters",
    })
```

### Test Update Pattern
```python
# Before [VERIFIED: tests/unit/test_validation.py]
result = validate_query("SELECT * FROM users")

# After
result = validate_query("SELECT * FROM users", dialect="tsql")

# For SP tests, also pass safe_procedures
from src.db.dialects.mssql import MssqlDialect
MSSQL_SAFE = MssqlDialect().safe_procedures
result = validate_query("EXEC sp_help", dialect="tsql", safe_procedures=MSSQL_SAFE)
```

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest (existing) |
| Config file | `pyproject.toml` [VERIFIED: project uses uv] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -x -q` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONF-01 | Missing `dialect` raises ValueError with actionable message | unit | `uv run pytest tests/unit/test_config.py -x -k dialect` | Exists (needs new tests) |
| CONF-01 | Each dialect string routes to correct dataclass type | unit | `uv run pytest tests/unit/test_config.py -x -k dialect` | Exists (needs new tests) |
| CONF-02 | MssqlConnectionConfig validates MSSQL-specific fields | unit | `uv run pytest tests/unit/test_config.py -x -k mssql` | Exists (needs new tests) |
| CONF-02 | DatabricksConnectionConfig validates Databricks-specific fields | unit | `uv run pytest tests/unit/test_config.py -x -k databricks` | Exists (needs new tests) |
| CONF-02 | GenericConnectionConfig validates generic fields | unit | `uv run pytest tests/unit/test_config.py -x -k generic` | Exists (needs new tests) |
| CONF-02 | Unknown fields produce warning log | unit | `uv run pytest tests/unit/test_config.py -x -k unknown` | Exists (needs new tests) |
| VALID-01 | validate_query passes dialect to sqlglot.parse | unit | `uv run pytest tests/unit/test_validation.py -x` | Exists (needs update) |
| VALID-02 | MSSQL SP list from dialect.safe_procedures | unit | `uv run pytest tests/unit/test_validation.py -x -k procedure` | Exists (needs update) |
| VALID-02 | Non-MSSQL returns empty safe_procedures | unit | `uv run pytest tests/unit/test_validation.py -x -k procedure` | New tests needed |
| VALID-03 | Denylist works identically across dialects | unit | `uv run pytest tests/unit/test_validation.py -x -k denylist` | New tests needed |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x -q`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] New config discrimination tests in `tests/unit/test_config.py`
- [ ] Cross-dialect denylist validation tests in `tests/unit/test_validation.py`
- [ ] Update 44 existing `validate_query()` calls to pass `dialect="tsql"`

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A (config only, no auth changes) |
| V3 Session Management | no | N/A |
| V4 Access Control | no | N/A (tool interface unchanged per D-05) |
| V5 Input Validation | yes | TOML field validation via dataclass + explicit checks; sqlglot dialect parameter restricted to known values |
| V6 Cryptography | no | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| Invalid dialect string bypasses validation | Tampering | Reject unknown dialect values in both config parsing and validate_query [VERIFIED: registry.get_dialect raises ValueError for unknown dialects] |
| Malicious TOML config with extra fields | Information Disclosure | D-06: warning log + ignore (non-critical) |
| Config injection via ${ENV_VAR} | Tampering | Existing `resolve_env_vars()` only at connection time, not at parse time [VERIFIED: codebase] |

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded `dialect="tsql"` in validate_query | Parameterized dialect | Phase 9 | Enables multi-dialect validation |
| Single flat ConnectionConfig | Per-dialect typed configs | Phase 9 | Type safety for dialect-specific fields |
| Module-level SAFE_PROCEDURES | Dialect property safe_procedures | Phase 9 | Dialect-aware SP allowlisting |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | DatabricksConnectionConfig needs host, http_path, catalog, schema_name, token fields | Architecture Patterns | Low -- D-12 gives Claude discretion; actual Databricks connection fields may differ but are only consumed in Phase 10+ |
| A2 | GenericConnectionConfig needs only sqlalchemy_url field | Architecture Patterns | Low -- same D-12 discretion; may need additional fields for specific generic drivers |

## Open Questions

1. **ConnectionConfig type alias vs keeping old class**
   - What we know: Old `ConnectionConfig` is used in `AppConfig.connections` dict and throughout `connection.py`
   - What's unclear: Whether to make `ConnectionConfig` a `TypeAlias` for the union, or keep the old class and add new ones alongside
   - Recommendation: Make it a `TypeAlias = MssqlConnectionConfig | DatabricksConnectionConfig | GenericConnectionConfig`. The old class fields map 1:1 to `MssqlConnectionConfig`, so existing code that only handles MSSQL connections continues working with type narrowing.

2. **_check_execute and _check_stored_procedure with non-MSSQL dialects**
   - What we know: EXEC parses as garbage (Alias) in non-MSSQL dialects, so `_check_execute` never fires [VERIFIED: runtime test]
   - What's unclear: Whether to explicitly short-circuit SP checking for non-MSSQL dialects or rely on the parse-level filtering
   - Recommendation: Rely on parse-level filtering. If `safe_procedures` is empty (non-MSSQL), the `_check_execute` code path is harmless even if somehow reached. The garbage parse detection catches EXEC first.

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/config.py`, `src/db/validation.py`, `src/db/query.py`, `src/db/dialects/protocol.py`, `src/db/dialects/mssql.py`, `src/db/dialects/registry.py`
- Runtime verification: sqlglot 30.4.2 dialect behavior (tsql vs databricks AST types, EXEC parsing differences)
- Test suite grep: 44 `validate_query()` call sites across 4 test files

### Secondary (MEDIUM confidence)
- None needed -- all claims verified against codebase and runtime

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all verified in codebase
- Architecture: HIGH - patterns follow existing codebase conventions, decisions are locked
- Pitfalls: HIGH - verified via runtime sqlglot tests and codebase grep

**Research date:** 2026-04-14
**Valid until:** 2026-05-14 (stable -- no external dependency changes)
