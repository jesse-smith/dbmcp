---
phase: 260428-fr7
plan: 01
subsystem: config
tags: [config, mcp, error-handling, tdd]
requires:
  - src/config.py
  - src/mcp_server/schema_tools.py
provides:
  - AppConfig.load_error field for preserving parse failures
  - connect_database surfaces config.load_error to MCP clients
affects:
  - src/config.py
  - src/mcp_server/schema_tools.py
  - tests/unit/test_config.py
  - tests/unit/test_schema_tools_config_error.py
tech-stack:
  added: []
  patterns:
    - dataclass field extension (non-breaking, default None)
    - guard-clause error branching in async tool handler
key-files:
  created:
    - tests/unit/test_schema_tools_config_error.py
  modified:
    - src/config.py
    - src/mcp_server/schema_tools.py
    - tests/unit/test_config.py
decisions:
  - Absolute-path resolution in load_error for better debugging UX
  - Omitted the optional third smoke test for connect_database happy-path (plan explicitly permitted this; existing test_connect_tool.py already covers the post-name-check path)
metrics:
  duration: ~8 min
  completed: 2026-04-28
  tasks: 2
  files_changed: 4
  tests_added: 6
---

# Phase 260428-fr7 Plan 01: Surface Config Parse Failures to the MCP Summary

Preserve TOML parse failures from `load_config()` and surface them through `connect_database` so MCP clients see the real cause instead of the misleading "Available: none" message.

## What Changed

- `AppConfig` gained a `load_error: str | None = None` field (non-breaking; default keeps existing call sites intact).
- `load_config()` now returns `AppConfig(load_error=f"{type(e).__name__}: {e} (path=<resolved>)")` from both the `TOMLDecodeError` and generic `Exception` branches. The file path is resolved to absolute form for better debug output. Empty-connections fallback is preserved.
- `connect_database` in `src/mcp_server/schema_tools.py` now checks `config.load_error` before the name-lookup branch and returns `{"status": "error", "error_message": f"config parse error: {load_error}"}` when set. The legacy "Named connection 'X' not found ... Available: none" message is unchanged for the `load_error=None` path.

## Tests Added

- `tests/unit/test_config.py` (4 new tests + 1 updated):
  - `test_load_config_sets_load_error_on_invalid_toml` — asserts load_error contains path + `TOMLDecodeError` token
  - `test_load_config_sets_load_error_on_missing_dialect` — real-world v2.0 trigger
  - `test_load_config_load_error_is_none_on_success` — happy path unchanged
  - `test_load_config_returns_empty_connections_when_load_error_set` — empty-connections fallback
  - `test_malformed_toml_returns_defaults` — updated to assert load_error is populated
- `tests/unit/test_schema_tools_config_error.py` (new file, 2 tests):
  - `test_connect_database_surfaces_parse_error_when_load_error_set` — asserts prefix, substring match, and absence of legacy message
  - `test_connect_database_unknown_connection_message_unchanged_when_no_load_error` — preserves existing behavior

## Verification

- `uv run pytest tests/unit/test_config.py tests/unit/test_schema_tools_config_error.py -v` — all 57 pass
- `uv run pytest tests/unit/` — 809 passed, 37 skipped (no regressions)
- `uv run ruff check src/config.py src/mcp_server/schema_tools.py tests/unit/test_config.py tests/unit/test_schema_tools_config_error.py` — All checks passed

## Commits

- `c18612d` feat(260428-fr7-01): preserve TOML parse failures on AppConfig.load_error
- `fd48be3` feat(260428-fr7-02): surface config parse errors through connect_database

## Decisions Made

1. **Absolute path in load_error** — `config_path.resolve()` (with OSError fallback to the un-resolved string). The plan accepted "equivalent formatted string"; absolute paths give MCP clients and humans actionable debugging info (the original discovery bug was partially about path confusion).
2. **Skipped optional third smoke test in Task 2** — the plan explicitly allowed skipping it if mocking the full connection flow was too heavy. `test_connect_tool.py::test_connection_name_valid_calls_connect_with_config` already exercises the happy-path branch gate, so the skip has no coverage cost.

## Deviations from Plan

**None of consequence.** Two minor surface adjustments, both within the plan's stated latitude:

1. **[Enhancement] Resolved path to absolute form** — Plan said "include error type, message, and the file path". I used `config_path.resolve()` so users see `/Users/.../dbmcp.toml` instead of `dbmcp.toml`. Tests assert absolute-path substring match.
2. **[Plan-permitted skip] Third Task 2 smoke test omitted** — See Decisions #2 above.

The plan referenced a `load_config(explicit_path=...)` signature in task descriptions, but the actual function signature is `load_config()` (no args) and discovery is cwd-based. Tests use `monkeypatch.chdir(tmp_path)` to drive discovery, matching the existing test file's conventions. No signature change was needed.

## Success Criteria

- [x] `AppConfig.load_error` carries parse failures through the module singleton
- [x] MCP clients receive `config parse error: ...` from `connect_database` when dbmcp.toml fails to parse
- [x] Existing "not found / Available:" behavior preserved for `load_error=None`
- [x] Tests cover invalid TOML, missing-dialect TOML, successful load, error-surfacing, and unchanged not-found message
- [x] Zero new ruff warnings; full unit suite green (809 passed)

## Self-Check: PASSED

- src/config.py: FOUND (modified, load_error field + except branches)
- src/mcp_server/schema_tools.py: FOUND (modified, load_error guard clause)
- tests/unit/test_config.py: FOUND (modified, 4 new tests)
- tests/unit/test_schema_tools_config_error.py: FOUND (new file, 2 tests)
- Commit c18612d: FOUND
- Commit fd48be3: FOUND
