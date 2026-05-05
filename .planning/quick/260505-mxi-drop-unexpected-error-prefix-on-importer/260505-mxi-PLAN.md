---
phase: 260505-mxi
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/mcp_server/_errors.py
  - src/mcp_server/schema_tools.py
  - src/mcp_server/analysis_tools.py
  - tests/mcp_server/test_import_error_messaging.py
autonomous: true
requirements:
  - QUICK-260505-mxi
must_haves:
  truths:
    - "When databricks-sqlalchemy is absent, connect_database returns a message that starts with the install hint (not 'Unexpected error:')"
    - "ImportError/ModuleNotFoundError from any of the 4 generic handlers is surfaced verbatim, with no prefix"
    - "Non-import exceptions still go through the existing 'Unexpected error:' path unchanged"
    - "All 4 call sites (schema_tools.py:205, analysis_tools.py:143/247/403) use the same formatting helper"
    - "Regression tests pin the no-prefix wording for ImportError and the preserved prefix for generic Exception"
  artifacts:
    - path: "src/mcp_server/_errors.py"
      provides: "format_unexpected_error() helper — returns install-hint verbatim for ImportError/ModuleNotFoundError, 'Unexpected error: {Type}: {msg}' otherwise"
      exports: ["format_unexpected_error"]
    - path: "tests/mcp_server/test_import_error_messaging.py"
      provides: "Unit tests pinning wording for ImportError and generic Exception paths"
  key_links:
    - from: "src/mcp_server/schema_tools.py"
      to: "src/mcp_server/_errors.py"
      via: "from ._errors import format_unexpected_error"
      pattern: "format_unexpected_error\\("
    - from: "src/mcp_server/analysis_tools.py"
      to: "src/mcp_server/_errors.py"
      via: "from ._errors import format_unexpected_error (used at 3 handler sites)"
      pattern: "format_unexpected_error\\("
---

<objective>
Stop wrapping ImportError/ModuleNotFoundError in "Unexpected error:" when they bubble out of MCP tool handlers. These errors are almost always missing optional extras (e.g., databricks-sqlalchemy) and the dialect's raise site already provides an actionable install hint — the wrapper obscures it.

Purpose: Surface actionable install hints to MCP clients cleanly so users follow the hint instead of reporting a bug.
Output: Shared helper + 4 updated call sites + regression tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/todos/pending/2026-04-28-missing-databricks-package-error-prefix.md
@CLAUDE.md

<interfaces>
<!-- Current pattern at all 4 call sites is identical. Extracted for executor convenience. -->

From src/mcp_server/schema_tools.py (around line 200-210, inside connect_database generic handler):
```python
except Exception as e:
    logger.exception("Unexpected error in connect_database")
    ...
    error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
    return encode_response({"status": "error", "error_message": error_msg})
```

From src/mcp_server/analysis_tools.py (identical pattern at lines 143, 247, 403):
```python
except Exception as e:
    if isinstance(e, SQLAlchemyError):
        _cat, guidance = _classify_db_error(e)
        error_msg = f"{guidance} ({e})"
    else:
        error_msg = f"Unexpected error: {str(e)}"
    return encode_response({"status": "error", "error_message": error_msg})
```

Note: schema_tools.py uses `{type(e).__name__}: {str(e)}`, analysis_tools.py uses `{str(e)}`. The helper should preserve each site's existing format for non-import errors (add a `include_type` flag, or accept the non-import formatter as a callable). Simpler option: helper handles ImportError only, fall through to existing format otherwise.

ImportError raise site (context only, no change):
```python
# src/db/dialects/databricks.py
raise ImportError(
    "Databricks support requires databricks-sqlalchemy. "
    "Install with: pip install dbmcp[databricks]"
)
```
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add format_unexpected_error helper with tests (RED→GREEN)</name>
  <files>src/mcp_server/_errors.py, tests/mcp_server/test_import_error_messaging.py</files>
  <behavior>
    - Test 1: format_unexpected_error(ImportError("Install with: pip install dbmcp[databricks]")) returns exactly "Install with: pip install dbmcp[databricks]" — no prefix, no type name.
    - Test 2: format_unexpected_error(ModuleNotFoundError("No module named 'foo'")) returns exactly "No module named 'foo'" — no prefix.
    - Test 3: format_unexpected_error(RuntimeError("boom"), include_type=True) returns "Unexpected error: RuntimeError: boom" (preserves schema_tools format).
    - Test 4: format_unexpected_error(RuntimeError("boom"), include_type=False) returns "Unexpected error: boom" (preserves analysis_tools format).
    - Test 5 (acceptance pin): the returned string for ImportError MUST NOT start with "Unexpected error:".
  </behavior>
  <action>
    Create `src/mcp_server/_errors.py` with a single public function:

    ```python
    def format_unexpected_error(exc: BaseException, *, include_type: bool = False) -> str:
        """Format a generic-handler exception for MCP client error_message field.

        ImportError/ModuleNotFoundError are surfaced verbatim (they carry an
        actionable install hint at their raise site). All other exceptions keep
        the legacy "Unexpected error:" prefix so genuine bugs remain visible.
        """
        if isinstance(exc, (ImportError, ModuleNotFoundError)):
            return str(exc)
        if include_type:
            return f"Unexpected error: {type(exc).__name__}: {exc}"
        return f"Unexpected error: {exc}"
    ```

    Then create `tests/mcp_server/test_import_error_messaging.py` with the 5 tests above. Keep tests pure (no fixtures, no MCP wiring) — they pin the helper's contract.

    Run tests: `uv run pytest tests/mcp_server/test_import_error_messaging.py -x` — must pass.

    Why a helper (Rule of Three check): 4 identical call sites clears the threshold. The helper also gives us a single place to pin the no-prefix behavior via unit tests, avoiding a matrix of tool-level integration tests.
  </action>
  <verify>
    <automated>uv run pytest tests/mcp_server/test_import_error_messaging.py -x -v</automated>
  </verify>
  <done>Helper module exists, all 5 tests pass, test file explicitly asserts "does not start with 'Unexpected error:'" for ImportError.</done>
