# Roadmap: dbmcp

## Milestones

- ✅ **v1.0 TOON Response Format Migration** — Phases 1-2 (shipped 2026-03-05) · [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Concern Handling** — Phases 3-7 (shipped 2026-03-10) · [archive](milestones/v1.1-ROADMAP.md)
- ✅ **v2.0 Multi-Dialect Support** — Phases 8-13.1 (shipped 2026-05-06) · [archive](milestones/v2.0-ROADMAP.md)
- ✅ **v2.1 Databricks identifier fixes** — Phases 14-15.1 (shipped 2026-05-31) · [archive](milestones/v2.1-ROADMAP.md)

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

<details>
<summary>✅ v2.1 Databricks identifier fixes (Phases 14-15.1) — SHIPPED 2026-05-31</summary>

- [x] Phase 14: Connect-time hardening (Databricks) (4/4 plans) — completed 2026-05-28
- [x] Phase 15: Unified identifier resolver (cross-dialect) (6/6 plans) — completed 2026-05-29
- [x] Phase 15.1: Cross-catalog metadata threading — CR-02 / IDENT-08 (6/6 plans, INSERTED) — completed 2026-05-29

</details>

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-2 | v1.0 | 5/5 | Complete | 2026-03-05 |
| 3-7 | v1.1 | 11/11 | Complete | 2026-03-10 |
| 8-13.1 | v2.0 | 20/20 | Complete | 2026-05-06 |
| 14-15.1 | v2.1 | 16/16 | Complete | 2026-05-31 |

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
