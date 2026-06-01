---
phase: quick/260528-gsk
plan: 01
type: execute
wave: 1
mode: quick
depends_on: []
files_modified:
  - src/config.py
  - src/db/dialects/databricks.py
  - src/db/connection.py
  - tests/unit/test_config.py
  - tests/unit/test_connect_tool.py
  - tests/unit/test_connect_with_config_databricks.py
  - README.md
  - .planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md
  - .planning/debug/resolved/databricks-tls-self-signed.md
autonomous: false
requirements: [TLS-CA-01, TLS-CA-02, TLS-CA-03, TLS-CA-04]
must_haves:
  truths:
    - "User can set ca_bundle = \"~/.ssl-certs/gateway-ca.pem\" in [connections.X] (databricks dialect) and dbmcp passes it to the connector via _tls_trusted_ca_file"
    - "User can set DBMCP_CA_BUNDLE env var as fallback and it is honored when no per-connection ca_bundle is provided (named-config and URL routes both read it)"
    - "When ca_bundle is unset and DBMCP_CA_BUNDLE is unset, _tls_trusted_ca_file is ABSENT from connect_args (not empty-string) — preserving current default certifi behavior"
    - "Tilde and ${VAR} in ca_bundle resolve correctly (expanduser + resolve_env_vars) before reaching the connector"
    - "Precedence: explicit per-connection ca_bundle > URL ?ca_bundle= query param > DBMCP_CA_BUNDLE env > unset"
    - "URL-mode (sqlalchemy_url + databricks://...?ca_bundle=...) flows the bundle through _kwargs_from_url"
    - "MSSQL/generic dialects unchanged — ca_bundle is databricks-only in this plan"
    - "Live UAT probe via dbmcp-test against the real corp-MITM Databricks workspace succeeds with ca_bundle set"
  artifacts:
    - path: "src/config.py"
      provides: "DatabricksConnectionConfig.ca_bundle field; _parse_databricks_connection reads ca_bundle"
      contains: "ca_bundle"
    - path: "src/db/dialects/databricks.py"
      provides: "ca_bundle plumbed into create_engine — expanded path → _tls_trusted_ca_file in connect_args; URL ?ca_bundle= extracted in _kwargs_from_url"
      contains: "_tls_trusted_ca_file"
    - path: "src/db/connection.py"
      provides: "_connect_databricks_from_config resolves ca_bundle (config → env fallback → expanduser → resolve_env_vars) and passes it to dialect.create_engine"
      contains: "DBMCP_CA_BUNDLE"
    - path: "tests/unit/test_config.py"
      provides: "Coverage for DatabricksConnectionConfig.ca_bundle default + round-trip"
    - path: "tests/unit/test_connect_tool.py"
      provides: "Coverage for ca_bundle → _tls_trusted_ca_file plumbing in DatabricksDialect.create_engine (kwargs and URL modes; env fallback; absent-when-unset)"
    - path: "tests/unit/test_connect_with_config_databricks.py"
      provides: "Coverage for end-to-end named-config ca_bundle resolution including DBMCP_CA_BUNDLE precedence"
    - path: "README.md"
      provides: "Short Corp-MITM / ca_bundle usage section with toml example and DBMCP_CA_BUNDLE note"
    - path: ".planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md"
      provides: "Follow-up todo for Option-3 protocol-level promotion"
    - path: ".planning/debug/resolved/databricks-tls-self-signed.md"
      provides: "Resolved debug record with commit-hash resolution entry"
  key_links:
    - from: "TOML [connections.databricks-test].ca_bundle"
      to: "DatabricksConnectionConfig.ca_bundle"
      via: "_parse_databricks_connection (params.get + known_fields)"
      pattern: "ca_bundle"
    - from: "DatabricksConnectionConfig.ca_bundle (or DBMCP_CA_BUNDLE env)"
      to: "DatabricksDialect.create_engine kwargs"
      via: "_connect_databricks_from_config"
      pattern: "DBMCP_CA_BUNDLE|ca_bundle"
    - from: "DatabricksDialect.create_engine kwargs.ca_bundle"
      to: "merged_connect_args['_tls_trusted_ca_file']"
      via: "expanduser + dialect_defaults insertion (only when non-empty)"
      pattern: "_tls_trusted_ca_file"
    - from: "sqlalchemy_url ?ca_bundle="
      to: "kwargs.ca_bundle"
      via: "DatabricksDialect._kwargs_from_url query extraction + preserved-keys passthrough"
      pattern: "ca_bundle"
