---
created: 2026-04-28T18:30:00.000Z
title: Databricks list_schemas semantics + SHOW query blocking — two discovery gaps
area: databricks
source: Discovered during Phase 11 UAT Test 7 (2026-04-28)
files:
  - src/db/dialects/databricks.py (list_schemas implementation)
  - src/db/validation.py (query denylist)
---

## Problem

Two related issues observed while running UAT Test 7 against a live
Databricks workspace:

### 1. list_schemas with no catalog is misleading

Calling `list_schemas(connection_id=<databricks>)` with no `catalog` argument
returned a single row: `main` (0 tables, 0 views). That matches the `catalog`
default in `DatabricksConnectionConfig` (`"main"`), and the workspace does
not actually have a catalog named `main`.

Interpretation: the no-catalog path appears to return the *configured default
catalog as if it were a schema*, rather than introspecting schemas of that
catalog or listing available catalogs. The returned `table_count`/`view_count`
of `0` is consistent with "no catalog actually exists with this name" rather
than "this catalog has no schemas".

Expected behavior candidates (pick one, document it):
- (a) When no `catalog` is provided, use the configured default catalog and
  return its schemas via `SHOW SCHEMAS IN <catalog>`. Error cleanly if the
  catalog doesn't exist.
- (b) When no `catalog` is provided, return the list of available catalogs
  (via `SHOW CATALOGS`) so callers can discover what to pass.
- (c) Some hybrid — e.g., catalogs at top level, schemas when `catalog` is
  given (mirrors MSSQL's database/schema relationship).

Whichever is chosen, the current "silently returns configured default catalog
as a schema with zero tables" is misleading and should be fixed.

### 2. SHOW CATALOGS / SHOW SCHEMAS blocked by query validator

`execute_query("SHOW CATALOGS")` returns:
> Query blocked: OPERATIONAL - SHOW operations are not permitted

This is the generic denylist applied uniformly across dialects. For MSSQL,
blocking SHOW is fine — it doesn't exist. For Databricks, `SHOW CATALOGS` /
`SHOW SCHEMAS` / `SHOW TABLES` / `DESCRIBE` are the primary discovery
primitives. The dialect uses them internally (e.g., `list_schemas` builds
`SHOW SCHEMAS IN <catalog>`), but users can't run them ad-hoc.

Interpretation: the denylist should be dialect-aware. For Databricks, SHOW
and DESCRIBE should be allowed (or at least SHOW CATALOGS, which is pure
metadata discovery and has no side effects).

Related concern: if internal dialect queries go through the same validator
(unlikely but worth checking), Databricks introspection would silently
partially-fail today.

## Solution candidates

1. **list_schemas fix**: rework `DatabricksDialect.list_schemas` (or whichever
   method serves the MCP call) to use `SHOW SCHEMAS IN <catalog>` with a
   clear error path when the catalog doesn't exist. Decide and document what
   no-catalog means.
2. **Validator dialect awareness**: thread the connection's dialect into the
   query validator. For Databricks, allow at minimum `SHOW CATALOGS`,
   `SHOW SCHEMAS`, `SHOW TABLES`, `SHOW COLUMNS`, `DESCRIBE`, `DESCRIBE
   EXTENDED`. The denylist for read-only discovery primitives should be
   per-dialect.
3. **Discovery tool**: add a `list_catalogs` MCP tool for Databricks (no-op
   or error for dialects without catalogs). Mirrors the existing
   `list_schemas` / `list_tables` progression.

## Acceptance

- `list_schemas(connection_id=<databricks>)` with no catalog arg either:
  returns schemas of the configured default catalog AND raises a clean error
  if that catalog doesn't exist, OR returns the list of available catalogs.
  Documented in the tool's docstring either way.
- `execute_query("SHOW CATALOGS")` against a Databricks connection succeeds.
- New unit tests pin both behaviors.

## Notes

- Workaround used for Phase 11 UAT Test 7: passed `catalog="bmtct"` explicitly.
- Does not block Test 7 completion; does block ergonomic Databricks usage.

## Update (2026-04-28, later): third gap — get_table_schema catalog plumbing

`src/mcp_server/schema_tools.py:443` calls
`metadata_svc.table_exists(table_name, schema_name)` — no `catalog` argument.
The subsequent `metadata_svc.get_table_schema(...)` at line 449 DOES pass
catalog, but the existence check fails first, returning "Table 'X.Y' not
found" regardless of whether the table exists in the specified catalog.

Reproduction:
- List tables: `list_tables(catalog="bmtct", schema_filter=["playground"])`
  returns `playground.caboodle_tests` ✓
- Get schema: `get_table_schema(catalog="bmtct", schema_name="playground",
  table_name="caboodle_tests")` returns
  `"Table 'playground.caboodle_tests' not found"` ✗

Fix: thread `catalog` into `MetadataService.table_exists` (and the underlying
dialect method) the same way `get_table_schema` already does. Existence check
should use the fully-qualified name when a catalog is provided.

Files:
- `src/mcp_server/schema_tools.py:443`
- `src/db/metadata.py` (MetadataService.table_exists)
- `src/db/dialects/databricks.py` (any dialect-level table_exists override)
