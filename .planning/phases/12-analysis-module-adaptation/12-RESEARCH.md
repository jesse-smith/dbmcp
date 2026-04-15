# Phase 12: Analysis Module Adaptation - Research

**Researched:** 2026-04-15
**Domain:** Cross-dialect analysis tools (column stats, PK/FK discovery) with sqlglot transpilation
**Confidence:** HIGH

## Summary

Phase 12 adapts three MSSQL-specific analysis modules (column_stats.py, pk_discovery.py, fk_candidates.py) to work across MSSQL, Databricks, and generic dialects. The core strategy is: (1) replace hardcoded MSSQL type string sets with SQLAlchemy isinstance() type classification, (2) write base queries in standard SQL and transpile via sqlglot to target dialects, (3) replace INFORMATION_SCHEMA metadata queries with Inspector calls where possible, (4) add a Databricks Tier 3 fast path using DESCRIBE EXTENDED per-column stats, and (5) gate index-dependent features on dialect.supports_indexes.

Empirical validation of sqlglot transpilation confirms the approach is viable with specific caveats. The critical finding is that DATEDIFF is dialect-specific and cannot be written in "standard SQL" -- it must be written in TSQL form and transpiled. MONEY/SMALLMONEY types do NOT inherit from SQLAlchemy's Numeric, requiring explicit handling in the type classifier.

**Primary recommendation:** Write base queries using TSQL syntax (matching existing code), transpile to target dialect via `sqlglot.transpile(sql, read='tsql', write=dialect.sqlglot_dialect)`. Handle the three genuinely non-transpilable patterns (CAST AS TIME, STRING_SPLIT, sys.indexes) with small dialect branches.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- **D-01:** Hybrid approach following three-tier query strategy: Tier 1 (Inspector) for constraint/index metadata discovery, Tier 2 (sqlglot.transpile()) for standard SQL aggregate queries, Tier 3 (dialect-specific methods) only for Databricks precomputed stats.
- **D-02:** Analysis logic stays in the analysis module (column_stats.py, pk_discovery.py, fk_candidates.py). DialectStrategy protocol is NOT extended with analysis query methods.
- **D-03:** sqlglot.transpile() handles cross-dialect syntax: SELECT TOP N -> LIMIT N, DATEDIFF/LEN/CAST function mapping, identifier quoting. Base queries written in standard SQL, transpiled to target dialect at runtime.
- **D-04:** Small hand-coded dialect branches (~2-3) for system-table queries that genuinely don't transpile (sys.indexes DMV for MSSQL, Inspector fallback for others). Isolated to metadata helper methods.
- **D-05:** Replace hardcoded MSSQL type string sets (NUMERIC_TYPES, DATETIME_TYPES, STRING_TYPES) with SQLAlchemy isinstance() checks against TypeEngine hierarchy.
- **D-06:** Type categories via isinstance: numeric = `(types.Integer, types.Numeric)`, datetime = `(types.DateTime, types.Date)`, string = `(types.String)`, other = everything else. SQLAlchemy handles dialect-specific mappings automatically (e.g., MSSQL MONEY -> Numeric, Databricks STRING -> String).
- **D-07:** ColumnStatsCollector receives Inspector type objects instead of raw type strings. The _get_type_category() method signature changes from `(data_type: str)` to accepting TypeEngine instances.
- **D-08:** DESCRIBE EXTENDED fast path: probe the first column with `DESCRIBE EXTENDED catalog.schema.table column_name`. If precomputed stats are present (min, max, num_nulls, distinct_count), use fast path for all remaining columns. If stats absent, fall back to Tier 2 batch SQL aggregates for all columns.
- **D-09:** DESCRIBE EXTENDED returns per-column stats as key-value pairs (col_name=stat name, data_type=stat value). Stats only present when ANALYZE TABLE has been run or Predictive Optimization auto-ran it. No batch support -- one query per column.
- **D-10:** Databricks DESCRIBE EXTENDED column stats parsing is dbmcp-custom work -- databricks-sqlalchemy does not expose this through Inspector.
- **D-11:** ANLYS-05 (partition metadata) is already complete from Phase 11. Phase 12 marks ANLYS-05 as done, no implementation needed.
- **D-12:** Databricks informational constraints (PK, UNIQUE) are reported as constraint-backed in find_pk_candidates results -- they exist in INFORMATION_SCHEMA.TABLE_CONSTRAINTS even though ENFORCED='NO'. Response should note informational nature so LLM agents understand the distinction.
- **D-13:** target_has_index field in find_fk_candidates is gated by dialect.supports_indexes -- omitted entirely when supports_indexes=False. Not an empty/false value -- absent = "not supported".
- **D-14:** Generic dialect PK/FK discovery uses SQLAlchemy Inspector (get_pk_constraint(), get_unique_constraints()) instead of INFORMATION_SCHEMA raw SQL. MSSQL retains existing INFORMATION_SCHEMA queries.
- **D-15:** INTERSECT syntax is universal across MSSQL, Databricks, and PostgreSQL -- no transpilation needed for FK overlap queries.

