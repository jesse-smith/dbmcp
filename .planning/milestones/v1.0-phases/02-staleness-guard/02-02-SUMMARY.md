---
phase: 02-staleness-guard
plan: 02
subsystem: testing
tags: [tdd, staleness-guard, mock-invocation, parametrized-test, drift-detection]

# Dependency graph
requires:
  - phase: 02-staleness-guard
    provides: extract_fields() parser and compare_fields() comparison from plan 01
  - phase: 01-atomic-toon-migration
    provides: TOON structural outline format in all 9 tool docstrings
provides:
  - Parametrized staleness guard test covering all 9 MCP tools (success + error paths)
  - Tool invoker with per-tool mock configs for controlled response capture
  - Auto-discovery test ensuring new tools are caught
  - Synthetic drift detection verification
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: [recursive nested key extraction for deep docstring comparison, per-tool mock context managers]

key-files:
  created:
    - tests/staleness/tool_invoker.py
    - tests/unit/test_staleness.py
  modified:
    - src/mcp_server/schema_tools.py
    - src/mcp_server/query_tools.py
    - src/mcp_server/analysis_tools.py

key-decisions:
  - "Mock responses include all possible nested structures (numeric_stats, datetime_stats, string_stats) to verify complete field coverage"
  - "Recursive nested key extraction flattens deep response structures to match docstring parser's one-level-deep nesting model"
  - "Fixed 6 tool docstrings to add missing 'on success only' annotations -- real drift caught during test development"

patterns-established:
  - "Tool invoker: context-manager-based mock setup per tool, reusable for future test automation"
  - "Nested extraction: _extract_nested_keys() recursively gathers all dict keys from response structures"

requirements-completed: [DOCS-02]

# Metrics
duration: 6min
completed: 2026-03-05
---

# Phase 2 Plan 2: Staleness Guard Test Summary

**Parametrized staleness guard test validating all 9 MCP tool docstrings match actual response schemas, with 21 tests and 99% coverage**

## Performance

- **Duration:** 6 min
- **Started:** 2026-03-05T16:01:52Z
- **Completed:** 2026-03-05T16:08:17Z
- **Tasks:** 1
- **Files created:** 2
- **Files modified:** 3

## Accomplishments
- 21-test staleness guard covering all 9 tools on both success and error paths
- Tool discovery tests ensure new tools are caught (checks MCP registry count)
- Synthetic drift detection test confirms undocumented fields trigger failure
- Fixed 6 tool docstrings where success-only fields lacked conditional annotations
- 99% coverage across all staleness modules (parser, comparison, tool_invoker)
- Full test suite green: 434 passed, 41 skipped

## Task Commits

Each task was committed atomically:

1. **Task 1: Build tool invoker and parametrized staleness test** - `84d8f58` (feat)

## Files Created/Modified
- `tests/staleness/tool_invoker.py` - Per-tool mock configs and invoke_tool() for all 9 MCP tools
- `tests/unit/test_staleness.py` - 21-test parametrized staleness guard (success paths, error paths, discovery, drift detection)
- `src/mcp_server/schema_tools.py` - Added "on success only" annotations to list_schemas, list_tables docstrings
- `src/mcp_server/query_tools.py` - Added "on success only" annotations to get_sample_data, execute_query docstrings
- `src/mcp_server/analysis_tools.py` - Added "on success only" annotations to get_column_info, find_pk_candidates, find_fk_candidates docstrings

## Decisions Made
- Mock responses include ALL possible nested structures (numeric_stats, datetime_stats, string_stats in get_column_info) even though a real column would only have one -- ensures all declared fields are validated
- Used recursive `_extract_nested_keys()` helper to flatten deep response structures, matching how the docstring parser captures all descendants under a parent field
- Fixed docstrings during development rather than adjusting mocks -- the docstrings genuinely had missing conditional annotations

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed missing "on success only" annotations in 6 tool docstrings**
- **Found during:** Task 1 (error path tests failing)
- **Issue:** Fields like `schemas`, `total_schemas`, `tables`, `returned_count`, etc. were not annotated as "on success only" but only appear in success responses. The staleness test correctly flagged them as expected-but-missing in error responses.
- **Fix:** Added "// on success only" annotations to all success-exclusive fields in list_schemas, list_tables, get_sample_data, execute_query, get_column_info, find_pk_candidates, find_fk_candidates
- **Files modified:** src/mcp_server/schema_tools.py, src/mcp_server/query_tools.py, src/mcp_server/analysis_tools.py
- **Verification:** All 18 success+error path tests pass after fix
- **Committed in:** 84d8f58

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** The staleness guard immediately proved its value by catching real docstring-schema drift. No scope creep.

## Issues Encountered
- Pre-existing integration test failure (test_azure_ad_auth.py) due to external database connectivity -- not caused by our changes, out of scope

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Phase 2 (Staleness Guard) is now complete
- All 9 MCP tools have docstrings validated against actual response schemas
- Any future tool changes that add/remove response fields will be caught by the staleness guard on every pytest run

## Self-Check: PASSED

- tests/staleness/tool_invoker.py: FOUND
- tests/unit/test_staleness.py: FOUND
- Commit 84d8f58: FOUND

---
*Phase: 02-staleness-guard*
*Completed: 2026-03-05*
