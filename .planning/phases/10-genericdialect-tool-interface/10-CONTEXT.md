# Phase 10: GenericDialect & Tool Interface - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can connect to any SQLAlchemy-supported database via URL, with clean dependency separation. This phase delivers: (1) GenericDialect implementation registered with the dialect registry, (2) simplified connect_database tool interface with only connection_name and sqlalchemy_url params, (3) optional dependency groups moving pyodbc/azure-identity to [mssql] extra and keeping core install driver-free.

</domain>

<decisions>
## Implementation Decisions

### Tool Interface Design
- **D-01:** connect_database tool signature becomes two params only: `connection_name: str | None` and `sqlalchemy_url: str | None`. All MSSQL-specific params (server, database, username, password, port, authentication_method, trust_server_cert, connection_timeout, tenant_id) are removed immediately — clean break for v2.0, no deprecation period.
- **D-02:** When `sqlalchemy_url` is passed directly, the dialect is auto-detected from the URL scheme (e.g., `mssql+pyodbc://` -> mssql, `databricks://` -> databricks). A mapping dict handles known schemes.
- **D-03:** When `connection_name` is passed, the TOML config's `dialect` field determines the dialect (existing Phase 9 behavior).

### GenericDialect Behavior
- **D-04:** GenericDialect uses a URL-scheme-to-sqlglot-dialect mapping for query validation (postgresql -> postgres, mysql -> mysql, sqlite -> sqlite). Unknown schemes pass `dialect=None` to sqlglot (generic SQL parsing).
- **D-05:** GenericDialect uses ANSI double-quote identifier quoting (`"identifier"`). No engine-dependent quoting detection.
- **D-06:** GenericDialect capability flags: `supports_indexes=True` (most SQLAlchemy DBs support index metadata via Inspector), `has_fast_row_counts=False` (no DMV/system-table fast path — uses COUNT(*) fallback).
- **D-07:** GenericDialect.safe_procedures returns `frozenset()` (empty). No stored procedures are considered safe for generic databases.
- **D-08:** GenericDialect.create_engine accepts the sqlalchemy_url and passes it to `sqlalchemy.create_engine()` with reasonable defaults.

### Registry & Fallback Behavior
- **D-09:** TOML config path: `dialect` must be a registered dialect name. Unknown dialect names raise ValueError (fail-fast). GenericDialect only activates for explicit `dialect = "generic"`. This preserves Phase 8 D-06 for the config path.
- **D-10:** URL path: auto-detect from URL scheme. Known schemes map to registered dialects. Unknown schemes automatically route to GenericDialect with a **warning log** (not an error): "No optimized dialect for '{scheme}' — using generic fallback." The user isn't blocked but is informed.

### Dependency Separation
- **D-11:** Core install has zero DB drivers: mcp[cli], sqlalchemy, sqlglot, toon-format only. pyodbc + azure-identity move to `[mssql]` optional extra. Databricks packages go in `[databricks]` extra.
- **D-12:** Add `[all]` convenience extra that installs mssql + databricks + examples. For devs and CI.
- **D-13:** Missing dialect dependencies surface at connection time via lazy import with clear error messages. Each dialect's create_engine catches ImportError and raises: "MSSQL support requires pyodbc. Install with: pip install dbmcp[mssql]". No registry-time checks.

### Claude's Discretion
- **D-14:** Internal implementation of the URL-scheme-to-dialect mapping (dict structure, placement) — Claude picks based on cleanest organization.
- **D-15:** How GenericDialect's create_engine handles pool configuration and other engine kwargs — Claude picks reasonable defaults.
- **D-16:** How the connect_database tool function is refactored internally (routing logic between connection_name vs sqlalchemy_url paths) — Claude picks based on cleanest code.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DIAL-04, CONF-03, CONF-04, CONF-05 requirement details

### Existing Code (modification targets)
- `src/mcp_server/schema_tools.py` lines 247-258 — Current connect_database tool signature (to be replaced)
- `src/db/dialects/protocol.py` — DialectStrategy protocol (GenericDialect must implement)
- `src/db/dialects/registry.py` — register_dialect()/get_dialect() functions
- `src/db/dialects/mssql.py` — MssqlDialect reference implementation
- `src/config.py` — GenericConnectionConfig dataclass (already exists), AppConfig
- `src/db/connection.py` — ConnectionManager.connect() needs URL path support
- `pyproject.toml` — Dependencies section to be restructured with optional extras

### Prior Phase Context
- `.planning/phases/08-dialect-protocol-mssql-extraction/08-CONTEXT.md` — Protocol design, registry, extraction decisions
- `.planning/phases/09-config-discrimination-validation-dialect/09-CONTEXT.md` — Config discrimination, validation dialect decisions

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md` — MCS pattern, layer responsibilities
- `.planning/codebase/CONVENTIONS.md` — Naming patterns, dataclass style
- `.planning/codebase/STRUCTURE.md` — Module layout

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DialectStrategy` protocol in `src/db/dialects/protocol.py` — GenericDialect must implement all 8 members
- `register_dialect()`/`get_dialect()` in `src/db/dialects/registry.py` — GenericDialect registers here
- `GenericConnectionConfig` dataclass already exists in `src/config.py` with `dialect` and `sqlalchemy_url` fields
- `resolve_env_vars()` in `src/config.py` — Reusable for URL credential resolution

### Established Patterns
- Frozen dataclasses for all config models
- `get_logger(__name__)` for structured logging
- Module-level constants in SCREAMING_SNAKE_CASE
- Lazy imports not yet used — this phase introduces the pattern for optional dependencies
- MssqlDialect in `src/db/dialects/mssql.py` as reference implementation

### Integration Points
- `ConnectionManager.connect()` currently only handles MSSQL connection flow — needs refactoring to route through dialect.create_engine()
- MCP tool layer in `src/mcp_server/schema_tools.py` — connect_database function signature changes here
- `pyproject.toml` dependencies section — structural change to optional extras
- `src/db/dialects/__init__.py` — Registration of GenericDialect

</code_context>

<specifics>
## Specific Ideas

- URL-scheme-to-dialect mapping should cover at minimum: mssql+pyodbc -> mssql, databricks -> databricks, postgresql/postgres -> generic, mysql -> generic, sqlite -> generic
- Warning message for unknown URL schemes should include actionable info (what the user can do if they want optimized support)
- The [all] extra is a convenience alias, not a new feature — just combines the others

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 10-genericdialect-tool-interface*
*Context gathered: 2026-04-14*
