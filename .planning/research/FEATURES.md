# Feature Landscape

**Domain:** Multi-dialect database exploration MCP tool (extending SQL Server-only to Databricks + generic SQLAlchemy)
**Researched:** 2026-04-13

## Table Stakes

Features users expect from any multi-dialect database exploration tool. Missing = product feels broken or unusable with the new dialect.

| Feature | Why Expected | Complexity | Depends On | Notes |
|---------|--------------|------------|------------|-------|
| Schema listing across dialects | Core navigation; users need to browse structure first | Low | DialectStrategy protocol | Databricks: `information_schema.SCHEMATA` or Inspector. MSSQL: existing DMV path. Generic: Inspector. |
| Table listing with row counts | Core navigation; existing tool already does this for MSSQL | Med | Schema listing, dialect-aware row count | Databricks row counts need `DESCRIBE TABLE EXTENDED` or `ANALYZE TABLE`; no DMV equivalent. Generic: `COUNT(*)` fallback (already implemented). |
| Column metadata retrieval | Users expect `get_table_schema` to work on any connected database | Low | DialectStrategy protocol | SQLAlchemy Inspector handles most of this. Databricks Inspector uses `DESCRIBE TABLE EXTENDED` under the hood. `information_schema.COLUMNS` available in Unity Catalog (31 fields including COMMENT, FULL_DATA_TYPE, PARTITION_ORDINAL_POSITION). |
| Query execution with validation | Core value prop of dbmcp; must work on non-MSSQL dialects | Med | sqlglot dialect mapping | sqlglot already in stack. Must pass correct dialect for transpilation/validation. Databricks dialect = `databricks` in sqlglot. |
| Three-level namespace support (catalog.schema.table) | Databricks uses catalog.schema.table; users will expect it | Med | Config model, metadata layer | MSSQL is database.schema.table (similar structure but different semantics). Must map Databricks catalogs to the connection-level concept. |
| Identifier validation per dialect | Security feature; must not regress when adding dialects | Med | Metadata-based validation, dialect-aware quoting | MSSQL uses `[brackets]`, Databricks uses `backticks`. SQLAlchemy handles quoting but raw SQL in analysis tools needs dialect-aware escaping. |
| TOML config for Databricks connections | Users configure MSSQL via TOML today; Databricks must work the same way | Low | Config model | Databricks needs: host, http_path, catalog, schema, auth (token or OAuth). Discriminated by `dialect` field. |
| Sample data retrieval | `get_sample_data` is a core tool; must work everywhere | Low | Dialect-aware LIMIT syntax | MSSQL uses `TOP N`, Databricks/generic use `LIMIT N`. sqlglot can handle transpilation, or use dialect-specific SQL. |

## Differentiators

Features that set this tool apart from generic database connectors. Not expected but valuable for LLM agents.

