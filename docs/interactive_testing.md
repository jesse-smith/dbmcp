# dbmcp Interactive Testing

**Test environment:** SVWTSTEM04 / StemSoftClinic (Windows auth)
**Connection ID:** `542f8ffefc15`
**Branch:** `integration-test`
**Date started:** 2026-02-26

---

## Tools Under Test

### 1. connect_database
Connect to a SQL Server database with pooled connections. Supports sql, windows, azure_ad, and azure_ad_integrated auth methods.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Windows auth connect | Connected, got ID 542f8ffefc15, 2 schemas |
| SKIP | SQL auth connect | No SQL auth credentials available |
| PASS | Azure AD integrated connect | stjude-edw/EDW, got ID b1478cd5a0d7, 21 schemas |
| PASS | Invalid server/db handling | Invalid server: timeout (HYT00). Invalid db: login failed (4060). Both return structured failure, no crashes |
| SKIP | Connection timeout behavior | Pass-through to pyodbc/SQLAlchemy, low risk |

### 2. list_schemas
List all schemas with table/view counts. Excludes system schemas (sys, INFORMATION_SCHEMA, guest).

| Status | Test | Notes |
|--------|------|-------|
| PASS | Basic schema listing | EDW: 21 schemas, sorted by table_count desc, counts look correct |
| PASS | Verify system schema exclusion | sys, INFORMATION_SCHEMA, guest all excluded |

