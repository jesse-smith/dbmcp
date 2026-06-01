---
quick_id: 260428-l6x
slug: fix-databricks-test7-bugs
created: 2026-04-28T20:15:00Z
---

# Quick Task: Fix Databricks bugs found during Phase 11 UAT Test 7

## Scope

Fix four related Databricks bugs captured in
`.planning/todos/pending/2026-04-28-databricks-list-schemas-and-show-query-gaps.md`
plus the new 0-count observation:

1. **list_schemas no-catalog misleading** — returns configured default catalog as a schema with 0 tables.
2. **Validator blocks SHOW/DESCRIBE** — dialect-agnostic denylist breaks Databricks discovery primitives.
3. **get_table_schema catalog plumbing** — `table_exists` doesn't accept `catalog`, so it fails even when the table exists.
4. **0 table/view counts** — `_list_schemas_databricks` hardcodes both to 0.

## Implementation order (TDD per fix)

### Task 1 — Validator dialect-aware safe operational commands (#2)
- Extend `DialectStrategy` protocol with `safe_operational_commands: frozenset[str]` property.
- MSSQL, Generic: `frozenset()`.
- Databricks: `frozenset({"SHOW", "DESCRIBE", "DESC", "EXPLAIN"})`.
- Add `safe_operational_commands` kwarg to `validate_query`. In `_check_command`, if `cmd_name` is in the set, return no denial.
- Plumb through `QueryExecutor.execute_query` call site (src/db/query.py:543).
- TDD:
  - `test_validation.py`: SHOW CATALOGS passes with databricks allowlist; SHOW CATALOGS fails without; validate that MSSQL SHOW still blocked.

### Task 2 — table_exists catalog threading (#3)
- Signature: `def table_exists(self, table_name, schema_name="dbo", catalog: str | None = None) -> bool`.
- For Databricks with catalog: use raw SQL `SHOW TABLES IN <catalog>.<schema>` and check `tableName` column for match.
- For non-Databricks or no-catalog: current inspector path.
- Fix `schema_tools.py:443`: pass `catalog=catalog`.
- TDD:
  - Unit test: `test_metadata.py::test_table_exists_databricks_catalog` — mocks engine, asserts correct SQL issued with catalog.
  - Unit test: `test_table_exists_non_databricks_ignores_catalog` — MSSQL path uses inspector only.

### Task 3 — Populate table/view counts (#4)
- Rewrite `_list_schemas_databricks`: first `SHOW SCHEMAS IN <catalog>` for the schema list, then one query against `<catalog>.information_schema.tables` to get counts per schema.
- Aggregation: `table_count = SUM(CASE WHEN table_type='VIEW' THEN 0 ELSE 1 END)`, `view_count = SUM(CASE WHEN table_type='VIEW' THEN 1 ELSE 0 END)`.
- If information_schema query fails (permissions, older workspace), log and fall back to zero counts (never raise).
- TDD:
  - Unit test: mocks execute() to return schema list then count rows; verifies merged counts.
  - Unit test: mocks execute() failure on counts query; verifies schemas still returned with 0 counts.

### Task 4 — list_schemas no-catalog semantics (#1)
- In `MetadataService.list_schemas`: when `self._dialect.name == "databricks"` and `catalog is None`, extract catalog from `self.engine.url.query.get("catalog", "main")` and route to `_list_schemas_databricks`.
- Update docstring on both `list_schemas` (metadata + schema_tools) to document this behavior.
- TDD:
  - Unit test: `test_list_schemas_databricks_no_catalog_uses_engine_catalog` — mocks engine URL with catalog=foo, asserts SHOW SCHEMAS IN `foo` was issued.

## Files touched

- `src/db/dialects/protocol.py` — add `safe_operational_commands`
- `src/db/dialects/databricks.py` — implement safe_operational_commands
- `src/db/dialects/mssql.py` — implement safe_operational_commands (empty)
- `src/db/dialects/generic.py` — implement safe_operational_commands (empty)
- `src/db/validation.py` — accept new kwarg, check allowlist in `_check_command`
- `src/db/query.py` — thread dialect's safe_operational_commands into validate_query
- `src/db/metadata.py` — `_list_schemas_databricks` count population; `table_exists` catalog param; `list_schemas` no-catalog routing
- `src/mcp_server/schema_tools.py` — pass catalog to `table_exists`; update docstrings
- Tests in `tests/unit/`

## Success criteria

- All existing 812 unit tests still pass.
- New tests cover all four fixes.
- Live MCP verification (user-driven): SHOW CATALOGS works; list_schemas with no catalog uses engine default and shows non-zero counts; get_table_schema with catalog="bmtct" schema="playground" table="caboodle_tests" returns the table.

## Non-goals

- Changing the `list_tables` 0-count behavior for Databricks (out of scope — Test 7 only surfaced `list_schemas`).
- Adding a new MCP `list_catalogs` tool (future work).
- Re-doing the test coverage audit (tracked as separate todo).