| Feature | Value Proposition | Complexity | Depends On | Notes |
|---------|-------------------|------------|------------|-------|
| Databricks column statistics via ANALYZE TABLE | Native stats (min, max, nulls, distinct, avg_len, histogram) are precomputed; much faster than running aggregate queries | Med | Databricks dialect, DESCRIBE EXTENDED parsing | `ANALYZE TABLE ... FOR ALL COLUMNS` computes stats. `DESCRIBE EXTENDED table column` retrieves them. Predictive Optimization auto-runs this on Unity Catalog managed tables. Can fall back to Tier 2 aggregate queries if stats unavailable. |
| Databricks table metadata from DESCRIBE EXTENDED | Rich metadata: owner, creation time, last access, storage format (Delta/Parquet), table type (MANAGED/EXTERNAL), location | Low | Databricks dialect | JSON output available in DBR 16.2+ (`DESCRIBE EXTENDED ... AS JSON`). Valuable for LLM context about table provenance. |
| PK/FK discovery with informational constraint awareness | Databricks PK/FK constraints exist but are NOT enforced. Tool should surface this distinction clearly. | Med | Existing PK/FK analysis tools, dialect-aware constraint querying | `information_schema.TABLE_CONSTRAINTS` has `ENFORCED` column (always 'NO' for PK/FK in Databricks). Must communicate "informational only" to LLM consumers. Structural PK discovery (uniqueness checks) remains valuable as a complement. |
| Partition-aware metadata | Databricks tables are often partitioned; surfacing partition columns helps LLM write efficient queries | Low | DESCRIBE EXTENDED or information_schema.COLUMNS.PARTITION_ORDINAL_POSITION | Partition awareness is a Databricks-specific optimization hint that generic tools miss. |
| Unity Catalog tag metadata | Databricks Unity Catalog supports tags on catalogs, schemas, tables, and columns via `*_TAGS` information_schema views | Low | Databricks dialect | Tags carry business context (PII classification, data domain, ownership) that helps LLMs understand data semantics. |
| Dialect-agnostic analysis fallbacks | When dialect-specific stats aren't available, fall back gracefully to standard SQL aggregates | Med | Tier 2/3 query strategy | Three-tier approach: Tier 1 (Inspector), Tier 2 (standard SQL via sqlglot), Tier 3 (dialect-specific optimizations). This is the architectural differentiator. |
| Cross-dialect type normalization | Consistent type representation regardless of backend | Med | Type registry, dialect mapping | Databricks types (STRING, LONG, DOUBLE, TIMESTAMP_NTZ) differ from MSSQL (nvarchar, bigint, float, datetime2). Normalizing for LLM consumers reduces confusion. |

## Anti-Features

Features to explicitly NOT build. These seem useful but are traps.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Write operations for any dialect | Violates core security model. Read-only is the entire value proposition. | Keep strict read-only validation. Even Databricks `ANALYZE TABLE` is a write-ish operation (writes stats); consider carefully whether to auto-trigger it or only read existing stats. |
| Auto-triggering ANALYZE TABLE | Runs compute on user's cluster, costs money, may be slow on large tables. Side effect that violates read-only principle. | Read existing stats from DESCRIBE EXTENDED. If stats are stale/missing, report that and let the user decide. |
| Full Unity Catalog cross-catalog queries | Querying across catalogs adds massive complexity to identifier validation and metadata caching. | Scope to one catalog per connection (the one specified in the connection string). Users can create multiple connections for multiple catalogs. |
| Databricks-specific SQL in generic tools | Leaking Databricks SQL syntax into the generic path creates maintenance burden and breaks other dialects. | Keep dialect-specific SQL isolated in DialectStrategy implementations. Generic path uses only SQLAlchemy Inspector + standard SQL. |
| Index metadata for Databricks | Databricks does not have traditional B-tree indexes. Delta tables use data skipping, Z-ordering, and liquid clustering instead. | For `get_table_schema`, omit index section for Databricks or replace with "optimization hints" (partition columns, clustering info). Do not pretend indexes exist. |
| Enforced constraint semantics for Databricks PK/FK | Treating Databricks PK/FK as enforced would mislead LLM agents into wrong assumptions about data integrity. | Always surface the `informational_only` flag. Structural PK discovery (actual uniqueness checks) is more reliable for Databricks. |
| Histogram data from ANALYZE TABLE | Column histograms are internal optimizer artifacts, not meaningful for LLM consumers. Complex to parse and serialize. | Surface min/max/nulls/distinct from ANALYZE TABLE stats. Skip histogram serialization. |

## Feature Dependencies

