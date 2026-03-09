---
phase: 04-connection-management
plan: 01
subsystem: database
tags: [sqlalchemy, azure-ad, connection-pooling, pool-recycle, token-management]

# Dependency graph
requires:
  - phase: 03-code-quality
    provides: clean exception handling and test coverage baseline
provides:
  - auth-aware pool_recycle (2700s for Azure AD, 3600s for SQL/Windows)
  - auto-disconnect on Azure AD token re-acquisition failure
  - PoolConfig.azure_ad_pool_recycle configurable field
affects: [04-02-PLAN, connection-management]

# Tech tracking
tech-stack:
  added: []
  patterns: [auth-aware pool config, token-failure cleanup closure]

key-files:
  created: []
  modified:
    - src/db/connection.py
    - tests/unit/test_connection.py

key-decisions:
  - "Catch builtins.ConnectionError (not local ConnectionError) in creator closure since azure_auth raises the builtin"
  - "Pass connection_id into _create_engine via parameter for cleanup closure access"

patterns-established:
  - "Auth-aware pool configuration: Azure AD methods get shorter pool_recycle to stay ahead of token expiry"
  - "Token failure cleanup: creator closures catch token errors and auto-disconnect stale connections"

requirements-completed: [CONN-01]

# Metrics
duration: 4min
completed: 2026-03-09
---

# Phase 04 Plan 01: Auth-Aware Pool Recycling Summary

**Auth-aware pool_recycle=2700 for Azure AD connections with auto-disconnect on token re-acquisition failure**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-09T19:04:31Z
- **Completed:** 2026-03-09T19:08:51Z
- **Tasks:** 2
- **Files modified:** 2

## Accomplishments
- Azure AD connections now use pool_recycle=2700 (45 min) to proactively recycle before token expiry
- SQL and Windows auth connections unchanged at pool_recycle=3600
- Token re-acquisition failures during pool refresh trigger auto-disconnect of stale connections
- 11 new tests added (7 pool_recycle + 4 token failure), all 35 connection tests pass

## Task Commits

Each task was committed atomically:

1. **Task 1: Add azure_ad_pool_recycle to PoolConfig and implement auth-aware pool_recycle** - `bbf53f0` (feat)
2. **Task 2: Handle token re-acquisition failure with auto-disconnect** - `a9f31e8` (feat)

_Note: TDD tasks each followed red-green flow (tests written first, then implementation)_

## Files Created/Modified
- `src/db/connection.py` - Added azure_ad_pool_recycle field, auth-aware pool_recycle logic, token failure auto-disconnect in creator closure
- `tests/unit/test_connection.py` - 11 new tests for pool_recycle behavior and token failure handling

## Decisions Made
- Used `builtins.ConnectionError` (not local `ConnectionError`) in the creator closure's except clause because `azure_auth.AzureTokenProvider.get_token()` raises Python's built-in `ConnectionError`, which is unrelated to `src.db.connection.ConnectionError`
- Passed `connection_id` as a parameter to `_create_engine` so the creator closure can reference it for cleanup; during initial connect the engine is not yet stored, so auto-disconnect is a no-op
- Updated existing T020 test to expect pool_recycle=2700 (was 3600) since Azure AD Integrated now uses auth-aware recycling

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Fixed ConnectionError type mismatch in creator closure**
- **Found during:** Task 2
- **Issue:** The plan said to catch `ConnectionError` in the creator, but `connection.py` defines a local `ConnectionError(Exception)` that shadows the builtin. The `azure_auth` module raises `builtins.ConnectionError` (a subclass of `OSError`), so catching the local class would miss the real errors.
- **Fix:** Imported `builtins` and used `builtins.ConnectionError` in the except clause
- **Files modified:** src/db/connection.py
- **Verification:** All 4 token_failure tests pass with `BuiltinConnectionError` side_effects
- **Committed in:** a9f31e8

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Essential correctness fix -- without it, token failures would not be caught.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- Pool recycling foundation in place for Plan 02 (connection lifecycle management)
- Azure AD token expiry behavior still needs live testing (non-blocking; pool_recycle is primary defense)

---
*Phase: 04-connection-management*
*Completed: 2026-03-09*

## Self-Check: PASSED