---

<objective>
Add an optional `ca_bundle` field to DatabricksConnectionConfig + URL `?ca_bundle=` query param + `DBMCP_CA_BUNDLE` env-var fallback. When set, dbmcp passes the (expanduser-expanded, env-var-resolved) path to `databricks-sql-connector` via `_tls_trusted_ca_file` in `connect_args`. When unset, behavior is unchanged (connector uses its bundled certifi).

Purpose: Unblocks Databricks connections behind a corp Cloudflare Zero Trust / MITM gateway (Python ignores `NODE_EXTRA_CA_CERTS`; per `.planning/debug/databricks-tls-self-signed.md` Option 2 — see Resolution section there for full root-cause). Resolves the SSLCertVerificationError observed in the 260528 UAT path against the live corp workspace.

Output: Code + tests + README usage note, scoped to the Databricks dialect only. MSSQL/generic untouched. Cross-dialect promotion is filed as a follow-up todo (Option 3 in the debug doc).
</objective>

<execution_context>
@/Users/jsmith79/.claude/plugins/cache/gsd-plugin/gsd/2.40.1/workflows/execute-plan.md
@/Users/jsmith79/.claude/plugins/cache/gsd-plugin/gsd/2.40.1/templates/summary.md
</execution_context>

<context>
@.planning/STATE.md
@.planning/debug/databricks-tls-self-signed.md
@.planning/quick/260528-fks-fix-defect-a-databricks-catalog-defaults/260528-fks-SUMMARY.md
@CLAUDE.md

<interfaces>
<!-- Key contracts the executor will be touching. Extracted from current source. -->

From src/config.py — DatabricksConnectionConfig (line 70-79):
```python
@dataclass(frozen=True)
class DatabricksConnectionConfig:
    dialect: str = "databricks"
    host: str = ""
    http_path: str = ""
    catalog: str = ""
    schema_name: str = "default"
    token: str | None = None
```

From src/config.py — `_parse_databricks_connection` (line 236-246):
```python
def _parse_databricks_connection(name: str, params: dict) -> DatabricksConnectionConfig:
    known_fields = {"dialect", "host", "http_path", "catalog", "schema_name", "token"}
    _warn_unknown_fields(name, params, known_fields)
    return DatabricksConnectionConfig(
        host=params.get("host", ""),
        http_path=params.get("http_path", ""),
        catalog=params.get("catalog", ""),
        schema_name=params.get("schema_name", "default"),
        token=params.get("token"),
    )
```

From src/db/dialects/databricks.py — `_kwargs_from_url` preserved_keys (lines 153-159):
```python
preserved_keys = {
    "query_timeout",
    "pool_config",
    "connection_id",
    "disconnect_callback",
    "connection_timeout",
}
```
(Add `"ca_bundle"` here so URL-mode + non-URL kwargs both flow through.)

From src/db/dialects/databricks.py — `create_engine` connect_args construction (lines 246-269):
```python
connection_timeout = kwargs.get("connection_timeout", 30)
dialect_defaults = {
    "_socket_timeout": connection_timeout,
    "_retry_stop_after_attempts_count": 2,
}
user_connect_args = kwargs.get("connect_args") or {}
merged_connect_args = {**dialect_defaults, **user_connect_args}

return sa_create_engine(
    url,
    pool_pre_ping=True,
    echo=False,
    connect_args=merged_connect_args,
)
```
Insertion point: after `dialect_defaults` is built, conditionally add `_tls_trusted_ca_file`:
```python
ca_bundle = kwargs.get("ca_bundle") or ""
if ca_bundle:
    dialect_defaults["_tls_trusted_ca_file"] = os.path.expanduser(ca_bundle)
```

