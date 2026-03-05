---
phase: 02-staleness-guard
plan: 01
subsystem: testing
tags: [tdd, docstring-parser, field-comparison, staleness-guard, regex]

# Dependency graph
requires:
  - phase: 01-atomic-toon-migration
    provides: TOON structural outline format in all 9 tool docstrings
provides:
  - extract_fields() utility: parses TOON docstring Returns sections into structured field data
  - compare_fields() utility: bidirectional drift detection with conditional field awareness
  - 28 meta-tests covering parser and comparison logic
affects: [02-staleness-guard]

# Tech tracking
tech-stack:
  added: []
  patterns: [regex-based docstring parsing, ast-based docstring extraction to avoid circular imports, conditional field filtering by response path]

key-files:
  created:
    - tests/staleness/__init__.py
    - tests/staleness/docstring_parser.py
    - tests/staleness/comparison.py
    - tests/unit/test_staleness_parser.py
    - tests/unit/test_staleness_comparison.py
  modified: []

key-decisions:
  - "Used ast module for real-docstring tests to avoid circular imports with MCP server modules"
  - "Non-standard conditional annotations (e.g., 'detailed mode only') treated as optional -- not required in any response path"

patterns-established:
  - "Docstring parser: regex-based field extraction with indentation tracking for nesting"
  - "Comparison: conditional field exclusion via annotation parsing with 'on X only' pattern matching"

requirements-completed: [DOCS-02]

# Metrics
duration: 3min
completed: 2026-03-05
---

# Phase 2 Plan 1: Docstring Parser and Field Comparison Summary

**TDD-built docstring parser and bidirectional field comparison utilities for staleness guard drift detection**

## Performance

- **Duration:** 3 min
- **Started:** 2026-03-05T15:55:47Z
- **Completed:** 2026-03-05T15:59:22Z
- **Tasks:** 2
- **Files created:** 5

## Accomplishments
- extract_fields() parses TOON structural outline from docstrings: top-level fields, one-level nesting, and conditional annotations
- compare_fields() detects missing and extra fields bidirectionally with conditional field exclusion (on error only, on success only, detailed mode only)
- 28 meta-tests (15 parser + 13 comparison) all passing, covering edge cases, real docstrings, and nested structures
- Full unit test suite green (351 tests) with no regressions

## Task Commits

Each task was committed atomically:

1. **Task 1: TDD docstring parser** - `ada84e6` (feat)
2. **Task 2: TDD comparison logic** - `1ab9b1e` (feat)

_Both tasks followed TDD: RED (import error) -> GREEN (implementation passes all tests)_

## Files Created/Modified
- `tests/staleness/__init__.py` - Package marker for staleness guard utilities
- `tests/staleness/docstring_parser.py` - extract_fields() for TOON docstring parsing
- `tests/staleness/comparison.py` - compare_fields() for bidirectional drift detection
- `tests/unit/test_staleness_parser.py` - 15 meta-tests for parser (80+ lines)
- `tests/unit/test_staleness_comparison.py` - 13 meta-tests for comparison (40+ lines)

## Decisions Made
- Used `ast` module to extract real docstrings from source files without importing, avoiding circular import issues between MCP server modules
- Non-standard conditional annotations (e.g., "detailed mode only", "numeric columns only") treated as optional -- the staleness test cannot know if the condition was met at runtime
- Parser captures nested fields one level deep under list/object parents; deeper nesting (e.g., numeric_stats children under columns) captured as children of the immediate parent only

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Circular import when importing MCP tool functions directly**
- **Found during:** Task 1 (real docstring tests)
- **Issue:** `from src.mcp_server.schema_tools import connect_database` fails due to circular import with server.py
- **Fix:** Used `ast` module to parse source files and extract function docstrings without importing
- **Files modified:** tests/unit/test_staleness_parser.py
- **Verification:** All 15 parser tests pass including real docstring tests
- **Committed in:** ada84e6 (Task 1 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Necessary workaround for circular imports. No scope creep.

## Issues Encountered
- Pre-existing integration test failure (`test_azure_ad_auth.py`) due to external database connectivity -- not caused by our changes, out of scope

## User Setup Required

None - no external service configuration required.

## Next Phase Readiness
- Parser and comparison utilities ready for consumption by the staleness guard test (plan 02-02)
- Both modules export clean interfaces: extract_fields() and compare_fields()
- Conditional field handling covers all annotation patterns found in the 9 tool docstrings

---
*Phase: 02-staleness-guard*
*Completed: 2026-03-05*
