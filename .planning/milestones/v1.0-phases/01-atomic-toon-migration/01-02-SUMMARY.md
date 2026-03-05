---
phase: 01-atomic-toon-migration
plan: 02
subsystem: api
tags: [toon, serialization, mcp-tools, integration-tests]

# Dependency graph
requires:
  - phase: 01-atomic-toon-migration/01
    provides: "encode_response() in src/serialization.py, parse_tool_response() in tests/helpers.py"
provides:
  - "All 9 MCP tools return TOON-encoded strings via encode_response"
  - "All integration tests decode TOON via parse_tool_response"
  - "tests/utils.py assert helpers use parse_tool_response"
affects: [01-atomic-toon-migration/03, docstrings-update]

# Tech tracking
tech-stack:
  added: []
  patterns:
    - "encode_response(dict) replaces json.dumps(dict) in all tool return paths"
    - "parse_tool_response(str) replaces json.loads(str) in all test tool-response parsing"

key-files:
  created: []
  modified:
    - src/mcp_server/schema_tools.py
    - src/mcp_server/query_tools.py
    - src/mcp_server/analysis_tools.py
    - tests/utils.py
    - tests/integration/test_discovery.py
    - tests/integration/test_get_column_info.py
    - tests/integration/test_pk_discovery.py
    - tests/integration/test_query_execution.py
    - tests/integration/test_fk_candidates.py
    - tests/integration/test_sample_data.py

key-decisions:
  - "Removed default=str from analysis_tools.py json.dumps call -- encode_response pre-serializer handles datetime/Decimal/StrEnum"

patterns-established:
  - "Tool module pattern: from src.serialization import encode_response; return encode_response({...})"
  - "Test pattern: from tests.helpers import parse_tool_response; data = parse_tool_response(result)"

requirements-completed: [SRLZ-03, TEST-02, TEST-03]

# Metrics
duration: 4min
completed: 2026-03-04
---

# Phase 1 Plan 2: Atomic Swap Summary

**All 9 MCP tools now return TOON-encoded strings, all integration tests decode via parse_tool_response -- zero mixed JSON/TOON state**

## Performance

- **Duration:** 4 min
- **Started:** 2026-03-04T20:29:09Z
- **Completed:** 2026-03-04T20:33:04Z
- **Tasks:** 2
- **Files modified:** 10

## Accomplishments
- Replaced 40 json.dumps calls across 3 tool modules with encode_response
- Replaced 64+ json.loads calls across 6 integration test files and utils with parse_tool_response
- All 392 tests pass with zero regressions (41 skipped for env-dependent integration tests)

## Task Commits

Each task was committed atomically:

1. **Task 1: Migrate all 3 tool modules from json.dumps to encode_response** - `66c7b40` (feat)
2. **Task 2: Migrate all integration tests and utils from json.loads to parse_tool_response** - `cd4e500` (feat)

## Files Created/Modified
- `src/mcp_server/schema_tools.py` - 16 json.dumps replaced with encode_response, import json removed
- `src/mcp_server/query_tools.py` - 11 json.dumps replaced with encode_response, import json removed
- `src/mcp_server/analysis_tools.py` - 13 json.dumps replaced with encode_response, default=str removed, import json removed
- `tests/utils.py` - assert_json_contains and assert_json_has_keys now use parse_tool_response
- `tests/integration/test_discovery.py` - 11 json.loads replaced with parse_tool_response
- `tests/integration/test_get_column_info.py` - 14 json.loads replaced with parse_tool_response
- `tests/integration/test_pk_discovery.py` - 9 json.loads replaced with parse_tool_response
- `tests/integration/test_query_execution.py` - 13 json.loads replaced with parse_tool_response
- `tests/integration/test_fk_candidates.py` - 16 json.loads replaced with parse_tool_response
- `tests/integration/test_sample_data.py` - 1 json.loads replaced with parse_tool_response

## Decisions Made
- Removed `default=str` from analysis_tools.py -- encode_response's pre-serializer handles datetime, Decimal, and StrEnum that default=str was catching. This is stricter by design (TypeError on unrecognized types).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Fixed import sorting in test_sample_data.py**
- **Found during:** Task 2
- **Issue:** ruff I001 import sorting error after moving imports around
- **Fix:** Ran `uv run ruff check --fix` to auto-sort imports
- **Files modified:** tests/integration/test_sample_data.py
- **Verification:** ruff clean
- **Committed in:** cd4e500 (Task 2 commit)

---

**Total deviations:** 1 auto-fixed (1 blocking)
**Impact on plan:** Trivial import sorting fix. No scope creep.

## Issues Encountered
None

## User Setup Required
None - no external service configuration required.

## Next Phase Readiness
- All 9 tools return TOON, all tests consume TOON -- the atomic swap is complete
- Ready for Plan 03: docstring updates to reflect TOON format in tool documentation

---
*Phase: 01-atomic-toon-migration*
*Completed: 2026-03-04*
