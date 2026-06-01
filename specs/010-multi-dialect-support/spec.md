# Feature Specification: Multi-Dialect Support

> **STATUS: COMPLETE** | Merged: 2026-05-06 | Branch: (GSD milestone v2.0 — archived)

**Origin**: GSD milestone **v2.0** (Phases 8–13.1). Condensed summary reconstructed on the
return to spec-kit (2026-06-01). Full per-phase detail in the frozen archive at
[`docs/archive/gsd-planning/milestones/v2.0-ROADMAP.md`](../../docs/archive/gsd-planning/milestones/v2.0-ROADMAP.md).

## Summary

Extend dbmcp from a SQL Server-only server to a **three-dialect** MCP server — MSSQL,
Databricks, and Generic SQLAlchemy — behind a `DialectStrategy` protocol, with optimized
Databricks paths (catalog awareness, DESCRIBE EXTENDED, Tier-3 precomputed stats),
dialect-aware query validation, and test fixtures that exercise every dialect path.

## User Scenarios & Testing

### User Story 1 — Connect to any supported database (P1)

An operator connects to MSSQL, Databricks, or any SQLAlchemy URL using one simplified
`connect_database` interface, with a required `dialect` discriminator in config.

**Acceptance:** `connect_database` takes `connection_name | sqlalchemy_url`; pyodbc +
azure-identity live in the `mssql` extra, databricks packages in the `databricks` extra,
with lazy imports and clear error messages when an extra is missing.

### User Story 2 — Dialect-aware metadata & analysis (P1)

Schema, sample, and analysis tools return correct results per dialect, including Databricks
three-level namespace (catalog.schema.table) and partition metadata.

**Acceptance:** three-tier query strategy (Inspector → TSQL+sqlglot transpile →
dialect-specific); Databricks DESCRIBE EXTENDED property parsing; Tier-3 precomputed-stats
fast path; `supports_indexes` capability gating omits index data where it doesn't apply.

### User Story 3 — Dialect-aware query validation (P2)

The read-only safety validator parses and validates queries per dialect without weakening
the denylist.

**Acceptance:** sqlglot parse accepts a dialect parameter; safe-procedure list is
dialect-aware (MSSQL `sp_` / empty elsewhere); denylist unchanged across dialects.

## Requirements (all validated — v2.0)

- FR-001 — Multi-dialect support via `DialectStrategy` protocol.
- FR-002 — Databricks dialect with optimized stats/reflections.
- FR-003 — Generic dialect fallback for arbitrary SQLAlchemy databases.
- FR-004 — Simplified `connect_database` interface (connection_name / sqlalchemy_url).
- FR-005 — Discriminated TOML config with **required** `dialect` field (adjusted from default-to-mssql per D-02).
- FR-006 — SQLAlchemy Inspector-based metadata (Tier 1).
- FR-007 — Standard SQL analysis with sqlglot transpilation (Tier 2).
- FR-008 — Dialect-specific optimizations (Tier 3).
- FR-009 — Optional dependency groups (`mssql`, `databricks` extras) with lazy imports.
- FR-010 — Dialect-aware query validation (sqlglot parse + per-dialect safe-procedure list).
- FR-011 — Databricks three-level namespace + DESCRIBE EXTENDED table properties.
- FR-012 — Dialect-parameterized test fixtures; coverage floor raised to 85%.

## Success Criteria

- SC-001 — All existing MSSQL behavior preserved through the Phase 8 extraction.
- SC-002 — 872 tests across all three dialect paths; baseline coverage 90.64% (85% floor).
- SC-003 — Adding a new dialect = one file in `src/db/dialects/` + registry entry + optional extra.

## Out of Scope

- Pydantic migration for data models — current dataclasses work fine.
- Query result caching / result-set versioning — future milestone.
- Audit logging of query execution — future milestone.