From src/db/connection.py — `_connect_databricks_from_config` (line 563+):
```python
host = resolve_env_vars(config.host) if config.host else ""
http_path = resolve_env_vars(config.http_path) if config.http_path else ""
token = resolve_env_vars(config.token) if config.token else ""
catalog = resolve_env_vars(config.catalog) if config.catalog else ""
schema = resolve_env_vars(config.schema_name) if config.schema_name else "default"
# ... then dialect.create_engine(host=, http_path=, token=, catalog=, schema=)
```
This is the right place to resolve ca_bundle (config field → DBMCP_CA_BUNDLE env fallback → resolve_env_vars for `${VAR}` style → leave expanduser to the dialect to keep symmetry with URL mode). Pass `ca_bundle=` into `dialect.create_engine`.

From src/db/connection.py — `connect_with_url` (line 327+) and `_kwargs_from_url` interaction:
URL-mode (`connect_with_url`) does NOT need a code change in connection.py — `DatabricksDialect._kwargs_from_url` will pick up `?ca_bundle=` from the URL query and place it in kwargs. The env-var fallback for URL-mode is handled inside `create_engine` itself (already reads `DBMCP_CA_BUNDLE` when kwargs.ca_bundle is empty). This keeps both routes covered without duplicating the fallback in two places.

**Final precedence (combined effect):**
1. URL `?ca_bundle=` → kwargs (via `_kwargs_from_url`)
2. Per-connection config `ca_bundle` (named-config route only) → kwargs (via `_connect_databricks_from_config`)
3. `DBMCP_CA_BUNDLE` env var → applied inside `create_engine` when kwargs.ca_bundle is empty
4. None of the above → `_tls_trusted_ca_file` is ABSENT (default certifi behavior)

