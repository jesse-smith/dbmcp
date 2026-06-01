---
phase: quick-260428-mwr
plan: 01
type: execute
wave: 1
depends_on: []
files_modified:
  - src/db/query.py
  - src/db/metadata.py
  - tests/unit/test_query.py
  - tests/unit/test_metadata.py
autonomous: true
requirements:
  - DATABRICKS-SHOW-QUERY
  - DATABRICKS-CROSS-CATALOG-COLUMNS

must_haves:
  truths:
    - "execute_query('SHOW CATALOGS') on Databricks returns actual catalog rows, not 0 rows"
    - "execute_query('DESCRIBE ...') and other safe operational commands materialize rows"
    - "get_table_schema(catalog=X, schema_name=Y, table_name=Z) returns populated columns list for cross-catalog tables"
    - "Non-Databricks query and schema paths are unaffected"
  artifacts:
    - path: "src/db/query.py"
      provides: "Result materialization for safe operational commands"
      contains: "_process_select_results"
    - path: "src/db/metadata.py"
      provides: "Cross-catalog column fetch via DESCRIBE TABLE"
      contains: "_get_databricks_columns"
    - path: "tests/unit/test_query.py"
      provides: "Tests for SHOW/DESCRIBE result materialization"
    - path: "tests/unit/test_metadata.py"
      provides: "Tests for cross-catalog column fetch"
  key_links:
    - from: "src/db/query.py _run_query"
      to: "_process_select_results"
      via: "is_result_producing check on safe_operational_commands"
      pattern: "safe_operational_commands.*query_verb"
    - from: "src/db/metadata.py get_table_schema"
      to: "get_columns"
      via: "catalog-aware branch for Databricks"
      pattern: "_get_databricks_columns"
---

<objective>
Fix two Databricks bugs discovered during Phase 11 UAT Test 7:

1. `execute_query("SHOW CATALOGS")` returns 0 rows — the non-SELECT path in `_run_query`
   only tracks `rows_affected` and discards result sets. Databricks SHOW/DESCRIBE/EXPLAIN
   are result-producing reads, not write operations, and must be materialized like SELECT.

2. `get_table_schema(catalog="bmtct", ...)` returns an empty columns list — `get_columns`
   uses SQLAlchemy Inspector which is bound to the engine's default catalog and silently
   returns empty for cross-catalog tables. The DESCRIBE TABLE EXTENDED output already
   parses correctly for DTE properties; reuse the same SQL path for columns.

Purpose: These two bugs make Databricks catalog exploration unusable from the MCP
client — the primary use case of this project.

Output: Two targeted fixes with TDD, zero regressions on existing tests.
</objective>

<execution_context>
@$HOME/.claude/get-shit-done/workflows/execute-plan.md
@$HOME/.claude/get-shit-done/templates/summary.md
</execution_context>

<context>
@.planning/PROJECT.md
@.planning/STATE.md
</context>

<tasks>

