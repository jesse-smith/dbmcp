# MCP Tool Docstring Review

Reviewed 2026-03-03 during 007-analysis-tools work. The three analysis tools
(`get_column_info`, `find_pk_candidates`, `find_fk_candidates`) were updated
with experimental caveats and typed JSON return schemas. The six existing tools
were not updated but have the following issues.

---

## `connect_database` (schema_tools.py:89)

- **Returns section is vague**: "JSON string with connection details including connection_id" — doesn't document `status`, `message`, `schema_count`, `has_cached_docs`
- **Enum-like fields undocumented**: `status` can be `"connected"` or `"failed"` (not `"success"`/`"error"` like the analysis tools — inconsistency worth noting)
- **`authentication_method`** enum values are documented in Args, good

## `list_schemas` (schema_tools.py:178)

- **Returns section is vague**: "JSON string with schema list" — doesn't document the per-schema fields (`schema_name`, `table_count`, `view_count`) or `total_schemas`

## `list_tables` (schema_tools.py:225)

- **Returns section is vague**: "JSON string with table list and pagination metadata" — doesn't document the per-table fields, pagination fields (`returned_count`, `total_count`, `offset`, `limit`, `has_more`), or the difference between `summary` and `detailed` output
- **Stale references**: "(T132)", "(T133)" are internal task IDs leaked into the docstring — an LLM caller doesn't need these
- **Enum-like fields**: `sort_by`, `sort_order`, `object_type`, `output_mode` are well-documented in Args but not in Returns
- **`table_type`** in the response (from `t.table_type.value`) is undocumented

## `get_table_schema` (schema_tools.py:311)

- **Returns section is vague**: "JSON string with table schema details" — this is the most complex response (columns, indexes, relationships) and has zero field documentation
- **Error format inconsistent**: uses `{"error": ...}` vs the analysis tools' `{"status": "error", "error_message": ...}`

## `get_sample_data` (query_tools.py:26)

- **Returns section is vague**: "JSON string with sample rows and metadata" — doesn't document `sample_id`, `table_id`, `actual_rows_returned`, `truncated_columns`, `sampled_at`, `rows` format
- **Error format inconsistent**: uses `{"error": ...}`

## `execute_query` (query_tools.py:110)

- **Returns section is the best of the bunch** — actually lists the fields with descriptions
- **Could benefit from `<type>` schema format** for consistency with the new tools
- **Enum-like fields**: `status` is `<"success" | "blocked" | "error">`, `query_type` is `<"select" | "insert" | "update" | "delete" | "other">` — documented in prose but not as enums

---

## Cross-cutting issues

- **Inconsistent error response format**: Three different patterns across the codebase:
  1. Analysis tools: `{"status": "error", "error_message": "..."}`
  2. Schema/query tools: `{"error": "..."}`
  3. `connect_database`: `{"status": "failed", "message": "..."}`
- **No typed return schemas** on any of the 6 older tools (the analysis tools are now the only ones that have them)

## Recommended approach

1. Update all 6 docstrings to use `<type>` placeholder JSON schemas matching the analysis tool format
2. Document error responses accurately as-is (don't change code behavior in a docstring pass)
3. Remove stale task ID references from `list_tables`
4. File a separate issue to unify the error response format across all tools
