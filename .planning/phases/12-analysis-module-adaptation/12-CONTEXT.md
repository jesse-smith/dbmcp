# Phase 12: Analysis Module Adaptation - Context

**Gathered:** 2026-04-15
**Status:** Ready for planning

<domain>
## Phase Boundary

Make all three analysis tools (get_column_info, find_pk_candidates, find_fk_candidates) work across MSSQL, Databricks, and generic dialects. Deliver: (1) dialect-aware column statistics using hybrid Inspector + transpiled SQL approach, (2) Databricks Tier 3 fast path reading precomputed stats from DESCRIBE EXTENDED, (3) dialect-aware PK/FK candidate discovery using Inspector for constraints and capability-gated index metadata, (4) SQLAlchemy isinstance()-based type classification replacing hardcoded MSSQL type sets.

ANLYS-05 (partition metadata in schema responses) was already completed in Phase 11 — no additional work needed.

</domain>

<decisions>
## Implementation Decisions

### SQL Transpilation Strategy
- **D-01:** Hybrid approach following three-tier query strategy: Tier 1 (Inspector) for constraint/index metadata discovery, Tier 2 (sqlglot.transpile()) for standard SQL aggregate queries, Tier 3 (dialect-specific methods) only for Databricks precomputed stats.
- **D-02:** Analysis logic stays in the analysis module (column_stats.py, pk_discovery.py, fk_candidates.py). DialectStrategy protocol is NOT extended with analysis query methods — avoids bloating the protocol with 15+ query methods.
- **D-03:** sqlglot.transpile() handles cross-dialect syntax: SELECT TOP N → LIMIT N, DATEDIFF/LEN/CAST function mapping, identifier quoting. Base queries written in standard SQL, transpiled to target dialect at runtime.
- **D-04:** Small hand-coded dialect branches (~2-3) for system-table queries that genuinely don't transpile (sys.indexes DMV for MSSQL, Inspector fallback for others). Isolated to metadata helper methods.

### Type Classification
- **D-05:** Replace hardcoded MSSQL type string sets (NUMERIC_TYPES, DATETIME_TYPES, STRING_TYPES) with SQLAlchemy isinstance() checks against TypeEngine hierarchy. Inspector's get_columns() returns proper type objects.
- **D-06:** Type categories via isinstance: numeric = `(types.Integer, types.Numeric)`, datetime = `(types.DateTime, types.Date)`, string = `(types.String)`, other = everything else. SQLAlchemy handles dialect-specific mappings automatically (e.g., MSSQL MONEY → Numeric, Databricks STRING → String).
- **D-07:** ColumnStatsCollector receives Inspector type objects instead of raw type strings. The _get_type_category() method signature changes from `(data_type: str)` to accepting TypeEngine instances.

### Databricks Fast Path
- **D-08:** DESCRIBE EXTENDED fast path: probe the first column with `DESCRIBE EXTENDED catalog.schema.table column_name`. If precomputed stats are present (min, max, num_nulls, distinct_count), use fast path for all remaining columns. If stats absent, fall back to Tier 2 batch SQL aggregates for all columns.
- **D-09:** DESCRIBE EXTENDED returns per-column stats as key-value pairs (col_name=stat name, data_type=stat value). Stats only present when ANALYZE TABLE has been run or Predictive Optimization auto-ran it. No batch support — one query per column.
- **D-10:** Databricks DESCRIBE EXTENDED column stats parsing is dbmcp-custom work — databricks-sqlalchemy does not expose this through Inspector. Parser handles graceful fallback when stats are absent (null/empty result).
- **D-11:** ANLYS-05 (partition metadata) is already complete from Phase 11 — partition_columns is already returned in get_table_schema responses. Phase 12 marks ANLYS-05 as done, no implementation needed.

### Constraint Semantics
- **D-12:** Databricks informational constraints (PK, UNIQUE) are reported as constraint-backed in find_pk_candidates results — they exist in INFORMATION_SCHEMA.TABLE_CONSTRAINTS even though ENFORCED='NO'. Response should note informational nature so LLM agents understand the distinction.
- **D-13:** target_has_index field in find_fk_candidates is gated by dialect.supports_indexes — omitted entirely when supports_indexes=False (same pattern as Phase 11 index gating in get_table_schema). Not an empty/false value — absent = "not supported".
- **D-14:** Generic dialect PK/FK discovery uses SQLAlchemy Inspector (get_pk_constraint(), get_unique_constraints()) instead of INFORMATION_SCHEMA raw SQL. MSSQL retains existing INFORMATION_SCHEMA queries.
- **D-15:** INTERSECT syntax is universal across MSSQL, Databricks, and PostgreSQL — no transpilation needed for FK overlap queries.

