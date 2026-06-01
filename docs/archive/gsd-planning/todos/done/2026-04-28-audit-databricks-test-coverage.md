---
created: 2026-04-28T17:45:00.000Z
title: Audit test coverage for Databricks connect_with_config path
area: testing
source: Discovered during Phase 11 UAT Test 7 investigation (2026-04-28)
files:
  - tests/unit/ (existing Databricks tests)
  - src/db/connection.py:376-433 (connect_with_config)
  - src/db/dialects/databricks.py:60-107 (DatabricksDialect.create_engine)
---

## Problem

A latent integration bug in `ConnectionManager.connect_with_config` for
Databricks shipped through Phase 11 undetected: the branch builds a SQLAlchemy
URL and calls `connect_with_url(url, dialect, ...)` → `dialect.create_engine(sqlalchemy_url=url)`,
but `DatabricksDialect.create_engine` reads `kwargs["host"]` / `kwargs["http_path"]`
and has no `sqlalchemy_url` handling. So the live call path raises
`ValueError: Missing required parameter: host` no matter what config is passed.

That this slipped through the test suite (607 tests at time of merge) means
either:
- Databricks `connect_with_config` isn't exercised end-to-end
- Tests mock at a layer that hides the URL ↔ kwargs mismatch
- Or the test path goes through the kwargs signature directly and never
  through `connect_with_url`

Env-var substitution for `host`/`http_path` (only `token` goes through
`resolve_env_vars` in connection.py:425) has the same coverage hole.

## Scope

Audit the Databricks-related tests and answer:

1. Is there an integration-style test that calls `connect_database` (the MCP
   tool) or `ConnectionManager.connect_with_config` with a
   `DatabricksConnectionConfig`, up to the point where `dialect.create_engine`
   is invoked?
2. If yes, why did it not catch the signature mismatch? (Mocking the dialect?
   Mocking `connect_with_url`?)
3. Are env-var substitution tests present for Databricks `host`/`http_path`?
   (They are present for MSSQL password and generic sqlalchemy_url — see
   `tests/unit/test_config.py` and `test_connection*.py`.)

## Deliverable

A short audit note in `.planning/todos/done/` (or promoted to a phase plan if
gaps warrant structured work) listing:
- Which code paths are covered end-to-end for Databricks
- Which are only unit-tested with mocks
- Recommendation: add integration tests that go through
  `connect_with_config` → `connect_with_url` → `dialect.create_engine`
  without mocking the dialect, so signature changes are caught.

## Acceptance

- Clear yes/no on each audit question above, with file references.
- Concrete list of missing tests (if any) with proposed test names/locations.
- Blocker-or-not verdict for subsequent Databricks work.
