---
created: 2026-04-28T20:30:00.000Z
title: execute_query("SHOW CATALOGS") passes validator but returns 0 rows
area: databricks
source: Discovered during Phase 11 UAT Test 7 live verification after 260428-l6x (2026-04-28)
files:
  - src/db/query.py (result-fetching path for non-SELECT query_type)
  - src/db/query.py (parse_query_type / inject_row_limit for "other" queries)
---

## Problem

After 260428-l6x made the validator dialect-aware, `SHOW CATALOGS` is no
longer blocked:

```
query_id: 3be00e4c-...
query_type: other
is_allowed: true
execution_time_ms: 527
rows_returned: 0
rows_affected: 0
status: success
columns[0]:
rows[0]:
```

`is_allowed: true` confirms the validator fix is working. But `rows_returned:
0` / `columns[0]:` is wrong — the query executed (527ms against Databricks)
and definitely produced rows. The same underlying SQL path inside
`_list_databricks_catalogs` successfully returned 19 catalogs using
`text("SHOW CATALOGS")` via `engine.connect().execute().fetchall()`.

## Likely cause

`QueryExecutor.execute_query` classifies this as `query_type=other` (not
SELECT). The result-materialization path for `other` queries probably
doesn't call `.fetchall()` or doesn't build a column list — it only tracks
`rows_affected` for write statements. Databricks SHOW/DESCRIBE queries are
result-set-producing reads classified as "other", which the executor
doesn't know how to materialize.

Hypothesis: the code path returns before calling `conn.execute(...).fetchall()`
for non-SELECT queries, or it fetches but discards rows because no `columns`
metadata was built.

## Scope

- Allow the result-fetch path to materialize rows for Databricks
  SHOW/DESCRIBE/EXPLAIN (the verbs listed in `safe_operational_commands`).
  Simplest approach: when the dialect's `safe_operational_commands` set
  classifies the verb as a discovery read, treat it like SELECT for
  row materialization (but skip row_limit injection since SHOW doesn't
  accept LIMIT).
- Or: detect "is result-producing" at parse time (sqlglot gives us the
  Command node; we can ask whether the statement returns a result set).

## Reproduction

1. Connect to Databricks.
2. `execute_query(connection_id, "SHOW CATALOGS")`.
3. Observe `rows_returned: 0` despite successful execution.

Compare with the same query issued internally by
`MetadataService._list_databricks_catalogs` (which uses
`conn.execute(text("SHOW CATALOGS")).fetchall()` directly and gets rows).

## Acceptance

- `execute_query(connection_id, "SHOW CATALOGS")` on Databricks returns the
  actual catalog rows in `rows` with a single column like `catalog`.
- `DESCRIBE` / `SHOW TABLES` / `SHOW SCHEMAS` behave similarly.
- Unit test covers the "passes validator + materializes rows" path.
- MSSQL path unaffected (empty `safe_operational_commands` → no change).

## Notes

- Partially related to but distinct from the column-introspection gap
  (`.planning/todos/pending/2026-04-28-databricks-get-table-schema-empty-columns.md`):
  both stem from Databricks discovery paths not being first-class in the
  query/metadata code, but they live in different modules.
- Not a Test 7 blocker — the 4 core gaps are verified passing.
