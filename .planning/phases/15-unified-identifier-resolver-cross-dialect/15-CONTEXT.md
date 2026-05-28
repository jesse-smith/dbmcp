# Phase 15: Unified identifier resolver (cross-dialect) - Context

**Gathered:** 2026-05-28
**Status:** Ready for planning

<domain>
## Phase Boundary

One shared identifier resolver behind all five namespace-aware tools
(`list_schemas`, `list_tables`, `get_table_schema`, `get_sample_data`,
`get_column_info`). Dialect-aware depth parsing (Databricks=3, MSSQL=2,
generic=1), strict `table_name`↔explicit-param conflict detection, and a
per-dialect `default_schema` that replaces the hardcoded `schema_name="dbo"`.
Builds on Phase 14's IDENT-01 invariant (Databricks catalog always known
post-connect). Covers IDENT-03 → IDENT-07.

</domain>

<decisions>
## Implementation Decisions

### Resolver architecture
- **D-01:** Resolver lives in a new standalone module `src/db/identifiers.py` with a `resolve_identifier(...)` function. Parsing + conflict logic is dialect-agnostic and lives here; dialect-specific facts come from new `DialectStrategy` properties (see D-08, D-09).
- **D-02:** Resolver returns a frozen dataclass `ResolvedIdentifier(catalog: str | None, schema: str | None, table: str)` — typed, self-documenting, no positional misorder risk across 5 call sites.
- **D-03:** Invoked at each `@mcp.tool` boundary. Each tool calls the resolver, then passes already-normalized `(catalog, schema, table)` down to `MetadataService`. Service methods stop defaulting and consume resolved parts. Resolution stays in one layer; tools own user-input interpretation.

### Parsing & conflict rules (IDENT-03/04)
- **D-04:** Conflict = disagreement only. `table_name='sales.orders'` + `schema_name='sales'` → OK (agree). `+ schema_name='hr'` → error. Matches IDENT-04 literal wording; redundant-but-consistent input is allowed.
- **D-05:** Resolver raises `ValueError` (already mapped to error-response at every tool boundary). Messages name the specific conflict or depth, e.g. `Conflicting schema: table_name specifies 'hr' but schema_name='sales'` and `Databricks identifiers allow at most 3 parts (catalog.schema.table); got 4: a.b.c.d`. Do NOT introduce a new exception type — Phase 14 deferred the error-class cleanup to a separate tech-debt pass.
- **D-06:** Quoting/splitting strategy deferred to research. Researcher MUST check whether `sqlglot` (existing dependency) exposes a dialect-aware identifier parser to reuse before hand-rolling dot-splitting. Requirement: a table literally named `my.table` (quoted: `[my.table]`, `` `my.table` ``) must parse as one part, not two.

