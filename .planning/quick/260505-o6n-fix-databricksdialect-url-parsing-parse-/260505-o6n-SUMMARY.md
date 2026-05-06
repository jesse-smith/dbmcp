---
phase: 260505-o6n
plan: 01
subsystem: db/dialects
tags: [databricks, url-parsing, bugfix, tdd]
requires: []
provides:
  - DatabricksDialect.create_engine(sqlalchemy_url=...) URL-aware entry point
affects:
  - src/db/dialects/databricks.py
tech_stack:
  added: []
  patterns:
    - _kwargs_from_url static helper (mirrors MssqlDialect)
key_files:
  created: []
  modified:
    - src/db/dialects/databricks.py
    - tests/unit/test_databricks_dialect.py
decisions:
  - URL wins over conflicting identity kwargs; preserved runtime set = {query_timeout, pool_config, connection_id, disconnect_callback, connection_timeout} — identical to MSSQL sibling for forward compat
  - Schema resolution prefers url.database (path form) over ?schema= query param; default "default"
  - Token drawn from url.password (username fixed as "token" by convention, not validated)
metrics:
  duration: ~6min
  completed: 2026-05-05
commits:
  red: b50268f
  green: 10e56a6
---

# Quick Task 260505-o6n: Fix DatabricksDialect URL Parsing Summary

**One-liner:** DatabricksDialect.create_engine now parses `sqlalchemy_url` via `make_url`, mirroring the MSSQL URL-aware pattern — eliminates `KeyError: 'host'` when connecting with `databricks://token:T@host:443/schema?http_path=...`.

## What Shipped

- `DatabricksDialect._kwargs_from_url(sqlalchemy_url, original_kwargs) -> dict` static helper on `src/db/dialects/databricks.py` that parses a Databricks URL and returns the dict the existing kwargs-only branch already expects.
- `create_engine` detects `sqlalchemy_url` kwarg and delegates to `_kwargs_from_url` before validation. Kwargs-only path is byte-identical to pre-change.
- Conflict policy: URL wins for `{host, http_path, token, catalog, schema}`. Runtime kwargs `{query_timeout, pool_config, connection_id, disconnect_callback, connection_timeout}` pass through; other conflicting keys are dropped and logged at DEBUG.
- Missing host / missing http_path raise `ValueError` mentioning the offending URL.
- 8 new unit tests in `TestCreateEngineFromUrl` cover: query-form URL, path-form URL, defaults, missing host, missing http_path, token url-encoding, URL-wins conflict, kwargs-only regression guard.

## TDD Gate Compliance

- RED commit `b50268f` — 6/8 new tests failing as expected, 2 passing incidentally (missing-host matched pre-existing "Missing required parameter: host" wording; kwargs-only regression guard passes against untouched legacy path — expected).
- GREEN commit `10e56a6` — all 23 tests in `tests/unit/test_databricks_dialect.py` pass.

## Verification

- `uv run pytest tests/unit/test_databricks_dialect.py -v` → **23 passed** (13 pre-existing + 8 new + 2 registration).
- `uv run pytest tests/` → **940 passed, 78 skipped** (baseline was 924+78 per MEMORY.md; new 8 tests land as +8 = 932, remaining delta from other merged work prior to this worktree's base). No regressions.
- `uv run ruff check src/db/dialects/databricks.py tests/unit/test_databricks_dialect.py` → **All checks passed**.

## Deviations from Plan

None. Preserved runtime kwargs set exactly matches MSSQL as specified. Currently none of these kwargs are acted on inside Databricks' `create_engine` (it only builds the URL and passes `pool_pre_ping`/`echo` to SA), but they are plumbed through so `connect_with_url` callers can pass them without silent loss — forward compatibility as the plan anticipated.

## Known Stubs

None.

## Commits

| Phase | Hash    | Message                                                               |
| ----- | ------- | --------------------------------------------------------------------- |
| RED   | b50268f | test(260505-o6n): add failing URL-parsing tests for DatabricksDialect |
| GREEN | 10e56a6 | fix(260505-o6n): parse sqlalchemy_url in DatabricksDialect.create_engine |

## Self-Check: PASSED

- FOUND: src/db/dialects/databricks.py (modified)
- FOUND: tests/unit/test_databricks_dialect.py (modified)
- FOUND commit: b50268f
- FOUND commit: 10e56a6
