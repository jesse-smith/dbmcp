---
phase: quick-5
plan: 01
subsystem: mcp-server/schema-tools
tags: [refactor, complexity, connect-database]
dependency_graph:
  requires: []
  provides: [ResolvedConnectionParams-dataclass, connection-resolution-helpers]
  affects: [schema_tools.py, schema.py]
tech_stack:
  added: []
  patterns: [parameter-resolution-extraction, pick-helper-pattern]
key_files:
  created: []
  modified:
    - src/models/schema.py
    - src/mcp_server/schema_tools.py
decisions:
  - Used tuple return pattern (params, error) for _resolve_connection_params instead of exceptions
  - Extracted _pick and _resolve_env_field micro-helpers to eliminate per-field if/else branching
  - Separated _merge_with_config (named connection path) from _defaults_only (direct args path)
metrics:
  duration: 2min
  completed: "2026-03-11"
  tasks_completed: 2
  tasks_total: 2
---

# Quick Task 5: Refactor connect_database Complexity Summary

Extracted connection parameter resolution into private helpers with ResolvedConnectionParams dataclass, reducing connect_database cyclomatic complexity from 48 to under 15.

## What Was Done

### Task 1: Add ResolvedConnectionParams dataclass and extract helpers (b3b6ab1)

**Files modified:** `src/models/schema.py`, `src/mcp_server/schema_tools.py`

Added `ResolvedConnectionParams` dataclass to `src/models/schema.py` to group the 9 effective connection parameters.

Extracted five private helpers in `schema_tools.py`:
- `_pick(explicit, config_val)` -- returns explicit arg if provided, else config value
- `_resolve_env_field(explicit, config_val)` -- resolves credential fields with env var references
- `_merge_with_config(...)` -- merges explicit args with a named ConnectionConfig
- `_defaults_only(...)` -- builds effective params from explicit args + hardcoded defaults
- `_resolve_connection_params(...)` -- top-level orchestrator returning `(ResolvedConnectionParams | None, error_dict | None)`

Simplified `connect_database` to: call `_resolve_connection_params` -> early return on error -> parse auth method -> `_sync_connect` closure -> try/except.

### Task 2: Verify complexity and lint

- `scripts/check_complexity.py` exits 0 (all functions under 15)
- `uv run ruff check src/` clean
- 603 unit tests pass, 6 skipped

## Deviations from Plan

None -- plan executed exactly as written. No further decomposition was needed after Task 1; complexity was already under 15.

## Verification Results

| Check | Result |
|-------|--------|
| `scripts/check_complexity.py` | PASSED (all under 15) |
| `uv run ruff check src/` | All checks passed |
| `uv run pytest tests/ --ignore=tests/integration` | 603 passed, 6 skipped |
| Public API unchanged | Yes -- same parameters, return shape, error messages |

## Self-Check: PASSED
