---
status: complete
plan: .planning/quick/260428-jr7-fix-databricks-connect-with-config-integ/260428-jr7-PLAN.md
commits:
  - fe93fd0
  - 4fdaa90
started: 2026-04-28T17:45:00Z
completed: 2026-04-28T18:15:00Z
---

# Quick Task 260428-jr7 — Summary

## What changed

- `tests/unit/test_connect_with_config_databricks.py` — new file, regression
  coverage for the `ConnectionManager.connect_with_config` → Databricks path.
  Mocks ONLY at `dialect.create_engine` so signature mismatches are caught.
  Asserts that (a) env-var references in `host`, `http_path`, `token`,
  `catalog`, `schema_name` are resolved before the dialect is invoked, and
  (b) `sqlalchemy_url` is never passed to `dialect.create_engine` — locking
  out reintroduction of the old URL-based bug.
- `src/db/connection.py` —
  - Extracted `_register_engine` helper that performs the post-engine
    bookkeeping shared by `connect_with_url` and the new direct Databricks
    path (`_test_connection`, engine/dialect/connection registry, Connection
    record build). Pure refactor validated against the full suite before the
    Databricks edit landed.
  - Rewrote the Databricks branch of `connect_with_config` to:
    1. Resolve env vars for `host`, `http_path`, `token`, `catalog`,
       `schema_name` (same pattern as MSSQL's `password`/`tenant_id` handling).
    2. Call `dialect.create_engine(host=..., http_path=..., token=...,
       catalog=..., schema=...)` directly — no URL, no `connect_with_url`
       detour.
    3. Hand the resulting engine to `_register_engine` for the bookkeeping.
  - Explicit mapping: `DatabricksConnectionConfig.schema_name` →
    `DatabricksDialect.create_engine`'s `schema` kwarg (naming mismatch
    between config and dialect protocols; documented in the code).
- `tests/unit/test_connect_tool.py` — adjustments to existing tests that
  had pinned the old (broken) URL-based code path. Test intent preserved;
  assertions now pin the correct direct-kwargs path.

## Why (not in commits)

Phase 11 introduced both bugs simultaneously but they were mutually invisible
— the env-var bug couldn't manifest because the signature bug prevented the
code from ever reaching env-var usage. UAT Test 7 was the first real-world
invocation of this path, which is why neither bug surfaced in the 607-test
pre-merge suite. The audit of that coverage gap is captured as a separate
todo: `.planning/todos/pending/2026-04-28-audit-databricks-test-coverage.md`.

## Verification

- Full unit suite: 812 passed, 37 skipped (was 809/37; +3 new tests from the
  regression file).
- Ruff: zero warnings on all changed files.
- Live MCP verification: pending — requires restart of the MCP server and a
  working `$DATABRICKS_HOST`/`$DATABRICKS_HTTP_PATH`/`$DATABRICKS_TOKEN`
  environment (tracked under Phase 11 UAT Test 7).

## Known follow-ups

- Phase 11 UAT Test 7 can now be attempted. If the MCP server inherits the
  Databricks env vars, the live `connect_database(connection_name="databricks-test")`
  call should now route through the fixed code path.
- The "Unexpected error:" error-wording polish remains open
  (`.planning/todos/pending/2026-04-28-missing-databricks-package-error-prefix.md`).
- Test coverage audit open
  (`.planning/todos/pending/2026-04-28-audit-databricks-test-coverage.md`).

## Deviations from plan

None of substance. Ruff flagged two unused imports during the final sweep
(auto-fixed); otherwise implementation tracked the plan exactly.
