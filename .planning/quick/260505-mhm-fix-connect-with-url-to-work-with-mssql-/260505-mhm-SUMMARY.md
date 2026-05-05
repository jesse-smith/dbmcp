---
phase: 260505-mhm
plan: 01
subsystem: db/dialects
tags: [mssql, connection, url-parsing, bugfix]
requires: [sqlalchemy.engine.url.make_url]
provides: [MssqlDialect.create_engine URL-mode]
affects: [connect_database via connect_with_url]
tech-stack:
  added: []
  patterns: [url-parsing-branch, conflict-policy-url-wins]
key-files:
  created: []
  modified:
    - src/db/dialects/mssql.py
    - src/mcp_server/schema_tools.py
    - tests/unit/test_mssql_dialect.py
decisions:
  - "URL wins on kwarg conflict; only runtime kwargs (query_timeout, pool_config, connection_timeout, connection_id, disconnect_callback) survive alongside sqlalchemy_url"
  - "Default authentication_method: SQL if url.username and url.password, else WINDOWS"
  - "trust_server_cert accepts 'true'/'1'/'yes' (case-insensitive) as truthy; everything else is False (default)"
metrics:
  completed: 2026-05-05
  commits: 3
  tests-added: 9
---

# Phase 260505-mhm Plan 01: Fix connect_database with URL for MSSQL — Summary

Fix `connect_database(sqlalchemy_url=...)` for MSSQL by adding a URL-parsing branch to `MssqlDialect.create_engine` so the dialect derives server/database/credentials/auth from the URL instead of failing with `KeyError: 'server'`.

## Files Changed

| File | Change |
|---|---|
| `src/db/dialects/mssql.py` | Added `_kwargs_from_url()` static helper (~85 lines). Added URL-branch at top of `create_engine()` that invokes the helper when `sqlalchemy_url` is present. Added `from sqlalchemy.engine.url import make_url` import. Updated docstring with URL mode semantics, supported query params, and conflict policy. |
| `src/mcp_server/schema_tools.py` | Expanded `connect_database` docstring with MSSQL URL query-param contract (3 params + default rules) and a concrete `mssql+pyodbc://user:pass@host/db?...` example. |
| `tests/unit/test_mssql_dialect.py` | Added `TestCreateEngineFromUrl` class with 9 test cases (see below). |

## Commits

| Commit | Type | Description |
|---|---|---|
| `c07b071` | test | RED — 9 failing URL-parsing tests (KeyError: 'server') |
| `77721ca` | feat | GREEN — `_kwargs_from_url` helper + URL branch + updated docstring |
| `de838d9` | docs | `connect_database` MSSQL URL query-param documentation |

## Tests Added (9)

All in `tests/unit/test_mssql_dialect.py::TestCreateEngineFromUrl`. Mocks `sa_create_engine` — no live DB touched.

1. `test_create_engine_parses_url_sql_auth` — SQL auth from `user:pass@host:1433/db`
2. `test_create_engine_parses_url_windows_auth` — `?authentication_method=windows`
3. `test_create_engine_parses_url_trust_server_cert_true` — `?trust_server_cert=true`
4. `test_create_engine_parses_url_trust_server_cert_variants` — `1`/`yes`/`TRUE`/`True` truthy; `0`/`false`/`FALSE`/`no` falsy
5. `test_create_engine_url_missing_host_raises` — `mssql+pyodbc:///db` → ValueError("server")
6. `test_create_engine_url_missing_database_raises` — `mssql+pyodbc://host/` → ValueError("database")
7. `test_create_engine_url_invalid_auth_method_raises` — `?authentication_method=bogus` → ValueError listing accepted values
8. `test_create_engine_url_ignores_conflicting_kwargs` — URL host wins over `server="other"` kwarg
9. `test_create_engine_kwargs_only_path_unchanged` — regression guard on legacy kwargs-only path

Plan requested 8 cases; delivered 9 (split `trust_server_cert` coverage into a focused test and a variants matrix).

## Final Conflict Policy

When `sqlalchemy_url` is present:

- **URL wins** for all connection-identity values: server, database, port, username, password, authentication_method, trust_server_cert, tenant_id.
- **Runtime kwargs preserved:** `query_timeout`, `pool_config`, `connection_timeout`, `connection_id`, `disconnect_callback`.
- **Conflicting kwargs are ignored** with a `logger.debug(...)` listing the dropped keys. No exception raised.

