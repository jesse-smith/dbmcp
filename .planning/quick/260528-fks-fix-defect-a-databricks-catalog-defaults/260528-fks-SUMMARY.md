---
quick_id: 260528-fks
status: complete
date: 2026-05-28
branch: gsd/v2.1-databricks-identifier-fixes
description: Fix Defect A — Databricks catalog defaults bypass IDENT-01
commit: 72f26f8
---

# Quick Task 260528-fks — Summary

## Outcome

Phase 14 Defect A fixed at the source. `DatabricksConnectionConfig.catalog` and `_parse_databricks_connection` no longer default to `"main"`; both default to `""`. A toml entry with `catalog` omitted now flows an empty string into `dialect.create_engine`, which raises `ValueError("Databricks catalog is required")`, which `ConnectionManager.connect_with_config` catches and re-raises as the enriched `ConnectionError("Databricks connection requires a catalog. Accessible catalogs: ...")`. The user sees an actionable error instead of a misleading `Catalog 'main' was not found`.

A parallel `or "main"` leftover in `src/db/metadata.py:928` (the DESCRIBE EXTENDED catalog fallback) was also cleaned up — now falls back to `self._engine_catalog()` (the engine's URL catalog, post-IDENT-01 invariant).

## Changed files

- `src/config.py:77` — `DatabricksConnectionConfig.catalog` default `"main"` → `""`
- `src/config.py:243` — `_parse_databricks_connection` `params.get("catalog", "main")` → `params.get("catalog", "")`
- `src/db/metadata.py:928` — `dte_catalog = catalog or "main"` → `catalog or self._engine_catalog()`
- `tests/unit/test_config.py` — updated `test_databricks_fields` catalog assertion to `""`; added `test_parse_databricks_connection_omitted_catalog_defaults_to_empty` and `test_parse_databricks_connection_explicit_catalog_preserved` (regression guard)
- `tests/unit/test_connect_tool.py` — updated `test_databricks_config_defaults_catalog_and_schema` to assert `kwargs["catalog"] == ""` (was locking in the "main" bug)
- `tests/unit/test_metadata.py` — 4 dialect-mocked tests now patch `_engine_catalog` to keep their `_parse_databricks_table_properties` mock happy

## Verification

**Targeted unit tests (TDD red → green):**

| Test | Pre-fix | Post-fix |
|---|---|---|
| `test_config::test_databricks_fields` | FAIL (`'main' == ''`) | PASS |
| `test_config::test_parse_databricks_connection_omitted_catalog_defaults_to_empty` | FAIL (`'main' == ''`) | PASS |
| `test_config::test_parse_databricks_connection_explicit_catalog_preserved` | PASS (vacuous regression guard) | PASS |
| `test_connect_tool::test_databricks_config_defaults_catalog_and_schema` | PASS pre-edit (locked in bug) | PASS post-edit (asserts new behavior) |

**Existing IDENT-01 enrichment tests** at `tests/unit/test_connect_with_config_databricks.py:173-248` cover the empty-string codepath end-to-end (probe-engine fallback, `Accessible catalogs:` enumeration, `__cause__` chaining). They pass unchanged — catalog-omitted toml now reaches the same path.

**Full suite:** `uv run pytest tests/` → **993 passed, 78 skipped, 0 failed**. No regressions.

**Ruff:** `uv run ruff check src/config.py src/db/metadata.py tests/unit/test_config.py tests/unit/test_metadata.py` → clean.

## Live UAT against `dbmcp-test`

Pending — to run after MCP reconnection. Procedure:

1. Comment out `catalog = "..."` in `dbmcp.toml`, reconnect `dbmcp-test`.
2. Call `connect_database(connection_name="<dbx-conn>")`. Expect: `Databricks connection requires a catalog. Accessible catalogs: ...` ConnectionError. NOT `Catalog 'main' was not found`. NOT a silent connect-to-main success.
3. Uncomment `catalog = "bmtct"`, reconnect, repeat. Expect: success, schemas listed.

## Out-of-scope items observed

- **URL-mode env-var resolution gap** — still pending. `${VAR}` placeholders in `sqlalchemy_url` strings are not resolved by `connect_with_url`, unlike named-config which routes through `resolve_env_vars`. Surfaced by Probe 3 of quick task `260515-m30`. Separate quick task.
- **Pre-existing ruff warning** in `src/metrics.py` (Generator import location) — not touched, out of scope (per MEMORY.md).

## Commit

Single atomic commit: `72f26f8` — `fix(config): drop "main" catalog defaults so IDENT-01 fires for omitted toml (Phase 14 A)`. Code + 5 test files together (one red→green increment with the test-fixture updates that the metadata.py change cascaded into).
