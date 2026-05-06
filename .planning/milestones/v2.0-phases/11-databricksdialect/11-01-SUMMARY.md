---
phase: 11-databricksdialect
plan: 01
subsystem: database
tags: [databricks, sqlalchemy, dialect, token-auth]

# Dependency graph
requires:
  - phase: 08-dialect-protocol-mssql-extraction
    provides: DialectStrategy protocol, dialect registry, MssqlDialect reference implementation
  - phase: 09-config-discrimination-validation-dialect
    provides: DatabricksConnectionConfig dataclass, config routing in connect_with_config
  - phase: 10-genericdialect-tool-interface
    provides: GenericDialect pattern, connect_with_url method, resolve_dialect_from_url
provides:
  - DatabricksDialect class implementing DialectStrategy protocol
  - Dialect registered under 'databricks' in registry
  - ConnectionManager routing for DatabricksConnectionConfig
  - pyproject.toml databricks extras with package versions
affects: [11-02-databricks-metadata, future-databricks-features]

# Tech tracking
tech-stack:
  added: [databricks-sqlalchemy>=2.0.0, databricks-sql-connector>=4.0.0 (optional extras)]
  patterns: [lazy-import-gating-for-optional-deps, databricks-url-construction-with-quote-plus]

key-files:
  created:
    - src/db/dialects/databricks.py
    - tests/unit/test_databricks_dialect.py
  modified:
    - src/db/dialects/__init__.py
    - src/db/connection.py
    - tests/unit/test_connect_tool.py
    - tests/unit/test_connection_manager.py
    - pyproject.toml

key-decisions:
  - "Used backtick quoting for Databricks identifiers per Databricks SQL specification"
  - "Token URL-encoded via quote_plus to handle special characters safely"
  - "Changed fallback error from NotImplementedError to ValueError for unsupported config types"

patterns-established:
  - "Lazy import gating: try/except at module top, check in create_engine, raise with install instructions"
  - "Databricks URL format: databricks://token:{encoded_token}@{host}?http_path=...&catalog=...&schema=..."

requirements-completed: [DIAL-03]

# Metrics
duration: 4min
completed: 2026-04-15
---

# Phase 11 Plan 01: DatabricksDialect and Connection Routing Summary

**DatabricksDialect with token auth URL construction, lazy import gating, and ConnectionManager routing via connect_with_config**

## Performance

- **Duration:** 4 min
- **Started:** 2026-04-15T15:32:21Z
- **Completed:** 2026-04-15T15:36:36Z
- **Tasks:** 2
- **Files modified:** 7

## Accomplishments
- DatabricksDialect implements all 8 DialectStrategy protocol members with correct capability flags (no indexes, no fast row counts, no stored procedures)
- Lazy import gating prevents ImportError when databricks packages not installed, with helpful install message
- ConnectionManager.connect_with_config routes DatabricksConnectionConfig to connect_with_url with properly constructed databricks:// URL
- pyproject.toml databricks extras populated with databricks-sqlalchemy>=2.0.0 and databricks-sql-connector>=4.0.0
- 25 new tests (14 dialect + 6 connect_tool + 5 connection_manager update), 709 total unit tests passing

## Task Commits

Each task was committed atomically:

1. **Task 1: Implement DatabricksDialect and register in dialect system** - `658d3ce` (feat)
2. **Task 2: Wire DatabricksConnectionConfig into ConnectionManager.connect_with_config()** - `551b99d` (feat)

_Note: TDD tasks -- tests written first (RED), then implementation (GREEN)._

## Files Created/Modified
- `src/db/dialects/databricks.py` - DatabricksDialect class with token auth URL construction and lazy import gating
- `src/db/dialects/__init__.py` - Registration of DatabricksDialect and export
- `src/db/connection.py` - connect_with_config routing for DatabricksConnectionConfig
- `pyproject.toml` - databricks optional extras populated
- `tests/unit/test_databricks_dialect.py` - 14 tests for protocol compliance, URL construction, registry
- `tests/unit/test_connect_tool.py` - 5 new tests for Databricks config routing
- `tests/unit/test_connection_manager.py` - Updated unsupported config test (ValueError instead of NotImplementedError)

## Decisions Made
- Used backtick quoting for Databricks identifiers per Databricks SQL specification (D-06)
- Token URL-encoded via `quote_plus` to handle special characters safely (D-02, T-11-01 mitigation)
- Changed fallback error in connect_with_config from `NotImplementedError` to `ValueError` for unsupported config types -- more appropriate now that all known config types are handled

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Updated existing test expecting NotImplementedError**
- **Found during:** Task 2 (connect_with_config routing)
- **Issue:** test_connection_manager.py had a test expecting NotImplementedError for DatabricksConnectionConfig, which was a Phase 11 placeholder
- **Fix:** Updated test to use a MagicMock config type and expect ValueError for genuinely unsupported types
- **Files modified:** tests/unit/test_connection_manager.py
- **Verification:** All 709 unit tests pass
- **Committed in:** 551b99d (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 bug fix -- stale test expectation)
**Impact on plan:** Minimal -- expected consequence of implementing previously-stubbed functionality.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- DatabricksDialect registered and routable via ConnectionManager
- Plan 02 can build metadata features (DESCRIBE TABLE, SHOW SCHEMAS, etc.) on top of this foundation
- Databricks packages remain optional -- all tests pass without them installed

## Self-Check: PASSED

---
*Phase: 11-databricksdialect*
*Completed: 2026-04-15*
