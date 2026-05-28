---
phase: quick/260528-gsk
plan: 01
status: complete
subsystem: db/dialects/databricks
tags: [tls, databricks, ca-bundle, corp-mitm, config]
requires: []
provides:
  - DatabricksConnectionConfig.ca_bundle field (str, default "")
  - DBMCP_CA_BUNDLE env-var fallback (process-wide)
  - URL ?ca_bundle= query param plumbing
  - _tls_trusted_ca_file injected into databricks-sql-connector connect_args
  - Probe engine in _require_databricks_catalog also honors ca_bundle
affects:
  - src/config.py
  - src/db/dialects/databricks.py
  - src/db/connection.py
  - README.md
tech-stack:
  added: []
  patterns:
    - "Optional connect_arg with absent-when-unset semantics (preserves existing certifi default)"
    - "Three-tier precedence: per-connection cfg > URL query > DBMCP_CA_BUNDLE env > unset"
key-files:
  created:
    - .planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md
  modified:
    - src/config.py
    - src/db/dialects/databricks.py
    - src/db/connection.py
    - tests/unit/test_config.py
    - tests/unit/test_databricks_dialect.py
    - tests/unit/test_connect_with_config_databricks.py
    - tests/unit/test_connect_tool.py
    - README.md
decisions:
  - "Place env-var fallback inside DatabricksDialect.create_engine (not in _connect_databricks_from_config) so URL-mode benefits without duplicating logic in connect_with_url."
  - "Tests for create_engine plumbing live in test_databricks_dialect.py (the dedicated dialect test file), not test_connect_tool.py — closer to the code under test."
  - "Loosen 2 pre-existing exact-equality kwargs assertions to subset checks; ca_bundle is a default-empty additional kwarg, exact equality was over-specified."
metrics:
  duration: ~25min
  tasks_completed: 4
  files_created: 1
  files_modified: 8
  tests_added: 15
  completed_date: 2026-05-28
---

# Phase quick/260528-gsk Plan 01: Databricks ca_bundle Config Summary

**One-liner:** Adds optional `ca_bundle` config field + `DBMCP_CA_BUNDLE` env fallback that pipes a custom CA path into databricks-sql-connector via `_tls_trusted_ca_file`, unblocking Databricks connections behind corp Cloudflare/MITM TLS gateways.

## Objective Recap

Per `.planning/debug/databricks-tls-self-signed.md` Option 2: ship a Databricks-only `ca_bundle` knob (named-config field + URL query param + env-var fallback) so the corp Cloudflare-Zero-Trust workspace path passes TLS verification. MSSQL/generic untouched (filed as Option-3 follow-up todo).

## Files Changed

**Created:**
- `.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md` — Option-3 promotion deferred.

**Modified:**
- `src/config.py` — `DatabricksConnectionConfig.ca_bundle: str = ""`; parser known_fields + constructor.
- `src/db/dialects/databricks.py` — `os` import; `_kwargs_from_url` preserves + extracts ca_bundle (URL wins); `create_engine` reads `kwargs.ca_bundle or DBMCP_CA_BUNDLE` env, applies `expanduser`, sets `_tls_trusted_ca_file`, INFO-logs the path (T-gsk-05 mitigation).
- `src/db/connection.py` — `_connect_databricks_from_config` resolves `${VAR}` in `config.ca_bundle` and passes through; `_require_databricks_catalog` accepts + propagates `ca_bundle` so the IDENT-01 probe engine also goes through the gateway CA.
- `tests/unit/test_config.py` — 4 parser/dataclass tests.
- `tests/unit/test_databricks_dialect.py` — 7 dialect-level tests (kwargs, URL, tilde, env fallback, kwarg-beats-env, URL-beats-env, absent-when-unset).
- `tests/unit/test_connect_with_config_databricks.py` — 4 named-config integration tests; loosened 1 pre-existing exact-equality assertion.
- `tests/unit/test_connect_tool.py` — loosened 1 pre-existing exact-equality assertion.
- `README.md` — Corporate MITM TLS Gateways subsection (toml example + DBMCP_CA_BUNDLE note + precedence chain).

## Commit Hashes