<task type="auto" tdd="true">
  <name>Task 1: Fix execute_query to materialize rows for safe operational commands (SHOW/DESCRIBE/EXPLAIN)</name>
  <files>src/db/query.py, tests/unit/test_query.py</files>

  <behavior>
    - Test: execute_query("SHOW CATALOGS") with Databricks dialect and mock returning [("bmtct",), ("main",)] → query.rows == [{"catalog": "bmtct"}, {"catalog": "main"}], query.rows_affected == 2
    - Test: execute_query("DESCRIBE TABLE t") with Databricks dialect → rows materialized
    - Test: execute_query("INSERT INTO t ...") still takes the write/commit path (rows_affected, not rows)
    - Test: execute_query("SHOW CATALOGS") without Databricks dialect (no safe_operational_commands) → blocked by validator (is_allowed=False), rows==[]
    - Test: execute_query("SELECT ...") path unchanged
  </behavior>

  <action>
  In `src/db/query.py`, method `_run_query`:

  The current non-SELECT branch (line ~652) is:
  ```python
  rows_affected = result.rowcount if result.rowcount >= 0 else 0
  conn.commit()
  return [], [], rows_affected, None, None
  ```

  This unconditionally discards result sets for all non-SELECT queries. Fix:

  1. Before the non-SELECT branch, determine if the query is a result-producing operational
     command. Extract the first token of `executed_query` (strip, uppercase, split()[0]).
     A query is result-producing when that verb is in `self._dialect.safe_operational_commands`
     (guard: `self._dialect is not None`).

  2. If result-producing: call `_process_select_results(result, conn, executed_query, row_limit)`
     and return its tuple directly. Do NOT call `conn.commit()` — these are pure reads.
     Set `rows_affected` from `len(rows)` in the returned tuple.

  3. Else (write/DDL): keep current behavior unchanged — `rowcount` + `commit()`.

  Important: Do NOT inject row limits into operational commands (the `inject_row_limit`
  call at line ~561 is already guarded by `query_type == QueryType.SELECT`, so no change
  needed there).

  The fix is ~6 lines in `_run_query`. Do not touch `_process_select_results` or any
  other method.

  Write the failing tests first in `tests/unit/test_query.py` in class
  `TestQueryExecution`. Mock pattern (copy from existing `test_execute_select_query`
  at line 631): mock_result with `.keys()` and `.fetchall()`, mock_conn.execute
  returning mock_result. For the Databricks dialect mock, set
  `service._dialect.safe_operational_commands = frozenset({"SHOW", "DESCRIBE"})`.
  </action>

  <verify>
    <automated>uv run pytest tests/unit/test_query.py -x -q 2>&1 | tail -20</automated>
  </verify>

  <done>
    Tests for SHOW result materialization pass (RED then GREEN). Full test_query.py suite
    still passes. No new ruff warnings.
  </done>
</task>

<task type="auto" tdd="true">
  <name>Task 2: Fix get_table_schema cross-catalog column fetch for Databricks</name>
  <files>src/db/metadata.py, tests/unit/test_metadata.py</files>

  <behavior>
    - Test: get_table_schema(catalog="bmtct", schema_name="playground", table_name="t") with Databricks dialect → columns list is non-empty (populated from DESCRIBE TABLE output)
    - Test: DESCRIBE TABLE output rows before "# Detailed Table Information" section are parsed as columns (col_name=row[0], data_type=row[1])
    - Test: cross-catalog column fetch does NOT call inspector.get_columns (inspector is not catalog-aware)
    - Test: non-Databricks path still calls inspector.get_columns as before (catalog param ignored)
    - Test: when catalog=None and Databricks dialect, falls through to inspector path (default catalog, same as before — no regression)
  </behavior>

  <action>
  In `src/db/metadata.py`, method `get_table_schema` (line ~884):

  Currently `get_table_schema` calls `self.get_columns(table_name, schema_name)` unconditionally,
  which uses `self.inspector.get_columns(table_name, schema=schema_name)` — the inspector is
  bound to the engine's default catalog and silently returns [] for cross-catalog tables.

  **The fix:** Add a private method `_get_databricks_columns` that extracts column rows from
  the DESCRIBE TABLE EXTENDED output already issued by `_parse_databricks_table_properties`.
  Then in `get_table_schema`, when `catalog` is provided and dialect is Databricks, use this
  new method instead of `get_columns`.

  Implementation steps:

  1. Add `_get_databricks_columns(self, table_name, schema_name, catalog) -> list[Column]`:
     - Issues `DESCRIBE TABLE {quoted_catalog}.{quoted_schema}.{quoted_table}` (not EXTENDED —
       simpler output, just columns; or reuse DESCRIBE TABLE EXTENDED if already available).
     - Parse rows: stop when row[0] starts with "#" or row[0] is empty string (section marker).
       These are the column definition rows: row[0]=col_name, row[1]=data_type, row[2]=comment.
     - For each column row, build a `Column` object with:
       - `column_id = f"{catalog}.{schema_name}.{table_name}.{col_name}"`
       - `table_id = f"{catalog}.{schema_name}.{table_name}"`
       - `column_name = col_name`
       - `ordinal_position = idx` (1-based)
       - `data_type = data_type`
       - All other fields (max_length, is_nullable, is_identity, etc.) left as defaults
         (None / False) — DESCRIBE TABLE does not provide them; this is an acceptable
         limitation for cross-catalog reads.
       - `is_primary_key = False`, `is_foreign_key = False`
     - On SQLAlchemyError or any exception: log warning and return [].

  2. In `get_table_schema` (line ~884), change the `get_columns` call to:
     ```python
     if catalog and self._dialect and self._dialect.name == "databricks":
         columns = self._get_databricks_columns(table_name, schema_name, catalog)
     else:
         columns = self.get_columns(table_name, schema_name)
     ```

  The existing `get_columns` method is unchanged. No MSSQL/generic paths are affected.
  Use `self._dialect.quote_identifier()` for all identifiers (already established pattern).

  Write failing tests first in `tests/unit/test_metadata.py`. Add a new class
  `TestGetTableSchemaCrossCatalogColumns`. Mock pattern: patch
  `engine.connect().__enter__().execute()` to return a mock result whose `.fetchall()`
  returns representative DESCRIBE TABLE rows like:
  ```python
  [
      ("id", "int", ""),
      ("name", "string", ""),
      ("", "", ""),                          # blank separator
      ("# Detailed Table Information", "", ""),
      ("Catalog", "bmtct", ""),
  ]
  ```
  Assert `result["columns"]` has 2 entries with column_name "id" and "name".
  Also assert inspector.get_columns was NOT called.
  </action>

  <verify>
    <automated>uv run pytest tests/unit/test_metadata.py -x -q 2>&1 | tail -20</automated>
  </verify>

  <done>
    Tests for cross-catalog column fetch pass (RED then GREEN). Full test_metadata.py suite
    still passes. No new ruff warnings. `uv run pytest tests/ -x -q` exits 0.
  </done>
