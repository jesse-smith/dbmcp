# Validation Contract

**Feature**: 005-denylist-query-validation
**Date**: 2026-02-26

## Public Interface: QueryService

The validation interface is internal to the `QueryService` class. The MCP server is the only external consumer, and it calls `execute_query()` which handles validation internally.

### Changed Method: execute_query

```
execute_query(connection_id, query_text, row_limit=1000, allow_write=False) -> Query
```

**Behavior change**: Validation is now AST-based instead of keyword-based. The method signature, return type, and external contract are unchanged.

**Result contract** (unchanged):
- `Query.is_allowed = True` + results: query was safe and executed
- `Query.is_allowed = False` + `error_message`: query was denied
- `Query.is_allowed = True` + `error_message`: query was safe but execution failed

**New addition**: `Query.denial_reasons` populated when denied, providing structured categorization. The `error_message` string is still populated for backward compatibility.

### New Internal Function: validate_query

```
validate_query(sql: str, allow_write: bool = False) -> ValidationResult
```

Pure function. No side effects. No database connection required.

**Input**: Raw SQL text + write permission flag
**Output**: ValidationResult (is_safe: bool, reasons: list[DenialReason])

**Validation rules** (in order of evaluation):
1. Parse SQL with sqlglot (tsql dialect)
2. If parse fails → Denied(PARSE_FAILURE)
3. For each statement in batch:
   a. Check if statement type is in denied set
   b. For Execute statements: check procedure name against safe allowlist
   c. For Select statements: check for SELECT INTO
   d. Walk nested statements (BEGIN/END, IF/ELSE, WHILE) recursively
4. If allow_write=True: filter out DML denials (INSERT, UPDATE, DELETE, MERGE)
5. If any denials remain → Denied with all reasons
6. Otherwise → Safe

### MCP Tool Response Format (unchanged)

The `execute_query` MCP tool response JSON is unchanged:

```json
{
  "status": "blocked",
  "query_id": "...",
  "query_type": "other",
  "is_allowed": false,
  "error_message": "Query blocked: DDL - CREATE TABLE operations are not permitted"
}
```

The error_message now includes the denial category prefix for clarity.