### Catalog gate & default schema (IDENT-05/06/07)
- **D-07:** `catalog` errors everywhere on non-Databricks. Resolver raises `ValueError` when `catalog` is passed on a dialect with max depth < 3. **Unify all five tools** — the 3 existing tools' `catalog` docstrings ("Ignored for non-Databricks dialects") change to *rejected*. ⚠ **Backward-incompatible**: `catalog` on MSSQL/generic goes from silently-ignored to error on `list_schemas`/`list_tables`/`get_table_schema`. Planner must size this behavior change.
- **D-08:** New `DialectStrategy.default_schema` property: MSSQL → `'dbo'`; generic → `None` (no default; engine/caller decides); Databricks → `None` at the property level, relying on the session/engine default schema (Databricks has no workspace-wide default — do not hardcode a name, per Phase 14's `'main'` warning).
- **D-09:** New `DialectStrategy.max_identifier_depth` (or equivalent) property: Databricks=3, MSSQL=2, generic=1. Feeds D-01 depth parsing.
- **D-10:** No-schema path: resolver returns `schema=None` for generic; metadata calls pass `schema=None` to the SQLAlchemy inspector, which uses the connection's default schema. No synthetic fallback.

### SC4 dbo sweep + tests
- **D-11:** Remove `schema_name="dbo"` from the 5 tool signatures AND the `MetadataService`/`query.py` methods they call (`src/db/metadata.py` lines ~731/781/817/833/852/1126; `src/db/query.py:81`). Defaults become `None`; resolver/`default_schema` supplies the value. Kills the hardcoded `dbo` so SQLite/Databricks never silently get `'dbo'`.
- **D-12:** SC2 shared test matrix = exhaustive parametrized unit tests on `resolve_identifier` (dialect × depth × conflict/agreement/catalog-gate), PLUS one thin parametrized test asserting each of the 5 tools routes through the resolver and surfaces its `ValueError` as an error response. Test the boundary, not duplicated logic 5×.

### Roadmap correction
- **D-13:** Fix the `src/tools/` → `src/mcp_server/` path slip in ROADMAP.md Phase 15 SC4 text as part of this phase. Real tool surface is `src/mcp_server/{schema,query,analysis}_tools.py`. **NOTE (research):** confirmed NO-OP — ROADMAP SC4 already reads `src/mcp_server/`; no `src/tools/` reference exists. No fix needed.

### Scope expansion (added 2026-05-28 during plan-checker revision)
- **D-14:** `find_pk_candidates` and `find_fk_candidates` (in `src/mcp_server/analysis_tools.py`, lines ~155/~260) become **full namespace-aware tools** alongside the original 5 — total now **7 tools**. User decision (2026-05-28) resolving the SC4-vs-D-11 tension: ROADMAP SC4 ("No tool signature in `src/mcp_server/` carries `schema_name='dbo'`") is categorical, and both tools carry the identical `schema_name="dbo"` default — the exact Databricks/SQLite bug IDENT-07 removes. Therefore both tools get: (a) `schema_name="dbo"` → `None` signature sweep (D-11 extended), (b) `table_name` depth-parsing through `resolve_identifier`, (c) the D-07 catalog gate, and (d) a `catalog` param (Databricks-only, errors on MSSQL/generic). The shared test matrix (D-12) extends to assert all **7** tools route through the resolver. This intentionally supersedes D-11's "5 tool" enumeration and SC1's "five" wording; the spirit (one resolver, no hardcoded `dbo`, categorical SC4) governs.

### Claude's Discretion
- Exact property names (`max_identifier_depth`, `default_schema`) and frozen-dataclass field naming.
- Test file placement/factoring (planner/executor call, per TESTING.md).
- Exact error-message phrasing (D-05 gives templates).

</decisions>

<specifics>
## Specific Ideas

- `get_sample_data` and `get_column_info` gain the `catalog` param (IDENT-05/06); the analysis/query tools currently lack it.
- The roadmap SC4 reads `src/tools/`; actual tools are in `src/mcp_server/`, and `dbo` defaults also live in `src/db/metadata.py` and `src/db/query.py` (D-11 scope).

</specifics>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Phase scope and requirements
- `.planning/ROADMAP.md` §Phase 15 — Success criteria, Depends-on Phase 14.
- `.planning/REQUIREMENTS.md` §IDENT-03..07 — Locked requirements.
- `.planning/phases/14-connect-time-hardening-databricks/14-CONTEXT.md` — IDENT-01 invariant, dialect-owned pattern, deferred error-class/naming cleanup this phase must NOT pull in.

### Existing code the planner must read
- `src/mcp_server/schema_tools.py` — `list_schemas`, `list_tables`, `get_table_schema` (existing `catalog` param + `schema_name="dbo"`).
- `src/mcp_server/query_tools.py` — `get_sample_data` (gains `catalog`; `schema_name="dbo"` at :27).
- `src/mcp_server/analysis_tools.py` — `get_column_info` (gains `catalog`; `schema_name="dbo"` at :29/:155/:260).
- `src/db/dialects/protocol.py` — `DialectStrategy` Protocol; add `default_schema` + depth properties here + 3 impls.
- `src/db/dialects/{mssql,databricks,generic}.py` — dialect impls.
- `src/db/metadata.py` — `dbo` defaults (~731/781/817/833/852/1126); Databricks catalog routing (lines 82-106, 293-303, 866-872).
- `src/db/query.py` :81 — `dbo` default.

### Project conventions
- `.planning/codebase/CONVENTIONS.md` — style, error-handling.
- `.planning/codebase/TESTING.md` — test placement, 85% coverage floor.

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- No identifier parser exists today — resolver is net-new (no migration of existing splitting logic).
- `DialectStrategy.quote_identifier` already encodes per-dialect quoting — reuse for D-06 quote-aware splitting if not using sqlglot.
- Every `@mcp.tool` already maps `ValueError → {"status":"error","error_message":...}` — resolver `ValueError`s surface cleanly with no new plumbing.

### Established Patterns
- Dialect-owned behavior (SQL, quoting, catalog) on `DialectStrategy` — `default_schema`/depth properties fit this pattern.
- `dialect.name == "databricks"` gating already used in `metadata.py` for catalog routing.

### Integration Points
- `src/db/identifiers.py` (new) — resolver + `ResolvedIdentifier`.
- `DialectStrategy` + 3 impls — new `default_schema` and depth properties.
- 5 tools in `src/mcp_server/` — call resolver at boundary, drop `dbo` defaults.
- `MetadataService`/`query.py` — drop `dbo` defaults, accept resolved parts/`None`.

</code_context>

<deferred>
## Deferred Ideas

- Error-class taxonomy (`ConfigurationError`) — Phase 14 deferred to a dedicated tech-debt pass; not this phase (D-05 stays `ValueError`).
- `list_catalogs`/`list_databases` tool — DISC-01 backlog.
- Row-limit naming / `sample_size` typing inconsistencies — deferred out of v2.1.

</deferred>

---

*Phase: 15-unified-identifier-resolver-cross-dialect*
*Context gathered: 2026-05-28*
