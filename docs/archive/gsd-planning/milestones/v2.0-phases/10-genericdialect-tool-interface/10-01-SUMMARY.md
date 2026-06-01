---
phase: 10-genericdialect-tool-interface
plan: 01
subsystem: database
tags: [sqlalchemy, dialect, protocol, generic, url-routing]

# Dependency graph
requires:
  - phase: 08-dialect-protocol-mssql-extraction
    provides: DialectStrategy protocol and MssqlDialect implementation
provides:
  - GenericDialect implementing all 8 DialectStrategy protocol members
  - URL-scheme-to-dialect routing via resolve_dialect_from_url
  - Lazy pyodbc import with clear ImportError guidance
  - _URL_SCHEME_TO_SQLGLOT mapping for sqlglot dialect resolution
affects: [10-02, 10-03, connection-manager-refactor]

# Tech tracking
tech-stack:
  added: []
  patterns: [generic-dialect-fallback, url-scheme-routing, lazy-optional-imports]

key-files:
  created:
    - src/db/dialects/generic.py
    - tests/unit/test_generic_dialect.py
    - tests/unit/test_url_routing.py
    - tests/unit/test_optional_deps.py
  modified:
    - src/db/dialects/protocol.py
    - src/db/dialects/registry.py
    - src/db/dialects/mssql.py
    - src/db/dialects/__init__.py

key-decisions:
  - "Kept azure_auth import at module level to avoid breaking 13 existing test patches"
  - "Used try/except at module level for pyodbc (None sentinel) instead of fully lazy import inside create_engine, preserving test patchability"
  - "Simplified GenericDialect.create_engine to pool_pre_ping + echo only, avoiding SQLite pool_size incompatibility"

patterns-established:
  - "Generic fallback pattern: unknown URL schemes get GenericDialect with sqlglot_dialect=None and warning log"
  - "URL scheme routing: resolve_dialect_from_url centralizes dialect selection from connection URLs"

requirements-completed: [DIAL-04, CONF-05]

# Metrics
duration: 9min
completed: 2026-04-14
---

# Phase 10 Plan 01: GenericDialect, URL Routing, and Lazy Imports Summary

**GenericDialect with ANSI SQL quoting and Inspector-only metadata, URL-scheme-to-dialect routing for any SQLAlchemy backend, and lazy pyodbc guard for non-MSSQL installs**

## Performance

- **Duration:** 9 min
- **Started:** 2026-04-14T20:04:56Z
- **Completed:** 2026-04-14T20:14:06Z
- **Tasks:** 2
- **Files modified:** 8

## Accomplishments
- GenericDialect implements all 8 DialectStrategy protocol members with ANSI double-quote quoting, empty safe_procedures, and no fast row counts
- resolve_dialect_from_url routes mssql/databricks to registered dialects, postgresql/mysql/sqlite to GenericDialect with sqlglot mapping, and unknown schemes to GenericDialect with warning
- pyodbc wrapped in try/except at module level; create_engine raises ImportError with install instructions when missing
- Protocol updated: sqlglot_dialect return type widened from str to str | None

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement GenericDialect class** - `73e86b4` (test: RED), `8b3b474` (feat: GREEN)
2. **Task 2: URL routing, lazy imports, deferred registration** - `88b53c7` (test: RED), `50f3ac2` (feat: GREEN)

_TDD tasks have separate test and implementation commits._

## Files Created/Modified
- `src/db/dialects/generic.py` - GenericDialect class with all 8 protocol members, _URL_SCHEME_TO_SQLGLOT mapping
- `src/db/dialects/protocol.py` - sqlglot_dialect return type widened to str | None
- `src/db/dialects/registry.py` - resolve_dialect_from_url, _URL_SCHEME_TO_DIALECT mapping
- `src/db/dialects/mssql.py` - pyodbc try/except at module level, ImportError guard in create_engine
- `src/db/dialects/__init__.py` - GenericDialect registration, resolve_dialect_from_url export
- `tests/unit/test_generic_dialect.py` - 17 tests for protocol compliance and engine behavior
- `tests/unit/test_url_routing.py` - 8 tests for URL scheme routing and warning behavior
- `tests/unit/test_optional_deps.py` - 2 tests for lazy pyodbc import behavior

## Decisions Made
- Kept azure_auth import at module level: 13 existing tests patch `src.db.dialects.mssql.AzureTokenProvider`, making it infeasible to move to lazy import without mass test rewrite
- Used try/except + None sentinel for pyodbc at module level: preserves patchability for 6 existing tests that mock `src.db.dialects.mssql.pyodbc`
- Simplified GenericDialect.create_engine to only set pool_pre_ping and echo: SQLite uses SingletonThreadPool which rejects pool_size/max_overflow kwargs

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SQLite pool_size incompatibility in GenericDialect.create_engine**
- **Found during:** Task 1 (GenericDialect implementation)
- **Issue:** Plan specified pool_size=5, max_overflow=10, pool_recycle=3600 but SQLite uses SingletonThreadPool which rejects those kwargs
- **Fix:** Removed pool_size/max_overflow/pool_recycle, kept pool_pre_ping=True and echo=False only
- **Files modified:** src/db/dialects/generic.py
- **Verification:** create_engine with sqlite:/// succeeds, pool._pre_ping is True
- **Committed in:** 8b3b474

**2. [Rule 1 - Bug] Lazy import approach broke existing test patches**
- **Found during:** Task 2 (lazy imports)
- **Issue:** Plan specified moving pyodbc and azure_auth imports inside create_engine(), but 19 existing tests patch module-level attributes (src.db.dialects.mssql.pyodbc, src.db.dialects.mssql.AzureTokenProvider)
- **Fix:** Kept azure_auth at module level; wrapped pyodbc in try/except at module level with None sentinel; check `if pyodbc is None` inside create_engine
- **Files modified:** src/db/dialects/mssql.py
- **Verification:** All 732 tests pass with 0 regressions
- **Committed in:** 50f3ac2

**3. [Rule 1 - Bug] caplog not capturing warnings from dbmcp logger**
- **Found during:** Task 2 (URL routing tests)
- **Issue:** dbmcp root logger sets propagate=False, preventing pytest caplog from capturing log messages
- **Fix:** Used unittest.mock.patch on logger.warning instead of caplog fixture
- **Files modified:** tests/unit/test_url_routing.py
- **Verification:** test_unknown_scheme_warning passes
- **Committed in:** 50f3ac2

---

**Total deviations:** 3 auto-fixed (3 bugs)
**Impact on plan:** All auto-fixes necessary for correctness and test compatibility. No scope creep.

## Issues Encountered
None beyond the deviations documented above.

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- GenericDialect and URL routing ready for integration with ConnectionManager (Plan 02)
- resolve_dialect_from_url provides the entry point for connect_database tool to accept any URL
- _URL_SCHEME_TO_DIALECT extensible for future dialect registrations (databricks entry placeholder exists)

---
*Phase: 10-genericdialect-tool-interface*
*Completed: 2026-04-14*
