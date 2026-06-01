---
phase: 12-analysis-module-adaptation
plan: 02
subsystem: analysis
tags: [sqlalchemy, inspector, pk-discovery, fk-candidates, databricks, dialect-aware, supports-indexes]

requires:
  - phase: 12-analysis-module-adaptation
    provides: Dialect-aware ColumnStatsCollector, transpile_query() helper, constructor params for dialect/inspector, PKCandidate.constraint_enforced and FKCandidateData.target_has_index optional fields
provides:
  - Dialect-aware PKDiscovery with Inspector-based constraint discovery and informational constraint annotation
  - Dialect-aware FKCandidateSearch with Inspector-based table listing, constraint checks, and index gating
  - All three MCP analysis tools fully wired with dialect/inspector (zero INFORMATION_SCHEMA in tool wrappers)
affects: [analysis-tools, mcp-server]

tech-stack:
  added: []
  patterns: [Inspector-first constraint discovery with MSSQL INFORMATION_SCHEMA fallback, supports_indexes gating for target_has_index, fnmatch for SQL LIKE pattern replacement]

key-files:
  created: []
  modified:
    - src/analysis/pk_discovery.py
    - src/analysis/fk_candidates.py
    - src/mcp_server/analysis_tools.py
    - tests/unit/test_pk_discovery.py
    - tests/unit/test_fk_candidates.py
    - tests/staleness/tool_invoker.py

key-decisions:
  - "Inspector-first with MSSQL INFORMATION_SCHEMA fallback for constraint and table discovery"
  - "supports_indexes gating: target_has_index=None when dialect.supports_indexes is False (absent from to_dict)"
  - "fnmatch for SQL LIKE pattern conversion in Inspector-based table listing (% -> *, _ -> ?)"
  - "constraint_enforced=False for Databricks (informational), True for generic, None for MSSQL (backward compat)"

patterns-established:
  - "_use_inspector() helper method pattern for dialect branching decisions"
  - "Inspector.get_table_names() + Python filtering replacing STRING_SPLIT for non-MSSQL"
  - "Inspector.get_pk_constraint/get_unique_constraints replacing INFORMATION_SCHEMA for non-MSSQL"
  - "Inspector.get_indexes() replacing sys.indexes DMV for non-MSSQL"

requirements-completed: [ANLYS-03, ANLYS-04]

duration: 11min
completed: 2026-04-15
---

# Phase 12 Plan 02: PK/FK Discovery Adaptation Summary

**Dialect-aware PK/FK candidate discovery with Inspector-based constraints, supports_indexes gating, and informational constraint annotation for Databricks**

## Performance

- **Duration:** 11 min
- **Started:** 2026-04-15T19:20:46Z
- **Completed:** 2026-04-15T19:32:38Z
- **Tasks:** 3
- **Files modified:** 6

## Accomplishments
- PKDiscovery uses Inspector for generic/Databricks constraint discovery, INFORMATION_SCHEMA retained for MSSQL
- FKCandidateSearch uses Inspector for table listing (replacing STRING_SPLIT), constraint checks, and index checks
- target_has_index gated by supports_indexes (None for Databricks, absent from serialized output)
- Databricks constraints annotated as informational (constraint_enforced=False)
- All three MCP analysis tool wrappers now use Inspector-based checks (zero INFORMATION_SCHEMA in tool layer)
- 852 tests passing (22 new tests), zero regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: Refactor PKDiscovery for dialect-aware constraint discovery** - `ee5f2e7` (feat)
2. **Task 2: Refactor FKCandidateSearch for dialect-aware index checks and table listing** - `52a407f` (feat)
3. **Task 3: Wire find_pk_candidates and find_fk_candidates MCP tools with dialect/inspector** - `9524652` (feat)

## Files Created/Modified
- `src/analysis/pk_discovery.py` - Dialect-aware PKDiscovery with _get_constraint_candidates_inspector/_mssql methods, Inspector-based structural column listing, transpiled uniqueness SQL
- `src/analysis/fk_candidates.py` - Dialect-aware FKCandidateSearch with Inspector table listing, constraint checks, index gating, transpiled overlap SQL
- `src/mcp_server/analysis_tools.py` - find_pk_candidates and find_fk_candidates wired with dialect/inspector, Inspector-based table/column existence checks
- `tests/unit/test_pk_discovery.py` - Added TestInspectorConstraintDiscovery (7 tests) and TestDialectBackwardCompat (3 tests)
- `tests/unit/test_fk_candidates.py` - Added TestInspectorTableDiscovery (4 tests), TestDialectAwareMetadata (5 tests), TestTranspiledOverlap (1 test), TestInspectorCandidateColumns (2 tests)
- `tests/staleness/tool_invoker.py` - Updated find_pk_candidates and find_fk_candidates mocks for Inspector-based flow

## Decisions Made
- Inspector-first with MSSQL INFORMATION_SCHEMA fallback for constraint and table discovery
- supports_indexes gating: target_has_index=None when dialect.supports_indexes is False (absent from serialized output)
- fnmatch for SQL LIKE pattern conversion in Inspector-based table listing (% -> *, _ -> ?)
- constraint_enforced=False for Databricks (informational), True for generic, None for MSSQL (backward compat)
- _use_inspector() helper method in FKCandidateSearch to reduce branching duplication

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing PKFilter test assertion for new constructor signature**
- **Found during:** Task 2 (FKCandidateSearch refactor)
- **Issue:** Existing test_pk_filter_on_uses_pk_discovery asserted PKDiscovery was called without dialect/inspector kwargs, but the new code always passes them
- **Fix:** Updated assertion to expect dialect=None, inspector=None in the constructor call
- **Files modified:** tests/unit/test_fk_candidates.py
- **Verification:** Test passes with updated assertion
- **Committed in:** 52a407f

**2. [Rule 1 - Bug] Updated staleness guard mocks for Inspector-based flow**
- **Found during:** Task 3 (MCP tool wiring)
- **Issue:** Staleness guard tests failed because find_pk_candidates and find_fk_candidates now use Inspector instead of connection.execute() for table/column existence
- **Fix:** Updated _find_pk_candidates_success_mocks and _find_fk_candidates_success_mocks to mock inspect(), get_dialect(), and Inspector methods with correct table/column names matching test args
- **Files modified:** tests/staleness/tool_invoker.py
- **Verification:** Staleness tests pass for both tools
- **Committed in:** 9524652

---

**Total deviations:** 2 auto-fixed (2 bug fixes)
**Impact on plan:** Both necessary for test correctness after Inspector-based refactor. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three analysis modules (column_stats, pk_discovery, fk_candidates) fully adapted for MSSQL, Databricks, and generic dialects
- All three MCP analysis tools (get_column_info, find_pk_candidates, find_fk_candidates) properly wire dialect and inspector
- Phase 12 complete -- all ANLYS requirements (ANLYS-01 through ANLYS-05) satisfied

---
## Self-Check: PASSED

All 7 files verified present. All 3 task commits verified in git log.

*Phase: 12-analysis-module-adaptation*
*Completed: 2026-04-15*
