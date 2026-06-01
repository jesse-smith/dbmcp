# Tasks: Databricks Identifier Fixes

> **STATUS: COMPLETE** | Merged: 2026-05-31 | Branch: (GSD milestone v2.1 — archived)

**Origin**: GSD milestone **v2.1**, 3 phases (14, 15, 15.1 inserted) / 16 plans, all complete.
Condensed checklist; per-plan detail and 14 quick-task records in
[`docs/archive/gsd-planning/milestones/v2.1-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v2.1-ROADMAP.md).

## Phase 14 — Connect-time hardening, Databricks (4 plans)

- [X] IDENT-01: `connect_database` rejects catalog-less Databricks connections with a `SHOW CATALOGS` list.
- [X] IDENT-02: remove the silent catalog-listing fallback in `list_schemas`; guard with a negative-assertion test.
- [X] Live-UAT threat fixes: catalog-default bypass, connection_id collision across catalogs, URL catalog ignored.

## Phase 15 — Unified identifier resolver, cross-dialect (6 plans)

- [X] IDENT-03: shared `resolve_identifier` (`src/db/identifiers.py`) — dialect-aware depth via `len(Table.parts)`.
- [X] IDENT-04: disagreement-only conflict detection between dotted segments and explicit params.
- [X] IDENT-05/06: add `catalog` param to `get_sample_data` / `get_column_info` (Databricks-gated).
- [X] IDENT-07: per-dialect `default_schema`; remove every hardcoded `"dbo"`.
- [X] Route all 7 namespace-aware tools through the resolver (D-12 boundary matrix); catalog gate before depth check.

## Phase 15.1 — Cross-catalog metadata threading, CR-02 / IDENT-08 (6 plans, INSERTED)

- [X] IDENT-08: `CatalogAwareReflector` (`src/analysis/_sql.py`) — stateless raw 3-part SQL, no `USE CATALOG`.
- [X] Target the resolved catalog for `find_pk_candidates`, `find_fk_candidates`, and column stats.
- [X] Security: backtick escaping (CR-01), `quote_tsql_identifier()` for FK generation (WR-04) — 16/16 threats.
- [X] Live cross-catalog UAT (bmtct → cerner_src), 7/7 with negative controls, no stale-catalog bleed.

## Tests (TEST-01/02)

- [X] TEST-01: env-var substitution on `catalog`/`schema_name` in `connect_with_config`.
- [X] TEST-02: `SQLAlchemyError` → `ConnectionError` wrapping on the Databricks connect path.

**Outcome:** CR-02 eliminated; 1072 tests; 85% floor; 16 plans + 14 quick-tasks over 25 days.
Non-blocking Phase 15.1 code-review follow-ups carried to [`TECH-DEBT.md`](../TECH-DEBT.md) (TD-03).