### 3. list_tables
List tables with row counts and metadata. Supports filtering by schema, name pattern, min row count, object type (table/view). Supports pagination and sorting.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Default listing (by row_count desc) | 100 returned of 440 total, sorted correctly, has_more=true, all metadata fields present |
| PASS | Schema filter | dbo filter returns 439 (vs 440 total), correctly excludes 1 non-dbo table |
| PASS | Name pattern filter (LIKE) | Tested: vw_% (12 hits), % (all), nonexistent (empty), bracket escapes %[_]V2[_]% (2 hits), SQL injection `' OR 1=1 --` (0 results, safely parameterized) |
| PASS | Min row count filter | >=1M returns 16 tables, total_count=16, has_more=false. (Issue #1 fixed in bugfix/tier1-issues) |
| PASS | Object type filter (table only) | 298 tables found. All table_type="table" |
| PASS | Object type filter (view only) | 142 views found, all row_count=null (expected). 298+142=440 checks out. Invalid type "procedure" returns clean validation error |
| PASS | Pagination (offset + limit) | Pages chain correctly (no overlap/gap), last page has_more=false, offset beyond end returns empty gracefully |
| PASS | Sort by name | Alphabetical asc confirmed (A_ACUTEGVHD → WorkflowUsers). Combines correctly with pagination |
| PASS | Detailed output mode | Adds columns array (column_name, data_type, is_nullable, is_primary_key) per table. Verified on Calendar table (4 cols). Spec contract doesn't document detailed schema — minor spec gap |

### 4. get_table_schema
Get full table metadata: columns, data types, constraints, indexes, declared foreign keys.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Basic table schema retrieval | PerformedActs: 21 cols, 10 indexes, 3 FKs. Full metadata per column (ordinal, type, nullable, default, identity, computed, PK, FK) |
| PASS | Include/exclude indexes | include_indexes=false omits indexes, keeps FKs. Correct |
| PASS | Include/exclude relationships | include_relationships=false omits FKs, keeps indexes. Correct |
| PASS | Non-dbo schema table | reporting.MaterialManagementInventoryDimension: 8 cols, PK found, no indexes/FKs. schema_name param works |
| PASS | Nonexistent table handling | Clean error: "Table 'dbo.TOTALLY_FAKE_TABLE_XYZ' not found" |

### 5. infer_relationships
Infer potential FK relationships for legacy databases with undeclared FKs. Metadata-only (Phase 1) and value-overlap (Phase 2) modes.

| Status | Test | Notes |
|--------|------|-------|
| BUG | Phase 1: metadata-only inference | All 4 tables timed out at ~10.4s with 0 candidates evaluated, 0 tables analyzed (see Issue #4). Cannot test scoring accuracy. |
| BLOCKED | Phase 2: with value overlap | Blocked by Issue #4 (Phase 1 timeout) |
| BLOCKED | Confidence threshold adjustment | Blocked by Issue #4 |
| BLOCKED | Overlap strategy: sampling vs full | Blocked by Issue #4 |

### 6. get_sample_data
Retrieve sample rows with multiple sampling strategies (top, tablesample, modulo). Auto-truncates large text/binary.

| Status | Test | Notes |
|--------|------|-------|
| PASS | All columns (default) | 3 rows returned with all 21 columns including datetime fields as ISO strings (e.g. `"1995-07-06T00:00:00"`). (Issue #5 fixed in bugfix/tier1-issues) |
| PASS | Top N sampling (column subset) | 5 rows returned, sequential from ID 13.4M (clustered index order). Fast, not representative. BIT→bool, NULL preserved, empty string distinct from null |
| BUG | Tablesample strategy (small N) | `TABLESAMPLE (5 ROWS)` on 60M-row table returned 0 rows — page-level granularity means small N often selects zero pages (see Issue #6) |
| PASS | Tablesample strategy (larger N) | 100 rows from 3 distinct page clusters (IDs ~802M, ~802.4M, ~818M). Confirms page-level random sampling with sequential rows within pages. Clearly different data region than top |
| BUG | Modulo strategy | Returns identical results to `top` — same 5 rows, same order. `ORDER BY (SELECT NULL)` is a no-op (see Issue #7). Modulo sampling is unimplemented despite being advertised |
| PASS | Column subset selection | Single column works. Invalid column returns clean SQL Server error (42S22) with column name. Column list affects optimizer's index choice (different starting rows for same table with different column sets — expected) |
| PASS | Large text/binary truncation | Binary: VARBINARY(MAX) truncated to `<binary: hex... (N bytes)>` with 32-byte hex preview, `truncated_columns` correctly populated. Text: NVARCHAR(MAX) with 35K/29K char XML truncated at 1000 chars with `... (N chars total)` suffix. Short values pass through untouched. Both types report in `truncated_columns` |

### 7. analyze_column
Infer column purpose (ID, enum, status, flag, amount, etc.) via statistical analysis. Useful for cryptic column names.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Analyze an ID column (PK) | PerformedActID: inferred `id` at 0.95 confidence. Correct. Note: numeric_statistics all null (min/max/mean not computed for IDs) — minor gap but arguably intentional |
| BUG | Analyze a flag/bit column | IsArchived (BIT, `Is*` prefix, 1 distinct value): inferred `unknown` at 0.50. Should be `flag` (see Issue #8). `is_enum: true` is reasonable |
| PASS | Analyze a datetime column | ActivityTime_StartDateTime: inferred `timestamp` at 0.85. Good stats: min=1900-01-01 (placeholder), max=2026-01-13, 8% null, 45% business hours |
| PASS | Analyze a text/string column | Comments (NVARCHAR MAX): inferred `unknown` at 0.50. Honest but unhelpful — no `text`/`freetext` purpose category exists. String stats useful: top values show 89% empty + N/A, 2994 distinct, max_length 995 |
| PASS | Analyze a FK ID column (not PK) | PerformedActCodeID: inferred `id` at 0.90. Technically correct but doesn't distinguish FK from PK. 1171 distinct across 20M rows = obvious FK, but `is_enum: false`. Name pattern dominates |
| BUG | Analyze an enum/status column | StatusID (4 distinct, 30% null): inferred `id` at 0.90 instead of `enum`/`status`. `is_enum: true` contradicts inferred purpose. `*ID` name pattern overrides cardinality signal (see Issue #9) |
| BUG | Analyze a numeric/amount column | Result_Value (DECIMAL 28,10, 149 distinct): inferred `unknown` at 0.50. Should be `amount`/`quantity`. Also `is_integer: true` on DECIMAL is wrong. Numeric stats all null (see Issue #9) |
| BUG | Analyze a column with all NULLs | ConfidentialityCodeID (100% null, 0 distinct): inferred `id` at 0.90 purely from name. Confidence should be heavily penalized when there's no data to analyze (see Issue #9) |
| BUG | Nonexistent column error handling | TOTALLY_FAKE_COLUMN: returns `unknown/0.50` with `data_type: "unknown", total_rows: 0`. No error — silently indistinguishable from a real column on a small table (see Issue #10) |
| BUG | Small table analysis | CVs_ProtocolDefinitionType.ElementID (7 rows): `data_type: "unknown", total_rows: 0, distinct_count: 0`. Metadata queries fail silently on small tables — identical output to nonexistent column (see Issue #10) |
| BUG | ID column without *ID suffix (MRN) | MRN on A_Transplant_Info_Rpt: `unknown` at 0.50. 2666 distinct / 3941 rows, all numeric strings 4-6 chars. MRN is a standard healthcare identifier abbreviation — should be `id`. Name pattern only matches `*ID` suffix |
| BUG | ID column named "Identifier" | PrimaryIdentifier on Human view: `unknown` at 0.50. 8001 distinct / 8539 rows (94% unique), all frequency-1 top values. "Identifier" is literally in the name — tool doesn't recognize it. Only `*ID` suffix triggers `id` inference |

### 8. execute_query
Execute ad-hoc SELECT queries with row limiting. Blocks write operations. Truncates large text/binary in results.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Basic SELECT | 5 rows, 121ms. `query_type: "select"`, `is_allowed: true`, `limited: false`. Columns + rows correctly structured. BIT→bool, null handling correct |
| PASS | CTE query (WITH clause) | CTE + JOIN, 438ms. Correctly parsed as `select`. `limited: true` when row_limit reached. Full CTE syntax supported |
| PASS | Row limit enforcement | `row_limit=3` on 20M-row table: returns 3 rows, `limited: true`, `rows_available: 20260071`. Tool injects `TOP (N)` into query. Also reports total available rows — nice UX |
| PASS | Write operation blocked (INSERT) | `status: "blocked"`, `query_type: "insert"`, `is_allowed: false`. Clean message: "DML - INSERT operations are not permitted" |
| PASS | Write operation blocked (UPDATE) | `status: "blocked"`, `query_type: "update"`, `is_allowed: false`. Clean message |
| PASS | Write operation blocked (DELETE) | `status: "blocked"`, `query_type: "delete"`, `is_allowed: false`. Clean message |
| PASS | Invalid SQL handling | Nonexistent table: `status: "error"`, SQL Server error 42S02 with table name. Informative, no crash |

### 9. export_documentation
Export full database documentation to local markdown files. Includes schemas, tables, relationships.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Basic export (no samples, no inferred) | Success: 101 tables, 2 schemas, 140 declared FKs, 155KB total. (Issue #11 fixed in bugfix/tier1-issues) |
| PASS | Export with sample data | 220KB total (vs 155KB without). Sample data sections confirmed in table .md files (e.g., Calendar shows 3 rows with ISO datetime values). No sample data when `include_sample_data=false` — correctly toggleable |
| BUG | Custom output directory | Absolute path rejected: `'/tmp/.../overview.md' is not in the subpath of '.'` (security restriction). Relative path `exports/custom_test` writes files correctly and creates valid `.cache_metadata.json`, BUT response `files_created` returns stale paths from default `docs/` location. See Issue #14 |
| BLOCKED | Include/exclude inferred relationships | Blocked by Issue #4 (infer_relationships timeout) — no inferred relationship data available to export |

### 10. load_cached_docs
Load previously exported documentation cache. Returns entity counts and cache age.

| Status | Test | Notes |
|--------|------|-------|
| PASS | Load after export | status=loaded, tables=101, declared_fks=140, cache_age_days=0, schema_hash present. All fields consistent with export output. Note: table count discrepancy — see Issue #13 |
| BUG | Load with incomplete/no cache | Returns `status: "loaded"` on a partial/corrupt cache from a prior failed run. Schema counts present (dbo: 297+142) but `entity_counts.tables: 0`, `declared_fks: 0`, `cache_age_days: null`. Should flag incomplete cache instead of claiming success (see Issue #12) |

### 11. check_drift
Compare cached docs hash against current database schema. Detects added/removed/modified tables.

| Status | Test | Notes |
|--------|------|-------|
| PASS | No drift (cache is current) | `drift_detected: false`, hashes match, `summary: "No changes detected"`. All diff lists empty |
| PASS | Drift detection with missing cache | Returns `drift_detected: true`, `summary: "Cache metadata missing"`. Correctly identifies incomplete cache. Current hash computed successfully |
| PASS | Drift detection with stale hash | Tampered cached hash to zeros. `drift_detected: true`, `summary: "Structural changes detected in existing tables"`. Added/removed/modified lists all empty (correct — tables unchanged, only hash differs) |
| PASS | Auto-refresh on drift | `auto_refreshed: true`, cache re-exported, hash restored. Note: auto-refresh hardcodes `include_inferred_relationships=True` and uses default `include_sample_data=False` (line 999-1001 in `server.py`) — doesn't preserve prior export settings. Size jumped 155KB→393KB due to inferred relationship computation |

---

## Issues Found

### Issue #1: `list_tables` total_count ignores min_row_count filter — FIXED
**Severity**: Medium (incorrect pagination metadata) — **Fixed in `bugfix/tier1-issues` (commit b7207e6)**
**Location**: `src/db/metadata.py` lines 414-419 (`_list_tables_mssql`)
**Description**: The count query (`count_query`) builds its WHERE clause from `where_sql`, which includes schema_name, name_pattern, and object_type filters — but does NOT include the `min_row_count >= :min_row_count` condition. The main data query (line 449) adds it separately. This causes `total_count` and `has_more` to reflect the pre-min_row_count population, misleading paginating clients.
**Fix**: Add the same `min_row_count` condition to the count query. Requires joining `row_counts` CTE in the count query as well, since row counts come from `sys.dm_db_partition_stats`.
**Repro**: `list_tables(min_row_count=1000000)` → returns 16 tables but `total_count=440, has_more=true`

### Issue #2: `list_tables` pagination field names are misleading and diverge from spec — FIXED
**Severity**: Low (confusing but functional) — **Fixed in `bugfix/tier2-issues` (commit f75c8e9)**
**Location**: `src/mcp_server/server.py` lines 314-321
**Description**: The response uses `total_tables` (= len of current page) and `total_count` (= total matching population). The naming is counterintuitive — `total_tables` sounds like the bigger number. The spec contract (`specs/001-db-schema-explorer/contracts/mcp_tools.md` line 307) defines `total_tables` (total population) and `filtered_count` (matched filters), which have different semantics and names than the implementation.
**Suggestion**: Rename to `returned_count` + `total_count`, or align with the spec's `total_tables` + `filtered_count`. Either way, pick names where the semantics are obvious.

### Issue #3: `infer_relationships` doesn't account for already-declared foreign keys
**Severity**: Medium (functional gap, noisy results on well-documented DBs)
**Location**: `src/inference/relationships.py` lines 211-214
**Description**: The inferencer iterates all non-PK columns and scores them against all target tables, but never checks whether a column already has a declared FK constraint. This means: (1) declared FKs are re-inferred as candidates with confidence scores, duplicating `get_table_schema` output, and (2) inference work is wasted on already-known relationships.
**Desired behavior**:
- Columns with existing declared FKs should be included in output but marked as `"declared_fk": true` (or similar) rather than scored — they're known relationships, not inferences.
- Inference scoring should only run on columns *without* declared FKs, where it adds value by finding undocumented links.
- A `dev_mode` (or `include_declared: bool = False`) parameter should allow bypassing this behavior so inference scoring can still be tested/validated against known FKs.
**Impact**: On databases with good FK coverage (like StemSoftClinic), results will be dominated by already-known relationships, reducing signal-to-noise for the actual novel inferences.

### Issue #4: `infer_relationships` times out on databases with >~100 objects, returning zero results
**Severity**: High (tool is non-functional on real-world databases)
**Location**: `src/inference/relationships.py` lines 38, 329-376
**Description**: Two compounding problems:
1. **Slow metadata path**: `_get_all_tables` (line 365) and `_get_columns` (line 329) use SQLAlchemy `inspector` reflection, which issues individual queries per table/schema. The rest of dbmcp uses optimized SQL Server DMV queries for this. On StemSoftClinic (440 objects), just enumerating tables + fetching the first column set exceeds the timeout.
2. **Non-configurable timeout**: The 10s default (`DEFAULT_INFERENCE_TIMEOUT_SECONDS`, line 38) is hardcoded and not exposed as a tool parameter. Even if the user knows inference will take longer, they can't adjust it.
**Result**: All 4 test tables (PerformedActs, BaseEntities, BaseEntities_Human, BaseEntityPerformedActs) returned `timed_out: true` with `tables_analyzed: 0, total_candidates_evaluated: 0`.
**Fix**: (1) Add `timeout_seconds` parameter to the MCP tool. (2) Replace `inspector` calls with DMV-based queries matching the `_list_tables_mssql` pattern, or reuse `MetadataService` methods. (3) Consider caching the all-tables column metadata across invocations on the same connection.

### Issue #5: `get_sample_data` crashes on tables with datetime columns — FIXED
**Severity**: High (tool is non-functional on most real tables without column filtering workaround) — **Fixed in `bugfix/tier1-issues` (commit 597bec1)**
**Location**: `src/db/query.py` lines 404-432 (`_truncate_value`) and `src/mcp_server/server.py` line 586 (`json.dumps`)
**Description**: `_truncate_value` handles `None`, `bytes`, and `str` but passes all other types through unchanged. Python `datetime` objects (from SQL Server DATETIME columns) are not JSON-serializable, so `json.dumps` in server.py raises `TypeError`. Also likely affects `date`, `time`, `Decimal`, and `timedelta` types.
**Repro**: `get_sample_data(table_name="PerformedActs")` → error. Workaround: pass `columns` param excluding datetime columns.
**Fix**: Add `datetime`/`date`/`time`/`Decimal` handling in `_truncate_value` (convert to `.isoformat()` / `str()`), or add a `default=` handler to `json.dumps` in the server response.

### Issue #6: `get_sample_data` tablesample returns 0 rows for small sample sizes on large tables — FIXED
**Severity**: Medium (silent failure — returns empty result instead of error) — **Fixed in `bugfix/tier2-issues` (commit 07a3136)**
**Location**: `src/db/query.py` lines 329-348 (`_build_tablesample_query`)
**Description**: SQL Server's `TABLESAMPLE (N ROWS)` samples at the 8KB data page level, not individual rows. The `N ROWS` hint is statistical — on a 60M-row table, `TABLESAMPLE (5 ROWS)` translates to such a tiny fraction that SQL Server often selects zero pages, returning 0 rows with no error or warning.
**Repro**: `get_sample_data(table_name="PerformedActs", sampling_method="tablesample", sample_size=5)` → 0 rows, `sample_size=100` → 100 rows.
**Fix options**: (1) Calculate a `PERCENT` value instead of using `ROWS` hint: `TABLESAMPLE (max(0.01, N/total_rows * 100) PERCENT)`. (2) Fall back to `top` when tablesample returns 0 rows and log a warning. (3) Document the limitation and recommend larger sample sizes for tablesample.

### Issue #7: `get_sample_data` modulo strategy is unimplemented (identical to top) — FIXED
**Severity**: Medium (misleading API — advertises 3 distinct strategies but only 2 are functional) — **Fixed in `bugfix/tier2-issues` (commit 7a05637)**
**Location**: `src/db/query.py` lines 350-377 (`_build_modulo_query`)
**Description**: The modulo strategy is documented as "deterministic sampling using modulo on row number (repeatable)" but the SQL Server implementation generates `SELECT TOP (N) ... ORDER BY (SELECT NULL)`, which is a no-op ordering hint. The optimizer returns rows in clustered index order, producing identical results to `top`. A real modulo implementation would need to: (1) identify a sequential/identity column, (2) calculate a modulo interval based on table row count and sample size, (3) filter with `WHERE id_col % interval = 0`.
**Repro**: Compare `get_sample_data(sampling_method="top", sample_size=5)` vs `get_sample_data(sampling_method="modulo", sample_size=5)` on PerformedActs — identical rows returned.
**Fix**: Either implement actual modulo sampling (requires row count + identity column detection), or remove/deprecate the option and document it as not yet available.

### Issue #8: `analyze_column` fails to detect BIT columns with `Is*` prefix as flags
**Severity**: Medium (incorrect inference on an obvious pattern)
**Location**: `src/inference/columns.py` (purpose detection logic)
**Description**: `IsArchived` is a BIT column with `Is*` naming prefix and only 1 distinct value — a textbook boolean flag. The tool infers `unknown` at 0.50 confidence instead of `flag`. The `Is*`/`Has*` prefix pattern and BIT data type should be strong signals for flag detection. Also, the tool has no `text`/`freetext` purpose category, so free-text columns like Comments always fall to `unknown`.
**Repro**: `analyze_column(column_name="IsArchived", table_name="PerformedActs")` → `inferred_purpose: "unknown", confidence: 0.5`

### Issue #9: `analyze_column` name pattern `*ID` overrides data signals; numeric stats never populated
**Severity**: High (inference quality is poor — tool's core value proposition is undermined)
**Location**: `src/inference/columns.py`
**Description**: Multiple compounding problems:
1. **`*ID` name dominance**: The `*ID` suffix name pattern always wins at 0.90 confidence, ignoring cardinality. StatusID (4 distinct values, textbook enum) → `id`. ConfidentialityCodeID (100% null, 0 distinct) → `id` at 0.90. The name heuristic should be one input, not the override.
2. **Numeric stats never populated**: Every column tested returns null for min/max/mean/median/std_dev, regardless of data type. The statistics queries appear to not execute or not populate results.
3. **`is_integer: true` on DECIMAL**: Result_Value (DECIMAL 28,10) reports `is_integer: true`. Type detection doesn't account for decimal precision.
4. **No confidence penalty for null data**: 100% null columns get same confidence as fully populated ones. Confidence should reflect data quality.
5. **`is_enum` contradicts `inferred_purpose`**: StatusID returns `is_enum: true` but `inferred_purpose: "id"` — the enum flag is computed but ignored by the purpose classifier.
**Repro**: `analyze_column(column_name="StatusID", table_name="BaseEntities")` → `id` at 0.90 with `is_enum: true`. `analyze_column(column_name="Result_Value", table_name="PerformedActs_QuantitativeObservation")` → `unknown` at 0.50, all stats null.

### Issue #10: `analyze_column` fails silently on nonexistent columns and small tables — FIXED
**Severity**: Medium (confusing UX — no way to distinguish invalid input from valid-but-unknown) — **Fixed in `bugfix/tier2-issues` (commit b28b246)**
**Location**: `src/inference/columns.py` and/or `src/mcp_server/server.py`
**Description**: Both nonexistent columns and small tables return `data_type: "unknown", total_rows: 0, distinct_count: 0, inferred_purpose: "unknown"`. No error is raised. A fake column (`TOTALLY_FAKE_COLUMN`) produces identical output to a real column on a 7-row table (`CVs_ProtocolDefinitionType.ElementID`). Nonexistent columns should return an explicit error. Small tables should still return valid metadata.
**Repro**: `analyze_column(column_name="TOTALLY_FAKE_COLUMN", table_name="PerformedActs")` → no error, `total_rows: 0`. `analyze_column(column_name="ElementID", table_name="CVs_ProtocolDefinitionType")` → same output, `total_rows: 0`.

### Issue #11: `export_documentation` crashes — type mismatch between FK collection and storage layer — FIXED
**Severity**: High (tool is completely non-functional) — **Fixed in `bugfix/tier1-issues` (commit cb4be90)**
**Location**: `src/mcp_server/server.py` lines 779-783, `src/cache/storage.py` line 178
**Description**: `server.py` line 782 calls `metadata_svc.get_foreign_keys()` which returns `list[dict]` (raw SQLAlchemy inspector output). The result is typed as `list[DeclaredFK]` (line 779) but never actually converted. When `storage.py` line 178 tries `fk.source_table_id`, it fails because dicts use `[]` access not `.` attribute access. This crashes on any database with tables (the FK loop runs for every table).
**Repro**: `export_documentation(connection_id="542f8ffefc15", include_sample_data=False, include_inferred_relationships=False)` → `"'dict' object has no attribute 'source_table_id'"`
**Fix**: Convert the raw FK dicts to `DeclaredFK` objects in `server.py` after calling `get_foreign_keys()`, mapping SQLAlchemy inspector dict keys (`constrained_columns`, `referred_table`, `referred_columns`, etc.) to `DeclaredFK` fields (`source_table_id`, `source_column`, `target_table_id`, `target_column`).

### Issue #12: `load_cached_docs` reports `status: "loaded"` on incomplete/corrupt cache
**Severity**: Low (misleading but not destructive)
**Location**: `src/cache/storage.py` (load path) and `src/mcp_server/server.py` (response building)
**Description**: When loading a partial cache (from a prior failed export), the tool returns `status: "loaded"` with schema-level data but `entity_counts.tables: 0`, `declared_fks: 0`, `cache_age_days: null`, `schema_hash: null`. The consumer has no indication the cache is incomplete. Should return `status: "partial"` or `status: "incomplete"` with a warning, or validate that entity counts are consistent with schema counts before claiming success.
**Repro**: `load_cached_docs(connection_id="542f8ffefc15")` after a failed `export_documentation` → `status: "loaded"` with contradictory data (schemas show 440 objects but `tables: 0`).

### Issue #13: `export_documentation` silently truncates tables at 100 per schema — FIXED
**Severity**: Medium (data loss — export is incomplete without indication) — **Fixed in `bugfix/tier2-issues` (commit 72e97ca)**
**Location**: `src/mcp_server/server.py` lines 763-766
**Description**: `export_documentation` calls `metadata_svc.list_tables(schema_name=...)` without passing a `limit` parameter. The `list_tables` method in `src/db/metadata.py` defaults to `limit=100`. Since pagination is never used, only the first 100 tables per schema are exported. For StemSoftClinic: dbo has 439 objects but only 100 are fetched; reporting has 1, so 101 total. The storage layer (`cache/storage.py`) correctly writes whatever it receives — the truncation happens upstream in the collection loop. Schema-level counts in the cache (dbo: 297+142) come from `list_schemas` which queries correctly, creating a visible discrepancy with `entity_counts.tables: 101`.
**Repro**: `export_documentation(connection_id="542f8ffefc15")` → reports 101 tables. `load_cached_docs` → `entity_counts.tables: 101` but schema counts sum to 440.
**Fix**: Pass `limit=0` or a sufficiently large limit in the `list_tables` call within `export_documentation`, or loop with pagination until `has_more=false`.

### Issue #14: `export_documentation` custom output_dir — response reports wrong file paths + absolute paths rejected — FIXED
**Severity**: Low (files are written correctly; only the response metadata is wrong) — **Fixed in `bugfix/tier2-issues` (commit e33f666)**
**Location**: `src/mcp_server/server.py` line 855, `src/cache/storage.py` line 750
**Description**: Two sub-issues with custom `output_dir`:
1. **Wrong `files_created` in response**: `server.py:855` calls `storage.get_cache_metadata(connection_id)` which always reads from the default cache location (`docs/{connection_id}/.cache_metadata.json`), not the custom output directory. When exporting to `exports/custom_test`, the response returns stale `files_created` paths from the previous default-location export. The custom export does write a correct `.cache_metadata.json` in the custom dir — it's just never read back.
2. **Absolute paths rejected**: `output_dir="/tmp/dbmcp_test_export"` fails with `"'/tmp/.../overview.md' is not in the subpath of '.'"` because `relative_to(self.base_dir.parent)` on line 152 of `storage.py` can't compute a relative path outside the project root. This is arguably a reasonable security restriction but should return a clearer error message rather than an internal ValueError.
**Repro**: `export_documentation(connection_id="542f8ffefc15", output_dir="exports/custom_test")` → files written correctly to `exports/custom_test/` but `files_created` in response shows `docs/542f8ffefc15/...` paths.
**Fix**: (1) Pass the custom `output_dir` to `get_cache_metadata` or read metadata from the `cache` return value. (2) For absolute paths, either support them or validate early with a clear error.

### Issue #15: `check_drift` auto-refresh doesn't preserve prior export settings — FIXED
**Severity**: Low (functional but surprising behavior) — **Fixed in `bugfix/tier2-issues` (commit fc8f639)**
**Location**: `src/mcp_server/server.py` lines 999-1002
**Description**: When `check_drift(auto_refresh=True)` triggers a re-export, it hardcodes `include_inferred_relationships=True` and omits `include_sample_data` (defaults to `False`). Prior export settings stored in `.cache_metadata.json` (which records `include_sample_data` and `include_inferred_relationships`) are not read or passed through. This means an auto-refresh can silently change the cache contents — e.g., a cache originally exported with `include_sample_data=True` loses its sample data after drift refresh.
**Repro**: Export with `include_sample_data=True` (220KB). Tamper cache hash. Run `check_drift(auto_refresh=True)` → re-export uses defaults, sample data lost, size changes.
**Fix**: Read `include_sample_data` and `include_inferred_relationships` from the existing `.cache_metadata.json` before re-exporting, and pass them to `export_documentation`.

---

## Issue Priority

### Tier 1: High impact, easy fix — ALL FIXED
1. ~~**#5** — sample_data datetime crash~~ — fixed (597bec1), verified against live DB
2. ~~**#1** — list_tables count ignores min_row_count~~ — fixed (b7207e6), verified against live DB
3. ~~**#11** — export FK type mismatch crash~~ — fixed (cb4be90), verified against live DB (140 FKs exported)

### Tier 2: Medium impact, easy fix — ALL FIXED
4. ~~**#13** — export truncates at 100 tables/schema~~ — fixed (72e97ca), verified: 440 tables exported (was 101)
5. ~~**#10** — analyze_column silent failure on bad input~~ — fixed (b28b246), verified: fake column returns error, small table returns data
6. ~~**#6** — tablesample 0 rows for small N~~ — fixed (07a3136), verified: falls back to top, returns 5 rows (was 0)
7. ~~**#2** — list_tables field naming vs spec~~ — fixed (f75c8e9), verified: `returned_count` replaces `total_tables`
8. ~~**#7** — modulo unimplemented~~ — fixed (7a05637), verified: evenly-spaced IDs distinct from top's sequential IDs
9. ~~**#14** — export custom output_dir wrong paths~~ — fixed (e33f666), validation pending
10. ~~**#15** — auto-refresh doesn't preserve settings~~ — fixed (fc8f639), validation pending

### Tier 3: Deprioritize — refactor planned
11. **#9** — analyze_column inference quality (→ LLM-assisted)
12. **#8** — analyze_column flag detection (→ LLM-assisted)
13. **#4** — infer_relationships timeout (→ LLM-assisted)
14. **#3** — infer_relationships declared FK handling (→ LLM-assisted)
15. **#12** — load_cached_docs false success (→ export redesign)

---

## Session Log

- **2026-02-26:** Connected to SVWTSTEM04/StemSoftClinic via Windows auth. Connection successful (ID: 542f8ffefc15, 2 schemas found).
- **2026-02-26:** Tested all 11 tools, found 12 issues (#1–#12). Prioritized into 3 tiers.
- **2026-02-26:** Fixed Tier 1 issues (#5, #1, #11) on `bugfix/tier1-issues` branch, merged to `integration-test`. All three verified against live DB after MCP server restart.
- **2026-02-26:** Tested `load_cached_docs` after successful export — PASS. Discovered Issue #13: `export_documentation` silently truncates at 100 tables/schema due to default `limit=100` in `list_tables`. Root cause in `server.py` lines 763-766 (no limit/pagination passed). Added to Tier 2.
- **2026-02-26:** Tested export with sample data — PASS (220KB, sample sections present, correctly toggleable). Tested custom output_dir — BUG: files written correctly but response `files_created` returns stale paths from default location (`server.py:855` reads metadata from wrong dir). Absolute paths rejected with unclear internal error. Filed as Issue #14.
- **2026-02-26:** Tested all check_drift scenarios. No drift — PASS. Simulated drift (tampered cache hash) — PASS, correctly detected. Auto-refresh — PASS, re-exported and restored hash. Minor note: auto-refresh hardcodes `include_inferred_relationships=True` and doesn't preserve prior export settings (`server.py:999-1001`).
- **2026-02-26:** Fixed Tier 2 issues on `bugfix/tier2-issues` branch (7 issues, 8 commits). Validating against live DB:
  - **#13 VERIFIED**: `export_documentation` now exports 440 tables (was 101). `load_cached_docs` shows `entity_counts.tables: 440` matching schema totals. 630KB total, 402 declared FKs.
  - **#10 VERIFIED**: `TOTALLY_FAKE_COLUMN` returns `"error": "Column 'TOTALLY_FAKE_COLUMN' does not exist in [dbo].[PerformedActs]"`. Real column on small table (`CVs_ProtocolDefinitionType.CodedValueID`, 7 rows) returns `total_rows: 7, distinct_count: 7`. Note: original issue referenced `ElementID` which was never a real column on that table — the fix correctly catches both cases.
  - **#6 VERIFIED**: `tablesample` with `sample_size=5` on PerformedActs (20M rows) now returns 5 rows via automatic fallback to `top`. Response shows `sampling_method: "top"` indicating fallback occurred.
  - **#2 VERIFIED**: `list_tables` response now uses `returned_count: 3` (was `total_tables: 3`). `total_count: 440` unchanged.
  - **#7 VERIFIED**: `modulo` with `sample_size=5` on PerformedActs returns evenly-spaced IDs (494M, 781M, 803M, 814M, 823M) vs `top`'s sequential IDs (822608122–822608166). Response shows `sampling_method: "modulo"`.