```
DialectStrategy protocol
  -> MssqlDialect (preserves existing behavior)
  -> DatabricksDialect (new)
  -> GenericDialect (new fallback)

Discriminated TOML config
  -> Databricks connection params (host, http_path, catalog, token/OAuth)
  -> connect_database tool simplification

Three-level namespace (catalog.schema.table)
  -> Schema listing for Databricks
  -> Table listing for Databricks
  -> Identifier validation for Databricks

SQLAlchemy Inspector (Tier 1)
  -> get_columns, get_pk_constraint, get_foreign_keys (all dialects)
  -> Databricks Inspector uses DESCRIBE TABLE EXTENDED internally

Standard SQL analysis (Tier 2)
  -> Column stats (COUNT, COUNT DISTINCT, MIN, MAX, AVG, STDEV)
  -> PK discovery (uniqueness checks)
  -> FK candidate search (value overlap)
  -> sqlglot transpilation for dialect differences

Dialect-specific optimizations (Tier 3)
  -> MSSQL: DMV queries (sys.dm_db_partition_stats for row counts)
  -> Databricks: DESCRIBE EXTENDED for precomputed stats
  -> Databricks: information_schema for constraint metadata
  -> Databricks: Partition/clustering metadata
```

## MVP Recommendation

Prioritize (must-have for v2.0):

1. **DialectStrategy protocol + MSSQL migration** - Refactor existing code behind strategy interface. Zero behavior change for MSSQL users. This gates everything else.
2. **Discriminated TOML config + connect_database simplification** - Users need to connect before anything else works. Databricks connection params are different enough to require typed config.
3. **Databricks schema/table/column listing via Inspector** - The databricks-sqlalchemy dialect implements reflection via DESCRIBE TABLE EXTENDED internally. Lean on Inspector for Tier 1.
4. **Query execution with dialect-aware validation** - Pass sqlglot dialect explicitly. Databricks query validation must work correctly.
5. **GenericDialect fallback** - Inspector-only path for PostgreSQL, MySQL, SQLite, etc. No custom SQL. This is cheap if the strategy pattern is right.

Defer to post-MVP:

- **Databricks ANALYZE TABLE stats reading**: Requires parsing DESCRIBE EXTENDED column-level output. Valuable but not blocking. Fall back to Tier 2 aggregate queries initially.
- **Unity Catalog tags**: Nice-to-have enrichment, not core functionality.
- **Partition-aware metadata**: Low effort but not needed for basic functionality.
- **Cross-dialect type normalization**: Current type registry handles MSSQL. Databricks types need mapping but SQLAlchemy already normalizes somewhat.

## Databricks-Specific Capabilities Reference

### Metadata Sources Available

| Source | What It Provides | Access Method |
|--------|-----------------|---------------|
| `information_schema.TABLES` | table_type (MANAGED/EXTERNAL/VIEW), owner, created, last_altered, data_source_format, storage_path | SQL query |
| `information_schema.COLUMNS` | 31 fields including FULL_DATA_TYPE, COMMENT, PARTITION_ORDINAL_POSITION, IS_NULLABLE | SQL query |
| `information_schema.TABLE_CONSTRAINTS` | PK/FK/CHECK constraints with ENFORCED='NO' for PK/FK | SQL query |
| `information_schema.KEY_COLUMN_USAGE` | Which columns participate in PK/FK constraints | SQL query |
| `information_schema.REFERENTIAL_CONSTRAINTS` | FK relationship details (referenced table/columns) | SQL query |
| `DESCRIBE TABLE EXTENDED` | Column schema + table properties (owner, location, format, stats) | SQL command |
| `DESCRIBE EXTENDED table column` | Column-level stats from ANALYZE TABLE (min, max, nulls, distinct, avg_len) | SQL command |
| `SHOW COLUMNS` | Column names only (minimal utility vs. DESCRIBE/information_schema) | SQL command |
| SQLAlchemy Inspector | get_columns, get_pk_constraint, get_table_names (uses DESCRIBE internally) | Python API |

### Column Statistics from ANALYZE TABLE

When `ANALYZE TABLE ... FOR ALL COLUMNS` has been run (or Predictive Optimization has auto-run it), `DESCRIBE EXTENDED table column` returns:

