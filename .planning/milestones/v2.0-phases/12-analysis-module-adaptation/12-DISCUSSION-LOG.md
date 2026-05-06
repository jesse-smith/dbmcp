# Phase 12: Analysis Module Adaptation - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-15
**Phase:** 12-analysis-module-adaptation
**Areas discussed:** SQL transpilation strategy, Type classification, Databricks fast path, Constraint semantics
**Mode:** Advisor mode (minimal_decisive calibration, 4 parallel research agents)

---

## SQL Transpilation Strategy

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: Inspector + Transpiled SQL | Inspector for constraints (Tier 1), sqlglot.transpile() for aggregates (Tier 2), dialect-specific for Tier 3 | :heavy_check_mark: |
| Dialect-specific query methods | Add ~15 query methods per dialect to DialectStrategy protocol | |

**User's choice:** Hybrid (Recommended)
**Notes:** Aligns with existing three-tier query strategy. Avoids bloating DialectStrategy with analysis-specific methods. Analysis logic stays in analysis module.

---

## Type Classification

| Option | Description | Selected |
|--------|-------------|----------|
| SQLAlchemy isinstance() checks | Use Inspector TypeEngine objects with isinstance() against type hierarchy | :heavy_check_mark: |
| Per-dialect type string sets | Maintain separate NUMERIC_TYPES/DATETIME_TYPES/STRING_TYPES per dialect | |

**User's choice:** isinstance() checks (Recommended)
**Notes:** SQLAlchemy handles dialect-specific type mapping automatically. Zero maintenance for new dialects. Replaces hardcoded MSSQL type sets entirely.

---

## Databricks Fast Path

| Option | Description | Selected |
|--------|-------------|----------|
| Always try fast path first (probe) | Try DESCRIBE EXTENDED on first column; if stats present, use for all; else fall back to Tier 2 batch | :heavy_check_mark: |
| Check condition before attempting | Require flag/heuristic to decide whether to try DESCRIBE EXTENDED | |

**User's choice:** Always try fast path first
**Notes:** Key discovery: DESCRIBE EXTENDED has no batch support (1 query per column). Probe-first-column heuristic avoids N+1 queries when stats absent. Also confirmed ANLYS-05 (partition metadata) already complete from Phase 11.

---

## Constraint Semantics

| Option | Description | Selected |
|--------|-------------|----------|
| Report informational + gate indexes | Report Databricks informational constraints as constraint-backed with context; omit target_has_index when supports_indexes=False | :heavy_check_mark: |

**User's choice:** Yes, both (Recommended)
**Notes:** Follows Phase 11 pattern for capability gating. Inspector used for generic dialect constraints. INTERSECT confirmed universal — no transpilation needed.

---

## Claude's Discretion

- Internal refactoring of analysis class constructors
- ColumnStatsCollector fast path vs Tier 2 code path structure
- Whether to add AnalysisQueryBuilder helper for sqlglot transpilation
- Column existence check adaptation approach

## Deferred Ideas

- ANLYS-06: Histogram data from Databricks ANALYZE TABLE stats
- ANLYS-07: Cross-dialect type normalization display mapping
- Databricks JSON format for DESCRIBE EXTENDED (DBR 16.2+ only)
