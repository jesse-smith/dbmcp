# Phase 8: Dialect Protocol & MSSQL Extraction - Context

**Gathered:** 2026-04-13
**Status:** Ready for planning

<domain>
## Phase Boundary

Define a DialectStrategy protocol that abstracts dialect-specific behavior, extract all SQL Server-specific code into an MssqlDialect implementation, create a dialect registry, and verify zero behavior regression. This phase does NOT add new dialects (Generic/Databricks come in Phases 10-11) or change the connect_database tool interface (Phase 10).

</domain>

<decisions>
## Implementation Decisions

### Protocol Design
- **D-01:** Use `typing.Protocol` (structural subtyping) for DialectStrategy. No ABC. This is the first abstract pattern in the codebase — Protocol fits the existing dataclass-oriented, lightweight style.
- **D-02:** Capability flags are bool properties on the protocol (e.g., `supports_indexes: bool`, `has_fast_row_counts: bool`). Not an enum set.
- **D-03:** Protocol methods match ROADMAP spec: `name`, `sqlglot_dialect`, `create_engine`, `fast_row_counts`, `quote_identifier`, plus capability flag properties. No additions at this stage — additional methods can be added in later phases.

### Extraction Boundary
- **D-04:** `azure_auth.py` moves into the dialect package, co-located with MssqlDialect code.

### Registry & Resolution
- **D-05:** Simple dict registry mapping dialect name strings to DialectStrategy classes. Module-level dict with `register_dialect()` and `get_dialect()` functions.
- **D-06:** Unknown dialect names raise an error in Phase 8. GenericDialect fallback will be added in Phase 10. Fail-fast over silent misconfiguration.

### Claude's Discretion
- **D-07:** How optional features signal "not supported" (return None vs guard with capability flag) — Claude picks based on cleanest call sites.
- **D-08:** How ConnectionManager splits with dialect (dialect owns engine creation vs ConnectionManager delegates to dialect) — Claude picks based on cleanest separation of concerns.
- **D-09:** How DMV queries survive extraction (move to MssqlDialect vs stay in MetadataService behind dialect checks) — Claude picks based on three-tier query strategy alignment.
- **D-10:** Module layout within `src/db/dialects/` — Claude picks between subpackage (`mssql/`) vs flat files based on volume of MSSQL-specific code being extracted.
- **D-11:** Whether dialect files live at `src/db/dialects/` (under db package, recommended) or `src/dialects/` (top-level) — Claude picks based on existing codebase organization.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Project Context
- `.planning/PROJECT.md` — Core value, three-tier query strategy, milestone goals
- `.planning/REQUIREMENTS.md` — DIAL-01 through DIAL-05, META-05, TEST-01 requirement details
- `.planning/ROADMAP.md` — Phase 8 success criteria and dependency chain

### Existing Code (extraction sources)
- `src/db/connection.py` — ConnectionManager with MSSQL-specific ODBC string building, Azure AD token handling, pool config
- `src/db/metadata.py` — MetadataService with Inspector + DMV dual approach, dialect_name attribute
- `src/db/validation.py` — validate_query() currently hardcodes no dialect to sqlglot.parse()
- `src/db/azure_auth.py` — Entirely MSSQL-specific (pyodbc token attachment, AzureTokenProvider)
- `src/db/query.py` — QueryService with MSSQL-specific elements
- `src/config.py` — TOML config with MSSQL-specific connection fields

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md` — MCS pattern, layer responsibilities
- `.planning/codebase/CONVENTIONS.md` — Naming patterns, type hint style, import organization

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `MetadataService.dialect_name` attribute already exists — can be leveraged for dialect-aware branching during transition
- `PoolConfig` dataclass in connection.py is dialect-agnostic — can remain as-is
- `DENIED_TYPES` dict and validation logic in `validation.py` is already dialect-agnostic (pure sqlglot AST)

### Established Patterns
- Dataclasses for data structures (not Pydantic)
- StrEnum for enum types
- Module-level constants in SCREAMING_SNAKE_CASE
- `get_logger(__name__)` for structured logging
- Type hints with `str | None` union syntax (Python 3.10+)
- No existing Protocol/ABC usage — this introduces the first one

### Integration Points
- `ConnectionManager.connect()` is the primary entry point that will need to accept/use a dialect
- `MetadataService.__init__()` receives an Engine — dialect info may need to flow through here
- `validate_query()` will need a dialect parameter (VALID-01, but that's Phase 9 scope)
- MCP tool functions in `src/mcp_server/` call services — shouldn't need changes in Phase 8 if interfaces stay stable

</code_context>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches. User wants structural subtyping (Protocol), simple dict registry, and co-located MSSQL code. All implementation detail decisions deferred to Claude's judgment.

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 08-dialect-protocol-mssql-extraction*
*Context gathered: 2026-04-13*
