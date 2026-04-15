---
phase: 12-analysis-module-adaptation
plan: 01
subsystem: analysis
tags: [column-stats, dialect-aware, transpilation, databricks, isinstance-types]
dependency_graph:
  requires: [Phase 11 dialect infrastructure]
  provides: [dialect-aware ColumnStatsCollector, transpile_query helper, updated analysis models]
  affects: [get_column_info MCP tool, analysis module constructors]
tech_stack:
  added: []
  patterns: [sqlglot transpilation, isinstance type classification, Inspector-based column discovery, DESCRIBE EXTENDED fast path]
key_files:
  created:
    - src/analysis/_sql.py
  modified:
    - src/analysis/column_stats.py
    - src/analysis/pk_discovery.py
    - src/analysis/fk_candidates.py
    - src/analysis/__init__.py
    - src/models/analysis.py
    - src/mcp_server/analysis_tools.py
    - tests/unit/test_column_stats.py
    - tests/staleness/tool_invoker.py
decisions:
  - Unified _get_type_category accepts both TypeEngine and str for backward compat
  - Probe-first-column heuristic for Databricks fast path avoids N+1 queries
  - String-based type sets retained as _NUMERIC_TYPES_STR fallback when Inspector unavailable
metrics:
  duration: 13min
  completed: 2026-04-15
  tasks: 3
  files: 9
---

# Phase 12 Plan 01: Column Stats Dialect Adaptation Summary

Dialect-aware ColumnStatsCollector using sqlglot transpilation, isinstance() type classification, Inspector-based column discovery, and Databricks DESCRIBE EXTENDED fast path with probe-first-column heuristic.

## What Was Done

### Task 1: Transpilation helper, model updates, constructor changes
- Created `src/analysis/_sql.py` with `transpile_query()` -- TSQL base queries pass through unchanged for MSSQL, transpiled via sqlglot for other dialects
- Added `constraint_enforced: bool | None = None` to PKCandidate model (Databricks informational constraints)
- Changed `FKCandidateData.target_has_index` from `bool` to `bool | None = None` with conditional `to_dict()` inclusion
- Updated all three analysis class constructors (ColumnStatsCollector, PKDiscovery, FKCandidateSearch) to accept `dialect` and `inspector` optional params
- Exported `transpile_query` from `src/analysis/__init__.py`

### Task 2: ColumnStatsCollector dialect-aware refactoring (TDD)
- Replaced hardcoded MSSQL type string sets (NUMERIC_TYPES, DATETIME_TYPES, STRING_TYPES) with isinstance() checks against SQLAlchemy TypeEngine hierarchy
- Added MONEY/SMALLMONEY name-based fallback since they don't inherit from Numeric
- Added Inspector-based `column_exists()`, `get_columns_by_pattern()`, `get_column_data_type()` methods (with INFORMATION_SCHEMA fallback when no inspector)
- Wrapped all SQL query methods with `transpile_query(sql, self._dialect)` for cross-dialect support
- Added dialect-branched datetime time component detection: HOUR/MINUTE/SECOND for Databricks/generic, CAST AS TIME for MSSQL
- Implemented Databricks DESCRIBE EXTENDED fast path (`_try_describe_extended_stats`, `_build_stats_from_describe_extended`)
- Implemented probe-first-column heuristic in `get_columns_info()` for bulk fast path decisions
- Added 23 new tests across TestTypeClassification, TestInspectorColumnDiscovery, TestDatabricksFastPath, TestTranspilation classes

### Task 3: Wire get_column_info MCP tool
- Updated `get_column_info` in `analysis_tools.py` to pass `dialect` and `inspector` to ColumnStatsCollector
- Replaced INFORMATION_SCHEMA table existence check with `inspector.get_table_names()` (dialect-agnostic)
- Updated staleness test mock infrastructure to handle Inspector-based flow
- `find_pk_candidates` and `find_fk_candidates` left unchanged (deferred to Plan 02)

## Deviations from Plan

None -- plan executed exactly as written. All three tasks were found already implemented in prior feature branch commits (1e55fda through 2adde50). Verification confirmed all acceptance criteria met and full test suite passing.

## Verification Results

- `uv run pytest tests/unit/test_column_stats.py -x -q`: 45 passed
- `uv run pytest tests/unit/test_analysis_models.py -x -q`: 29 passed
- `uv run pytest tests/ -x -q`: 830 passed, 41 skipped
- `uv run ruff check src/analysis/ src/models/analysis.py src/mcp_server/analysis_tools.py`: All checks passed

## Commits

| Task | Commit | Message |
|------|--------|---------|
| 1 | 1e55fda | feat(12-01): create transpilation helper, update models and analysis constructors |
| 2 (RED) | 5ec8525 | test(12-01): add failing tests for dialect-aware column stats |
| 2 (GREEN) | d999559, ea47ed6 | feat(12-01): refactor ColumnStatsCollector for dialect-aware queries |
| 3 | 33ba219, 2adde50 | feat(12-01): wire get_column_info MCP tool with dialect and inspector |

## Self-Check: PASSED

All 9 key files verified present. All 6 commit hashes verified in git log.
