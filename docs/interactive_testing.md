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
| BUG | Min row count filter | Filtering works, but total_count ignores min_row_count (see Issue #1). >=1M returns 16 tables correctly, but total_count=440 and has_more=true are wrong |
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
| BUG | All columns (default) | Crashes: "Object of type datetime is not JSON serializable" (see Issue #5). Any table with DATETIME columns fails when columns param is omitted |
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
| BUG | Basic export (no samples, no inferred) | Crashes: "'dict' object has no attribute 'source_table_id'" (see Issue #11). FK collection returns raw dicts, storage layer expects DeclaredFK model objects |
| BLOCKED | Export with sample data | Blocked by Issue #11 |
| BLOCKED | Custom output directory | Blocked by Issue #11 |
| BLOCKED | Include/exclude inferred relationships | Blocked by Issue #11 |

### 10. load_cached_docs
Load previously exported documentation cache. Returns entity counts and cache age.

| Status | Test | Notes |
|--------|------|-------|
| BLOCKED | Load after export | Blocked by Issue #11 (export crashes) |
| BUG | Load with incomplete/no cache | Returns `status: "loaded"` on a partial/corrupt cache from a prior failed run. Schema counts present (dbo: 297+142) but `entity_counts.tables: 0`, `declared_fks: 0`, `cache_age_days: null`. Should flag incomplete cache instead of claiming success (see Issue #12) |

### 11. check_drift
Compare cached docs hash against current database schema. Detects added/removed/modified tables.

| Status | Test | Notes |
|--------|------|-------|
| BLOCKED | No drift (cache is current) | Blocked by Issue #11 (no valid cache to compare against) |
| PASS | Drift detection with missing cache | Returns `drift_detected: true`, `summary: "Cache metadata missing"`. Correctly identifies incomplete cache. Current hash computed successfully |
| BLOCKED | Auto-refresh on drift | Blocked by Issue #11 (auto-refresh calls export_documentation internally) |

---

## Issues Found

### Issue #1: `list_tables` total_count ignores min_row_count filter
**Severity**: Medium (incorrect pagination metadata)
**Location**: `src/db/metadata.py` lines 414-419 (`_list_tables_mssql`)
**Description**: The count query (`count_query`) builds its WHERE clause from `where_sql`, which includes schema_name, name_pattern, and object_type filters — but does NOT include the `min_row_count >= :min_row_count` condition. The main data query (line 449) adds it separately. This causes `total_count` and `has_more` to reflect the pre-min_row_count population, misleading paginating clients.
**Fix**: Add the same `min_row_count` condition to the count query. Requires joining `row_counts` CTE in the count query as well, since row counts come from `sys.dm_db_partition_stats`.
**Repro**: `list_tables(min_row_count=1000000)` → returns 16 tables but `total_count=440, has_more=true`

### Issue #2: `list_tables` pagination field names are misleading and diverge from spec
**Severity**: Low (confusing but functional)
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

### Issue #5: `get_sample_data` crashes on tables with datetime columns
**Severity**: High (tool is non-functional on most real tables without column filtering workaround)
**Location**: `src/db/query.py` lines 404-432 (`_truncate_value`) and `src/mcp_server/server.py` line 586 (`json.dumps`)
**Description**: `_truncate_value` handles `None`, `bytes`, and `str` but passes all other types through unchanged. Python `datetime` objects (from SQL Server DATETIME columns) are not JSON-serializable, so `json.dumps` in server.py raises `TypeError`. Also likely affects `date`, `time`, `Decimal`, and `timedelta` types.
**Repro**: `get_sample_data(table_name="PerformedActs")` → error. Workaround: pass `columns` param excluding datetime columns.
**Fix**: Add `datetime`/`date`/`time`/`Decimal` handling in `_truncate_value` (convert to `.isoformat()` / `str()`), or add a `default=` handler to `json.dumps` in the server response.

### Issue #6: `get_sample_data` tablesample returns 0 rows for small sample sizes on large tables
**Severity**: Medium (silent failure — returns empty result instead of error)
**Location**: `src/db/query.py` lines 329-348 (`_build_tablesample_query`)
**Description**: SQL Server's `TABLESAMPLE (N ROWS)` samples at the 8KB data page level, not individual rows. The `N ROWS` hint is statistical — on a 60M-row table, `TABLESAMPLE (5 ROWS)` translates to such a tiny fraction that SQL Server often selects zero pages, returning 0 rows with no error or warning.
**Repro**: `get_sample_data(table_name="PerformedActs", sampling_method="tablesample", sample_size=5)` → 0 rows, `sample_size=100` → 100 rows.
**Fix options**: (1) Calculate a `PERCENT` value instead of using `ROWS` hint: `TABLESAMPLE (max(0.01, N/total_rows * 100) PERCENT)`. (2) Fall back to `top` when tablesample returns 0 rows and log a warning. (3) Document the limitation and recommend larger sample sizes for tablesample.

### Issue #7: `get_sample_data` modulo strategy is unimplemented (identical to top)
**Severity**: Medium (misleading API — advertises 3 distinct strategies but only 2 are functional)
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

### Issue #10: `analyze_column` fails silently on nonexistent columns and small tables
**Severity**: Medium (confusing UX — no way to distinguish invalid input from valid-but-unknown)
**Location**: `src/inference/columns.py` and/or `src/mcp_server/server.py`
**Description**: Both nonexistent columns and small tables return `data_type: "unknown", total_rows: 0, distinct_count: 0, inferred_purpose: "unknown"`. No error is raised. A fake column (`TOTALLY_FAKE_COLUMN`) produces identical output to a real column on a 7-row table (`CVs_ProtocolDefinitionType.ElementID`). Nonexistent columns should return an explicit error. Small tables should still return valid metadata.
**Repro**: `analyze_column(column_name="TOTALLY_FAKE_COLUMN", table_name="PerformedActs")` → no error, `total_rows: 0`. `analyze_column(column_name="ElementID", table_name="CVs_ProtocolDefinitionType")` → same output, `total_rows: 0`.

### Issue #11: `export_documentation` crashes — type mismatch between FK collection and storage layer
**Severity**: High (tool is completely non-functional)
**Location**: `src/mcp_server/server.py` lines 779-783, `src/cache/storage.py` line 178
**Description**: `server.py` line 782 calls `metadata_svc.get_foreign_keys()` which returns `list[dict]` (raw SQLAlchemy inspector output). The result is typed as `list[DeclaredFK]` (line 779) but never actually converted. When `storage.py` line 178 tries `fk.source_table_id`, it fails because dicts use `[]` access not `.` attribute access. This crashes on any database with tables (the FK loop runs for every table).
**Repro**: `export_documentation(connection_id="542f8ffefc15", include_sample_data=False, include_inferred_relationships=False)` → `"'dict' object has no attribute 'source_table_id'"`
**Fix**: Convert the raw FK dicts to `DeclaredFK` objects in `server.py` after calling `get_foreign_keys()`, mapping SQLAlchemy inspector dict keys (`constrained_columns`, `referred_table`, `referred_columns`, etc.) to `DeclaredFK` fields (`source_table_id`, `source_column`, `target_table_id`, `target_column`).

### Issue #12: `load_cached_docs` reports `status: "loaded"` on incomplete/corrupt cache
**Severity**: Low (misleading but not destructive)
**Location**: `src/cache/storage.py` (load path) and `src/mcp_server/server.py` (response building)
**Description**: When loading a partial cache (from a prior failed export), the tool returns `status: "loaded"` with schema-level data but `entity_counts.tables: 0`, `declared_fks: 0`, `cache_age_days: null`, `schema_hash: null`. The consumer has no indication the cache is incomplete. Should return `status: "partial"` or `status: "incomplete"` with a warning, or validate that entity counts are consistent with schema counts before claiming success.
**Repro**: `load_cached_docs(connection_id="542f8ffefc15")` after a failed `export_documentation` → `status: "loaded"` with contradictory data (schemas show 440 objects but `tables: 0`).

---

## Issue Priority

### Tier 1: High impact, easy fix
1. **#5** — sample_data datetime crash (~10 lines)
2. **#1** — list_tables count ignores min_row_count (~15 lines)
3. **#11** — export FK type mismatch crash (~20 lines, but deprioritize if export refactored)

### Tier 2: Medium impact, easy fix
4. **#10** — analyze_column silent failure on bad input
5. **#6** — tablesample 0 rows for small N
6. **#2** — list_tables field naming vs spec
7. **#7** — modulo unimplemented (remove or implement)

### Tier 3: Deprioritize — refactor planned
8. **#9** — analyze_column inference quality (→ LLM-assisted)
9. **#8** — analyze_column flag detection (→ LLM-assisted)
10. **#4** — infer_relationships timeout (→ LLM-assisted)
11. **#3** — infer_relationships declared FK handling (→ LLM-assisted)
12. **#12** — load_cached_docs false success (→ export redesign)

---

## Session Log

- **2026-02-26:** Connected to SVWTSTEM04/StemSoftClinic via Windows auth. Connection successful (ID: 542f8ffefc15, 2 schemas found).