</task>

</tasks>

<threat_model>
## Trust Boundaries

| Boundary | Description |
|----------|-------------|
| MCP client → QueryService | query_text is untrusted user input |
| MCP client → MetadataService | catalog/schema/table names are untrusted |

## STRIDE Threat Register

| Threat ID | Category | Component | Disposition | Mitigation Plan |
|-----------|----------|-----------|-------------|-----------------|
| T-mwr-01 | Injection | `_run_query` first-token extraction | accept | First token only used to check membership in a frozenset of safe verbs ("SHOW", "DESCRIBE", etc.) — no SQL construction from it |
| T-mwr-02 | Injection | `_get_databricks_columns` catalog/schema/table | mitigate | All identifiers backtick-quoted via `self._dialect.quote_identifier()`, consistent with existing `table_exists` and `_parse_databricks_table_properties` patterns |
| T-mwr-03 | Elevation of Privilege | safe_operational_commands result path | accept | Commands only reach result materialization if they first pass `validate_query` (which gates on `safe_operational_commands`); the result path itself is read-only (no commit) |
</threat_model>

<verification>
```
uv run pytest tests/unit/test_query.py tests/unit/test_metadata.py -x -q
uv run ruff check src/db/query.py src/db/metadata.py
uv run pytest tests/ -x -q
```

All must exit 0 with zero warnings.
</verification>

<success_criteria>
- execute_query("SHOW CATALOGS") on Databricks returns actual catalog rows (columns + rows populated)
- execute_query("DESCRIBE TABLE x") on Databricks returns describe rows
- Non-Databricks SHOW-like queries remain blocked (validator catches them — safe_operational_commands is empty for MSSQL/generic)
- get_table_schema(catalog="bmtct", schema_name="playground", table_name="t") returns populated columns list
- MSSQL get_table_schema path unchanged (inspector.get_columns still called)
- Full test suite green, zero ruff warnings
</success_criteria>

<output>
After completion, create `.planning/quick/260428-mwr-fix-bugs-just-surfaced-and-listed-in-tod/260428-mwr-SUMMARY.md`
</output>
