---
phase: 12-analysis-module-adaptation
plan: 01
subsystem: analysis
tags: [sqlglot, sqlalchemy, transpilation, databricks, column-stats, isinstance, inspector]

requires:
  - phase: 11-databricks-dialect
    provides: DialectStrategy protocol with sqlglot_dialect property, DatabricksDialect, GenericDialect
provides:
  - Dialect-aware ColumnStatsCollector with transpiled SQL queries
  - Shared transpile_query() helper for TSQL-to-dialect transpilation
  - Databricks DESCRIBE EXTENDED fast path for precomputed column stats
  - isinstance-based type classification replacing hardcoded string sets
  - Inspector-based column discovery methods
  - Updated PKCandidate.constraint_enforced and FKCandidateData.target_has_index optional fields
affects: [12-02-pk-fk-adaptation, analysis-tools, mcp-server]

tech-stack:
  added: []
  patterns: [transpile_query(sql, dialect) for TSQL-to-target, isinstance type classification, Inspector fallback pattern, DESCRIBE EXTENDED probe-first-column heuristic]

key-files:
  created:
    - src/analysis/_sql.py
  modified:
    - src/analysis/column_stats.py
    - src/analysis/__init__.py
    - src/analysis/pk_discovery.py
    - src/analysis/fk_candidates.py
    - src/models/analysis.py
    - src/mcp_server/analysis_tools.py
    - tests/unit/test_column_stats.py
    - tests/staleness/tool_invoker.py

key-decisions:
  - "Write base SQL in TSQL syntax and transpile via sqlglot -- matches existing code, single source of truth"
  - "isinstance-based type classification with MONEY/SMALLMONEY name fallback -- handles SA type hierarchy edge cases"
  - "Keep string-based _get_type_category_str() as fallback for backward compat without Inspector"
  - "Probe-first-column heuristic for Databricks DESCRIBE EXTENDED -- avoids N+1 when stats absent"

patterns-established:
  - "transpile_query(sql, dialect) pattern: write TSQL base SQL, pass through transpile_query before text()"
  - "Inspector-first with INFORMATION_SCHEMA fallback: check self._inspector, else use SQL query"
  - "DESCRIBE EXTENDED probe: test first column, use fast path for all if stats present"

requirements-completed: [ANLYS-01, ANLYS-02, ANLYS-05]

duration: 13min
completed: 2026-04-15
---

# Phase 12 Plan 01: Column Stats Adaptation Summary

**Dialect-aware ColumnStatsCollector with sqlglot transpilation, isinstance type classification, Inspector-based metadata, and Databricks DESCRIBE EXTENDED fast path**

## Performance

- **Duration:** 13 min
- **Started:** 2026-04-15T19:04:37Z
- **Completed:** 2026-04-15T19:17:48Z
- **Tasks:** 3
- **Files modified:** 9

## Accomplishments
- Replaced hardcoded MSSQL type string sets with isinstance() classification against SQLAlchemy TypeEngine hierarchy
- Added sqlglot transpilation to all ColumnStatsCollector SQL queries via shared transpile_query() helper
- Implemented Databricks DESCRIBE EXTENDED fast path with probe-first-column heuristic
- Wired get_column_info MCP tool to pass dialect and inspector through to ColumnStatsCollector
- All 830 tests passing with zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Create shared transpilation helper, update models, and update analysis constructors** - `1e55fda` (feat)
2. **Task 2: Refactor ColumnStatsCollector for dialect-aware queries and Databricks fast path** - `5ec8525` (test), `d999559` (feat)
3. **Task 3: Wire get_column_info MCP tool to pass dialect and inspector** - `33ba219` + `2adde50` (feat)

## Files Created/Modified
- `src/analysis/_sql.py` - Shared transpile_query() helper for TSQL-to-dialect transpilation
- `src/analysis/column_stats.py` - Dialect-aware ColumnStatsCollector with isinstance classification, Inspector-based discovery, transpiled SQL, Databricks fast path
- `src/analysis/__init__.py` - Exports transpile_query
- `src/analysis/pk_discovery.py` - Constructor updated with dialect/inspector params
- `src/analysis/fk_candidates.py` - Constructor updated with dialect/inspector params
- `src/models/analysis.py` - PKCandidate.constraint_enforced, FKCandidateData.target_has_index made optional
- `src/mcp_server/analysis_tools.py` - get_column_info wired with dialect/inspector, Inspector-based table existence
- `tests/unit/test_column_stats.py` - Added TestTypeClassification, TestInspectorColumnDiscovery, TestDatabricksFastPath, TestTranspilation (23 new tests)
- `tests/staleness/tool_invoker.py` - Updated get_column_info mocks for Inspector-based flow

## Decisions Made
- Write base SQL in TSQL syntax and transpile via sqlglot -- matches existing code, single source of truth
- isinstance-based type classification with MONEY/SMALLMONEY name fallback -- handles SA type hierarchy edge cases
- Keep string-based _get_type_category_str() as fallback for backward compat without Inspector
- Probe-first-column heuristic for Databricks DESCRIBE EXTENDED -- avoids N+1 when stats absent

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed staleness guard test mock for get_column_info**
- **Found during:** Task 3 (Wire get_column_info MCP tool)
- **Issue:** Staleness guard test failed because get_column_info now uses Inspector.get_table_names() instead of INFORMATION_SCHEMA, and calls conn_manager.get_dialect()
- **Fix:** Updated _get_column_info_success_mocks to mock inspect() and get_dialect()
- **Files modified:** tests/staleness/tool_invoker.py
- **Verification:** Staleness test passes for get_column_info
- **Committed in:** 2adde50

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary for test correctness after Inspector-based refactor. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- ColumnStatsCollector fully adapted for all three dialects
- PKDiscovery and FKCandidateSearch constructors prepared with dialect/inspector params (ready for Plan 02)
- transpile_query() helper available for reuse in Plan 02

---
*Phase: 12-analysis-module-adaptation*
*Completed: 2026-04-15*