### Claude's Discretion
- **D-16:** Internal refactoring of analysis class constructors (how Inspector/dialect/connection are threaded through).
- **D-17:** How ColumnStatsCollector splits between fast path and Tier 2 code paths internally.
- **D-18:** Whether to add a thin AnalysisQueryBuilder helper for sqlglot transpilation or inline transpile calls.
- **D-19:** How column existence checks adapt (currently INFORMATION_SCHEMA) -- Inspector.get_columns() or transpiled query.

### Deferred Ideas (OUT OF SCOPE)
- **ANLYS-06**: Histogram data from Databricks ANALYZE TABLE stats
- **ANLYS-07**: Cross-dialect type normalization display mapping
- Databricks JSON format for DESCRIBE EXTENDED (stable but requires DBR 16.2+) -- text format sufficient for now

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|------------------|
| ANLYS-01 | get_column_info works across all dialects using standard SQL aggregates (Tier 2) with sqlglot transpilation | Empirically validated: sqlglot handles TOP->LIMIT, LEN->LENGTH, STDEV->STDDEV, CAST AS FLOAT, DATEDIFF correctly when read='tsql'. CAST AS TIME needs dialect branch. |
| ANLYS-02 | Databricks get_column_info reads precomputed stats from DESCRIBE EXTENDED when available (Tier 3) | DESCRIBE EXTENDED column_name returns key-value pairs. Probe-first-column heuristic avoids N+1 when stats absent. Custom parser needed (D-10). |
| ANLYS-03 | find_pk_candidates works across all dialects using uniqueness/null checks, with informational-constraint awareness for Databricks | Inspector.get_pk_constraint() + get_unique_constraints() for generic/Databricks. MSSQL retains INFORMATION_SCHEMA. Databricks ENFORCED='NO' needs annotation. |
| ANLYS-04 | find_fk_candidates works across all dialects using Inspector-based index checks and value overlap via INTERSECT | INTERSECT confirmed universal. sys.indexes must be MSSQL-only branch. target_has_index gated by supports_indexes. Inspector replaces INFORMATION_SCHEMA for generic. |
| ANLYS-05 | Databricks partition metadata surfaced in table schema responses | Already complete from Phase 11 (partition_columns in get_table_schema). No work needed. |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlglot | 30.4.2 | SQL transpilation between dialects | Already in project deps; empirically validated for all analysis query patterns [VERIFIED: uv run python -c import] |
| sqlalchemy | >=2.0.0 | Inspector API for type objects and constraint metadata | Already in project deps; provides dialect-agnostic type hierarchy [VERIFIED: codebase] |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| sqlalchemy.types | (part of SA) | isinstance-based type classification | Replacing hardcoded MSSQL type string sets |
| sqlalchemy.dialects.mssql | (part of SA) | MONEY, SMALLMONEY type imports | MSSQL-specific type classification edge case |

**No new dependencies required.** All libraries already in project.

## Architecture Patterns

### Recommended Constructor Refactoring (D-16)