| Statistic | Description | Equivalent to Current MSSQL Approach |
|-----------|-------------|--------------------------------------|
| `min` | Minimum value | Same as current MIN() aggregate |
| `max` | Maximum value | Same as current MAX() aggregate |
| `num_nulls` | Null count | Same as current SUM(CASE WHEN ... IS NULL) |
| `distinct_count` | Approximate distinct count | Same as current COUNT(DISTINCT) |
| `avg_col_len` | Average column length | Same as current AVG(LEN()) for strings |
| `max_col_len` | Maximum column length | Same as current MAX(LEN()) for strings |
| `histogram` | Internal optimizer histogram | No current equivalent; skip for LLM consumers |

### Namespace Mapping

| Concept | MSSQL | Databricks | Generic SQLAlchemy |
|---------|-------|------------|-------------------|
| Top level | Server/Database (connection-scoped) | Catalog (Unity Catalog) | Database (connection-scoped) |
| Mid level | Schema (dbo, etc.) | Schema | Schema (public, etc.) |
| Object level | Table/View | Table/View | Table/View |
| Qualified name | `[schema].[table]` | `` `catalog`.`schema`.`table` `` | `"schema"."table"` |
| Quote character | `[]` | `` ` `` | `""` (standard SQL) |

### Constraint Behavior

| Aspect | MSSQL | Databricks |
|--------|-------|------------|
| PK enforced | Yes | No (informational only) |
| FK enforced | Yes | No (informational only) |
| CHECK enforced | Yes | Yes |
| NOT NULL enforced | Yes | Yes |
| Unique enforced | Yes | No (informational, tied to PK) |
| PK/FK in information_schema | Yes | Yes (TABLE_CONSTRAINTS, KEY_COLUMN_USAGE) |
| PK/FK aid query optimizer | N/A (enforced) | Yes (optimizer uses them for join reordering) |

## Complexity Assessment

| Feature Area | Estimated Complexity | Risk Level | Rationale |
|-------------|---------------------|------------|-----------|
| DialectStrategy protocol | Med | Low | Well-understood pattern; existing code already has is_mssql branching |
| MSSQL migration to strategy | Med | Low | Extracting existing code into strategy impl; behavior must not change |
| Databricks connection/config | Low | Low | Standard TOML config pattern; databricks-sql-connector is mature (v4.2.5) |
| Inspector-based metadata | Low | Med | databricks-sqlalchemy inspector support is not fully documented; may hit gaps |
| Query validation per dialect | Med | Med | sqlglot dialect mapping is well-supported but edge cases exist |
| Analysis tools adaptation | High | Med | Column stats, PK discovery, FK search all contain MSSQL-specific SQL that needs dialect alternatives |
| Identifier validation | Med | Med | Different quoting, different system schemas, different metadata sources |
| GenericDialect fallback | Low | Low | Inspector-only, no custom SQL; simplest path |

## Sources

- Databricks INFORMATION_SCHEMA docs: https://docs.databricks.com/en/sql/language-manual/sql-ref-information-schema.html (HIGH confidence)
- Databricks COLUMNS schema: https://docs.databricks.com/en/sql/language-manual/information-schema/columns.html (HIGH confidence)
- Databricks TABLE_CONSTRAINTS: https://docs.databricks.com/en/sql/language-manual/information-schema/table_constraints.html (HIGH confidence)
- Databricks TABLES schema: https://docs.databricks.com/en/sql/language-manual/information-schema/tables.html (HIGH confidence)
- Databricks DESCRIBE TABLE EXTENDED: https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-describe-table.html (HIGH confidence)
- Databricks ANALYZE TABLE: https://docs.databricks.com/en/sql/language-manual/sql-ref-syntax-aux-analyze-table.html (HIGH confidence)
- Databricks constraints: https://docs.databricks.com/en/tables/constraints.html (HIGH confidence)
- databricks-sqlalchemy on DeepWiki: https://deepwiki.com/databricks/databricks-sqlalchemy (MEDIUM confidence - reflection support inferred, not fully documented)
- databricks-sql-connector v4.2.5: https://github.com/databricks/databricks-sql-python (HIGH confidence)
- Existing dbmcp codebase: column_stats.py, pk_discovery.py, fk_candidates.py, metadata.py (HIGH confidence - direct code review)
