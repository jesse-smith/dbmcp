# Tasks: Multi-Dialect Support

> **STATUS: COMPLETE** | Merged: 2026-05-06 | Branch: (GSD milestone v2.0 — archived)

**Origin**: GSD milestone **v2.0**, 7 phases (6 + 13.1 inserted) / 20 plans, all complete.
Condensed checklist; per-plan detail and 12 quick-task records in
[`docs/archive/gsd-planning/milestones/v2.0-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v2.0-ROADMAP.md).

## Phase 8 — Dialect Protocol & MSSQL Extraction (3 plans)

- [X] Define `DialectStrategy` protocol (`src/db/dialects/protocol.py`) + registry-backed dispatch.
- [X] Extract existing MSSQL behavior into `MssqlDialect` with zero behavior change.

## Phase 9 — Config Discrimination & Validation Dialect (2 plans)

- [X] Discriminated TOML config with required `dialect` field (D-02).
- [X] Dialect-aware query validation (sqlglot parse + per-dialect safe-procedure list).

## Phase 10 — GenericDialect & Tool Interface (3 plans)

- [X] `GenericDialect` fallback for arbitrary SQLAlchemy URLs.
- [X] Simplify `connect_database` to `connection_name | sqlalchemy_url`; relocate extras + lazy imports.

## Phase 11 — DatabricksDialect (2 plans)

- [X] `DatabricksDialect`: three-level namespace, DESCRIBE EXTENDED parsing, partition metadata.
- [X] Tier-3 precomputed-stats fast path (probe-first-column heuristic).

## Phase 12 — Analysis Module Adaptation (2 plans)

- [X] Cross-dialect column stats + PK/FK discovery via TSQL-base + sqlglot transpilation.
- [X] `supports_indexes` capability gating (`target_has_index=None` when unsupported).

## Phase 13 — Test Infrastructure & Coverage (4 plans)

- [X] Dialect-parameterized fixtures (generic + Databricks mock-based, no live connections required).
- [X] Ratchet coverage floor 70 → 85 (baseline 90.64%); 872 tests across all dialect paths.

## Phase 13.1 — Close v2.0 Gap (4 plans, INSERTED)

- [X] WIRING-01/02/03: thread the registered dialect through connect_database, get_sample_data, ConnectionManager.connect.
- [X] quick 260506-n8s: move sample-query SQL into `DialectStrategy.build_sample_query`.
- [X] Reconcile tech debt (TD-01..04 from the 2026-05-05 audit).

**Outcome:** 3 dialects shipped; 20 plans + 12 quick-tasks over 23 days. The quick-task pileup
during live Databricks verification is the source of LEARNINGS L-01 (live-smoke-gate).