Current analysis class constructors take `(connection, schema_name, table_name)`. They need dialect and Inspector access. Recommended pattern matching MetadataService:

```python
# Source: Established pattern from src/db/metadata.py
class ColumnStatsCollector:
    def __init__(
        self,
        connection: Connection,
        schema_name: str,
        table_name: str,
        dialect: DialectStrategy | None = None,
        inspector: Inspector | None = None,
    ):
        self.connection = connection
        self.schema_name = schema_name
        self.table_name = table_name
        self._dialect = dialect
        self._inspector = inspector
```

This preserves backward compatibility (dialect=None defaults to MSSQL behavior) while enabling dialect-aware paths. [VERIFIED: existing MetadataService pattern in src/db/metadata.py]

### Transpilation Helper (D-18)

The transpile call pattern repeats 6+ times across the three analysis modules. A thin helper is warranted:

```python
def _transpile_query(self, sql: str) -> str:
    """Transpile TSQL-syntax SQL to target dialect."""
    if self._dialect is None or self._dialect.sqlglot_dialect == "tsql":
        return sql  # No transpilation needed for MSSQL
    result = sqlglot.transpile(sql, read="tsql", write=self._dialect.sqlglot_dialect)
    return result[0]
```

This can be a mixin, a standalone function, or a method on each class. Recommend standalone function in a shared `src/analysis/_sql.py` module since all three classes need it. [ASSUMED -- exact location is Claude's discretion]

### Query Building Pattern for Transpilation

Base queries should use TSQL syntax (matching existing code exactly), with column names and table names injected via `dialect.quote_identifier()` instead of hardcoded brackets. The transpile step handles syntax conversion:

```python
# Before (MSSQL-only):
col_q = f"[{column_name}]"
table_q = f"[{schema_name}].[{table_name}]"
sql = f"SELECT MIN(LEN({col_q})) FROM {table_q}"

# After (dialect-aware):
col_q = self._dialect.quote_identifier(column_name)
table_q = f"{self._dialect.quote_identifier(schema_name)}.{self._dialect.quote_identifier(table_name)}"
sql = f"SELECT MIN(LEN({col_q})) FROM {table_q}"
transpiled = self._transpile_query(sql)
```

**Critical caveat:** sqlglot transpilation changes identifier quoting (brackets -> backticks for Databricks). When we pre-quote identifiers with `dialect.quote_identifier()` and then pass through sqlglot, the quoting may conflict. The safer approach: build SQL with placeholder identifiers, transpile, then quote. Or: let sqlglot handle quoting by not pre-quoting. [VERIFIED: sqlglot converts `[col]` to backtick-quoted `\`col\`` when transpiling tsql -> databricks]

**Recommended approach:** Use bracket quoting in base SQL (TSQL read dialect handles it), let sqlglot convert to target dialect quoting. This means the existing bracket-quoted SQL is already correct as input to `sqlglot.transpile(sql, read='tsql', write=target)`. [VERIFIED: empirical test confirmed bracket->backtick conversion]

### Type Classification Pattern (D-05, D-06, D-07)

```python
from sqlalchemy import types
from sqlalchemy.engine import Inspector

def _get_type_category(type_obj: types.TypeEngine) -> str:
    """Classify a SQLAlchemy type into analysis categories."""
    if isinstance(type_obj, (types.Integer, types.Numeric)):
        return "numeric"
    # MSSQL MONEY/SMALLMONEY don't inherit from Numeric -- handle explicitly
    type_name = type(type_obj).__name__.upper()
    if type_name in ("MONEY", "SMALLMONEY"):
        return "numeric"
    if isinstance(type_obj, (types.DateTime, types.Date, types.Time)):
        return "datetime"
    if isinstance(type_obj, types.String):
        return "string"
    return "other"
```

[VERIFIED: empirical test confirmed MONEY/SMALLMONEY do NOT inherit from types.Numeric]

### Column Discovery via Inspector (D-19)

Replace INFORMATION_SCHEMA column queries with Inspector:

```python
# Column existence check
columns = inspector.get_columns(table_name, schema=schema_name)
col_names = {c["name"] for c in columns}
exists = column_name in col_names

# Column listing with types
for col in columns:
    name = col["name"]
    type_obj = col["type"]  # TypeEngine instance
    category = _get_type_category(type_obj)
```

[VERIFIED: MetadataService.get_columns() already uses this pattern in src/db/metadata.py]

### MCP Tool Wiring Pattern

analysis_tools.py `_sync_work()` functions need to pass dialect and inspector:

```python
def _sync_work():
    conn_manager = get_connection_manager()
    engine = conn_manager.get_engine(connection_id)
    dialect = conn_manager.get_dialect(connection_id)
    
    with engine.connect() as connection:
        inspector = inspect(engine)
        collector = ColumnStatsCollector(
            connection=connection,
            schema_name=schema_name,
            table_name=table_name,
            dialect=dialect,
            inspector=inspector,
        )
```

[VERIFIED: schema_tools.py already uses `conn_manager.get_dialect(connection_id)` pattern]

### Databricks Fast Path (D-08, D-09, D-10)

```python
def _try_describe_extended_stats(self, column_name: str) -> dict | None:
    """Try to get precomputed stats via DESCRIBE EXTENDED.
    
    Returns dict with stat keys if available, None if not.
    """
    qualified = f"{self._dialect.quote_identifier(catalog)}.{self._dialect.quote_identifier(schema)}.{self._dialect.quote_identifier(table)}"
    sql = f"DESCRIBE EXTENDED {qualified} {self._dialect.quote_identifier(column_name)}"
    result = self.connection.execute(text(sql))
    rows = result.fetchall()
    
    stats = {}
    for row in rows:
        key = (row[0] or "").strip()
        val = (row[1] or "").strip()
        if key in ("min", "max", "num_nulls", "distinct_count", "avg_col_len", "max_col_len"):
            stats[key] = val
    
    # If no stats keys found, ANALYZE TABLE hasn't been run
    if not stats or all(v in ("", "null", None) for v in stats.values()):
        return None
    return stats
```

Reference: `_parse_databricks_table_properties()` in src/db/metadata.py for DESCRIBE EXTENDED parsing pattern. [VERIFIED: existing codebase]

### Capability-Gated Fields (D-13)

```python
# In FKCandidateData.to_dict() or at construction time:
if dialect.supports_indexes:
    metadata["target_has_index"] = has_index
# When supports_indexes is False, key is absent entirely
```

This matches the Phase 11 pattern for index gating in get_table_schema. [VERIFIED: src/db/metadata.py lines 824-837]

### Anti-Patterns to Avoid
- **Extending DialectStrategy protocol with analysis methods:** D-02 explicitly prohibits this. Would bloat protocol with 15+ methods.
- **Writing "standard SQL" as base dialect:** Empirical testing shows standard SQL -> TSQL converts COUNT to COUNT_BIG and mishandles DATEDIFF argument order. TSQL as read dialect is safer since it matches existing queries.
- **Pre-quoting identifiers before transpilation:** sqlglot already handles identifier quoting conversion (brackets -> backticks). Pre-quoting with dialect.quote_identifier() before transpile will produce double-quoted or misquoted output.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| SQL syntax conversion (TOP->LIMIT, LEN->LENGTH) | Manual string replacement | `sqlglot.transpile(sql, read='tsql', write=target)` | 6+ syntax differences; sqlglot handles edge cases (nested expressions, quoting) |
| Type classification across dialects | Expanded string sets per dialect | `isinstance()` against SQLAlchemy TypeEngine hierarchy | SQLAlchemy already maps dialect types to generic hierarchy (NVARCHAR->String, DATETIME2->DateTime, etc.) |
| Constraint discovery | Raw INFORMATION_SCHEMA SQL per dialect | `Inspector.get_pk_constraint()`, `get_unique_constraints()` | Inspector works across all SQLAlchemy dialects automatically |
| Column metadata discovery | INFORMATION_SCHEMA.COLUMNS queries | `Inspector.get_columns()` | Returns type objects (not strings), handles dialect differences |

**Key insight:** The existing MSSQL-specific SQL is already valid input for sqlglot's TSQL parser. The refactoring is mostly about (1) replacing bracket quoting with dialect-aware quoting, (2) adding a transpile step, and (3) switching metadata queries from INFORMATION_SCHEMA to Inspector.

## Common Pitfalls

### Pitfall 1: MONEY/SMALLMONEY Type Classification
**What goes wrong:** D-06 states "MSSQL MONEY -> Numeric" suggesting isinstance() handles it automatically. It does NOT.
**Why it happens:** MONEY and SMALLMONEY inherit directly from TypeEngine, not from Numeric. This is a SQLAlchemy implementation detail.
**How to avoid:** Add explicit type name checks for MONEY/SMALLMONEY as a fallback after isinstance() checks. Use `type(obj).__name__.upper()` for the string comparison.
**Warning signs:** Numeric columns showing up as "other" category in MSSQL stats output.

### Pitfall 2: sqlglot COUNT -> COUNT_BIG Conversion
**What goes wrong:** When transpiling standard SQL to TSQL, sqlglot converts `COUNT(*)` to `COUNT_BIG(*)`.
**Why it happens:** sqlglot's TSQL generator prefers COUNT_BIG for large table safety.
**How to avoid:** Use `read='tsql'` (not standard) as the source dialect. TSQL->TSQL is a no-op for COUNT. TSQL->Databricks correctly keeps COUNT.
**Warning signs:** Existing MSSQL tests breaking due to unexpected COUNT_BIG in generated SQL.

### Pitfall 3: DATEDIFF Is Not Standard SQL
**What goes wrong:** DATEDIFF syntax varies wildly between dialects. Standard SQL has no DATEDIFF function.
**Why it happens:** TSQL uses DATEDIFF(datepart, start, end). Databricks uses DATEDIFF(end, start) for day-only, or DATEDIFF(datepart, start, end) in newer Spark SQL.
**How to avoid:** Write DATEDIFF in TSQL syntax and let sqlglot transpile. The TSQL->Databricks path correctly converts `DATEDIFF(day, MIN(col), MAX(col))` to `DATEDIFF(DAY, CAST(MIN(col) AS TIMESTAMP), CAST(MAX(col) AS TIMESTAMP))`.
**Warning signs:** Wrong date range values in Databricks stats output.

### Pitfall 4: CAST AS TIME Has No Databricks Equivalent
**What goes wrong:** The datetime stats query uses `CAST([col] AS TIME) <> '00:00:00'` for time component detection. Databricks has no TIME type.
**Why it happens:** sqlglot converts `CAST(col AS TIME)` to `CAST(col AS TIMESTAMP)` for Databricks, which is semantically different.
**How to avoid:** This is one of the ~2-3 genuine dialect branches needed. For Databricks, use `HOUR(col) <> 0 OR MINUTE(col) <> 0 OR SECOND(col) <> 0`. For generic, use the same Databricks approach (HOUR/MINUTE/SECOND are ANSI-compatible).
**Warning signs:** has_time_component always returning True on Databricks.

### Pitfall 5: STRING_SPLIT Is MSSQL-Only
**What goes wrong:** FK candidate target table filtering uses `STRING_SPLIT(:table_list, ',')` which is MSSQL-specific.
**Why it happens:** STRING_SPLIT is a T-SQL table-valued function with no equivalent in Databricks/generic SQL.
**How to avoid:** Replace with Inspector-based table listing (Inspector.get_table_names()) and Python-side filtering, or build a parameterized IN clause. The Inspector approach is already used by MetadataService for generic dialects.
**Warning signs:** FK candidate search failing on Databricks with "STRING_SPLIT not found".

### Pitfall 6: Identifier Quoting Conflict with sqlglot
**What goes wrong:** If you pre-quote identifiers with `dialect.quote_identifier()` (backticks for Databricks) and then pass to sqlglot with `read='tsql'`, sqlglot doesn't recognize backtick-quoted identifiers as TSQL.
**Why it happens:** sqlglot expects bracket-quoted identifiers when `read='tsql'`.
**How to avoid:** Keep bracket quoting in the SQL template (matching TSQL convention), and let sqlglot convert brackets to target dialect quoting during transpilation. Do NOT call `dialect.quote_identifier()` for SQL that will be transpiled.
**Warning signs:** Syntax errors or double-quoting in transpiled SQL.

## Code Examples

### sqlglot Transpilation Validated Patterns

All patterns below were empirically validated with sqlglot 30.4.2.

#### TOP N -> LIMIT (column_stats.py sample_values query)
```python
# Input (TSQL):
"SELECT TOP 10 [col] as value, COUNT(*) as frequency FROM [schema].[table] WHERE [col] IS NOT NULL GROUP BY [col] ORDER BY COUNT(*) DESC"
# Output (Databricks):
"SELECT `col` AS value, COUNT(*) AS frequency FROM `schema`.`table` WHERE NOT `col` IS NULL GROUP BY `col` ORDER BY COUNT(*) DESC LIMIT 10"
```
[VERIFIED: empirical test]

#### LEN -> LENGTH (column_stats.py string length query)
```python
# Input (TSQL):
"SELECT MIN(LEN([col])), MAX(LEN([col])), AVG(CAST(LEN([col]) AS FLOAT)) FROM [schema].[table]"
# Output (Databricks):
"SELECT MIN(LENGTH(CAST(`col` AS STRING))), MAX(LENGTH(CAST(`col` AS STRING))), AVG(CAST(LENGTH(CAST(`col` AS STRING)) AS FLOAT)) FROM `schema`.`table`"
```
Note: sqlglot wraps LEN->LENGTH with CAST(x AS STRING) for Databricks. This is correct behavior.
[VERIFIED: empirical test]

#### STDEV -> STDDEV (column_stats.py numeric stats query)
```python
# Input (TSQL):
"SELECT STDEV(CAST([col] AS FLOAT)) FROM [schema].[table]"
# Output (Databricks):
"SELECT STDDEV(CAST(`col` AS FLOAT)) FROM `schema`.`table`"
```
[VERIFIED: empirical test]

#### DATEDIFF (column_stats.py datetime stats query)
```python
# Input (TSQL):
"SELECT DATEDIFF(day, MIN([col]), MAX([col])) FROM [schema].[table]"
# Output (Databricks):
"SELECT DATEDIFF(DAY, CAST(MIN(`col`) AS TIMESTAMP), CAST(MAX(`col`) AS TIMESTAMP)) FROM `schema`.`table`"
```
[VERIFIED: empirical test]

#### INTERSECT (fk_candidates.py overlap query)
```python
# Input (standard SQL -- no transpilation needed):
"SELECT COUNT(*) FROM (SELECT [col] FROM [s].[t1] INTERSECT SELECT [col] FROM [s].[t2]) AS overlap"
# Output: unchanged syntax, only identifier quoting changes
```
[VERIFIED: empirical test confirms D-15]

### Non-Transpilable Patterns (Need Dialect Branches)

#### Time Component Detection (CAST AS TIME)
```python
# MSSQL: CAST([col] AS TIME) <> '00:00:00'
# Databricks/Generic: HOUR(col) <> 0 OR MINUTE(col) <> 0 OR SECOND(col) <> 0
if self._dialect and self._dialect.name == "databricks":
    time_check = f"HOUR({col_q}) <> 0 OR MINUTE({col_q}) <> 0 OR SECOND({col_q}) <> 0"
else:
    time_check = f"CAST({col_q} AS TIME) <> '00:00:00'"
```
[VERIFIED: sqlglot converts CAST AS TIME to CAST AS TIMESTAMP for Databricks -- wrong semantics]

#### sys.indexes DMV (MSSQL-only)
```python
# MSSQL: sys.indexes query (existing code in fk_candidates.py)
# Databricks: supports_indexes=False, so target_has_index is omitted
# Generic: Inspector.get_indexes() fallback
if self._dialect and self._dialect.supports_indexes:
    if self._dialect.name == "mssql":
        # existing sys.indexes query
        ...
    else:
        # Inspector.get_indexes() for generic dialects
        indexes = self._inspector.get_indexes(table_name, schema=schema_name)
        has_index = any(col_name in idx.get("column_names", []) for idx in indexes)
```
[VERIFIED: codebase analysis of fk_candidates.py]

#### STRING_SPLIT Table Filtering
```python
# MSSQL: STRING_SPLIT(:table_list, ',') in SQL
# All dialects: Use Inspector + Python filtering
if target_tables is not None:
    all_tables = self._inspector.get_table_names(schema=schema)
    filtered = [(schema, t) for t in all_tables if t in set(target_tables)]
```
[VERIFIED: STRING_SPLIT does not transpile -- sqlglot passes it through unchanged]

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Hardcoded MSSQL type strings | isinstance() against TypeEngine | Phase 12 | Enables automatic Databricks/generic type classification |
| INFORMATION_SCHEMA for column metadata | Inspector.get_columns() | Phase 12 | Returns type objects instead of strings; works across dialects |
| Bracket quoting everywhere | sqlglot handles quoting via transpile | Phase 12 | Correct quoting for any target dialect |
| MSSQL-only analysis SQL | TSQL base + sqlglot transpile | Phase 12 | Same queries work across MSSQL, Databricks, generic |

## Assumptions Log

| # | Claim | Section | Risk if Wrong |
|---|-------|---------|---------------|
| A1 | MONEY/SMALLMONEY type name check via `type(obj).__name__.upper()` is the cleanest fallback | Type Classification Pattern | LOW -- could use full module path check instead; same result |
| A2 | Databricks DESCRIBE EXTENDED column-level syntax returns key-value rows with "min", "max", "num_nulls", "distinct_count" keys | Databricks Fast Path | MEDIUM -- exact key names may differ; D-09 provides expected format but parser must handle variations |
| A3 | HOUR()/MINUTE()/SECOND() functions work on generic SQLAlchemy dialects (PostgreSQL, SQLite) | Non-Transpilable Patterns | LOW -- these are ANSI SQL functions; PostgreSQL supports them; SQLite has no native datetime functions but EXTRACT works |
| A4 | Databricks INFORMATION_SCHEMA.TABLE_CONSTRAINTS includes ENFORCED column | Constraint Semantics | MEDIUM -- documented in Databricks docs but not empirically verified against live cluster |
| A5 | Transpilation helper in shared `src/analysis/_sql.py` is the right abstraction | Architecture Patterns | LOW -- if pattern doesn't repeat enough, can inline instead |

## Open Questions

1. **Databricks DESCRIBE EXTENDED column stats key names**
   - What we know: D-09 specifies "min", "max", "num_nulls", "distinct_count", "avg_col_len", "max_col_len"
   - What's unclear: Exact key casing, whether empty stats return empty rows or no rows at all
   - Recommendation: Build parser defensively with case-insensitive matching and handle both empty-row and absent-row cases. The probe-first-column heuristic (D-08) means we only need to handle the "no stats" case once.

2. **Generic dialect time component detection**
   - What we know: HOUR/MINUTE/SECOND work in PostgreSQL and Databricks
   - What's unclear: Whether they work in SQLite (which has limited datetime support)
   - Recommendation: Use HOUR/MINUTE/SECOND for Databricks and generic. SQLite is not a primary target and can fall back to "other" classification for datetime columns.

3. **catalog parameter plumbing for Databricks analysis tools**
   - What we know: MetadataService receives catalog as a parameter for Databricks cross-catalog queries
   - What's unclear: Whether analysis tools need a catalog parameter or can infer from connection default
   - Recommendation: Databricks DESCRIBE EXTENDED needs fully-qualified `catalog.schema.table`. The catalog should come from the connection's default catalog (already set in engine URL). The MCP tool interface should not need a catalog parameter for analysis tools -- it's implicit in the connection.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.x |
| Config file | pyproject.toml [tool.pytest] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| ANLYS-01 | Column stats work across all 3 dialects via transpiled SQL | unit | `uv run pytest tests/unit/test_column_stats.py -x` | Exists (needs dialect-parameterized tests) |
| ANLYS-02 | Databricks fast path reads DESCRIBE EXTENDED stats | unit | `uv run pytest tests/unit/test_column_stats.py -k databricks -x` | Wave 0 |
| ANLYS-03 | PK candidates work across dialects with informational constraint annotation | unit | `uv run pytest tests/unit/test_pk_discovery.py -x` | Exists (needs dialect-parameterized tests) |
| ANLYS-04 | FK candidates work across dialects, index gating, Inspector fallback | unit | `uv run pytest tests/unit/test_fk_candidates.py -x` | Exists (needs dialect-parameterized tests) |
| ANLYS-05 | Partition metadata in schema responses | unit | N/A | Already complete (Phase 11) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_column_stats.py tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py tests/unit/test_analysis_models.py -x -q`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd-verify-work`

### Wave 0 Gaps
- [ ] Dialect-parameterized test fixtures (mock DialectStrategy with different sqlglot_dialect/supports_indexes values)
- [ ] Databricks DESCRIBE EXTENDED column stats mock data for fast path tests
- [ ] Updated mock setup: analysis class constructors will take dialect/inspector params
- [ ] PKCandidate model may need `constraint_enforced` field for Databricks informational constraint annotation

## Security Domain

### Applicable ASVS Categories

| ASVS Category | Applies | Standard Control |
|---------------|---------|-----------------|
| V2 Authentication | no | N/A |
| V3 Session Management | no | N/A |
| V4 Access Control | no | Read-only enforcement unchanged |
| V5 Input Validation | yes | sqlglot transpilation does NOT sanitize inputs; identifier quoting via dialect.quote_identifier() prevents SQL injection in generated analysis SQL. All user-provided column/table names must be quoted. |
| V6 Cryptography | no | N/A |

### Known Threat Patterns

| Pattern | STRIDE | Standard Mitigation |
|---------|--------|---------------------|
| SQL injection via column_name/table_name in analysis queries | Tampering | dialect.quote_identifier() for all identifiers in generated SQL; parameterized queries via sqlalchemy text() with bind params where possible |
| Unvalidated sqlglot output | Tampering | sqlglot output is deterministic for given input; transpiled SQL inherits safety of source SQL; no user-controlled raw SQL injection point |

## Sources

### Primary (HIGH confidence)
- sqlglot 30.4.2 empirical testing -- validated all 6 transpilation patterns (TOP, LEN, STDEV, DATEDIFF, CAST, INTERSECT) for tsql->databricks and tsql->generic
- SQLAlchemy type hierarchy -- empirically verified isinstance() behavior for MONEY, SMALLMONEY, DATETIME2, NVARCHAR, BIT, TINYINT, etc.
- Codebase analysis -- src/analysis/ (3 modules), src/db/metadata.py, src/db/dialects/, src/mcp_server/analysis_tools.py, tests/unit/ (91 existing tests)

### Secondary (MEDIUM confidence)
- Databricks DESCRIBE EXTENDED column stats format -- from CONTEXT.md D-09, consistent with Databricks documentation [ASSUMED -- not tested against live cluster]
- Databricks INFORMATION_SCHEMA.TABLE_CONSTRAINTS ENFORCED column -- from CONTEXT.md D-12 [ASSUMED]

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- no new dependencies, all empirically validated
- Architecture: HIGH -- patterns established in prior phases, constructor refactoring is straightforward
- Pitfalls: HIGH -- empirically discovered via sqlglot testing (MONEY, COUNT_BIG, CAST AS TIME, DATEDIFF)
- Databricks fast path: MEDIUM -- DESCRIBE EXTENDED format from context decisions, not live-tested

**Research date:** 2026-04-15
**Valid until:** 2026-05-15 (stable -- sqlglot and SQLAlchemy APIs change slowly)
