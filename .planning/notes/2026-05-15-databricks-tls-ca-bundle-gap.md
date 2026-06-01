# Databricks dialect lacks custom-CA / TLS configuration

**Surfaced:** 2026-05-15 during Phase 14 UAT
**Severity:** major (blocks Databricks usage on TLS-intercepting networks)
**Phase 14 relation:** unrelated — Phase 14 didn't touch TLS or transport. Pre-existing latent gap, exposed by an environment change.

## Symptom

`mcp__dbmcp-test__connect_database(connection_name="databricks-test")` fails:

```
SSLError(SSLCertVerificationError(1, '[SSL: CERTIFICATE_VERIFY_FAILED]
certificate verify failed: self-signed certificate in certificate chain
(_ssl.c:1018)'))
```

Trace originates in `urllib3.HTTPSConnectionPool` inside `databricks-sql-connector`, called by `_test_connection`'s `engine.connect()`.

## Diagnosis

- `src/db/dialects/databricks.py` and `src/db/connection.py` Databricks paths have **zero** SSL/cert handling. `trust_server_cert` is wired only for MSSQL (connection.py:157, 213, 486).
- `databricks-sql-connector` defers HTTPS to `urllib3`, which uses `certifi`'s bundle (`/Users/jsmith79/.../.venv/.../certifi/cacert.pem`) — does not consult system trust store.
- No `REQUESTS_CA_BUNDLE` / `SSL_CERT_FILE` / `CURL_CA_BUNDLE` env vars set in the dbmcp-test MCP server's process.
- On a TLS-intercepting corporate path (or any path that introduces a non-public root cert), connection fails before any dbmcp logic runs.
- Worked a few days ago — environment changed (corp cert rotation, WARP behavior, or system trust update); dbmcp never had a fallback.

## Suggested fix scope

1. Add `databricks_ca_bundle` / `ssl_ca_path` connection arg honored in `DatabricksDialect.create_engine`, plumbed to `databricks-sql-connector`'s SSL options.
2. Auto-pick up `SSL_CERT_FILE` / `REQUESTS_CA_BUNDLE` env vars when set.
3. Optional: `trust_server_cert: bool` parity with MSSQL for dev workflows (warn loudly).

Exact integration point: `databricks.sql.connect(...)` accepts `_tls_trusted_ca_file` / `_tls_no_verify` kwargs (see databricks-sql-connector docs). Pass these through `create_engine` connect_args.

## Tests blocked by this gap

- Phase 14 UAT tests 1–5 (all live Databricks behaviors) — blocked: third-party.
- Any future live Databricks integration verification on TLS-intercepted networks.

## Acceptance criteria for fix phase

- `connect_database` against Databricks succeeds when CA bundle is supplied via either named-config field, URL query, or env var.
- Existing connections without the field continue to work (no behavior change on non-intercepted paths).
- Documented in `dbmcp.toml` example.
