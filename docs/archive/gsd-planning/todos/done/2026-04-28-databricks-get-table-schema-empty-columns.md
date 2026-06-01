---
created: 2026-04-28T20:30:00.000Z
title: Databricks get_table_schema returns empty columns list (cross-catalog)
area: databricks
source: Discovered during Phase 11 UAT Test 7 live verification after 260428-l6x (2026-04-28)
files:
  - src/db/metadata.py (get_table_schema, column introspection paths)
  - src/db/dialects/databricks.py (if dialect-specific column fetch is warranted)
---

## Problem

`get_table_schema(connection_id=..., catalog="bmtct", schema_name="playground",
table_name="caboodle_tests")` returns a valid response that includes the
DTE (DESCRIBE EXTENDED) properties — owner, location, storage_format, etc. —
but `columns[0]:` (empty list). The table definitely has columns; the
DESCRIBE EXTENDED fast path ran successfully.

```
status: success
table:
  table_name: caboodle_tests
  schema_name: playground
  columns[0]:
  foreign_keys[0]:
  created_time: "Wed Sep 24 14:14:03 UTC 2025"
  table_type_detail: MANAGED
  location: "abfss://..."
  storage_format: delta
  owner: jsmith79@stjude.org
  catalog: bmtct
```

## Likely cause

The SQLAlchemy Inspector path for `get_columns` isn't cross-catalog aware.
The databricks-sqlalchemy Inspector is bound to the engine's configured
catalog (`main` here), so it doesn't find columns when asked about
`playground.caboodle_tests` — it silently returns an empty list instead of
raising.

By contrast, DTE extraction in `_parse_databricks_table_properties` issues
an explicit `DESCRIBE EXTENDED <catalog>.<schema>.<table>` and works
cross-catalog.

## Scope

Thread `catalog` into the column introspection path the same way 260428-l6x
threaded it into `table_exists`. Likely candidates:

- Add a Databricks fast path that runs `DESCRIBE TABLE <catalog>.<schema>.<table>`
  or reuses the DESCRIBE EXTENDED output already captured (the column rows
  come before the `# Detailed Table Information` section).
- Or: open a new Inspector scoped to the target catalog for the duration of
  the call (if databricks-sqlalchemy supports catalog switching).

The DESCRIBE EXTENDED output parser likely already sees the column rows but
discards them — cheaper to re-use what we parsed than to issue a second
query.

## Reproduction

1. Connect to Databricks (any connection where default catalog != target).
2. `get_table_schema(catalog="bmtct", schema_name="playground",
   table_name="caboodle_tests")`.
3. Observe `columns[0]:` even though the table has columns.

## Acceptance

- `get_table_schema(catalog=X, schema_name=Y, table_name=Z)` returns a
  populated `columns` list when the target table exists in `X.Y`, regardless
  of the engine's configured default catalog.
- Unit test covers the cross-catalog column-fetch path.
- Existing tests for column metadata still pass (MSSQL inspector path
  unchanged).

## Notes

- Not a Test 7 blocker — the 4 core gaps fixed in quick task 260428-l6x are
  verified passing. This is the next-in-line Databricks usability issue.