### Claude's Discretion
- **D-16:** Internal refactoring of analysis class constructors (how Inspector/dialect/connection are threaded through) — Claude picks based on cleanest integration.
- **D-17:** How ColumnStatsCollector splits between fast path and Tier 2 code paths internally — Claude picks based on testability and clarity.
- **D-18:** Whether to add a thin AnalysisQueryBuilder helper for sqlglot transpilation or inline transpile calls — Claude picks based on whether the pattern repeats enough to warrant abstraction.
- **D-19:** How column existence checks adapt (currently INFORMATION_SCHEMA) — Claude picks between Inspector.get_columns() or transpiled query based on what's cleaner.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — ANLYS-01 through ANLYS-05 requirement details (note: ANLYS-05 already complete from Phase 11)

### Existing Code (modification targets)
- `src/analysis/column_stats.py` — ColumnStatsCollector with MSSQL-specific SQL, type sets, bracket quoting
- `src/analysis/pk_discovery.py` — PKDiscovery with INFORMATION_SCHEMA queries, bracket quoting
- `src/analysis/fk_candidates.py` — FKCandidateSearch with sys.indexes DMV, STRING_SPLIT, bracket quoting
- `src/mcp_server/analysis_tools.py` — MCP tool wrappers that instantiate analysis classes
- `src/models/analysis.py` — ColumnStatistics, PKCandidate, FKCandidateData, FKCandidateResult models
- `src/db/dialects/protocol.py` — DialectStrategy protocol (supports_indexes, quote_identifier used by analysis)
- `src/db/dialects/databricks.py` — DatabricksDialect (DESCRIBE EXTENDED parsing reference from Phase 11)
- `src/db/metadata.py` — MetadataService with Inspector usage patterns and _parse_databricks_table_properties

### Prior Phase Context
- `.planning/phases/08-dialect-protocol-mssql-extraction/08-CONTEXT.md` — Protocol design, capability flags
- `.planning/phases/10-genericdialect-tool-interface/10-CONTEXT.md` — GenericDialect, Inspector-only metadata
- `.planning/phases/11-databricksdialect/11-CONTEXT.md` — DESCRIBE EXTENDED parsing, supports_indexes gating, catalog awareness

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md` — MCS pattern, layer responsibilities
- `.planning/codebase/CONVENTIONS.md` — Naming patterns, dataclass style
- `.planning/codebase/STRUCTURE.md` — Module layout

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `DialectStrategy.quote_identifier()` — Replaces hardcoded `[bracket]` quoting in all analysis SQL
- `DialectStrategy.supports_indexes` — Gates target_has_index in FK candidates (established pattern from Phase 11)
- `MetadataService._parse_databricks_table_properties()` — Reference for DESCRIBE EXTENDED parsing pattern
- SQLAlchemy Inspector — `get_columns()`, `get_pk_constraint()`, `get_unique_constraints()` for dialect-agnostic metadata
- sqlglot — Already in dependencies for query validation, transpile() function available

### Established Patterns
- Capability flag gating: omit fields when not supported (Phase 11 index gating)
- Dialect branching via `self._dialect` attribute in MetadataService
- TOON-encoded responses with optional fields (absent = not applicable)
- Frozen dataclasses for data models
- asyncio.to_thread() wrapping synchronous DB calls in MCP tools

### Integration Points
- ColumnStatsCollector, PKDiscovery, FKCandidateSearch constructors need dialect/Inspector plumbing
- analysis_tools.py _sync_work() functions need to pass dialect context to analysis classes
- ConnectionManager provides both Engine and dialect access
- Models in src/models/analysis.py may need optional fields for enforcement context

</code_context>

<specifics>
## Specific Ideas

- The probe-first-column heuristic for Databricks fast path: try DESCRIBE EXTENDED on column 1, if stats present use fast path for all, otherwise batch via Tier 2 — avoids N+1 queries when stats are absent
- DESCRIBE EXTENDED column output format: rows of (col_name=stat name, data_type=stat value) with keys "min", "max", "num_nulls", "distinct_count", "avg_col_len", "max_col_len"
- Research flag from STATE.md: "sqlglot transpilation coverage for analysis query patterns needs empirical validation" — researcher should validate that sqlglot handles the specific function mappings (DATEDIFF, LEN, STDEV, CAST) between tsql/databricks/generic
- INFORMATION_SCHEMA.TABLE_CONSTRAINTS works on Databricks with ENFORCED='NO' for informational constraints

</specifics>

<deferred>
## Deferred Ideas

- **ANLYS-06**: Histogram data from Databricks ANALYZE TABLE stats — deferred to future milestone
- **ANLYS-07**: Cross-dialect type normalization display mapping — deferred to future milestone
- Databricks JSON format for DESCRIBE EXTENDED (stable but requires DBR 16.2+) — text format sufficient for now

</deferred>

---

*Phase: 12-analysis-module-adaptation*
*Context gathered: 2026-04-15*
