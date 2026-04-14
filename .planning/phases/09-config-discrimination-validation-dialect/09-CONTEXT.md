# Phase 9: Config Discrimination & Validation Dialect - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Users can configure non-MSSQL connections via TOML with typed per-dialect config models, and execute validated queries against any supported dialect. This phase adds the `dialect` discriminator field to TOML config, creates separate config dataclasses per dialect, and makes `validate_query()` dialect-aware. The connect_database tool interface is NOT changed (deferred to Phase 10).

</domain>

<decisions>
## Implementation Decisions

### Config Model Design
- **D-01:** Separate frozen dataclasses per dialect: `MssqlConnectionConfig`, `DatabricksConnectionConfig`, `GenericConnectionConfig`. Each has only the fields that dialect needs. No base class or inheritance — matches existing flat dataclass style.
- **D-02:** The `dialect` field in TOML is **always required** for every connection. This overrides CONF-01's original "default to mssql" spec — explicit over implicit. Existing configs must add `dialect = "mssql"`.
- **D-03:** Parse function reads `dialect` from each TOML connection table, then instantiates the correct typed config class based on that value.

### Backward Compatibility
- **D-04:** When a connection config omits `dialect`, raise a `ValueError` with actionable message: `Connection "X" missing required 'dialect' field. Add dialect = "mssql" for SQL Server connections.` Clear migration path, not a silent failure.
- **D-05:** The connect_database MCP tool signature stays unchanged in Phase 9. Old SQL Server-specific parameters remain. Tool interface simplification is Phase 10 (CONF-03).

### Field Validation
- **D-06:** Unrecognized fields in a connection config produce a warning log and are silently ignored. No hard failure on unknown fields — forgiving for users, catches nothing critical.

### Safe Procedure List
- **D-07:** Add `safe_procedures` property to `DialectStrategy` protocol. `MssqlDialect` returns the existing 22 sp_ frozenset. Other dialects return `frozenset()` (empty). Keeps dialect knowledge inside dialect implementations.
- **D-08:** Config-level SP allowlist extensions (`allowed_stored_procedures` in TOML) remain global — they apply to all dialects. Merged with `dialect.safe_procedures` at validation time.

### Validation Plumbing
- **D-09:** `validate_query()` accepts a `dialect` parameter as a **required** sqlglot dialect string (e.g., `"tsql"`, `"databricks"`). No default value — every caller must explicitly pass the dialect. Callers get the string from `DialectStrategy.sqlglot_dialect`.
- **D-10:** All existing test calls to `validate_query()` will be updated to pass `dialect="tsql"` explicitly. No test helper or fixture — direct and clear.
- **D-11:** Safe procedure checking in `validate_query()` also needs the dialect to determine which procedures are safe. The function will accept an additional `safe_procedures` parameter (frozenset) rather than reading from global state — keeps it pure.

### Claude's Discretion
- **D-12:** Internal structure of per-dialect config dataclass fields (which fields go where, naming) — Claude picks based on what each dialect actually needs.
- **D-13:** Whether `validate_query` takes `safe_procedures` as a separate param or bundles dialect+safe_procedures into a single object — Claude picks based on cleanest call sites.
- **D-14:** How `_parse_connections()` dispatches to per-dialect parsers (match/case, dict lookup, if/elif) — Claude picks based on existing patterns.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — CONF-01 (updated: dialect now required), CONF-02, VALID-01, VALID-02, VALID-03

### Existing Code (modification targets)
- `src/config.py` — Current `ConnectionConfig` flat dataclass, `_parse_connections()`, `AppConfig`
- `src/db/validation.py` — `validate_query()` with hardcoded `dialect="tsql"`, `SAFE_PROCEDURES` frozenset, `get_allowed_procedures()`
- `src/db/query.py` line 539 — Single production caller of `validate_query()`
- `src/db/dialects/protocol.py` — `DialectStrategy` protocol (needs `safe_procedures` property)
- `src/db/dialects/mssql.py` — `MssqlDialect` (needs `safe_procedures` implementation)
- `src/db/dialects/registry.py` — Dialect registry for config routing

### Test Files (validate_query callers)
- `tests/unit/test_validation.py` — Primary validation test suite (~20 calls)
- `tests/unit/test_validation_edge_cases.py` — Edge case fixtures (~8 calls)
- `tests/unit/test_query.py` — CTE and integration validation tests (~6 calls)
- `tests/compliance/test_nfr_compliance.py` — Compliance tests (~5 calls)

### Prior Phase Context
- `.planning/phases/08-dialect-protocol-mssql-extraction/08-CONTEXT.md` — Phase 8 decisions (protocol design, registry, extraction boundary)

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DialectStrategy` protocol with `sqlglot_dialect` property — ready for validation to consume
- Dialect registry (`register_dialect`/`get_dialect`) — can route config parsing by dialect name
- `DENIED_TYPES` dict in validation.py — dialect-independent (sqlglot AST types are the same across dialects)
- `_ENV_VAR_PATTERN` and `resolve_env_vars()` — reusable for all dialect configs
- `_DEFAULTS_BOUNDS` validation pattern — reusable for dialect-specific field bounds

### Established Patterns
- Frozen dataclasses for config models
- Module-level constants in SCREAMING_SNAKE_CASE
- `get_logger(__name__)` for structured logging
- Warning logs for non-critical config issues (existing pattern in `_validate_defaults`)
- `ValueError` for critical config problems (existing pattern)

### Integration Points
- `_parse_connections()` is the TOML→ConnectionConfig gateway — this becomes the dispatch point for per-dialect parsing
- `QueryService._execute_query_internal()` calls `validate_query()` — needs to thread dialect through
- `ConnectionManager` holds the dialect — can provide sqlglot_dialect string to callers
- MCP tool layer shouldn't need changes (Phase 9 keeps tool interface stable)

</code_context>

<specifics>
## Specific Ideas

- CONF-01 requirement should be updated to reflect "dialect always required" decision (override from original "default to mssql")
- The 22 MSSQL sp_ procedures move from module-level constant in validation.py to MssqlDialect.safe_procedures property
- validate_query() becomes fully pure — no reading from global config or module-level state

</specifics>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 09-config-discrimination-validation-dialect*
*Context gathered: 2026-04-14*