</task>

<task type="auto">
  <name>Task 2: Wire helper into all 4 MCP tool handler sites</name>
  <files>src/mcp_server/schema_tools.py, src/mcp_server/analysis_tools.py</files>
  <action>
    Replace the 4 `error_msg = f"Unexpected error: ..."` lines with calls to the new helper. Preserve each file's existing format for non-import errors (the helper's `include_type` flag handles this).

    **schema_tools.py (line ~205, connect_database):**
    - Add import: `from ._errors import format_unexpected_error`
    - Replace: `error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"`
    - With:    `error_msg = format_unexpected_error(e, include_type=True)`
    - Leave the `logger.exception("Unexpected error in connect_database")` line at :200 unchanged — internal logging still wants the full context even for ImportError.

    **analysis_tools.py (lines 143, 247, 403):**
    - Add import: `from ._errors import format_unexpected_error`
    - Replace each: `error_msg = f"Unexpected error: {str(e)}"`
    - With:         `error_msg = format_unexpected_error(e, include_type=False)`
    - The surrounding `if isinstance(e, SQLAlchemyError)` branch is unchanged (SQLAlchemy classification takes precedence over ImportError handling — import failures at analysis time would not be SQLAlchemyError anyway).

    Do NOT remove the logger.exception call in schema_tools.py — operators still want ImportError in server logs for debugging install issues.
  </action>
  <verify>
    <automated>uv run pytest tests/ -x -q && uv run ruff check src/mcp_server/_errors.py src/mcp_server/schema_tools.py src/mcp_server/analysis_tools.py</automated>
  </verify>
  <done>
    - All 4 call sites use `format_unexpected_error(e, ...)`.
    - Full test suite passes (no regressions).
    - ruff clean on touched files.
    - grep confirms: `grep -n "Unexpected error:" src/mcp_server/*.py` returns only the logger.exception line in schema_tools.py (not the f-string) and the helper's own internal format strings in _errors.py.
  </done>
</task>

</tasks>

<verification>
Phase-level checks:

1. **Acceptance criterion (pins todo):** Running the MCP server without databricks-sqlalchemy and calling `connect_database(sqlalchemy_url="databricks://...")` returns `error_message` starting with "Databricks support requires databricks-sqlalchemy. Install with: pip install dbmcp[databricks]" — NOT "Unexpected error: ...".

2. **Regression pin:** `uv run pytest tests/mcp_server/test_import_error_messaging.py -v` — 5 tests pass, including the explicit "does not start with 'Unexpected error:'" assertion.

3. **No broken behavior:** `uv run pytest tests/ -x -q` — full suite green (872+ tests).

4. **No stray prefixes:** `grep -rn "f\"Unexpected error:" src/mcp_server/` returns only matches inside `_errors.py` (helper's own format strings).

5. **Lint clean:** `uv run ruff check src/mcp_server/` — no new warnings on touched files.
</verification>

<success_criteria>
- [ ] `src/mcp_server/_errors.py` exists with `format_unexpected_error` helper
- [ ] All 5 helper unit tests pass, including the explicit no-prefix assertion for ImportError
- [ ] schema_tools.py:205 and analysis_tools.py:143/247/403 all route through the helper
- [ ] `logger.exception` in connect_database is preserved (operator debugging retained)
- [ ] Full test suite passes (no regressions)
- [ ] ruff clean on touched files
- [ ] Source todo `.planning/todos/pending/2026-04-28-missing-databricks-package-error-prefix.md` can be moved to completed
</success_criteria>

<output>
After completion, create `.planning/quick/260505-mxi-drop-unexpected-error-prefix-on-importer/260505-mxi-SUMMARY.md` summarizing:
- Helper added and which call sites now route through it
- Test file and count of pinned assertions
- Confirmation that source todo's acceptance criterion is met
- Any deviations (e.g., if a 5th call site was discovered during implementation)
</output>
