---
phase: 07-wire-orphaned-exports
plan: 02
subsystem: database
tags: [sqlalchemy, error-handling, mcp-tools, error-classification]

# Dependency graph
requires:
  - phase: 04-targeted-error-handling
    provides: "_classify_db_error function in connection.py"
provides:
  - "All 9 MCP tool safety nets classify SQLAlchemy errors with actionable guidance"
  - "Parametrized tests covering error classification wiring for all tools"
affects: []

# Tech tracking
tech-stack:
  added: []
  patterns: ["isinstance+_classify_db_error pattern in MCP tool safety nets"]

key-files:
  created: []
  modified:
    - src/mcp_server/schema_tools.py
    - src/mcp_server/query_tools.py
    - src/mcp_server/analysis_tools.py
    - tests/unit/test_async_tools.py

key-decisions:
  - "Used create=True on mock.patch for _classify_db_error to support both pre- and post-wiring test execution"

patterns-established:
  - "Error classification pattern: isinstance(e, SQLAlchemyError) -> _classify_db_error(e) -> f'{guidance} ({e})' in all MCP tool safety nets"

requirements-completed: [CONN-02]

# Metrics
duration: 4min
completed: 2026-03-10
---

# Phase 7 Plan 2: Wire Error Classification Summary

**_classify_db_error wired into all 9 MCP tool safety nets with isinstance guard and parametrized test coverage**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-10T19:51:43Z
- **Completed:** 2026-03-10T19:56:11Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- All 9 MCP tool safety nets now classify SQLAlchemy errors with actionable user guidance
- _classify_db_error is no longer dead code -- it is called in production error paths
- 18 new parametrized tests (9 SQLAlchemy classification + 9 generic fallback) verify wiring
- Non-SQLAlchemy errors preserve their original generic fallback message text

## Task Commits

Each task was committed atomically:

1. **Task 1: Add parametrized error classification wiring tests** - `ecdf9f7` (test - TDD RED)
2. **Task 2: Wire _classify_db_error into all 9 MCP tool safety nets** - `9700fb5` (feat - TDD GREEN)

**Plan metadata:** pending (docs: complete plan)

## Files Created/Modified
- `src/mcp_server/schema_tools.py` - Added SQLAlchemyError import, _classify_db_error import, enhanced 4 safety nets
- `src/mcp_server/query_tools.py` - Added SQLAlchemyError import, _classify_db_error import, enhanced 2 safety nets
- `src/mcp_server/analysis_tools.py` - Added SQLAlchemyError import, _classify_db_error import, enhanced 3 safety nets
- `tests/unit/test_async_tools.py` - Added 18 parametrized tests for error classification wiring

## Decisions Made
- Used `create=True` on `mock.patch` for `_classify_db_error` to allow tests to work both before and after the function is imported into tool modules

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed import sorting in schema_tools.py**
- **Found during:** Task 2
- **Issue:** ruff I001 flagged unsorted import block after adding SQLAlchemyError import
- **Fix:** Ran `ruff check --fix` to reorder imports
- **Files modified:** src/mcp_server/schema_tools.py
- **Committed in:** 9700fb5 (part of task commit)

---

**Total deviations:** 1 auto-fixed (1 bug)
**Impact on plan:** Trivial import ordering fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- CONN-02 requirement complete: error classification is fully wired end-to-end
- All orphaned exports from prior phases are now connected to production code paths

---
*Phase: 07-wire-orphaned-exports*
*Completed: 2026-03-10*
