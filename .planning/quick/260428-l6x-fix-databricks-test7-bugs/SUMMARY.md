---
status: complete
plan: .planning/quick/260428-l6x-fix-databricks-test7-bugs/PLAN.md
commits:
  - f651c2b
  - 16c62c3
  - 1c07dfd
started: 2026-04-28T20:15:00Z
completed: 2026-04-28T20:55:00Z
---

# Quick Task 260428-l6x — Summary

## What changed

Four Databricks bugs discovered during Phase 11 UAT Test 7 are now fixed.

### Gap #2 — Validator allows SHOW/DESCRIBE for Databricks
- New `safe_operational_commands: frozenset[str]` property on
  `DialectStrategy`. Databricks returns `{SHOW, DESCRIBE, DESC, EXPLAIN}`;
  MSSQL and Generic return empty.
- `validate_query` accepts a `safe_operational_commands` kwarg. When a
  parsed `exp.Command`'s verb is in the allowlist, it's passed. KILL and
  stored-procedure paths are untouched.
- `QueryExecutor.execute_query` threads the dialect's allowlist through.

### Gap #3 — `table_exists` accepts catalog
- `MetadataService.table_exists` now has an optional `catalog: str | None`.
  For Databricks with catalog, issues `SHOW TABLES IN `catalog`.`schema`` and
  checks row[1] (`tableName`) for a match. Non-Databricks path unchanged.
- `schema_tools.get_table_schema` now passes `catalog=catalog` to
  `table_exists`, unblocking `get_table_schema(catalog="bmtct", schema="playground", ...)`.

### Gap #4 — list_schemas populates table/view counts
- `_list_schemas_databricks` now runs a single grouped query against
  `<catalog>.information_schema.tables` after the `SHOW SCHEMAS IN` and
  merges counts in by schema name. On failure (permissions, older workspace)
  logs a warning and falls back to zero counts — never raises.

### Gap #1 — list_schemas no-catalog semantics
- When dialect is Databricks and `catalog is None`, extract the configured
  catalog from `engine.url.query["catalog"]` (which DatabricksDialect sets
  when building the URL) and route to `_list_schemas_databricks`. Falls back
  to `"main"` if not present.
- Replaces the previous behavior of falling through to the generic inspector,
  which returned the default catalog name as a single pseudo-schema with zero
  tables.
- Docstrings updated on both the metadata method and the MCP tool.

## Files touched

- `src/db/dialects/protocol.py` — added `safe_operational_commands`
- `src/db/dialects/databricks.py` — implements allowlist
- `src/db/dialects/mssql.py` — empty allowlist
- `src/db/dialects/generic.py` — empty allowlist
- `src/db/validation.py` — new kwarg, threaded through `_check_command`
- `src/db/query.py` — passes dialect allowlist to `validate_query`
- `src/db/metadata.py` — `table_exists` catalog param;
  `_list_schemas_databricks` counts + no-catalog routing;
  new `_databricks_default_catalog` helper
- `src/mcp_server/schema_tools.py` — passes catalog to `table_exists`;
  docstring updates
- Tests: `tests/unit/test_validation.py`, `tests/unit/test_metadata.py`,
  `tests/unit/test_dialect_protocol.py`

## Verification

- Full unit suite: 824 passed, 37 skipped (was 812/37; +12 new tests).
- Ruff: zero warnings on all changed files. (Pre-existing warnings in
  unrelated paths like `tests/staleness/`, `src/metrics.py`, and
  `tests/integration/test_real_transpilation.py` are unchanged and out of scope.)
- Live MCP verification: pending user restart.

## Test 7 sub-checks impacted

| Sub-check | Before | After |
|---|---|---|
| `connect_database(connection_name="databricks-test")` | ✅ | ✅ |
| `list_schemas(connection_id=...)` without catalog | ❌ misleading | ✅ uses engine default + real counts |
| `list_schemas(connection_id=..., catalog="bmtct")` | ⚠️ zero counts | ✅ populated counts |
| `get_table_schema(catalog="bmtct", schema="playground", table="caboodle_tests")` | ❌ blocked | ✅ should pass |
| `execute_query("SHOW CATALOGS")` | ❌ blocked | ✅ passes validator |

## Known follow-ups

- "Unexpected error:" prefix on ImportError (separate todo, still open).
- Databricks test-coverage audit (separate todo, still open).
- Potential future: MCP `list_catalogs` tool (optional, deferred).
