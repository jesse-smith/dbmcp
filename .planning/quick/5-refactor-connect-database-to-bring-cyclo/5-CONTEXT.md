# Quick Task 5: Refactor connect_database to bring cyclomatic complexity under 15 - Context

**Gathered:** 2026-03-11
**Status:** Ready for planning

<domain>
## Task Boundary

Refactor the connect_database function in src/mcp_server/schema_tools.py to bring cyclomatic complexity from 48 down to under 15, fixing CI failures caused by the complexity check in scripts/check_complexity.py.

</domain>

<decisions>
## Implementation Decisions

### Decomposition Strategy
- Extract connection-resolution logic into private helper functions in the same file (schema_tools.py)
- Matches existing patterns like _validate_list_tables_params and _build_table_entry

### Parameter Passing Style
- Use a dataclass (ResolvedConnectionParams) to group the ~9 resolved connection values
- Provides type safety, avoids long argument lists, and makes the flow clearer

### Error Handling Pattern
- Consolidate the repeated try/except pattern (ValueError/SQLAlchemyError/Exception) into a shared helper or decorator
- This pattern is duplicated across connect_database, list_schemas, list_tables, and get_table_schema
- Reduces boilerplate and keeps error handling consistent

</decisions>

<specifics>
## Specific Ideas

- Current complexity score: 48 (max allowed: 15)
- Main complexity drivers: config merging branches (named connection vs explicit args), per-parameter if/else chains, env var resolution with error returns, validation, multiple exception handlers
- The dataclass should live in src/models/schema.py or alongside the helpers in schema_tools.py
- Error handler should work with the existing encode_response + logger pattern

</specifics>