| Task | Commit | Description |
|------|--------|-------------|
| 1 | `ba0816d` | feat(config): add ca_bundle field to DatabricksConnectionConfig |
| 2 | `a9f7ac4` | feat(databricks): plumb ca_bundle through dialect (kwargs + URL + env) |
| 3 | `c8ff345` | feat(connection): pass ca_bundle through named-config route + catalog-probe enrichment |
| 4 | `207fb54` | docs(databricks): document ca_bundle for corp-MITM TLS gateways + file Option-3 follow-up |

## Verification

- **Targeted test files:** `tests/unit/test_config.py`, `tests/unit/test_databricks_dialect.py`, `tests/unit/test_connect_with_config_databricks.py`, `tests/unit/test_connect_tool.py` — 140/140 passed.
- **Full suite:** `uv run pytest tests/` → **1008 passed, 78 skipped** (matches the dialect-marker opt-out baseline). No regressions.
- **Ruff:** `uv run ruff check` on all changed files passes clean. Pre-existing ruff warnings in unrelated files (tests/staleness/, tests/unit/test_async_tools.py, etc.) left untouched per the scope-boundary rule.

## Deviations from Plan

**Rule 1 — Bug fix (test over-specification):** Two pre-existing tests (`test_connect_with_config_resolves_env_vars_and_calls_dialect_with_kwargs`, `test_databricks_config_calls_dialect_with_resolved_kwargs`) used exact-equality (`assert kwargs == {...}`) on the dialect kwargs dict. Adding `ca_bundle` (default `""`) as a new kwarg broke them. Loosened to subset checks while keeping the original identity-kwarg assertions intact, plus the explicit `assert "sqlalchemy_url" not in kwargs` Bug-B guard. Documented inline.

Otherwise: plan executed as written.

## Live UAT Outcome

**First probe after MCP reconnect (pre-merge-with-certifi fix):** `SSLCertVerificationError: self-signed certificate in certificate chain`. Probe revealed that `_tls_trusted_ca_file` is plumbed correctly but, when set, the connector's underlying urllib3 *replaces* the trust store rather than augmenting it. Pointing at the gateway CA alone loses access to standard intermediates (DigiCert), so the chain still fails verification.

**Follow-up fix:** Added `_merge_ca_bundle_with_certifi` to `src/db/dialects/databricks.py` — concatenates user's bundle with `certifi.where()` at connect time, caches by content hash in OS temp dir, passes the merged path to the connector. Commit: `269a6da`.

**Final UAT after fix (post-MCP-reconnect):**
- `connect_database(connection_name="databricks-test")` → `status: success`, `connection_id: d9ce935f5dbb`, schemas: 22.
- `execute_query(SELECT 1 AS probe)` → `status: success`, 1 row returned in 469ms.

Full Thrift round-trip confirmed: TCP + TLS + SQL response on the previously-intermittently-failing path.

## Resolution Cleanup

- Debug record `.planning/debug/databricks-tls-self-signed.md` → moved to `.planning/debug/resolved/` with Resolution block referencing commits `ba0816d`, `a9f7ac4`, `c8ff345`, `207fb54`, `269a6da`.
- README updated: notes that ca_bundle is auto-merged with certifi (no manual concat required).
- 1011 tests passing (was 1008 before the merge tests).

## Pointers

- **Follow-up todo (Option 3):** `.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md`
- **Source debug record (still in-flight, will move to `resolved/` in Task 6):** `.planning/debug/databricks-tls-self-signed.md`

## Self-Check: PASSED

- File `src/config.py` modified: FOUND (`ca_bundle: str = ""` present).
- File `src/db/dialects/databricks.py` modified: FOUND (`_tls_trusted_ca_file` insertion, `import os`, `preserved_keys` includes `ca_bundle`).
- File `src/db/connection.py` modified: FOUND (`_connect_databricks_from_config` resolves and passes ca_bundle; `_require_databricks_catalog` accepts ca_bundle).
- File `README.md` modified: FOUND ("Corporate MITM TLS Gateways" section).
- File `.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md`: FOUND.
- Commits `ba0816d`, `a9f7ac4`, `c8ff345`, `207fb54` all present in `git log`.
- Full test suite: 1008 passed, 78 skipped. Targeted ruff: clean.
