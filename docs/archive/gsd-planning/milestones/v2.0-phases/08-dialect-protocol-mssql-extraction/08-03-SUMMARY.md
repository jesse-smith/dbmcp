---
phase: 08-dialect-protocol-mssql-extraction
plan: 03
subsystem: database
tags: [sqlalchemy, mssql, dialect-protocol, refactor]

# Dependency graph
requires:
  - phase: 08-02
    provides: MssqlDialect class with create_engine, quote_identifier, fast_row_counts
provides:
  - ConnectionManager delegating engine creation to MssqlDialect
  - MetadataService using dialect capability flags for branching
  - QueryService using dialect.quote_identifier for identifier quoting
  - QueryService using dialect.sqlglot_dialect for query parsing
affects: [09-validation-transpilation, 10-generic-fallback, 12-analysis-tools]

# Tech tracking
tech-stack:
  added: []
  patterns: [dialect-aware service wiring, auto-inference from engine.dialect.name, optional dialect parameter with backward compat]

key-files:
  created: []
  modified:
    - src/db/connection.py
    - src/db/metadata.py
    - src/db/query.py
    - tests/unit/test_connection.py
    - tests/unit/test_query_timeout.py
    - tests/compliance/test_nfr_compliance.py

key-decisions:
  - "Auto-infer dialect from engine.dialect.name when not explicitly provided -- backward compat for existing MetadataService(engine) and QueryService(engine) calls"
  - "Keep is_mssql property on MetadataService for backward compat -- future deprecation"
  - "Keep _classify_db_error in connection.py since it is only used there for error wrapping"
  - "Test mocks updated to patch MssqlDialect at src.db.connection.MssqlDialect or src.db.dialects.mssql.sa_create_engine instead of removed src.db.connection.create_engine"

patterns-established:
  - "Dialect auto-inference: services check engine.dialect.name == 'mssql' and create MssqlDialect() when no dialect is provided"
  - "Dialect None = sqlite/test mode: all services use self._dialect is None to detect sqlite test path"
  - "Test mock pattern: patch src.db.connection.MssqlDialect for ConnectionManager tests, patch src.db.dialects.mssql.sa_create_engine for internal engine creation tests"

requirements-completed: [DIAL-02, META-05, TEST-01]

# Metrics
duration: 14min
completed: 2026-04-14
---

# Phase 8 Plan 3: Service Integration Summary

**ConnectionManager, MetadataService, and QueryService wired to MssqlDialect -- replacing all hardcoded MSSQL logic with dialect protocol calls while preserving zero-change public APIs**

## Performance

- **Duration:** 14 min
- **Started:** 2026-04-14T15:52:41Z
- **Completed:** 2026-04-14T16:06:38Z
- **Tasks:** 2
- **Files modified:** 6

## Accomplishments
- ConnectionManager.connect() delegates engine creation to MssqlDialect internally; removed _build_odbc_connection_string and _create_engine methods
- MetadataService uses dialect.has_fast_row_counts capability flag instead of self.is_mssql for DMV branching
- QueryService uses dialect.quote_identifier for all identifier quoting, dialect.sqlglot_dialect for query parsing, and dialect-None check for sqlite paths
- All 675 tests pass with zero regressions (TEST-01 verified)
- All test mocks updated: 44 connection tests, 12 query timeout tests, 16 NFR compliance tests

## Task Commits

Each task was committed atomically:

1. **Task 1: Wire MssqlDialect into ConnectionManager** - `118ea1e` (feat)
2. **Task 2: Wire dialect into MetadataService and QueryService** - `d438624` (feat)

## Files Created/Modified
- `src/db/connection.py` - ConnectionManager delegates to MssqlDialect, added _dialects dict and get_dialect()
- `src/db/metadata.py` - MetadataService accepts optional dialect, uses capability flags
- `src/db/query.py` - QueryService accepts optional dialect, uses quote_identifier and sqlglot_dialect
- `tests/unit/test_connection.py` - All mocks updated from src.db.connection.create_engine to MssqlDialect patching
- `tests/unit/test_query_timeout.py` - All mocks updated to use dialect module targets
- `tests/compliance/test_nfr_compliance.py` - NFR-005 tests updated to use MssqlDialect patching

## Decisions Made
- Auto-infer dialect from engine.dialect.name when not explicitly provided, preserving backward compat for all existing service instantiation sites (MetadataService(engine), QueryService(engine))
- Kept is_mssql property on MetadataService for backward compat -- no tests or code currently need it removed, will deprecate in future
- Test mock target strategy: use src.db.connection.MssqlDialect for tests needing mock engines, use src.db.dialects.mssql.sa_create_engine for tests inspecting pool kwargs or creator patterns

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Added event mock to tests patching sa_create_engine**
- **Found during:** Task 1 (Connection test mock updates)
- **Issue:** Tests patching src.db.dialects.mssql.sa_create_engine would fail because MssqlDialect.create_engine() calls @event.listens_for(engine, "connect") on the mock engine, which SQLAlchemy rejects
- **Fix:** Added @patch("src.db.dialects.mssql.event") to all tests that mock sa_create_engine, with mock_event parameter in test signatures
- **Files modified:** tests/unit/test_connection.py, tests/unit/test_query_timeout.py
- **Verification:** All 44 connection tests and 12 query timeout tests pass
- **Committed in:** 118ea1e (Task 1 commit)

**2. [Rule 3 - Blocking] Updated compliance test mocks for NFR-005**
- **Found during:** Task 1 (Running full test suite)
- **Issue:** tests/compliance/test_nfr_compliance.py also patched src.db.connection.create_engine which no longer exists
- **Fix:** Updated 4 NFR-005 compliance tests to use src.db.connection.MssqlDialect patching pattern
- **Files modified:** tests/compliance/test_nfr_compliance.py
- **Verification:** All 16 compliance tests pass (14 passed, 2 skipped as before)
- **Committed in:** 118ea1e (Task 1 commit)

---

**Total deviations:** 2 auto-fixed (2 blocking)
**Impact on plan:** Both auto-fixes necessary for test suite to pass. No scope creep -- test mock targets are a direct consequence of the connection.py refactor.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All three services (ConnectionManager, MetadataService, QueryService) are now dialect-aware
- Phase 9 (validation transpilation) can use dialect.sqlglot_dialect for dialect-specific query validation
- Phase 10 (generic fallback) can add new dialects that auto-register and auto-infer
- Phase 12 (analysis tools) can use dialect protocol for analysis module wiring

---
## Self-Check: PASSED

All 6 modified files verified present. Both task commits (118ea1e, d438624) verified in git log. 675 tests pass, 0 failures.

---
*Phase: 08-dialect-protocol-mssql-extraction*
*Completed: 2026-04-14*
