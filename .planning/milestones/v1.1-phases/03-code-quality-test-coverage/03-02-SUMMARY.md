---
phase: 03-code-quality-test-coverage
plan: 02
subsystem: database
tags: [sqlalchemy, exception-handling, error-narrowing, code-quality]

# Dependency graph
requires:
  - phase: 03-01
    provides: "metrics.py deletion (removes 1 broad exception)"
provides:
  - "All service/db layer exception handlers narrowed to SQLAlchemyError"
  - "Exception type context in debug/warning log messages"
affects: [03-03, testing]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "SQLAlchemyError for all db-layer exception catching"
    - "type(e).__name__ prefix in error log messages"

key-files:
  created: []
  modified:
    - src/db/metadata.py
    - src/db/query.py
    - src/db/connection.py
    - tests/unit/test_connection.py
    - tests/compliance/test_nfr_compliance.py

key-decisions:
  - "SQLAlchemyError only -- no pyodbc catching (SQLAlchemy wraps pyodbc errors)"
  - "MCP tool safety nets (9 blocks) intentionally kept as except Exception"

patterns-established:
  - "DB layer catches SQLAlchemyError; MCP tools catch Exception as safety nets"
  - "Error log messages include {type(e).__name__} for diagnostics"

requirements-completed: [QUAL-02]

# Metrics
duration: 12min
completed: 2026-03-09
---

# Phase 3 Plan 2: Narrow Exception Handlers Summary

**Narrowed 15 broad except Exception blocks to SQLAlchemyError across metadata.py, query.py, and connection.py with diagnostic type context in error messages**

## Performance

- **Duration:** 12 min
- **Started:** 2026-03-09T16:57:41Z
- **Completed:** 2026-03-09T17:09:26Z
- **Tasks:** 2
- **Files modified:** 5

## Accomplishments
- Replaced all 11 except Exception blocks in metadata.py with except SQLAlchemyError
- Replaced 3 except Exception blocks in query.py with except SQLAlchemyError
- Replaced 1 except Exception block in connection.py with except SQLAlchemyError
- Added exception type name ({type(e).__name__}) to error/debug log messages for diagnostics
- Preserved all 9 MCP tool safety net exception handlers unchanged
- Zero broad except Exception blocks remain outside mcp_server/

## Task Commits

Each task was committed atomically:

1. **Task 1: Narrow exception handlers in metadata.py (11 blocks)** - `2bc16d5` (fix)
2. **Task 2: Narrow exception handlers in query.py (3 blocks) and connection.py (1 block)** - `fa673ef` (fix)

## Files Created/Modified
- `src/db/metadata.py` - 11 except Exception blocks narrowed to SQLAlchemyError, import added
- `src/db/query.py` - 3 except Exception blocks narrowed to SQLAlchemyError, import added
- `src/db/connection.py` - 1 except Exception block narrowed to SQLAlchemyError, import added
- `tests/unit/test_connection.py` - 3 test mocks updated from Exception to SQLAlchemyError
- `tests/compliance/test_nfr_compliance.py` - 2 test mocks updated from Exception to SQLAlchemyError

## Decisions Made
- Used SQLAlchemyError (not pyodbc exceptions) per user decision -- SQLAlchemy wraps pyodbc errors, so raw pyodbc leaks indicate a real problem worth knowing about
- No custom exception classes introduced -- only narrowed to existing SQLAlchemy hierarchy
- MCP tool safety nets preserved as except Exception per prior architecture decision

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated test mocks to match narrowed exception handlers**
- **Found during:** Task 2 (query.py and connection.py narrowing)
- **Issue:** 5 test mocks used bare Exception("...") as side_effect for create_engine; after narrowing to except SQLAlchemyError, the handler would no longer catch these, causing tests to fail with unhandled Exception instead of expected ConnectionError
- **Fix:** Updated mocks to use SQLAlchemyError("...") in test_connection.py (3 mocks) and test_nfr_compliance.py (2 mocks); added SQLAlchemyError import to both test files
- **Files modified:** tests/unit/test_connection.py, tests/compliance/test_nfr_compliance.py
- **Verification:** All 463 tests pass, ruff clean
- **Committed in:** fa673ef (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix)
**Impact on plan:** Necessary for test correctness after handler narrowing. No scope creep.

**Note:** Plan frontmatter stated 12 blocks in metadata.py but actual count was 11. The plan body listed 11 line references (6 inspector + 5 data/query). All blocks were narrowed.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All service/db layer exception handling is now honest -- only database errors are caught
- Non-database errors (TypeError, KeyError, etc.) will propagate naturally for debugging
- Ready for Plan 03-03 (test coverage improvements)

---
*Phase: 03-code-quality-test-coverage*
*Completed: 2026-03-09*
