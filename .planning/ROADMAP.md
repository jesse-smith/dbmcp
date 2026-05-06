# Roadmap: dbmcp

## Milestones

- ✅ **v1.0 TOON Response Format Migration** — Phases 1-2 (shipped 2026-03-05) · [archive](milestones/v1.0-ROADMAP.md)
- ✅ **v1.1 Concern Handling** — Phases 3-7 (shipped 2026-03-10) · [archive](milestones/v1.1-ROADMAP.md)
- ✅ **v2.0 Multi-Dialect Support** — Phases 8-13.1 (shipped 2026-05-06) · [archive](milestones/v2.0-ROADMAP.md)

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

## Progress

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1-2 | v1.0 | 5/5 | Complete | 2026-03-05 |
| 3-7 | v1.1 | 11/11 | Complete | 2026-03-10 |
| 8-13.1 | v2.0 | 20/20 | Complete | 2026-05-06 |

## Backlog

### Phase 999.1: API consistency pass across MCP tools (BACKLOG)

**Goal:** Normalize the 9 tool signatures so users get predictable arg names, defaults, and capabilities across all dialects. Surfaced while validating v2.0 against live Databricks (post-phase 13.1); deliberately deferred from v2.0 scope.
**Captured:** 2026-05-06
**Source:** live Databricks verification after /gsd-validate-phase 13.1 + /gsd-quick 260506-n8s

**Inconsistencies to resolve:**

1. **`catalog` kwarg coverage gap.** Present on `list_schemas`, `list_tables`, `get_table_schema`. Missing on `get_sample_data`, `get_column_info`, `find_pk_candidates`, `find_fk_candidates`. Databricks/Unity-Catalog users can list/describe cross-catalog but cannot sample/analyze cross-catalog without reconnecting. User-visible impact.

2. **Hardcoded `schema_name: str = "dbo"` default.** Baked into `get_table_schema`, `get_sample_data`, `get_column_info`, `find_pk_candidates`, `find_fk_candidates`. MSSQL-ism that is never correct for Databricks/Postgres and nonsensical for SQLite. Consider dialect-aware default (e.g., via `ConnectionManager.get_dialect(connection_id).default_schema`) or drop the default and require the caller to specify.

3. **Row-limit naming.** `list_tables`→`limit`, `find_fk_candidates`→`limit`, `execute_query`→`row_limit`. Same concept, two names. Pick one (likely `row_limit` since it is explicit about units).

4. **`sample_size` typing.** `get_sample_data: int | None = None` (default resolved indirectly) vs `get_column_info: int = 10` (explicit default). Different conventions for an identical parameter.

**Success Criteria:**
1. Any tool that takes `schema_name` also accepts `catalog: str | None = None` (or the `catalog` concept is reframed as part of a connection/selector primitive).
2. Zero hardcoded `"dbo"` defaults on public tool signatures.
3. Single consistent name + typing convention for row-limit and sample-size parameters across all tools.
4. Regression tests cover Databricks cross-catalog sample + analysis paths.

**Not in v2.0:** v2.0 shipped dialect strategy + wiring; this is API-surface polish that does not belong in a milestone retroactively.
