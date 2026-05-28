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

With `catalog` commented out in `dbmcp.toml` and `dbmcp-test` reconnected:

| # | Probe | Result | What it proves |
|---|---|---|---|
| 1 | `connect_database(connection_name="databricks-test")` (catalog omitted) | Enriched ConnectionError: `Databricks connection requires a catalog, and probing SHOW CATALOGS failed (...). Pass one via ?catalog= in the URL or catalog= in the config.` | **Defect A fixed** — catalog-omitted toml routes through the IDENT-01 enrichment instead of silently substituting `"main"`. D-06 branch (probe also failed → names both the catalog requirement AND the probe failure cause AND the user-actionable fix). Pre-fix would have been `Catalog 'main' was not found` or a silent connect-to-main if `main` existed. |
| 2 | `connect_database(sqlalchemy_url="databricks://...?catalog=bmtct&...")` | TLS error from `databricks-sql-connector` (`SSLCertVerificationError ... self-signed certificate in certificate chain`) | **Catalog routing past the dialect guard works** — failure is at TLS layer, not at catalog validation. Probe 2 of `260515-m30` (2026-05-15) succeeded on this exact URL/host combination, so the code path is exercised; the TLS gap is environmental drift since then (corp VPN / MITM cert chain). |
| 3 | `connect_database(connection_name="databricks-test")` with toml `catalog = "bmtct"` uncommented | Same TLS error as probe 2 | Live success-path verification blocked by the same TLS gap. Logically subsumed by probe 2 — both routes converge on the same network call with `catalog="bmtct"` in the engine URL. |

**Positive verification status:** code-level only. The TLS gap is orthogonal to Defect A — same gap recorded as Probe 3 of quick task `260515-m30` and the pre-existing Databricks TLS gap from Phase 14 partial UAT (commit `93e106b`). It blocks all live success-path verification regardless of dialect mode (URL vs. named-config), because both routes converge on the same `databricks-sql-connector` HTTPS handshake.

Code-level positive coverage is provided by:
- `test_parse_databricks_connection_explicit_catalog_preserved` (regression guard — explicit catalog flows through unchanged)
- `test_databricks_config_calls_dialect_with_resolved_kwargs` (existing — explicit catalog reaches `dialect.create_engine`)
- `test_connect_with_url_catalog_param_routes_through_dialect_kwargs` family (prior task `260515-m30` URL-mode integration)

A live success-path probe for this commit will need the TLS cert chain resolved separately (out of scope — same blocker as the existing pre-existing-todo for Databricks integration tests).

## Live UAT — Closing Round (2026-05-28, post-`260528-gsk` ca_bundle fix)

The TLS gap that blocked Probes 2 & 3 above was resolved by quick task `260528-gsk` (commits `ba0816d`..`269a6da` — ca_bundle config + auto-merge with certifi). Re-ran the success-path probes against live Databricks with that fix in place.

| # | Probe | Result | What it proves |
|---|---|---|---|
| 0 | `connect_database(connection_name="databricks-test")` with toml `catalog = "bmtct"` | `status: success`, `connection_id: d9ce935f5dbb`, 22 schemas | Baseline: explicit-catalog named-config route succeeds end-to-end. (Subsumes original Probe 3.) |
| 1 | `connect_database(connection_name="databricks-test")` with toml `catalog` commented out | Enriched ConnectionError: `Databricks connection requires a catalog. Accessible catalogs: bmtct, caboodle_src, cerner_src, ... (19 catalogs). Pass one via ?catalog= in the URL or catalog= in the config.` | **Defect A end-to-end:** catalog-omitted toml now surfaces IDENT-01 with a *populated* catalog list (probe-engine route also goes through the gateway CA via gsk's plumbing). Pre-fix would have silently substituted `"main"`. Stronger evidence than the earlier code-level run because the probe engine successfully enumerated catalogs over TLS. |
| 2 | `connect_database(sqlalchemy_url="databricks://token:...@host?http_path=...&catalog=bmtct&ca_bundle=~/.ssl-certs/gateway-ca.pem")` then `execute_query("SELECT 1 AS probe")` | Connect: `status: success`, `connection_id: 6c8116f88cdb`, 22 schemas. Query: 1 row, 539ms. | **URL-mode catalog routing succeeds end-to-end** with full Thrift round-trip (TCP + TLS + SQL response). Different `connection_id` from Probe 0 confirms a fresh URL-route engine, not a cached named-config result. |

**Positive verification status: COMPLETE.** All three originally-blocked probes (catalog-required error, URL-mode success, named-config-with-catalog success) now pass against live Databricks. Closes the only remaining UAT gap from the original report.

## Out-of-scope items observed

- **URL-mode env-var resolution gap** — still pending. `${VAR}` placeholders in `sqlalchemy_url` strings are not resolved by `connect_with_url`, unlike named-config which routes through `resolve_env_vars`. Surfaced by Probe 3 of quick task `260515-m30`. Separate quick task.
- **Pre-existing ruff warning** in `src/metrics.py` (Generator import location) — not touched, out of scope (per MEMORY.md).

## Commit

Single atomic commit: `72f26f8` — `fix(config): drop "main" catalog defaults so IDENT-01 fires for omitted toml (Phase 14 A)`. Code + 5 test files together (one red→green increment with the test-fixture updates that the metadata.py change cascaded into).
