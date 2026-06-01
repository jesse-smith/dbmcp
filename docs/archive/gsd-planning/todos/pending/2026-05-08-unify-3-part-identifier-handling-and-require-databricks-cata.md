---
created: 2026-05-08T18:11:45.982Z
title: Unify 3-part identifier handling and require Databricks catalog
area: database
files:
  - src/db/connection.py
  - src/db/dialects/registry.py
  - src/db/dialects/protocol.py
  - src/db/dialects/databricks.py
  - src/db/dialects/generic.py
  - src/tools/schema_tools.py
  - src/tools/analysis_tools.py
---

## Problem

Databricks stress test on 2026-05-08 against `dbmcp-test` surfaced a cluster of
related issues rooted in inconsistent handling of the 3-part identifier
(`catalog.schema.table`) on Databricks versus 2-part (`schema.table`) on MSSQL
versus 1-part on generic/SQLite.

**Concrete issues observed:**

1. **`connect_database` accepts Databricks connections with no catalog in the
   URL.** The server-side session default (`main` on Unity Catalog, sometimes
   inaccessible) silently becomes the catalog. Every downstream tool then
   fails or silently degrades. MSSQL, by contrast, forces a database in the
   SQLAlchemy URL — so Databricks is the outlier.
2. **`list_schemas` silently returns catalog names when the default catalog is
   inaccessible.** First observed run showed 20 entries labeled `schema_name`
   that were actually the output of `SHOW CATALOGS`. Fallback masked a
   `NO_SUCH_CATALOG_EXCEPTION` and made the misconfig look fine while every
   downstream tool failed.
3. **`get_sample_data` and `get_column_info` do not accept a `catalog` param.**
   They hardcode the connection-default catalog (via `SHOW TABLES FROM
   main.<schema>` in `get_column_info`, and via SQLAlchemy metadata in
   `get_sample_data`). No way to override.
4. **`schema_name='dbo'` default leaks into Databricks.** `dbo` is MSSQL-
   specific; should not be a cross-dialect default.
5. **No consistent rule for when `table_name` may carry leading segments
   (e.g. `catalog.schema.table`) versus when `schema_name` / `catalog` should
   fill in.** Currently `get_sample_data` treats a dotted `table_name` as a
   literal table name (prepending `dbo.` and bracketing the whole thing).

All five were verified by reconnecting with `catalog=bmtct` in the connection
config — once the default catalog was correct, the four affected tools
succeeded. So the bugs are scoping/defaulting bugs, not query-construction
bugs, except for issue 5.

## Solution

Design agreed during discussion (see chat for 2026-05-08):

**A. Require catalog at connect time for Databricks.**

- Validate in `connect_database` that a Databricks SQLAlchemy URL includes a
  `catalog` query param (or equivalent for the named-connection config path).
- On failure, fail fast with an error that lists accessible catalogs from
  `SHOW CATALOGS` (that query works even when the session default is broken).
- Treat this as analogous to MSSQL's database-in-URL requirement.
- Drop the silent catalog-listing fallback path in `list_schemas` — with
  fail-fast at connect time, no tool should ever reach that code with a bad
  default.

**B. Unified identifier resolver across tools.**

Per-dialect identifier depth:

| Dialect | Max parts |
|---|---|
| Databricks | 3 (catalog.schema.table) |
| MSSQL | 2 (schema.table) |
| Generic/SQLite | 1 (table) |

Parameter semantics (uniform across the five affected tools):

- `table_name` — may contain 1..N parts, where N = dialect max. More parts →
  error.
- `schema_name` — single identifier, no dots. Fills the schema slot if
  `table_name` does not.
- `catalog` — single identifier, no dots. Databricks-only. Passing it on
  MSSQL/generic → error (not silently ignored). Must be exposed on
  `get_sample_data` and `get_column_info` (currently missing).

Resolution order per slot:

1. Leading segment of `table_name` (if present)
2. Matching explicit param (if provided)
3. Connection default

Conflict handling: if `table_name` and the matching explicit param both
specify the same slot and disagree, **error** with a message naming the
conflict. No silent "most-specific wins."

**C. Remove `schema_name='dbo'` as a universal default.**

- Each dialect should advertise its own default schema (if any) on the
  DialectStrategy protocol.
- MSSQL → `dbo`. Databricks → `default` (or whatever the session default
  resolves to). Generic → no default, schema must be supplied or irrelevant.
- Tool signatures stop hardcoding `dbo`.

**D. Scope of the refactor.**

Tools needing the resolver:

- `list_tables`, `list_schemas`, `get_table_schema` — already accept
  `catalog`; add dotted-name parsing + conflict validation + dialect-aware
  defaults.
- `get_sample_data`, `get_column_info` — add `catalog` param, the same
  resolver, and dialect-aware schema defaults.

Plus `connect_database` for the catalog-required check.

Implementation: put parsing + validation in a single helper keyed on the
dialect strategy (free function or dialect method). Every tool routes through
it. One test file covers the full resolution matrix.

**E. Explicitly out of scope (separate follow-up).**

Cross-dialect `list_catalogs`/`list_databases` tool (SSMS-style database
enumeration via `sys.databases` on MSSQL and `SHOW CATALOGS` on Databricks)
is a tangent. Captured as a separate note — see
`.planning/notes/2026-05-08-think-cross-dialect-catalog-enumeration.md`.

## Acceptance

- `connect_database` fails fast on Databricks URLs lacking a catalog, with
  the error listing accessible catalogs.
- All five tools accept dotted `table_name` per dialect depth and validate
  conflicts against explicit params.
- `get_sample_data` and `get_column_info` accept an optional `catalog` param
  on Databricks; error on MSSQL/generic.
- No tool hardcodes `dbo` as a cross-dialect default.
- `list_schemas` no longer silently falls through to catalog enumeration.
- Full test suite green; new test file covers the resolution matrix
  (in-dialect, cross-dialect rejection, conflict detection, default filling).

## Priority

Medium. Not blocking core MSSQL workflow, but Databricks users will hit
issues 3 and 4 on first contact. Bundle into one PR to keep the
identifier-resolution contract consistent.
