---
phase: 04-connection-management
plan: 02
subsystem: database
tags: [sqlalchemy, atexit, sigterm, error-classification, graceful-shutdown]

# Dependency graph
requires:
  - phase: 04-connection-management
    plan: 01
    provides: auth-aware pool_recycle and token failure auto-disconnect
provides:
  - best-effort disconnect_all (swallows per-engine errors, logs at DEBUG)
  - _classify_db_error function mapping SQLSTATE codes to actionable categories
  - atexit registration for automatic cleanup on server exit
  - SIGTERM handler converting to sys.exit(0) so atexit fires
affects: [connection-management, error-handling]

# Tech tracking
tech-stack:
  added: []
  patterns: [best-effort cleanup, SQLSTATE-based error classification, atexit lifecycle management]

key-files:
  created:
    - tests/unit/test_server_lifecycle.py
  modified:
    - src/db/connection.py
    - src/mcp_server/server.py
    - tests/unit/test_connection.py

key-decisions:
  - "Source inspection test for atexit registration instead of module reload to avoid breaking global MCP tool registry"
  - "Catch (SQLAlchemyError, OSError) in disconnect_all per anti-pattern guidance (not bare Exception)"
  - "_classify_db_error is a module-level function (not a method) for reuse outside ConnectionManager"

patterns-established:
  - "Best-effort cleanup: iterate copy, catch per-item, always clear at end"
  - "SQLSTATE prefix matching: 28xxx=auth, 08xxx=connectivity, message patterns for Azure AD tokens"

requirements-completed: [CONN-02]

# Metrics
duration: 4min
completed: 2026-03-09
---

# Phase 04 Plan 02: Session Cleanup and Error Classification Summary

**Best-effort disconnect_all with atexit/SIGTERM lifecycle hooks and SQLSTATE-based error classification for actionable user messages**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-09T19:11:08Z
- **Completed:** 2026-03-09T19:15:32Z
- **Tasks:** 2
- **Files modified:** 4

## Accomplishments
- disconnect_all is now best-effort: catches per-engine (SQLAlchemyError, OSError), always clears internal dicts, logs at DEBUG
- _classify_db_error maps SQLSTATE 28xxx to auth_failure, 08xxx to connection_lost, token+expired messages to token_expired
- server.py registers atexit.register(_connection_manager.disconnect_all) at module level
- SIGTERM handler in main() converts to sys.exit(0) so atexit fires on process manager termination
- 12 new tests across 2 files (9 connection + 3 lifecycle), all 495 tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Best-effort disconnect_all and error classification function** - `eec6cdf` (feat)
2. **Task 2: Register atexit cleanup and SIGTERM handler in server.py** - `44d3267` (feat)

_Note: TDD tasks each followed red-green flow (tests written first, then implementation)_

## Files Created/Modified
- `src/db/connection.py` - Best-effort disconnect_all, _classify_db_error module function
- `src/mcp_server/server.py` - atexit.register and SIGTERM handler imports and registration
- `tests/unit/test_connection.py` - 9 new tests for disconnect_all best-effort and error classification
- `tests/unit/test_server_lifecycle.py` - 3 new tests for atexit and SIGTERM behavior

## Decisions Made
- Used source inspection (inspect.getsource) for atexit registration test instead of importlib.reload, which would destroy the global MCP tool registry and break unrelated tests
- _classify_db_error is a module-level function rather than a ConnectionManager method, allowing reuse by tool modules for error reporting
- Catch (SQLAlchemyError, OSError) tuple in disconnect_all per project anti-pattern guidance (not bare Exception)

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed atexit test approach to avoid MCP registry corruption**
- **Found during:** Task 2
- **Issue:** The plan suggested reloading the server module to test atexit registration. This creates a new FastMCP instance and ConnectionManager, destroying all tool registrations and causing test_staleness.py::test_tool_count_matches_mcp_registry to fail (0 tools vs 9 expected).
- **Fix:** Used inspect.getsource() to verify atexit registration in module source rather than reloading
- **Files modified:** tests/unit/test_server_lifecycle.py
- **Verification:** All 495 tests pass including the staleness check
- **Committed in:** 44d3267

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential correctness fix -- module reload would cause cross-test failures.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Phase 04 (Connection Management) is now complete: pool recycling (Plan 01) + lifecycle cleanup and error classification (Plan 02)
- All CONN-01 and CONN-02 requirements satisfied
- Azure AD token expiry behavior still needs live testing (non-blocking; pool_recycle + atexit are primary defenses)

---
*Phase: 04-connection-management*
*Completed: 2026-03-09*

## Self-Check: PASSED
