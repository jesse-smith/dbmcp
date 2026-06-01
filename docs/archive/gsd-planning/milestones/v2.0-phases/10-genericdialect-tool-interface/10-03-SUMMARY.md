---
phase: 10-genericdialect-tool-interface
plan: 03
subsystem: infra
tags: [pyproject, packaging, optional-deps, extras]

requires:
  - phase: 10-01
    provides: Lazy import pattern in dialect modules (pyodbc not imported at module level)
provides:
  - Driver-free core install (no pyodbc/azure-identity in base dependencies)
  - "[mssql] optional extra with pyodbc and azure-identity"
  - "[databricks] placeholder extra for Phase 11"
  - "[all] meta-extra combining mssql + databricks + examples"
affects: [11-databricks-dialect, packaging, deployment]

tech-stack:
  added: []
  patterns: [optional-dependency-extras, driver-free-core]

key-files:
  created:
    - tests/unit/test_pyproject_extras.py
  modified:
    - pyproject.toml
    - uv.lock

key-decisions:
  - "Core install includes only mcp[cli], sqlalchemy, sqlglot, toon-format -- no database drivers"
  - "[databricks] extra left empty as placeholder for Phase 11 population"

patterns-established:
  - "Optional extras: database drivers installed via pip install dbmcp[dialect]"
  - "Meta-extra [all] aggregates all dialect and utility extras"

requirements-completed: [CONF-04]

duration: 2min
completed: 2026-04-14
---

# Phase 10 Plan 03: Optional Dependency Extras Summary

**Restructured pyproject.toml to make core install driver-free with [mssql], [databricks], and [all] optional extras**

## Performance

- **Duration:** 2 min
- **Started:** 2026-04-14T20:17:34Z
- **Completed:** 2026-04-14T20:19:47Z
- **Tasks:** 1
- **Files modified:** 3

## Accomplishments
- Moved pyodbc and azure-identity from core dependencies to [mssql] optional extra
- Added [databricks] placeholder extra (empty, ready for Phase 11)
- Added [all] meta-extra combining mssql + databricks + examples
- Created 9 test cases verifying extras structure via pyproject.toml parsing
- Full test suite passes (648 passed, 41 skipped)

## Task Commits

Each task was committed atomically:

1. **Task 1: Restructure pyproject.toml dependencies** (TDD)
   - RED: `b8ca7b0` (test: add failing tests for pyproject extras)
   - GREEN: `14dbfdd` (feat: restructure pyproject.toml with optional dependency extras)

## Files Created/Modified
- `pyproject.toml` - Restructured dependencies: pyodbc/azure-identity moved to [mssql] extra, added [databricks] and [all] extras
- `uv.lock` - Updated lock file reflecting new dependency structure
- `tests/unit/test_pyproject_extras.py` - 9 tests verifying extras structure (core deps exclusion, extras inclusion, required core packages)

## Decisions Made
- Core install includes only mcp[cli], sqlalchemy, sqlglot, toon-format -- no database drivers
- [databricks] extra left empty as placeholder, to be populated in Phase 11
- Dev environment uses `uv pip install -e ".[mssql]"` to get pyodbc for testing

## Deviations from Plan

None - plan executed exactly as written.

## Issues Encountered

None.

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Core install is now driver-free, enabling non-MSSQL users to install without pyodbc
- [databricks] extra ready for Phase 11 to populate with databricks-sqlalchemy and databricks-sql-connector
- Lazy import pattern (from Plan 01) ensures runtime compatibility when extras are not installed

## Self-Check: PASSED

All files exist, all commits verified.

---
*Phase: 10-genericdialect-tool-interface*
*Completed: 2026-04-14*