Note: The scope said named-config could read env at parse time but the cleaner split is to put the env fallback in `create_engine` so URL-mode benefits too without changing `connect_with_url`. Confirmed against `connect_with_url` flow: it calls `dialect.create_engine(sqlalchemy_url=...)`, so env fallback inside `create_engine` covers both routes uniformly. Per-connection explicit value still wins via the precedence chain above.
</interfaces>
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Add ca_bundle field to DatabricksConnectionConfig + parser</name>
  <files>src/config.py, tests/unit/test_config.py</files>
  <behavior>
    Tests (RED first):
    - `test_databricks_config_default_ca_bundle_is_empty_string`: `DatabricksConnectionConfig()` → `ca_bundle == ""`.
    - `test_databricks_config_round_trip_ca_bundle`: parse toml `[connections.dbx]` with `ca_bundle = "~/.ssl-certs/gateway-ca.pem"` → resulting config object has `ca_bundle == "~/.ssl-certs/gateway-ca.pem"` (NO expansion at parse time — that happens at connect time).
    - `test_databricks_config_missing_ca_bundle_defaults_to_empty`: parse toml without `ca_bundle` → `ca_bundle == ""`.
    - `test_databricks_config_ca_bundle_is_known_field`: parse toml with `ca_bundle = "/x"` and assert no "unrecognized field" warning is emitted (use `caplog`).
  </behavior>
  <action>
    1. Edit `src/config.py`:
       - Add `ca_bundle: str = ""` to `DatabricksConnectionConfig` (after `token`).
       - Update `_parse_databricks_connection`: add `"ca_bundle"` to `known_fields`; add `ca_bundle=params.get("ca_bundle", "")` to the constructor call.
    2. Edit `tests/unit/test_config.py`: add the four tests above. Mirror the existing toml-parse fixture/pattern used for other databricks parser tests in this file (use `tomllib.loads` or whatever helper is already in use — grep first to match).
    3. Run: `uv run pytest tests/unit/test_config.py -k "databricks and ca_bundle" -x`. Confirm RED before code change, GREEN after.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_config.py -k "databricks" -x</automated>
  </verify>
  <done>
    - `DatabricksConnectionConfig.ca_bundle: str = ""` exists.
    - Parser accepts `ca_bundle` as known field, defaults missing to `""`, no expansion at parse time.
    - 4 new tests pass; no regressions in existing test_config.py.
    - Single commit: `feat(config): add ca_bundle field to DatabricksConnectionConfig`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Plumb ca_bundle through DatabricksDialect (kwargs + URL + env fallback)</name>
  <files>src/db/dialects/databricks.py, tests/unit/test_connect_tool.py</files>
  <behavior>
    Tests (RED first; place in test_connect_tool.py near existing DatabricksDialect.create_engine tests — grep for `_socket_timeout` to find the right test class/section; if a dedicated databricks-dialect test file exists alongside, prefer that):

    Mock `sa_create_engine` and assert on the `connect_args` dict it receives.

    - `test_databricks_ca_bundle_kwargs_passes_tls_trusted_ca_file`: call `DatabricksDialect().create_engine(host=..., http_path=..., catalog="c", ca_bundle="/abs/ca.pem")` → captured `connect_args["_tls_trusted_ca_file"] == "/abs/ca.pem"`.
    - `test_databricks_ca_bundle_tilde_expansion`: pass `ca_bundle="~/x.pem"` → captured value equals `os.path.expanduser("~/x.pem")` (use the running user's HOME so it's deterministic in CI).
    - `test_databricks_ca_bundle_absent_when_unset`: no `ca_bundle` kwarg, no `DBMCP_CA_BUNDLE` env (use `monkeypatch.delenv("DBMCP_CA_BUNDLE", raising=False)`) → `"_tls_trusted_ca_file" not in connect_args` (assert ABSENT, not empty string).
    - `test_databricks_ca_bundle_url_query_param`: pass `sqlalchemy_url="databricks://token:T@h.example.com/?http_path=/sql&catalog=c&ca_bundle=/url/ca.pem"` → captured `connect_args["_tls_trusted_ca_file"] == "/url/ca.pem"`.
    - `test_databricks_ca_bundle_env_fallback`: with `monkeypatch.setenv("DBMCP_CA_BUNDLE", "/env/ca.pem")` and no kwarg, no URL param → captured `connect_args["_tls_trusted_ca_file"] == "/env/ca.pem"` (with expanduser applied — pass an absolute path to keep test simple).
    - `test_databricks_ca_bundle_kwarg_beats_env`: kwarg `ca_bundle="/explicit/ca.pem"` AND `monkeypatch.setenv("DBMCP_CA_BUNDLE", "/env/ca.pem")` → captured value is `/explicit/ca.pem` (kwarg wins).
    - `test_databricks_ca_bundle_url_beats_env`: URL `?ca_bundle=/url/ca.pem` AND `DBMCP_CA_BUNDLE=/env/ca.pem` → captured value is `/url/ca.pem`.
  </behavior>
  <action>
    1. Edit `src/db/dialects/databricks.py`:
       a. Add `import os` at the top if not already imported (grep first; logger is, os may not be).
       b. In `_kwargs_from_url` (around line 153): add `"ca_bundle"` to `preserved_keys`. Then below the existing `query.get("...")` lines, extract `ca_bundle = query.get("ca_bundle", "")` and add `"ca_bundle": ca_bundle` to the `new_kwargs.update({...})` block. The preserved-keys logic already passes through any `original_kwargs["ca_bundle"]` if URL is supplied without one, but URL-supplied wins (matches existing URL-wins policy — explicitly: if both URL has ca_bundle and original kwargs has ca_bundle, the new_kwargs.update at the end overwrites with the URL value, consistent with the rest of the function).
       c. In `create_engine` (around line 256, after `dialect_defaults` dict is built):
          ```python
          ca_bundle = kwargs.get("ca_bundle") or os.environ.get("DBMCP_CA_BUNDLE", "")
          if ca_bundle:
              dialect_defaults["_tls_trusted_ca_file"] = os.path.expanduser(ca_bundle)
          ```
          Insert BEFORE `user_connect_args` merge so user-supplied `connect_args` can still override (consistent with existing precedence comment on line 260).
    2. Add the 7 tests above. Use `monkeypatch.setattr` on `src.db.dialects.databricks.sa_create_engine` to capture call args (mirror existing test patterns — grep for `sa_create_engine` in the test file). Also `monkeypatch.setattr` `_databricks_import_error` to None to bypass the import guard (pattern already in test_connect_with_config_databricks.py line 132).
    3. Run: `uv run pytest tests/unit/test_connect_tool.py -k "ca_bundle" -x`. Confirm RED, then GREEN.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_connect_tool.py tests/unit/test_config.py -k "databricks or ca_bundle" -x</automated>
  </verify>
  <done>
    - `_kwargs_from_url` extracts `ca_bundle` from URL query and preserves cross-call kwarg.
    - `create_engine` inserts `_tls_trusted_ca_file` into `connect_args` only when ca_bundle (kwarg or env) is non-empty; tilde-expanded.
    - 7 new tests pass; absent-when-unset is asserted as MISSING KEY (not empty string).
    - Existing `test_connect_tool.py` tests still pass (no regression on `_socket_timeout`/`_retry_stop_after_attempts_count` defaults).
    - Single commit: `feat(databricks): plumb ca_bundle through dialect (kwargs + URL + env)`.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 3: Wire ca_bundle through _connect_databricks_from_config (named-config route)</name>
  <files>src/db/connection.py, tests/unit/test_connect_with_config_databricks.py</files>
  <behavior>
    Tests (RED first):

    - `test_named_config_ca_bundle_passed_to_dialect`: toml config with `ca_bundle = "/cfg/ca.pem"` → captured kwargs to `dialect.create_engine` include `ca_bundle="/cfg/ca.pem"`.
    - `test_named_config_ca_bundle_env_var_resolved`: toml config with `ca_bundle = "${TEST_CA_PATH}"` and `monkeypatch.setenv("TEST_CA_PATH", "/resolved/ca.pem")` → kwargs.ca_bundle is `/resolved/ca.pem` (resolve_env_vars happened before reaching dialect).
    - `test_named_config_no_ca_bundle_passes_empty`: toml config without ca_bundle, no DBMCP_CA_BUNDLE env → either `ca_bundle=""` or absent in kwargs to dialect (assert it does NOT cause `_tls_trusted_ca_file` to appear in the final connect_args by going one level deeper into create_engine and asserting on connect_args directly — pick one assertion level, document it).
    - **Precedence integration test** `test_named_config_explicit_beats_env`: toml `ca_bundle = "/cfg/ca.pem"` + `monkeypatch.setenv("DBMCP_CA_BUNDLE", "/env/ca.pem")` → final `_tls_trusted_ca_file` is `/cfg/ca.pem` (the cfg value wins because it reaches `create_engine` as a non-empty kwarg, short-circuiting the env fallback inside create_engine).
  </behavior>
  <action>
    1. Edit `src/db/connection.py` — `_connect_databricks_from_config` (line 563+):
       - After existing `schema = ...` resolution, add:
         ```python
         ca_bundle_raw = config.ca_bundle or ""
         ca_bundle = resolve_env_vars(ca_bundle_raw) if ca_bundle_raw else ""
         ```
         (DBMCP_CA_BUNDLE env fallback intentionally NOT here — it's applied inside `dialect.create_engine` so URL-mode also benefits without duplication. Per-connection cfg resolves to "" when unset, dialect fallback then kicks in.)
       - In the `dialect.create_engine(host=, http_path=, ...)` call, add `ca_bundle=ca_bundle,` to the kwargs (only pass it if non-empty? — pass unconditionally; an empty string is treated as "not provided" by the dialect's `kwargs.get("ca_bundle") or os.environ.get(...)` chain, which is the desired fallback behavior).
       - Also pass `ca_bundle` to the `_require_databricks_catalog` probe-engine call (line 529-535) so the IDENT-01 enrichment probe also goes through the gateway CA when behind MITM. Add `ca_bundle=ca_bundle` to the `_require_databricks_catalog(...)` call AND to `_require_databricks_catalog`'s signature + its inner `dialect.create_engine(...)` call.
    2. Add the 4 tests above to `tests/unit/test_connect_with_config_databricks.py`. Pattern: monkeypatch the dialect's `create_engine` to capture kwargs; mirror the existing test fixtures (lines 73, 178, 223 use the same DATABRICKS_HOST env pattern).
    3. Run: `uv run pytest tests/unit/test_connect_with_config_databricks.py -k "ca_bundle" -x`. RED → GREEN.
    4. **Full regression check:** `uv run pytest tests/unit/test_config.py tests/unit/test_connect_tool.py tests/unit/test_connect_with_config_databricks.py -x`.
  </action>
  <verify>
    <automated>uv run pytest tests/unit/test_config.py tests/unit/test_connect_tool.py tests/unit/test_connect_with_config_databricks.py -x</automated>
  </verify>
  <done>
    - `_connect_databricks_from_config` resolves `${VAR}` in `config.ca_bundle` and passes it to `dialect.create_engine`.
    - `_require_databricks_catalog` probe also gets `ca_bundle` (so the IDENT-01 enrichment path doesn't break behind a MITM gateway).
    - 4 new tests pass; combined precedence test confirms cfg > env.
    - All three test files green; coverage stays above the 85% floor.
    - Single commit: `feat(connection): pass ca_bundle through named-config route + catalog-probe enrichment`.
  </done>
</task>

<task type="auto">
  <name>Task 4: Documentation + cross-dialect follow-up todo</name>
  <files>README.md, .planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md</files>
  <action>
    1. **README.md:** First grep README for the existing Databricks setup section (`grep -n -i "databricks" README.md | head`). Find a logical insertion point near the [connections.X] toml example for Databricks. Add a short subsection (one paragraph + one toml example):

       ```markdown
       ### Corporate MITM TLS Gateways (Databricks)

       If your Databricks workspace is reached via a corporate TLS-rewriting
       gateway (e.g. Cloudflare Zero Trust), Python won't trust the gateway's
       CA by default. Set `ca_bundle` in your connection config to point at
       the gateway CA file:

       ```toml
       [connections.databricks-prod]
       dialect = "databricks"
       host = "${DATABRICKS_HOST}"
       http_path = "${DATABRICKS_HTTP_PATH}"
       token = "${DATABRICKS_TOKEN}"
       catalog = "main"
       ca_bundle = "~/.ssl-certs/gateway-ca.pem"  # PEM file with the gateway CA
       ```

       Alternatively, set `DBMCP_CA_BUNDLE=/path/to/ca.pem` in your shell as a
       process-wide fallback (applies to all Databricks connections that don't
       set `ca_bundle` explicitly). Tilde and `${VAR}` are both expanded.
       ```

       If no Databricks section exists in README, add it at the end of the configuration section. Keep it ~10 lines.

    2. **Cross-dialect follow-up todo:** Create `.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md`:
       ```markdown
       ---
       slug: cross-dialect-ca-bundle-support
       category: database
       priority: low
       created: 2026-05-28
       trigger: "Databricks ca_bundle config field shipped (260528-gsk). MSSQL/generic don't have this hook yet — promote to dialect-protocol level when a second dialect runs into a corp-MITM gateway."
       ---

       # Promote ca_bundle to ConnectionConfig protocol (Option 3)

       ## Context
       Quick task 260528-gsk shipped Option 2 from `.planning/debug/resolved/databricks-tls-self-signed.md`:
       a Databricks-only `ca_bundle` field + `DBMCP_CA_BUNDLE` env fallback. MSSQL and generic
       dialects do not have an equivalent hook. User confirmed MSSQL endpoint is not currently
       behind the corp gateway, so this is non-urgent.

       ## Trigger to action
       File this as the work-to-do when ANY of:
       - A second dialect (MSSQL, generic, or future) hits a corp-MITM SSLCertVerificationError.
       - A user asks for a unified TLS-trust-bundle config across dialects.
       - The dialect protocol is being refactored for any other reason (ride that change).

       ## Scope
       - Promote `ca_bundle: str = ""` to a base `ConnectionConfig` protocol/dataclass field
         (or a mixin) that all dialect configs inherit.
       - Each dialect's `create_engine` consumes it via the dialect-appropriate connect_arg
         (`_tls_trusted_ca_file` for Databricks; pyodbc/MSSQL has its own; SQLAlchemy generic
         varies by driver — research each).
       - Keep `DBMCP_CA_BUNDLE` env fallback semantics; document precedence consistently.
       - One README section for all dialects, not per-dialect.

       ## Out of scope
       - Per-dialect TLS knobs beyond ca_bundle (cipher suites, cert pinning, etc.).
       ```
  </action>
  <verify>
    <automated>test -f .planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md && grep -q "ca_bundle" README.md</automated>
  </verify>
  <done>
    - README has a short Corp MITM section with toml example + DBMCP_CA_BUNDLE note.
    - Follow-up todo exists at the specified path with frontmatter + scope.
    - Single commit: `docs(databricks): document ca_bundle for corp-MITM TLS gateways + file Option-3 follow-up`.
  </done>
</task>

<task type="checkpoint:human-verify" gate="blocking">
  <name>Task 5: Live UAT probe via dbmcp-test against corp-MITM Databricks workspace</name>
  <what-built>
    Code changes from Tasks 1-3 are committed. `dbmcp.toml` already has a
    `[connections.databricks-test]` block. Executor MUST add
    `ca_bundle = "~/.ssl-certs/gateway-ca.pem"` to that block before the probe.
  </what-built>
  <how-to-verify>
    1. Add `ca_bundle = "~/.ssl-certs/gateway-ca.pem"` to the `[connections.databricks-test]` table in `dbmcp.toml` (the executor does this — it's a config edit, not a Claude-vs-user decision).
    2. Reload the dbmcp-test MCP server so it picks up the code change AND the new toml field. (User may need to do this from the MCP host UI; if so, prompt clearly.)
    3. Invoke `connect_database(connection_name="databricks-test")` via the dbmcp-test MCP tool 3 times in succession (LB-rewrite intermittency means a single success isn't conclusive — Probe A in the debug doc found 5/5 clean chains in one window).
    4. Each call must return a connection_id (no SSLCertVerificationError).
    5. Document the probe results (timestamp, attempt count, success/failure per attempt, connection_id returned) in `.planning/quick/260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca/260528-gsk-SUMMARY.md` under a "Live UAT" section.

    **If probe fails:**
    - Capture the full SSLCertVerificationError chain and Python TLS env (re-run Verification B from the debug doc).
    - Verify `~/.ssl-certs/gateway-ca.pem` exists and is readable from inside `uv run`'s venv.
    - Verify the path actually reaches `_tls_trusted_ca_file` by adding a one-time DEBUG log line in `create_engine` (revert before commit) OR by capturing connect_args via a unit-test-style assertion against the live config.
    - Report findings to the user; do not "fix forward" silently.

    **If probe succeeds:**
    - Continue to Task 6 (cleanup).
  </how-to-verify>
  <resume-signal>Type "approved" if 3/3 probes succeeded and SUMMARY.md is updated, or describe failures.</resume-signal>
</task>

<task type="auto">
  <name>Task 6: Resolve debug record + final SUMMARY entry</name>
  <files>.planning/debug/resolved/databricks-tls-self-signed.md, .planning/quick/260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca/260528-gsk-SUMMARY.md</files>
  <action>
    1. Create `.planning/debug/resolved/` directory if it doesn't exist (`mkdir -p`).
    2. Move `.planning/debug/databricks-tls-self-signed.md` → `.planning/debug/resolved/databricks-tls-self-signed.md` (`git mv`).
    3. Append to the resolved file (after the existing Resolution section):
       ```markdown

       ## Resolution Applied

       - **Date:** 2026-05-28
       - **Option:** 2 (targeted Databricks ca_bundle field + DBMCP_CA_BUNDLE env fallback)
       - **Quick task:** 260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca
       - **Commits:** {fill in commit hashes from Tasks 1-4 — get via `git log --oneline -10`}
       - **Live UAT result:** {paste the 3-probe outcome from SUMMARY.md}
       - **Cross-dialect follow-up:** `.planning/todos/pending/2026-05-28-cross-dialect-ca-bundle-support.md` (Option 3)
       - **Status:** RESOLVED
       ```
    4. Update the file's frontmatter `status` from `awaiting_human_decision` to `resolved` and `updated:` to `2026-05-28`.
    5. Ensure SUMMARY.md is complete (objective, files changed, commit list, Live UAT outcome, follow-up todo path).
    6. Single commit: `docs(quick-260528-gsk): resolve TLS debug record + SUMMARY`.
  </action>
  <verify>
    <automated>test -f .planning/debug/resolved/databricks-tls-self-signed.md && ! test -f .planning/debug/databricks-tls-self-signed.md && grep -q "RESOLVED" .planning/debug/resolved/databricks-tls-self-signed.md</automated>
  </verify>
  <done>
    - Debug record moved to `resolved/` and contains the Resolution Applied block with real commit hashes + UAT outcome.
    - SUMMARY.md complete.
    - Final commit pushed to feature branch (do NOT push to main; user will merge per their git workflow).
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| user toml → dbmcp config parser | User-controlled file path string crosses into Python file-IO at TLS handshake time |
| `DBMCP_CA_BUNDLE` env → Python TLS context | Env-var-supplied path becomes the trust anchor for HTTPS to Databricks |
| `?ca_bundle=` URL query param → connect_args | Query string traverses MCP RPC boundary (untrusted client could supply arbitrary path) |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-gsk-01 | Tampering | `_tls_trusted_ca_file` value passed to connector | accept | Config + env are operator-supplied (same trust level as the rest of dbmcp.toml — token, host). MCP RPC `?ca_bundle=` arrives from a connected agent, but agents already pass the SQL connection token in the same channel; ca_bundle adds no new authority beyond what they already have. No new exposure. |
| T-gsk-02 | Information Disclosure | ca_bundle path (e.g. `~/.ssl-certs/gateway-ca.pem`) appearing in logs | mitigate | Do NOT log ca_bundle value at INFO. The existing `logger.debug("sqlalchemy_url supplied; ignoring conflicting kwargs: %s", conflicting)` would emit the key name only when conflicts exist — fine. No new log statements added that emit the ca_bundle value. |
| T-gsk-03 | Denial of Service | Pointing ca_bundle at a non-existent or unreadable file | accept | databricks-sql-connector raises a clear OSError/FileNotFoundError; this surfaces to the MCP client as a normal connection failure. No silent fallback to system store (which would defeat the purpose of opting in to a CA pin). |
| T-gsk-04 | Elevation of Privilege | Malicious agent supplying `?ca_bundle=/path/to/attacker-controlled.pem` to spoof Databricks endpoint | accept | The attacker would also need to supply the `host` and `token` — at which point they're already connecting to whatever endpoint they want. ca_bundle does not raise privilege beyond existing host/token control. Operator scenarios (config-file-supplied) are trusted by definition. |
| T-gsk-05 | Repudiation | Connection succeeded with a custom CA — was it the corp gateway or an attacker? | mitigate | Existing INFO log at successful connection includes host. Add a one-line INFO log in `create_engine` ONLY when `_tls_trusted_ca_file` is set: `logger.info("Databricks TLS using custom ca_bundle: <path>")` so operator post-incident review can correlate. (Path goes to log file only, not MCP responses.) |
</threat_model>

<verification>
- All three test files green: `uv run pytest tests/unit/test_config.py tests/unit/test_connect_tool.py tests/unit/test_connect_with_config_databricks.py -x`.
- Full unit test suite: `uv run pytest tests/unit/ -x` (no regressions).
- Coverage floor maintained: `uv run pytest --cov=src --cov-fail-under=85`.
- Ruff clean: `uv run ruff check src/ tests/`.
- Live UAT: 3/3 successful `connect_database(connection_name="databricks-test")` probes via dbmcp-test against the real corp-MITM Databricks workspace.
- Documentation: README has Corp MITM section; debug record moved to `resolved/` with applied-resolution block + commit hashes.
- Follow-up todo filed at the specified path with Option-3 scope.
</verification>

<success_criteria>
- ca_bundle works in named-config mode (toml `[connections.X]` field).
- ca_bundle works in URL mode (`?ca_bundle=` query param).
- DBMCP_CA_BUNDLE env-var fallback works in BOTH modes.
- Precedence: per-connection cfg > URL query > env var > unset (= absent from connect_args).
- Tilde and `${VAR}` both expand.
- MSSQL/generic dialects untouched.
- Live probe against the corp Databricks workspace succeeds 3/3.
</success_criteria>

<output>
After completion, ensure `.planning/quick/260528-gsk-add-databricks-ca-bundle-config-dbmcp-ca/260528-gsk-SUMMARY.md` exists with:
- Objective recap
- Files changed list
- Commit hashes (one per task)
- Live UAT result (3-probe table with timestamps)
- Pointer to the follow-up todo
- Pointer to the resolved debug record
</output>
