# Phase 11: DatabricksDialect - Context

**Gathered:** 2026-04-14
**Status:** Ready for planning

<domain>
## Phase Boundary

Implement DatabricksDialect with token authentication, catalog-aware metadata, table property exposure, and partition info surfacing. This phase delivers: (1) DatabricksDialect implementing DialectStrategy with databricks-sqlalchemy engine construction, (2) metadata tools working across all three dialects with optional catalog parameter for Databricks, (3) Databricks table properties surfaced in get_table_schema, (4) index section conditionally omitted when dialect doesn't support indexes.

</domain>

<decisions>
## Implementation Decisions

### Engine & Auth
- **D-01:** Use databricks-sqlalchemy + databricks-sql-connector as the Databricks driver stack. Both packages go in the `[databricks]` optional extra in pyproject.toml.
- **D-02:** DatabricksDialect.create_engine() builds a `databricks://token:{token}@{host}?http_path={path}&catalog={catalog}&schema={schema}` URL from DatabricksConnectionConfig fields. Token resolved via `resolve_env_vars()` at connection time.
- **D-03:** Missing databricks packages surface at connection time via lazy import with clear error message (same pattern as MssqlDialect with pyodbc): `"Databricks support requires databricks-sqlalchemy. Install with: pip install dbmcp[databricks]"`
- **D-04:** DatabricksDialect capability flags: `supports_indexes=False` (Databricks has no traditional indexes), `has_fast_row_counts=False` (no DMV equivalent), `safe_procedures=frozenset()` (no stored procedures).
- **D-05:** DatabricksDialect.sqlglot_dialect returns `"databricks"` for query validation.
- **D-06:** DatabricksDialect.quote_identifier uses backtick quoting (`` `identifier` ``), matching Databricks SQL syntax.

### Table Properties
- **D-07:** Extend existing get_table_schema response with optional Databricks-specific fields: `owner`, `storage_format`, `table_type_detail` (MANAGED/EXTERNAL), `created_time`, `location`. These are populated via DESCRIBE EXTENDED for Databricks connections, absent for other dialects.
- **D-08:** No new MCP tool — all table metadata stays in get_table_schema as single source of truth.

### Catalog Namespace
- **D-09:** Connection config sets a default catalog (DatabricksConnectionConfig.catalog, defaults to "main"). This is used when no catalog is explicitly passed to tool calls.
- **D-10:** list_schemas, list_tables, and get_table_schema gain an optional `catalog` parameter. For Databricks, it overrides the connection's default catalog. For MSSQL and generic, it is ignored.
- **D-11:** Databricks table identifiers in responses use three-level format: `catalog.schema.table`. MSSQL/generic continue using `schema.table`.
- **D-12:** Cross-catalog navigation (querying across catalogs without reconnecting) is enabled via the optional catalog parameter. Full cross-catalog discovery (ENRICH-02) is deferred to a future phase.

### Metadata Gating
- **D-13:** When dialect.supports_indexes is False, the `indexes` key is omitted entirely from get_table_schema response (not an empty list). Missing key = "not supported" vs empty list = "none exist" — clearer semantic signal for LLM agents.
- **D-14:** Partition columns surfaced as a `partition_columns` list in the get_table_schema response for Databricks tables. Omitted for non-Databricks dialects or non-partitioned tables.

### Claude's Discretion
- **D-15:** Internal structure of DatabricksDialect class (how DESCRIBE EXTENDED is parsed, error handling for missing properties) — Claude picks based on cleanest implementation.
- **D-16:** How MetadataService routes to DESCRIBE EXTENDED for Databricks vs Inspector for others — Claude picks based on existing dialect-branching patterns.
- **D-17:** How the optional `catalog` parameter threads through MetadataService to Inspector calls — Claude picks based on cleanest plumbing.
- **D-18:** ConnectionManager.connect_with_config() routing for DatabricksConnectionConfig (replacing the current NotImplementedError) — Claude picks based on existing GenericConnectionConfig routing pattern.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — DIAL-03, META-01, META-02, META-03, META-04 requirement details

