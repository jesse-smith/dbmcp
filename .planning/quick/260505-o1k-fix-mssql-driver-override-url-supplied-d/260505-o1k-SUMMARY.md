---
phase: 260505-o1k
plan: 01
subsystem: db/dialects/mssql
tags: [bugfix, mssql, odbc, url-parsing, regression-test]
dependency_graph:
  requires:
    - MssqlDialect.create_engine (existing URL parsing path from 260505-mhm)
  provides:
    - URL-selectable ODBC driver override (Driver 17 / Driver 18 / future versions)
  affects:
    - src/db/dialects/mssql.py (_kwargs_from_url, create_engine, _build_odbc_connection_string)
    - tests/unit/test_mssql_dialect.py (TestCreateEngineFromUrl class — 3 new tests)
tech_stack:
  added: []
  patterns:
    - "URL query param → kwargs → downstream builder (mirrors existing trust_server_cert/tenant_id pattern)"
key_files:
  created: []
  modified:
    - src/db/dialects/mssql.py
    - tests/unit/test_mssql_dialect.py
decisions:
  - "driver kwarg is URL-only: kwargs-mode callers continue to receive Driver 18 default (no public API change to kwargs path)"
  - "driver_name computed as `driver or 'ODBC Driver 18 for SQL Server'` inside _build_odbc_connection_string — centralizes the default in one place"
  - "Parameter added at end of _build_odbc_connection_string signature with default=None — non-breaking for any internal callers"
metrics:
  duration: ~8 minutes
  tasks_completed: 2
  tests_added: 3
  completed_date: 2026-05-05
requirements:
  - QUICK-260505-o1k
---

# Quick Task 260505-o1k: Fix MSSQL Driver Override (URL-supplied driver now wins) Summary

One-liner: MssqlDialect now honors the `driver` query parameter in `sqlalchemy_url`, allowing URL-based callers to select any installed ODBC driver (e.g. Driver 17) instead of being silently forced onto the hardcoded Driver 18 default.

## What Changed

**Before:** `mssql+pyodbc://u:p@host/db?driver=ODBC+Driver+17+for+SQL+Server` was parsed, but the `driver` query param was dropped on the floor. `_build_odbc_connection_string` hardcoded `Driver={ODBC Driver 18 for SQL Server}` regardless.

**After:** The `driver` param now flows: `url.query['driver']` → `_kwargs_from_url` new_kwargs → `create_engine` local `driver` var → `_build_odbc_connection_string(driver=...)` → final ODBC string token `Driver={<URL-supplied name>}`. Kwargs-only callers (no `sqlalchemy_url`) see no change — `driver` resolves to `None` → default Driver 18.

## Tasks

| Task | Name                                                              | Commit  | Status |
| ---- | ----------------------------------------------------------------- | ------- | ------ |
| 1    | Add failing regression tests for URL-supplied driver override     | 40358bc | PASS   |
| 2    | Implement driver override in _kwargs_from_url and builder         | bcc3360 | PASS   |

## Tests Added (TestCreateEngineFromUrl)

1. `test_create_engine_url_driver_overrides_default` — URL `?driver=ODBC+Driver+17+for+SQL+Server` produces `Driver={ODBC Driver 17 for SQL Server}` and NOT Driver 18. RED → GREEN after fix.
2. `test_create_engine_url_without_driver_uses_default` — URL without driver query preserves Driver 18 (backward compat sentinel). Always green.
3. `test_create_engine_kwargs_path_uses_default_driver` — kwargs-only path (no sqlalchemy_url) still emits Driver 18. Always green.

## Verification

- `uv run pytest tests/unit/test_mssql_dialect.py` → 32 passed (was 29 + 3 new)
- `uv run pytest tests/unit/ -k "dialect"` → 160 passed, 37 skipped, no regressions

## Deviations from Plan

None — plan executed exactly as written. Minor note: tests 2 and 3 passed in RED phase as expected (they are regression sentinels for behavior that was already correct); only Test 1 failed in RED, confirming it drove the fix.

## Implementation Details

`src/db/dialects/mssql.py`:

1. `_kwargs_from_url` new_kwargs.update now includes `"driver": query.get("driver")` — returns `None` if the URL lacks `driver=`, so no behavior change when absent.
2. `create_engine` body adds `driver: str | None = kwargs.get("driver")` alongside other kwarg reads; passes `driver=driver` into the `_build_odbc_connection_string(...)` call.
3. `_build_odbc_connection_string` signature gains trailing `driver: str | None = None` param; body computes `driver_name = driver or "ODBC Driver 18 for SQL Server"` and inlines it into the first `parts` element via f-string `f"Driver={{{driver_name}}}"`.

## Self-Check: PASSED

- `src/db/dialects/mssql.py` modified (commit bcc3360 — 1 file changed, 10+/1-)
- `tests/unit/test_mssql_dialect.py` modified (commit 40358bc — 1 file changed, 71+)
- Commits 40358bc and bcc3360 present in `git log --oneline` on worktree-agent-a9548fd449f3a190f branch
- All 32 tests in test_mssql_dialect.py green; broader dialect smoke green (160 passed)