Rationale: URL is the explicit high-intent path (the user typed the whole connection string); runtime/pool tuning is orthogonal infrastructure config that callers legitimately vary independently of the URL.

## Deviations from Plan

### 1. TDD ordering — Task 1 RED absorbed Task 2's test content

**Why:** Task 1 had `tdd="true"` requiring a RED commit before GREEN. The minimum-viable RED set strongly overlaps with Task 2's enumerated 8-case suite. Writing one skinny test for Task 1 then duplicating work in Task 2 would have produced two `test(...)` commits with redundant content. Consolidated into a single `test(...)` commit (`c07b071`) covering all 9 cases; Task 2 is fully satisfied by that commit. No separate Task 2 commit exists — intentional.

**Impact:** Commit count is 3 instead of 4, but all planned test cases exist and pass. Plan's `<done>` for Task 2 (all 8 cases pass, existing MSSQL tests still pass) is satisfied.

### 2. Test file location

Plan said `tests/test_mssql_dialect.py`; actual project convention places unit tests under `tests/unit/`, and `tests/unit/test_mssql_dialect.py` already existed with 20 tests. Extended the existing file with a new `TestCreateEngineFromUrl` class rather than creating a duplicate at the root.

### 3. `connection_timeout` added to preserved-kwargs list

Plan's preserved set was `{sqlalchemy_url, query_timeout, pool_config, connection_id, disconnect_callback}`. Added `connection_timeout` too — it's a runtime/pool tuning value, not a connection-identity value, and keeping it out of the preserved set would have silently dropped user-supplied ODBC connection timeouts. Rule 2 (auto-add missing critical functionality): omitting it would cause a regression for existing callers that pass both a URL and a connection_timeout.

## Deferred Issues (out of scope)

`uv run ruff check src/ tests/` reports 17 errors in pre-existing files **not modified by this plan**:

- `tests/staleness/tool_invoker.py` (I001, F841, UP017)
- `tests/unit/test_async_tools.py` (I001, E402 x2)
- `tests/unit/test_connection_manager.py` (I001)
- `tests/unit/test_generic_dialect.py` (I001, F401)
- `tests/unit/test_helpers.py` (B017)
- `tests/unit/test_identifier_validation.py` (F401)
- `tests/unit/test_optional_deps.py` (F401)
- `tests/unit/test_staleness_comparison.py` (F401)
- `tests/unit/test_staleness_parser.py` (I001, F401)
- `tests/unit/test_type_registry.py` (F632)
- `tests/unit/test_url_routing.py` (F401)

All files modified by this plan (`src/db/dialects/mssql.py`, `src/mcp_server/schema_tools.py`, `tests/unit/test_mssql_dialect.py`) lint clean. Pre-existing issues are out of scope per deviation scope-boundary rule.

## Verification

- `uv run pytest tests/unit/test_mssql_dialect.py -x -v`: **29 passed** (9 new + 20 pre-existing).
- `uv run pytest tests/ -x`: **924 passed, 78 skipped** (skips match MEMORY.md dialect-marker opt-outs — no regression).
- `uv run ruff check src/db/dialects/mssql.py src/mcp_server/schema_tools.py tests/unit/test_mssql_dialect.py`: **All checks passed.**
- Manual smoke test (user-gated, not run): `connect_database(sqlalchemy_url="mssql+pyodbc://SVWTSTEM04/StemSoftClinicTest?authentication_method=windows&trust_server_cert=true")` is now exercisable without `KeyError: 'server'`.

## Success Criteria

- [x] MSSQL URL-based connection succeeds (no KeyError) — validated by 9 mocked tests covering all param flows.
- [x] Kwargs-only path unchanged — `test_create_engine_kwargs_only_path_unchanged` + 20 pre-existing tests pass.
- [x] Conflict policy (URL wins) implemented and documented — helper docstring + method docstring + `connect_database` docstring.
- [x] New tests cover: SQL auth URL, Windows auth URL, trust_server_cert parsing (both truthy and falsy variants), missing host, missing database, invalid auth method, conflicting kwargs, kwargs-only regression.

## Self-Check: PASSED

- `src/db/dialects/mssql.py` — FOUND (modified, contains `sqlalchemy_url` and `_kwargs_from_url`)
- `src/mcp_server/schema_tools.py` — FOUND (modified, docstring updated)
- `tests/unit/test_mssql_dialect.py` — FOUND (contains `TestCreateEngineFromUrl`)
- Commits `c07b071`, `77721ca`, `de838d9` — FOUND in `git log`
