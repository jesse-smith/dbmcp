---
status: partial
phase: 14-connect-time-hardening-databricks
source: [14-01-SUMMARY.md, 14-02-SUMMARY.md, 14-03-SUMMARY.md, 14-04-SUMMARY.md]
started: 2026-05-15T01:12:38Z
updated: 2026-05-15T01:43:42Z
---

## Current Test

[testing paused — 5 items blocked by pre-existing Databricks TLS gap]

## Tests

### 1. Named-config Databricks connect with catalog succeeds
expected: Connecting via `databricks-test` named config (catalog="bmtct") returns status:success with a connection_id.
result: blocked
blocked_by: third-party
reason: "dbmcp Databricks dialect lacks custom-CA / TLS configuration. databricks-sql-connector uses certifi bundle only; no SSL_CERT_FILE/REQUESTS_CA_BUNDLE pickup. Failure point is HTTPSConnectionPool inside _test_connection — pre-existing latent gap, surfaced by env change. Phase 14 did not modify TLS/transport. See .planning/notes/2026-05-15-databricks-tls-ca-bundle-gap.md."

### 2. SQLAlchemy URL without catalog raises enriched ConnectionError
expected: connect_database with a Databricks URL that omits ?catalog= fails with a ConnectionError whose message contains "Databricks connection requires a catalog" and "Accessible catalogs:" listing real catalogs from the workspace (chained from the dialect ValueError).
result: blocked
blocked_by: third-party
reason: "Same TLS gap as Test 1. The enrichment helper builds a probe engine and calls SHOW CATALOGS, which hits the same HTTPSConnectionPool failure before reaching Phase 14's catalog-list assembly."

### 3. SQLAlchemy URL with catalog succeeds
expected: connect_database with the same Databricks URL plus ?catalog=bmtct returns status:success — confirms URL-mode parity with named-config.
result: blocked
blocked_by: third-party
reason: "Same TLS gap as Test 1."

### 4. list_schemas on Databricks returns real schemas, not catalog names
expected: After connecting (catalog="bmtct"), list_schemas returns schema names within the bmtct catalog. It must NOT return catalog names (e.g., "main", "system", "bmtct") as schemas — the SHOW CATALOGS fallback is gone.
result: blocked
blocked_by: third-party
reason: "Same TLS gap as Test 1; cannot reach a connected Databricks engine to invoke list_schemas. Note: IDENT-02 is locked at unit-test level (test_list_schemas_databricks_does_not_fall_back_to_show_catalogs in test_metadata.py:771)."

### 5. Live execute_query SHOW CATALOGS surfaces catalog list
expected: Running execute_query "SHOW CATALOGS" against the connected `databricks-test` engine returns a list of catalogs.
result: blocked
blocked_by: third-party
reason: "Same TLS gap as Test 1."

### 6. Non-Databricks dialect ValueError not routed through helper
expected: Connecting to the `stemsoftclinictest` MSSQL config still works normally. (Negative regression: the new ValueError catch in connect_with_url is gated by isinstance(DatabricksDialect), so MSSQL is unaffected.)
result: pass
evidence: "connect_database(stemsoftclinictest) → connection_id 437307010365, status:success, dialect:mssql, schema_count:2. list_schemas returned dbo (246 tables), reporting (1 table). No regression from Phase 14's connect_with_url ValueError handler."

## Summary

total: 6
passed: 1
issues: 0
pending: 0
skipped: 0
blocked: 5

## Gaps

[none — blockers are not Phase 14 code defects]

## Outstanding Items

- **Pre-existing Databricks TLS / custom-CA gap** — captured in .planning/notes/2026-05-15-databricks-tls-ca-bundle-gap.md. Needs its own phase. Until fixed, live UAT of Phase 14's Databricks-specific behaviors is impossible on TLS-intercepted networks. Phase 14 catalog-hardening invariants are locked at unit-test level (987 passed, 91.14% coverage, IDENT-01/02 + TEST-01/02 closure tests all green).

## Notes

- Phase 14 branch is on `databricks-sql-connector 4.2.5`; the bumps to 4.2.6 / urllib3 landed on main 2026-05-11, after this branch was cut. Branch deps unchanged; failure is environmental + latent dialect gap.
- Phase 14 src changes touch only catalog validation (dialects/databricks.py), list_schemas fallback (metadata.py), and ConnectionError enrichment (connection.py). None touch TLS/transport.
