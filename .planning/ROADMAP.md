# Roadmap: dbmcp

## Milestones

- ✅ **v1.0 TOON Response Format Migration** — Phases 1-2 (shipped 2026-03-05) · [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Concern Handling** — Phases 3-7 (shipped 2026-03-10) · [archive](milestones/v1.1-ROADMAP.md)
- ✅ **v2.0 Multi-Dialect Support** — Phases 8-13.1 (shipped 2026-05-06) · [archive](milestones/v2.0-ROADMAP.md)
- ◆ **v2.1 Databricks identifier fixes** — Phases 14-15 (in progress)

## Phases

<details>
<summary>✅ v1.0 TOON Response Format Migration (Phases 1-2) — SHIPPED 2026-03-05</summary>

- [x] Phase 1: Atomic TOON Migration (3/3 plans) — completed 2026-03-04
- [x] Phase 2: Staleness Guard (2/2 plans) — completed 2026-03-05

</details>

<details>
<summary>✅ v1.1 Concern Handling (Phases 3-7) — SHIPPED 2026-03-10</summary>

- [x] Phase 3: Code Quality & Test Coverage (3/3 plans) — completed 2026-03-09
- [x] Phase 4: Connection Management (2/2 plans) — completed 2026-03-09
- [x] Phase 5: Security Hardening (2/2 plans) — completed 2026-03-09
- [x] Phase 6: Serialization & Configuration (2/2 plans) — completed 2026-03-10
- [x] Phase 7: Wire Orphaned Exports (2/2 plans) — completed 2026-03-10

</details>

<details>
<summary>✅ v2.0 Multi-Dialect Support (Phases 8-13.1) — SHIPPED 2026-05-06</summary>

- [x] Phase 8: Dialect Protocol & MSSQL Extraction (3/3 plans) — completed 2026-04-14
- [x] Phase 9: Config Discrimination & Validation Dialect (2/2 plans) — completed 2026-04-14
- [x] Phase 10: GenericDialect & Tool Interface (3/3 plans) — completed 2026-04-14
- [x] Phase 11: DatabricksDialect (2/2 plans) — completed 2026-04-15
- [x] Phase 12: Analysis Module Adaptation (2/2 plans) — completed 2026-04-15
- [x] Phase 13: Test Infrastructure & Coverage (4/4 plans) — completed 2026-04-27
- [x] Phase 13.1: Close v2.0 Gap — wiring + tech debt (4/4 plans, INSERTED) — completed 2026-05-06

</details>

### ◆ v2.1 Databricks identifier fixes (Phases 14-15) — IN PROGRESS

#### Phase 14: Connect-time hardening (Databricks)

**Goal:** Make `connect_database` strict about the Databricks catalog, remove the silent catalog-listing fallback in `list_schemas`, and close the residual regression-test gaps from the 2026-05-05 audit.

**Requirements covered:** IDENT-01, IDENT-02, TEST-01, TEST-02

**Success Criteria:**

1. Databricks connection via URL or named config without a catalog fails fast in `connect_database` with an error that includes the accessible-catalog list from `SHOW CATALOGS`.
2. `list_schemas` on Databricks never returns catalog names in place of schemas — the old fallback code is gone and a targeted test asserts the pre-IDENT-01 failure mode no longer reoccurs.
3. `test_env_var_substitution_for_catalog_and_schema` passes: env-var placeholders in Databricks `catalog` / `schema_name` resolve before engine creation.
4. `test_sqlalchemy_error_wrapped_as_connection_error` passes: `SQLAlchemyError` from `DatabricksDialect.create_engine` surfaces as `ConnectionError` with the host string.
5. Full test suite green; no existing MSSQL/generic tests regress.

**Plans:** 4/4 plans complete

- [x] 14-01-PLAN.md — Dialect layer: remove "main" fallbacks, add catalog guard in create_engine, add list_catalogs method
- [x] 14-02-PLAN.md — Metadata cleanup: delete _list_databricks_catalogs fallback, rename _databricks_default_catalog → _engine_catalog
- [x] 14-03-PLAN.md — Connect layer: add _require_databricks_catalog helper, wire into URL + config paths, fix line 499 "main" fallback (D-18)
- [x] 14-04-PLAN.md — Regression + closure tests: IDENT-01 (3 cases), IDENT-02 (no SHOW CATALOGS lock), TEST-01, TEST-02

#### Phase 15: Unified identifier resolver (cross-dialect)

**Goal:** Land one shared identifier resolver used by all five namespace-aware tools. Dialect-aware depth (3/2/1), strict conflict detection between `table_name` and explicit params, dialect-aware default schema.

**Requirements covered:** IDENT-03, IDENT-04, IDENT-05, IDENT-06, IDENT-07

**Success Criteria:**

1. `list_tables`, `list_schemas`, `get_table_schema`, `get_sample_data`, `get_column_info` all parse `table_name` per dialect depth and route through the shared resolver. Extra parts → clear error.
2. Conflicts between leading segments in `table_name` and the matching explicit param (`catalog` or `schema_name`) produce a named-conflict error across all five tools. Covered by a shared test matrix.
3. `get_sample_data` and `get_column_info` each expose a `catalog` parameter (Databricks-only; MSSQL/generic error on its presence). `bmtct.ml_infections_ref.mv_fever_episodes` and equivalents work end-to-end without `USE CATALOG` workarounds.
4. No tool signature in `src/mcp_server/` carries `schema_name: str = "dbo"`. A `default_schema` property on `DialectStrategy` supplies the fallback per connected dialect.
5. Full test suite green; 85% coverage floor maintained.

**Depends on:** Phase 14 (IDENT-01 lets the resolver assume catalog is always known post-connect for Databricks).

**Plans:** 6/6 plans complete

Plans:

- [x] 15-01-PLAN.md — Add default_schema + max_identifier_depth properties to DialectStrategy + 3 impls (IDENT-03/07)
- [x] 15-02-PLAN.md — dbo signature sweep in MetadataService/QueryService (SC4 service half, IDENT-07)
- [x] 15-03-PLAN.md — TDD: resolve_identifier + ResolvedIdentifier + shared catalog-gate in src/db/identifiers.py (IDENT-03/04/07)
- [x] 15-04-PLAN.md — Route 3 schema tools through resolver/shared gate; drop dbo; catalog Ignored→rejected (IDENT-03/04/07)
- [x] 15-05-PLAN.md — Add catalog to get_sample_data + get_column_info; resolver routing; SC3 3-part SQL (IDENT-05/06)
- [x] 15-06-PLAN.md — D-14: find_pk/fk_candidates → full namespace-aware tools; dbo sweep + resolver + catalog; D-12 matrix → 7 tools (IDENT-03/04/07)

#### Phase 15.1: Cross-catalog metadata threading (CR-02 / DISC-01) (INSERTED)

**Goal:** Thread the resolved catalog (`ResolvedIdentifier.catalog`) through to actual cross-catalog targeting for `find_pk_candidates`, `find_fk_candidates`, and `get_column_info` (column-stats) on Databricks, so an explicit non-default `catalog` reflects metadata FROM that catalog instead of silently returning the connection-default result (the CR-02 silent mis-targeting bug). The default-catalog path and the MSSQL/generic catalog gate remain unchanged. Mechanism: bypass the catalog-blind SQLAlchemy Inspector with stateless raw 3-part SQL (no `USE CATALOG`), reusing the established `MetadataService` pattern via a shared `CatalogAwareReflector` helper.

**Requirements covered:** IDENT-08 (PROPOSED — see note below)

**Success Criteria:**

1. `find_pk_candidates`, `find_fk_candidates`, and `get_column_info` (column-stats) called with an explicit non-default Databricks `catalog` return metadata FROM that catalog (columns/constraints/stats), not the connection default.
2. FK target-table enumeration is scoped to the resolved catalog (no target search in the default catalog).
3. The DESCRIBE EXTENDED fast path in column stats is catalog-scoped (3-part) alongside the aggregate path.
4. No `USE CATALOG` is emitted on any cross-catalog path (stateless 3-part names only); a unit test guards this.
5. Default-catalog path unchanged (Inspector still used); MSSQL/generic catalog gate unchanged (resolver still rejects).
6. Full suite green; coverage ≥ 85%; live cross-catalog UAT (bmtct → cerner_src) recorded in 15.1-UAT.md.

**Depends on:** Phase 15

**Plans:** 3/6 plans executed

Plans:

- [x] 15.1-01-PLAN.md — Extract shared CatalogAwareReflector helper (DESCRIBE TABLE columns + SHOW TABLES IN) in src/analysis/_sql.py (TDD)
- [x] 15.1-02-PLAN.md — Thread catalog through PKDiscovery (3-part _qualified_table + reflector reads) (TDD)
- [ ] 15.1-03-PLAN.md — Thread catalog through FKCandidateSearch (source + target scoped to resolved catalog) (TDD)
- [x] 15.1-04-PLAN.md — Thread catalog through ColumnStatsCollector (aggregate + DESCRIBE-EXTENDED fast path) (TDD)
- [ ] 15.1-05-PLAN.md — Wire catalog + cross-catalog existence check into all 3 tool entry points; full-suite/coverage gate (TDD)
- [ ] 15.1-06-PLAN.md — Live cross-catalog UAT (bmtct → cerner_src) via dbmcp-test; record 15.1-UAT.md (autonomous: false)

**Cross-cutting constraints:**

- Default-catalog path unchanged; no USE CATALOG emitted.

> **IDENT-08 proposed wording** (pending user ratification before REQUIREMENTS.md edit): "`find_pk_candidates`, `find_fk_candidates`, and the `get_column_info` column-statistics path actually TARGET the resolved Databricks catalog (not the connection default) when a non-default `catalog` is supplied. When the requested catalog differs from the connection default and cross-catalog targeting is achievable, results come from the requested catalog; the silent mis-targeting documented as CR-02 is eliminated. The default-catalog path and the MSSQL/generic catalog gate are unchanged."

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-2 | v1.0 | 5/5 | Complete | 2026-03-05 |
| 3-7 | v1.1 | 11/11 | Complete | 2026-03-10 |
| 8-13.1 | v2.0 | 20/20 | Complete | 2026-05-06 |
| 14-15 | v2.1 | 10/10 (+15.1: 0/6) | In Progress | — |

## Backlog

### DISC-01: Cross-dialect catalog/database enumeration tool (FUTURE)

**Goal:** Add a `list_catalogs`/`list_databases` tool that enumerates server-visible databases (MSSQL: `sys.databases`) or catalogs (Databricks: `SHOW CATALOGS`). Informational on MSSQL — listed entries may not be queryable from the current connection due to login scope.

**Captured:** 2026-05-08 (during v2.1 scoping)
**Source:** tangent from v2.1 design discussion — see `.planning/notes/2026-05-08-think-cross-dialect-catalog-enumeration.md`

**Why deferred:** pure additive feature, independent of the resolver refactor. Can share the `SHOW CATALOGS` helper introduced in Phase 14 (IDENT-01) once that lands.

### Deferred: Cross-catalog FK targets (different catalog than source)

**Captured:** 2026-05-29 (Phase 15.1 planning, RESEARCH Open Q1). Phase 15.1 scopes FK target enumeration to the resolved catalog only (KISS). Allowing FK targets in a *different* catalog than the source is deferred — not in v2.1.

---

_Former "Phase 999.1 API consistency pass" backlog item consumed into v2.1 scope on 2026-05-08. `catalog` kwarg coverage and `"dbo"` default are now IDENT-05/06/07. Row-limit naming and `sample_size` typing inconsistencies from that backlog item are deferred — not in v2.1._
