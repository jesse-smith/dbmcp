---
status: complete
phase: 15-unified-identifier-resolver-cross-dialect
source: [15-01-SUMMARY.md, 15-02-SUMMARY.md, 15-03-SUMMARY.md, 15-04-SUMMARY.md, 15-05-SUMMARY.md, 15-06-SUMMARY.md]
started: 2026-05-28T20:00:00Z
updated: 2026-05-28T20:54:00Z
---

## Current Test

[testing complete]

## Tests

### 1. Cold-start smoke — fresh MSSQL connect + sample data
expected: Fresh connect_database(stemsoftclinictest) → status:success + connection_id; get_sample_data on a known dbo table returns live rows. Confirms no connection/startup regression from the src/db/ resolver wiring.
result: pass
evidence: "connect_database(stemsoftclinictest) → connection_id 437307010365, status:success, dialect:mssql, schema_count:2. get_sample_data(PerformedActs, dbo) → 3 live rows, table_id 'dbo.PerformedActs' (correctly qualified, no 'None.' prefix). No regression from src/db/ resolver rewiring."

### 2. MSSQL dotted table_name resolves schema
expected: get_table_schema with table_name="dbo.<table>" and NO schema_name returns that table's columns. The resolver parses "dbo" out of the dotted name (depth 2 for MSSQL) — no error, correct columns.
result: pass
evidence: "get_table_schema(table_name='dbo.PerformedActs', no schema_name) → status:success, table_name:PerformedActs, schema_name:dbo, 21 columns. Resolver split the depth-2 dotted name correctly."

### 3. MSSQL schema default fills from dialect (no hardcoded dbo)
expected: A namespace tool (e.g. get_sample_data or find_pk_candidates) called with a bare table_name and NO schema_name still resolves to the dbo schema and returns data. The default now comes from DialectStrategy.default_schema='dbo', not a hardcoded signature default.
result: pass
evidence: "get_sample_data(table_name='PerformedActs', no schema_name) → table_id 'dbo.PerformedActs', 2 live rows. dbo filled from DialectStrategy.default_schema, not a signature default (SC4)."

### 4. Catalog gate rejects catalog on MSSQL (D-07)
expected: get_table_schema (or any namespace tool) called with catalog="anything" on the MSSQL connection returns status:error. The message indicates catalog is not supported / rejected on non-Databricks dialects (max_identifier_depth < 3). It does NOT silently ignore the catalog.
result: pass
evidence: "get_table_schema(catalog='somecatalog') on MSSQL → status:error, message 'catalog is not supported for the mssql dialect (max identifier depth 2; catalog requires depth 3)'. D-07 gate via _assert_catalog_allowed; no silent-ignore."

### 5. Conflict detection between table_name and schema_name (D-04)
expected: get_table_schema with table_name="dbo.<table>" AND schema_name="reporting" (a different schema) returns status:error mentioning conflicting/disagreeing schema. Redundant-but-consistent (table_name="dbo.X" + schema_name="dbo") is allowed.
result: pass
evidence: "Disagreement: get_table_schema('dbo.PerformedActs', schema_name='reporting') → status:error 'Conflicting schema: table_name implies dbo but schema_name=reporting'. Consistent: get_table_schema('dbo.PerformedActs', schema_name='dbo') → status:success, 21 columns (not rejected). D-04 disagreement-only conflict detection confirmed."

### 6. Databricks 3-part table_name end-to-end (SC3 fix)
expected: After connect_database(databricks-test, catalog="bmtct"), get_sample_data with table_name="bmtct.<schema>.<table>" returns live rows WITHOUT any USE CATALOG step. This is the SC3 gap flagged in VERIFICATION.md, fixed by quick task 260528-qcp. No "None"."table" corrupt SQL.
result: pass
evidence: "connect_database(databricks-test) → connection_id d9ce935f5dbb, catalog bmtct, 22 schemas. get_sample_data(table_name='bmtct.playground.caboodle_tests', no catalog/schema params) → status:success, 3 live rows, table_id 'playground.caboodle_tests'. Resolver split 3-part name to catalog=bmtct/schema=playground/table=caboodle_tests; valid 3-part Databricks SQL; no USE CATALOG; no 'None'.'table' corruption. SC3 fix (260528-qcp) verified live."

### 7. find_pk_candidates / find_fk_candidates namespace-aware (Plan 06)
expected: find_pk_candidates (and find_fk_candidates) now accept a dotted table_name and resolve schema correctly on MSSQL, and reject catalog on MSSQL (status:error). Confirms the last two tools were swept of dbo defaults and wired through resolve_identifier (5→7 resolver-routed tools).
result: pass
evidence: "find_pk_candidates(table_name='dbo.PerformedActs') → status:success, schema_name:dbo, found PK PerformedActID (constraint-backed). find_pk_candidates(catalog='somecatalog') on MSSQL → status:error (gate). find_fk_candidates(catalog='somecatalog') on MSSQL → status:error (gate). Both tools resolver-routed; 5→7 confirmed; categorical SC4 holds."

## Summary

total: 7
passed: 7
issues: 0
pending: 0
skipped: 0
blocked: 0

## Gaps

[none — Phase 15 identifier-resolver invariants verified end-to-end against live MSSQL and Databricks]

## Verification Note (2026-05-28)

All 7 tests run live via the `dbmcp-test` MCP server against both dialects:
- MSSQL: `stemsoftclinictest` (connection_id 437307010365)
- Databricks: `databricks-test`, catalog bmtct (connection_id d9ce935f5dbb)

Confirms the four phase invariants end-to-end (not just unit level):
- **IDENT-03/04/07** (dotted-name depth parsing, disagreement-only conflict, dialect default-schema fill) — Tests 2, 3, 5
- **D-07 catalog gate** (reject on shallow dialect via `_assert_catalog_allowed`) — Tests 4, 7
- **SC3** (Databricks 3-part `table_name` end-to-end, the gap flagged in 15-VERIFICATION.md and fixed by quick task `260528-qcp`) — Test 6
- **SC4 + 5→7 resolver-routed tools** (categorical `dbo`-default removal; find_pk/fk_candidates now namespace-aware) — Tests 3, 7

15-VERIFICATION.md was `status: gaps_found` (SC3) before the `260528-qcp` fix; this UAT supersedes it — the SC3 gap is closed and verified live.