### Existing Code (modification targets)
- `src/db/dialects/protocol.py` — DialectStrategy protocol (DatabricksDialect must implement)
- `src/db/dialects/registry.py` — register_dialect(), resolve_dialect_from_url(), _URL_SCHEME_TO_DIALECT already maps "databricks"
- `src/db/dialects/__init__.py` — Registration point for DatabricksDialect
- `src/db/dialects/mssql.py` — Reference implementation for dialect pattern (lazy import, create_engine structure)
- `src/db/dialects/generic.py` — Reference implementation for simpler dialect
- `src/config.py` — DatabricksConnectionConfig already defined (host, http_path, catalog, schema_name, token)
- `src/db/connection.py` lines 380-419 — connect_with_config() has NotImplementedError placeholder for DatabricksConnectionConfig
- `src/db/metadata.py` — MetadataService with dialect branching, Inspector-based metadata
- `src/mcp_server/schema_tools.py` — list_schemas, list_tables, get_table_schema tool signatures (need optional catalog param)
- `src/models/schema.py` — Table/Column/Index models (may need optional fields for Databricks properties)
- `pyproject.toml` — Empty `[databricks]` extras group to populate

### Prior Phase Context
- `.planning/phases/08-dialect-protocol-mssql-extraction/08-CONTEXT.md` — Protocol design, registry, capability flags
- `.planning/phases/09-config-discrimination-validation-dialect/09-CONTEXT.md` — Config models, validation dialect-awareness
- `.planning/phases/10-genericdialect-tool-interface/10-CONTEXT.md` — GenericDialect pattern, tool interface, lazy imports, dependency extras

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md` — MCS pattern, layer responsibilities
- `.planning/codebase/CONVENTIONS.md` — Naming patterns, dataclass style
- `.planning/codebase/STRUCTURE.md` — Module layout

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DialectStrategy` protocol with 8 members — DatabricksDialect implements same interface
- `MssqlDialect` in `src/db/dialects/mssql.py` — Reference for lazy import pattern (pyodbc), create_engine structure, capability flags
- `GenericDialect` in `src/db/dialects/generic.py` — Reference for simpler dialect with URL-based engine
- `DatabricksConnectionConfig` in `src/config.py` — Already defined with correct fields
- `_parse_databricks_connection()` in `src/config.py` — Already implemented
- `resolve_env_vars()` in `src/config.py` — Reusable for token credential resolution
- `_URL_SCHEME_TO_DIALECT` in registry already maps `"databricks": "databricks"`
- `connect_with_url()` in ConnectionManager — Pattern for URL-based connections (used by GenericDialect)

### Established Patterns
- Lazy import with clear error message (MssqlDialect pyodbc pattern)
- Frozen dataclasses for config models
- Capability flag properties on dialect classes (bool properties, not enum sets)
- MetadataService dialect branching via `self._dialect` attribute
- TOON-encoded responses with optional fields (absent = not applicable)

### Integration Points
- `ConnectionManager.connect_with_config()` — Replace NotImplementedError for DatabricksConnectionConfig
- `MetadataService.__init__()` — Receives dialect via constructor, already uses it for branching
- `src/db/dialects/__init__.py` — Register DatabricksDialect in registry
- `pyproject.toml` [databricks] extra — Populate with databricks-sqlalchemy, databricks-sql-connector
- MCP tool signatures — Add optional catalog parameter to 3 schema tools

</code_context>

<specifics>
## Specific Ideas

- databricks-sqlalchemy URL format: `databricks://token:{token}@{host}?http_path={path}&catalog={catalog}&schema={schema}`
- Partition columns are a first-class Databricks concept replacing traditional indexes — surface them where indexes would normally appear
- DESCRIBE EXTENDED output is key-value text that needs parsing — the dialect should encapsulate this parsing
- Blocker flagged in STATE.md: "databricks-sqlalchemy Inspector may raise non-SQLAlchemy exceptions" — research agent should investigate this

</specifics>

<deferred>
## Deferred Ideas

- **ENRICH-02**: Full cross-catalog schema discovery and switching within a single Databricks connection — future milestone
- **ENRICH-01**: Unity Catalog tag metadata (PII classification, data domain, ownership) — future milestone

</deferred>

---

*Phase: 11-databricksdialect*
*Context gathered: 2026-04-14*
