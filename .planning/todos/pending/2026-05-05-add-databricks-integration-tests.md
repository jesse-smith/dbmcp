---
created: 2026-05-05T00:00:00.000Z
title: Add residual Databricks connect_with_config regression tests
area: testing
source: Follow-up from quick task 260505-mr3 (Databricks test-coverage audit)
files:
  - tests/unit/test_connect_with_config_databricks.py (add 2 tests)
  - src/db/connection.py:462-513 (code under test — no changes)
  - src/db/dialects/databricks.py:70-112 (code under test — no changes)
---

## Context

Quick task 260505-mr3 audited Databricks `connect_with_config` test coverage and
concluded NOT a blocker — the two regression tests added in commit `4fdaa90`
(`tests/unit/test_connect_with_config_databricks.py`) close the structural gap
that let Bug A (missing env-var resolution on host/http_path) and Bug B
(dialect signature drift) ship through Phase 11.

Three minor residual gaps were identified. Two are small code-level gaps worth
hardening; one is a plan-documentation nit.

## Gaps to close

### 1. Env-var substitution for `catalog` and `schema_name` (connection.py:466-467)

Current regression tests pass literal strings for `catalog` and `schema_name`,
so `resolve_env_vars` on those lines is not exercised. If it were removed, no
test would fail.

- **Proposed test:** `tests/unit/test_connect_with_config_databricks.py::test_env_var_substitution_for_catalog_and_schema`
- **Assertion:** Given `catalog="${DBX_CATALOG}"` and `schema_name="${DBX_SCHEMA}"`
  with those env vars set, the kwargs captured by the spy have the resolved
  values (not the `${…}` literals).
- **Effort:** small (≤20 lines, reuses existing `_make_engine_spy` helper and
  the spy-at-class-level pattern from `test_connect_with_config_databricks.py:44`).

### 2. `SQLAlchemyError` → `ConnectionError` wrapping (connection.py:494-502)

The Databricks branch wraps `SQLAlchemyError` from `dialect.create_engine` into
`ConnectionError` with the host in the message. No test covers this path.

- **Proposed test:** `tests/unit/test_connect_with_config_databricks.py::test_sqlalchemy_error_wrapped_as_connection_error`
- **Assertion:** When the patched `DatabricksDialect.create_engine` raises
  `sqlalchemy.exc.SQLAlchemyError("boom")`, `connect_with_config` raises
  `ConnectionError` whose message contains the host string.
- **Effort:** small (≤15 lines).

### 3. Plan-writer hygiene (non-code)

The PLAN.md `<interfaces>` block in quick task 260505-mr3 described the live
call path as `connect_with_config → connect_with_url → dialect.create_engine(sqlalchemy_url=…)`.
Post-fix, the Databricks branch at `src/db/connection.py:462-513` bypasses
`connect_with_url` and calls `dialect.create_engine(**kwargs)` directly at
`connection.py:487-493`. Future audit/plan templates that cite the Databricks
call path should use the direct-dispatch pattern.

- **Action:** No code change. Consider updating any template or reference doc
  that echoes the old call path.

## Scope

- Add both tests in a single commit: `test(XX-YY): harden Databricks connect_with_config regression suite`.
- Run `uv run pytest tests/unit/test_connect_with_config_databricks.py -v` before committing.
- No production code changes.

## Acceptance

- Both new tests present and green.
- Full suite (`uv run pytest tests/`) remains green with zero new warnings.
- This todo moves to `done/` with the commit SHA recorded.

## Priority

Low. Existing coverage is adequate for the verdict reached in the audit. These
are hardening additions, not fixes.
