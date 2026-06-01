---
phase: 260505-own
plan: 01
subsystem: db.dialects.databricks
tags: [databricks, timeout, retry, connect-args, tdd]
dependency_graph:
  requires: []
  provides:
    - DatabricksDialect.create_engine now passes connect_args with _socket_timeout and _retry_stop_after_attempts_count
  affects:
    - src/db/dialects/databricks.py
    - tests/unit/test_databricks_dialect.py
tech_stack:
  added: []
  patterns:
    - dialect_defaults + user_connect_args merge (user wins per-key)
key_files:
  created: []
  modified:
    - src/db/dialects/databricks.py
    - tests/unit/test_databricks_dialect.py
decisions:
  - 30s default _socket_timeout mirrors MSSQL default connection_timeout
  - Retry cap of 2 applied by default so unreachable hosts fail in seconds, not minutes
  - User-supplied connect_args override per-key via {**defaults, **user} merge — extra user keys preserved
  - Single injection point after URL reconstruction covers both kwargs-mode and URL-mode uniformly
metrics:
  duration: ~5 min
  completed: 2026-05-05
---

# Quick Task 260505-own: Databricks connect_timeout default + retry cap Summary

**One-liner:** Plumbed `connect_args={"_socket_timeout": 30, "_retry_stop_after_attempts_count": 2}` into `DatabricksDialect.create_engine` so unreachable Databricks hosts fail in seconds instead of hanging for minutes on connector retries.

## What Changed

- `src/db/dialects/databricks.py` — `DatabricksDialect.create_engine` now computes merged `connect_args` from dialect defaults and caller overrides, passes to `sa_create_engine`. `connection_timeout` kwarg (preserved from kwargs-mode or URL-mode via `_kwargs_from_url`) drives `_socket_timeout`; defaults to 30s when absent. Retry cap defaults to 2. User `connect_args` dict wins per-key and preserves extra keys.
- `tests/unit/test_databricks_dialect.py` — added `TestCreateEngineConnectArgs` class with 6 tests covering defaults, kwarg override, user merge, retry cap override, URL-path defaults, and URL-path kwarg override.

## Commits

| Gate | Hash    | Message                                                                           |
| ---- | ------- | --------------------------------------------------------------------------------- |
| RED  | 7b69fb9 | test(260505-own): add failing tests for Databricks connect_args timeout + retry cap |
| GREEN| ca7e115 | fix(260505-own): apply connect_timeout default + retry cap to DatabricksDialect   |

## Verification

- `uv run pytest tests/unit/test_databricks_dialect.py -v` → 29 passed (23 baseline + 6 new)
- `uv run pytest tests/` → 946 passed, 78 skipped (dialect opt-out, no regressions)
- `uv run ruff check src/db/dialects/databricks.py tests/unit/test_databricks_dialect.py` → clean

## Deviations from Plan

None — plan executed exactly as written. RED produced 6 failing tests (all KeyError: 'connect_args' on the mock call kwargs), GREEN passed all tests with the exact diff in the plan's `<behavior>` block.

## TDD Gate Compliance

- RED gate: `test(260505-own): ...` at 7b69fb9
- GREEN gate: `fix(260505-own): ...` at ca7e115
- No REFACTOR gate needed (implementation is minimal and clean).

## Self-Check: PASSED

- Files exist:
  - FOUND: src/db/dialects/databricks.py (modified)
  - FOUND: tests/unit/test_databricks_dialect.py (modified)
- Commits exist:
  - FOUND: 7b69fb9
  - FOUND: ca7e115
