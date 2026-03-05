---
phase: quick-2
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - tests/unit/test_async_tools.py
  - tests/unit/test_query_timeout.py
  - src/db/connection.py
autonomous: true
requirements: [QUICK-2]

must_haves:
  truths:
    - "Zero ruff warnings on all files touched by query timeout and async changes"
    - "PoolConfig.query_timeout is documented in the dataclass docstring"
    - "No leftover attrs_before/connect_args artifacts from abandoned approach"
    - "Event mock pattern (patch src.db.connection.event) is consistent across all test files that mock ConnectionManager.connect()"
    - "All 9 MCP tools use asyncio.to_thread for sync DB work"
  artifacts:
    - path: "tests/unit/test_async_tools.py"
      provides: "Async wrapper tests with clean imports"
    - path: "tests/unit/test_query_timeout.py"
      provides: "Timeout tests with no unused variables"
    - path: "src/db/connection.py"
      provides: "PoolConfig with complete docstring"
  key_links:
    - from: "src/db/connection.py"
      to: "tests/unit/test_query_timeout.py"
      via: "event.listens_for(engine, 'connect') tested by mock_event"
      pattern: "event\\.listens_for"
    - from: "src/mcp_server/schema_tools.py"
      to: "tests/unit/test_async_tools.py"
      via: "asyncio.to_thread(_sync_work) tested by patch"
      pattern: "asyncio\\.to_thread"
---

<objective>
Fix ruff lint warnings and docstring gaps introduced by the query timeout and async DB execution changes.

Purpose: Ensure codebase quality standards are maintained after the multi-iteration implementation of query timeouts (event listener approach) and asyncio.to_thread wrapping.

Output: Clean lint, complete docs, all tests passing.
</objective>

<execution_context>
@./.claude/get-shit-done/workflows/execute-plan.md
@./.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@src/db/connection.py
@tests/unit/test_async_tools.py
@tests/unit/test_query_timeout.py
@tests/unit/test_connection.py
@tests/compliance/test_nfr_compliance.py
@src/mcp_server/schema_tools.py
@src/mcp_server/query_tools.py
@src/mcp_server/analysis_tools.py
</context>

<tasks>

<task type="auto">
  <name>Task 1: Fix ruff warnings and complete PoolConfig docstring</name>
  <files>tests/unit/test_async_tools.py, tests/unit/test_query_timeout.py, src/db/connection.py</files>
  <action>
Fix 4 ruff errors found in the query timeout / async changes:

1. **tests/unit/test_async_tools.py** (3 errors):
   - Remove unused `MagicMock` import (F401) — only `patch` is used
   - Remove unused `pytest` import (F401) — no pytest fixtures or markers used
   - Fix import sorting (I001) — after removing unused imports, ensure `from unittest.mock import patch` comes after stdlib, then third-party, then local. The comment `# Import through server to resolve circular imports` should stay above the `from src.mcp_server.server import ...` block.

2. **tests/unit/test_query_timeout.py** (1 error):
   - In `TestTimeoutEventCallbackBehavior.test_event_callback_sets_timeout_on_dbapi_connection` (around line 271), remove the unused assignment `original_event_listens_for = sqlalchemy.event.listens_for`. The `import sqlalchemy` line above it can also be removed since it's only used for that assignment. Verify: the test captures listeners via `mock_event.listens_for.side_effect = capture_listens_for`, not via the real sqlalchemy event — so the real import is unnecessary.

3. **src/db/connection.py** — Update PoolConfig docstring:
   - Add `query_timeout` to the Attributes docstring: `query_timeout: Per-statement query timeout in seconds. 0 disables timeout. (default: 30)`
  </action>
  <verify>
    <automated>uv run ruff check src/db/connection.py tests/unit/test_async_tools.py tests/unit/test_query_timeout.py tests/unit/test_connection.py tests/compliance/test_nfr_compliance.py src/mcp_server/schema_tools.py src/mcp_server/query_tools.py src/mcp_server/analysis_tools.py</automated>
  </verify>
  <done>Zero ruff errors on all files in scope. PoolConfig docstring includes query_timeout field.</done>
</task>

<task type="auto">
  <name>Task 2: Run full test suite to confirm no regressions</name>
  <files>tests/unit/test_query_timeout.py, tests/unit/test_async_tools.py, tests/unit/test_connection.py, tests/compliance/test_nfr_compliance.py</files>
  <action>
Run the full test suite (`uv run pytest tests/ -x --tb=short`) to confirm:
- All 62 tests in the 4 target files still pass after lint fixes
- No regressions in the broader test suite
- Zero ruff warnings project-wide (run `uv run ruff check src/ tests/` and confirm only the pre-existing `src/metrics.py` Generator warning if any)

If any test fails, diagnose and fix the root cause (likely an import removal that was actually needed).
  </action>
  <verify>
    <automated>uv run pytest tests/ -x --tb=short && uv run ruff check src/db/connection.py tests/unit/test_async_tools.py tests/unit/test_query_timeout.py</automated>
  </verify>
  <done>Full test suite passes with zero failures. Ruff clean on all modified files.</done>
</task>

</tasks>

<verification>
- `uv run ruff check src/db/connection.py tests/unit/test_async_tools.py tests/unit/test_query_timeout.py` returns 0 errors
- `uv run pytest tests/ -x` passes all tests
- `grep -n "query_timeout" src/db/connection.py` shows the field in both the dataclass body AND the docstring
- No references to `attrs_before` in connection.py outside the Azure AD Integrated auth path (which correctly uses it for the access token only)
- All 9 MCP tools in schema_tools.py, query_tools.py, analysis_tools.py use `await asyncio.to_thread(_sync_work)` pattern
</verification>

<success_criteria>
- Zero ruff errors on all files modified by query timeout / async changes
- PoolConfig docstring is complete with query_timeout documented
- Full test suite passes (all ~385+ tests)
- No leftover artifacts from the abandoned attrs_before approach for query timeout
</success_criteria>

<output>
After completion, create `.planning/quick/2-verify-query-timeout-changes-meet-codeba/2-SUMMARY.md`
</output>
