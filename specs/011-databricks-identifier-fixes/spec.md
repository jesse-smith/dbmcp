# Feature Specification: Databricks Identifier Fixes

> **STATUS: COMPLETE** | Merged: 2026-05-31 | Branch: (GSD milestone v2.1 — archived)

**Origin**: GSD milestone **v2.1** (Phases 14–15.1). Condensed summary reconstructed on the
return to spec-kit (2026-06-01). Full per-phase detail in the frozen archive at
[`docs/archive/gsd-planning/milestones/v2.1-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v2.1-ROADMAP.md)
and `v2.1-MILESTONE-AUDIT.md`.

## Summary

Fix Databricks catalog handling and unify 3-part identifier resolution across all seven
namespace-aware MCP tools, then thread the resolved catalog through to **real cross-catalog
metadata targeting** — eliminating the CR-02 silent mis-targeting bug. **Breaking change by
design:** catalog-less Databricks connections now fail fast with a clear, catalog-listing
error.

## User Scenarios & Testing

### User Story 1 — Fail fast on catalog-less Databricks connections (P1)

A user connecting to Databricks without a catalog gets an immediate, actionable error listing
accessible catalogs — not a mysterious downstream failure against the session default.

**Acceptance (IDENT-01/02):** `connect_database` rejects catalog-less Databricks connections
(URL or named config) with a `SHOW CATALOGS`-listing error; the silent catalog-listing
fallback in `list_schemas` is removed and guarded by a negative-assertion regression test.

### User Story 2 — Consistent identifier resolution across all tools (P1)

Every namespace-aware tool parses a dotted `table_name` to the correct depth for its dialect
and errors clearly on conflicts or over-depth input.

**Acceptance (IDENT-03/04):** one shared resolver (`src/db/identifiers.py`) parses at
dialect-aware depth (Databricks=3, MSSQL=2, generic=1) with disagreement-only conflict
detection between dotted segments and explicit `catalog`/`schema_name`; depth measured via
`len(Table.parts)`; over-depth produces a named error.

### User Story 3 — Correct cross-catalog metadata targeting (P1)

On Databricks, an explicit non-default `catalog` actually targets that catalog's metadata for
PK/FK candidates and column stats.

**Acceptance (IDENT-08, Phase 15.1):** these paths target the resolved catalog via stateless
raw 3-part SQL (shared `CatalogAwareReflector`, no `USE CATALOG`), bypassing the catalog-blind
Inspector. Verified live (bmtct → cerner_src, 7/7 cross-catalog UAT with negative controls,
no stale-catalog bleed on pooled connections).

## Requirements (all validated — v2.1)

- IDENT-01 — `connect_database` rejects catalog-less Databricks connections, listing accessible catalogs.
- IDENT-02 — `list_schemas` no longer silently returns catalog names; fallback removed + guarded.
- IDENT-03 — All 7 namespace-aware tools parse dotted `table_name` per dialect depth; error on extra parts.
- IDENT-04 — Conflicting explicit `schema_name`/`catalog` vs `table_name` segments produce a named-conflict error.
- IDENT-05 — `get_sample_data` accepts a `catalog` param on Databricks; errors on MSSQL/generic.
- IDENT-06 — `get_column_info` accepts a `catalog` param on Databricks; errors on MSSQL/generic.
- IDENT-07 — Per-dialect `default_schema` on `DialectStrategy`; no signature hardcodes `"dbo"`.
- IDENT-08 — PK/FK candidates + column-stats target the resolved non-default catalog via stateless 3-part SQL; CR-02 eliminated.
- TEST-01 — Regression test for env-var substitution on `catalog`/`schema_name` in `connect_with_config`.
- TEST-02 — Regression test for `SQLAlchemyError` → `ConnectionError` wrapping on the Databricks connect path.

## Success Criteria

- SC-001 — CR-02 silent mis-targeting bug eliminated, proven by live cross-catalog UAT.
- SC-002 — 1072 tests; 85% coverage floor maintained.
- SC-003 — 16/16 security threats resolved (backtick + TSQL-bracket injection closed: CR-01, WR-04).

## Deferred at close

See [`specs/TECH-DEBT.md`](../TECH-DEBT.md) (TD-01/02/03) and [`specs/BACKLOG.md`](../BACKLOG.md)
(BL-02 cross-catalog FK targets, BL-03 cross-dialect ca_bundle). The two substantive items are
documented as accepted tech debt in the passed v2.1 milestone audit.
