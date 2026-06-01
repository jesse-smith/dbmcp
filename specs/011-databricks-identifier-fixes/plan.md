# Implementation Plan: Databricks Identifier Fixes

> **STATUS: COMPLETE** | Merged: 2026-05-31 | Branch: (GSD milestone v2.1 — archived)

**Origin**: GSD milestone **v2.1** (Phases 14–15.1, 16 plans, shipped 2026-05-31).
Condensed summary; full detail in
[`docs/archive/gsd-planning/milestones/v2.1-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v2.1-ROADMAP.md),
`v2.1-MILESTONE-AUDIT.md`, and `RETROSPECTIVE.md`.

## Summary

Harden Databricks connect-time behavior, build one shared identifier resolver for all seven
namespace-aware tools, then (in an inserted decimal phase) thread the resolved catalog into
real cross-catalog metadata targeting. The code review of Phase 15 revealed it only *gated*
`catalog` rather than *threading* it — the CR-02 gap — which Phase 15.1 closed using stateless
raw 3-part SQL instead of session-mutating `USE CATALOG`.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: SQLAlchemy, sqlglot, databricks-sqlalchemy, existing stack
**Project Type**: MCP server
**Constraints**: read-only; preserve tool interfaces (except the deliberate breaking
catalog-required change); 85% coverage floor.
**New modules**: `src/db/identifiers.py` (resolver + catalog gate), `src/analysis/_sql.py`
(`CatalogAwareReflector`).

## Key Decisions

- **Breaking change: require catalog at Databricks connect time** (IDENT-01) — clear fail-fast
  over mysterious downstream wrong-catalog failures.
- **Single shared resolver across all 7 tools** (IDENT-03) — DRY; depth via `len(Table.parts)`,
  never `Table.name/db/catalog` (sqlglot pitfall).
- **Disagreement-only conflict detection** (IDENT-04) — redundant-but-consistent params allowed;
  contradictions error. Not "most-specific-wins."
- **Per-dialect `default_schema`** replaces hardcoded `"dbo"` (IDENT-07).
- **Catalog gate runs BEFORE the depth check** — a catalog on a shallow dialect reports the gate
  message, not a confusing depth error.
- **Cross-catalog targeting via stateless raw 3-part SQL, no `USE CATALOG`** (IDENT-08) — bypasses
  the catalog-blind Inspector; no per-connection session state, safe on pooled connections.
- **Shared `CatalogAwareReflector`** (Rule of Three: PK + FK + column-stats consumers).
- **FK target enumeration scoped to resolved catalog only** — KISS; cross-catalog FK targets
  deferred (the one "— Pending" decision; now [`BACKLOG.md`](../BACKLOG.md) BL-02).
- **`quote_tsql_identifier()` + backtick escaping** (CR-01/WR-04) — defense at the quoting boundary.

## Phases

- **14 — Connect-time hardening (Databricks)** (4 plans): catalog-required connect, `list_schemas`
  fallback removal, four live-UAT threat fixes (catalog bypass, conn-id collision, URL catalog ignored).
- **15 — Unified identifier resolver (cross-dialect)** (6 plans): `resolve_identifier`, dialect-aware
  depth, conflict detection, `catalog` param on sample/column tools, `default_schema`, D-12 boundary matrix.
- **15.1 — Cross-catalog metadata threading (CR-02 / IDENT-08)** (6 plans, INSERTED): `CatalogAwareReflector`,
  stateless 3-part SQL for PK/FK/column-stats, security hardening, live cross-catalog UAT.

## Constitution Check

PASS — single resolver (DRY), Rule-of-Three on the reflector, TDD (depth-via-parts and
gate-before-depth both driven by failing tests against documented sqlglot pitfalls), live
cross-catalog UAT satisfies the Principle III live-warehouse rule. The Phase 15→15.1 split is
the source of [`LEARNINGS.md`](../LEARNINGS.md) L-02 ("gate it" vs "support it").
