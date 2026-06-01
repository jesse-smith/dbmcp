# Feature Status Registry

Central registry of all features and their current status.

| Feature ID | Name | Branch | Status | Merged Date | Notes |
|------------|------|--------|--------|-------------|-------|
| 001 | DB Schema Explorer | `001-db-schema-explorer` | Complete | 2026-02-02 | All 11 phases implemented |
| 002 | Example Notebooks | `002-example-notebooks` | Archived | 2026-01-20 | Workflow changed: notebooks now tracked in 001 |
| 003 | Speckit Workflow Integration | `003-speckit-workflow-integration` | Complete | 2026-01-26 | Tooling feature - no spec docs |
| 003 | Allow CTE Queries | `003-allow-cte-queries` | Complete | 2026-02-03 | CTE+SELECT queries, DDL blocklist |
| 004 | Azure AD Integrated Auth | `004-azure-ad-integrated-auth` | Complete | 2026-02-26 | Token-based Azure AD auth via azure-identity |
| 005 | Denylist Query Validation | `005-denylist-query-validation` | Complete | 2026-02-26 | AST-based sqlglot validation, 22 safe stored procs |
| 006 | Codebase Refactor | `006-codebase-refactor` | Complete | 2026-02-27 | 5 module splits, test consolidation, cognitive complexity reduction |
| 007 | Data-Exposure Analysis Tools | `007-analysis-tools` | Complete | 2026-03-03 | Column stats, PK/FK candidate discovery |
| 008 | TOON Response Format Migration | (GSD v1.0 — archived) | Complete | 2026-03-05 | GSD milestone v1.0 (phases 1–2). All 9 tools → TOON + staleness guard. Detail in `docs/archive/gsd-planning/` |
| 009 | Concern Handling | (GSD v1.1 — archived) | Complete | 2026-03-10 | GSD milestone v1.1 (phases 3–7). Cleared 10 v1.0 audit concerns; TOML config; 70% coverage floor. Archive: `docs/archive/gsd-planning/` |
| 010 | Multi-Dialect Support | (GSD v2.0 — archived) | Complete | 2026-05-06 | GSD milestone v2.0 (phases 8–13.1). DialectStrategy: MSSQL/Databricks/Generic; 85% floor. Archive: `docs/archive/gsd-planning/` |
| 011 | Databricks Identifier Fixes | (GSD v2.1 — archived) | Complete | 2026-05-31 | GSD milestone v2.1 (phases 14–15.1). Unified resolver, catalog-required connect, cross-catalog targeting (CR-02). Archive: `docs/archive/gsd-planning/` |

> **Migration note (2026-06-01):** rows 008–011 summarize four milestones built under the
> GSD orchestrator before the project returned to spec-kit. Their feature dirs are condensed
> reconstructions; the complete GSD working set is frozen at
> [`docs/archive/gsd-planning/`](../docs/archive/gsd-planning/). The earlier duplicate `003`
> rows predate this migration and are left as-is.

## Cross-cutting registries

spec-kit tracks state per-feature; these sibling files hold project-wide context that has no
native home in spec-kit (carried forward from GSD):

- [`TECH-DEBT.md`](./TECH-DEBT.md) — open, actionable fixes not yet in code (3 todos + 7 Phase-15.1 follow-ups).
- [`BACKLOG.md`](./BACKLOG.md) — deferred future feature scope (catalog enumeration, cross-catalog FK, ca_bundle promotion).
- [`LEARNINGS.md`](./LEARNINGS.md) — durable project operating lessons (the live-warehouse rule was promoted into the constitution).

## Status Definitions

- **Draft**: Initial specification, not yet approved
- **In Progress**: Active development on feature branch
- **Complete**: All tasks finished, merged to main
- **Archived**: Feature closed without full implementation (see Notes)

## Usage

When completing a feature branch merge:

1. Run `/speckit.complete` to update this registry
2. Add status headers to spec.md, plan.md, tasks.md
3. Commit the status updates
