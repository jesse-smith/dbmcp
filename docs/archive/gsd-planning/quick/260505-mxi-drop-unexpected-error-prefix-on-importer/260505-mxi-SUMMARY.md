---
phase: 260505-mxi
plan: 01
subsystem: mcp_server
tags: [error-handling, ux, ergonomics]
requires: []
provides:
  - format_unexpected_error helper
affects:
  - src/mcp_server/schema_tools.py (connect_database generic handler)
  - src/mcp_server/analysis_tools.py (3 generic handlers)
tech_stack:
  added: []
  patterns:
    - Shared error-formatting helper across 4 identical MCP tool call sites
key_files:
  created:
    - src/mcp_server/_errors.py
    - tests/mcp_server/__init__.py
    - tests/mcp_server/test_import_error_messaging.py
  modified:
    - src/mcp_server/schema_tools.py
    - src/mcp_server/analysis_tools.py
decisions:
  - ImportError/ModuleNotFoundError surfaced verbatim (raise site already carries actionable install hint)
  - include_type flag preserves each call site's existing format for non-import errors
  - logger.exception retained in connect_database for operator debugging of install issues
metrics:
  duration: ~4min
  completed_date: 2026-05-05
  tasks_completed: 2
  files_touched: 5
  tests_added: 5
  tests_total_passing: 929
---

# Quick Task 260505-mxi: Drop "Unexpected error:" Prefix on ImportError Summary

Shared `format_unexpected_error` helper extracts the ImportError-verbatim / generic-prefixed formatting used by 4 identical MCP tool handlers; users without `databricks-sqlalchemy` now see the install hint cleanly instead of a wrapped "Unexpected error:" message.

## What Changed

- **New module** `src/mcp_server/_errors.py` exports `format_unexpected_error(exc, *, include_type=False)`:
  - Returns `str(exc)` verbatim for `ImportError`/`ModuleNotFoundError`
  - Returns `f"Unexpected error: {type(exc).__name__}: {exc}"` when `include_type=True`
  - Returns `f"Unexpected error: {exc}"` otherwise
- **4 call sites routed through the helper:**
  - `schema_tools.py:206` — connect_database (include_type=True; preserves `{Type}: {msg}` format)
  - `analysis_tools.py:144` — get_column_info (include_type=False)
  - `analysis_tools.py:248` — find_pk_candidates (include_type=False)
  - `analysis_tools.py:404` — find_fk_candidates (include_type=False)
- **logger.exception preserved** in connect_database (operators still see ImportError full stack in server logs for debugging install problems).

## Test File and Pinned Assertions

`tests/mcp_server/test_import_error_messaging.py` — 5 unit tests, all pure (no fixtures, no MCP wiring):

1. `test_import_error_is_verbatim_no_prefix` — exact equality for ImportError.
2. `test_module_not_found_error_is_verbatim_no_prefix` — exact equality for ModuleNotFoundError.
3. `test_generic_exception_with_type_prefix` — pins `"Unexpected error: RuntimeError: boom"` format.
4. `test_generic_exception_without_type_prefix` — pins `"Unexpected error: boom"` format.
5. `test_import_error_does_not_start_with_unexpected_prefix` — **acceptance pin for the source todo**: asserts `not result.startswith("Unexpected error:")` and `result.startswith("Databricks support requires databricks-sqlalchemy")`.

## Acceptance Criterion

Source todo `.planning/todos/pending/2026-04-28-missing-databricks-package-error-prefix.md` acceptance criterion is met: ImportError from the databricks dialect's raise site now reaches MCP clients as `"Databricks support requires databricks-sqlalchemy. Install with: pip install dbmcp[databricks]"` — no `"Unexpected error:"` prefix, no type name wrapper. The `test_import_error_does_not_start_with_unexpected_prefix` unit test pins this for all future regressions.

Todo can be moved from `.planning/todos/pending/` to `.planning/todos/completed/`.

## Deviations from Plan

**None.** No 5th call site was discovered; the 4 handlers listed in the plan were the only `f"Unexpected error:"` sites in `src/mcp_server/`. Test directory `tests/mcp_server/` did not exist and was created with an `__init__.py` (trivial, implied by the plan's target path).

## Verification Results

- `uv run pytest tests/mcp_server/test_import_error_messaging.py -x -v` — 5/5 pass.
- `uv run pytest tests/ -x -q` — **929 passed, 78 skipped** (baseline was 872; +5 new tests, and prior quick-task work since baseline accounts for the rest).
- `uv run ruff check src/mcp_server/_errors.py src/mcp_server/schema_tools.py src/mcp_server/analysis_tools.py` — clean.
- `grep -n "f\"Unexpected error:" src/mcp_server/*.py` — only matches inside `_errors.py` (helper's own format strings); no stray prefixes left in tool handlers.

## Commits

| Task | Type | Hash | Message |
|------|------|------|---------|
| 1 (RED) | test | 0859b53 | add failing tests for format_unexpected_error helper |
| 1 (GREEN) | feat | 02df7e0 | add format_unexpected_error helper |
| 2 | feat | 4afd68f | route 4 MCP tool handlers through format_unexpected_error |

## Self-Check: PASSED

- `src/mcp_server/_errors.py` FOUND
- `tests/mcp_server/test_import_error_messaging.py` FOUND
- `tests/mcp_server/__init__.py` FOUND
- Commits 0859b53, 02df7e0, 4afd68f FOUND in git log
- All 4 call sites confirmed routed through `format_unexpected_error` via grep
