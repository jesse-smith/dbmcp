# Implementation Plan: Multi-Dialect Support

> **STATUS: COMPLETE** | Merged: 2026-05-06 | Branch: (GSD milestone v2.0 — archived)

**Origin**: GSD milestone **v2.0** (Phases 8–13.1, 20 plans, shipped 2026-05-06).
Condensed summary; full detail in
[`docs/archive/gsd-planning/milestones/v2.0-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v2.0-ROADMAP.md),
`v2.0-MILESTONE-AUDIT.md`, and `RETROSPECTIVE.md`.

## Summary

Introduce a `DialectStrategy` protocol (strategy over inheritance) with MssqlDialect,
DatabricksDialect, and GenericDialect implementations and registry-backed dispatch. Write
base SQL in TSQL and transpile per-dialect via sqlglot rather than hand-writing N variants.
An audit after Phase 13 surfaced three wiring gaps + tech debt, closed by the inserted
decimal phase 13.1 rather than opening a new milestone.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: SQLAlchemy, sqlglot, pyodbc (`mssql` extra), databricks-sqlalchemy +
azure-identity (`databricks`/`mssql` extras), toon_format
**Project Type**: MCP server
**Constraints**: read-only; preserve all 9 tool interfaces; 85% coverage floor (ratcheted from 70%).

## Architecture — three-tier query strategy

1. **Tier 1** — SQLAlchemy Inspector for canonical metadata (with MSSQL `INFORMATION_SCHEMA` fallback).
2. **Tier 2** — TSQL-base analysis SQL transpiled per-dialect via sqlglot.
3. **Tier 3** — dialect-specific optimizations (Databricks DESCRIBE EXTENDED precomputed stats).

## Key Decisions

- **DialectStrategy protocol over inheritance** — least coupling; each dialect self-contained.
- **Dialect required in TOML config, no `mssql` default** (D-02) — explicit failure over silent
  cross-dialect misconfiguration (one integration test would have failed silently in prod).
- **TSQL + sqlglot transpile** — one canonical query form instead of N hand-written variants.
- **`supports_indexes` capability flag** — omit index data on Databricks without `isinstance` checks.
- **`build_sample_query` on the strategy** (quick 260506-n8s) — moved dialect-specific SQL out of
  QueryService; no more TSQL-as-default for non-MSSQL paths.
- **Lazy imports** guarded with `try/except ImportError` → actionable error when an extra is missing.
- **Coverage floor 70 → 85** (Phase 13) — single global knob, ~5pt headroom over 90.64% baseline.
- **Audit-driven decimal-phase insertion (13.1)** — standard gap-closure pattern.

## Phases

- **8** Dialect Protocol & MSSQL Extraction (3) · **9** Config Discrimination & Validation Dialect (2)
- **10** GenericDialect & Tool Interface (3) · **11** DatabricksDialect (2)
- **12** Analysis Module Adaptation (2) · **13** Test Infrastructure & Coverage (4)
- **13.1** Close v2.0 Gap — wiring (WIRING-01/02/03) + tech debt (4, INSERTED)

## Constitution Check

PASS — strategy pattern (Simplicity/composition); TSQL-transpile + capability flags (DRY);
TDD throughout; D-02 required-field embodies fail-fast. **Note:** the live-warehouse
validation rule (now Principle III) originates from this milestone — see
[`specs/LEARNINGS.md`](../LEARNINGS.md) L-01.
