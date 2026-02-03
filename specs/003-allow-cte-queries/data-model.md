# Data Model: Allow CTE Queries

**Feature**: 003-allow-cte-queries
**Date**: 2026-02-03

## Overview

This feature does not introduce new data entities. It modifies the behavior of existing query classification and execution logic.

## Existing Entities (Unchanged)

### QueryType (Enum)

```python
class QueryType(str, Enum):
    SELECT = "select"
    INSERT = "insert"
    UPDATE = "update"
    DELETE = "delete"
    OTHER = "other"
```

**Note**: The `OTHER` type will now only apply to blocked DDL/dangerous operations. CTEs will be classified by their final operation type (SELECT, INSERT, UPDATE, or DELETE).

### Query (Dataclass)

The `Query` model remains unchanged. CTE queries will populate the same fields:
- `query_type`: Will reflect the final operation type (SELECT/INSERT/UPDATE/DELETE)
- `is_allowed`: Based on operation type and `allow_write` flag
- `error_message`: Clear message if query is blocked

## New Constants

### BLOCKED_KEYWORDS

A class-level constant in `QueryService` defining keywords that should always be blocked:

```python
BLOCKED_KEYWORDS: frozenset[str] = frozenset({
    # DDL operations
    'CREATE', 'ALTER', 'DROP', 'TRUNCATE',
    # Code execution
    'EXEC', 'EXECUTE',
    # Permission operations
    'GRANT', 'REVOKE', 'DENY',
    # SQL Server specific
    'BACKUP', 'RESTORE', 'DBCC',
})
```

## Behavioral Changes

### Query Classification

| Query Pattern | Current Classification | New Classification |
|---------------|----------------------|-------------------|
| `SELECT ...` | SELECT | SELECT (unchanged) |
| `INSERT ...` | INSERT | INSERT (unchanged) |
| `WITH ... SELECT ...` | OTHER (blocked) | SELECT (allowed) |
| `WITH ... INSERT ...` | OTHER (blocked) | INSERT (allow_write controlled) |
| `CREATE TABLE ...` | OTHER (blocked) | OTHER (blocked, explicit message) |
| `DROP TABLE ...` | OTHER (blocked) | OTHER (blocked, explicit message) |
| `EXEC ...` | OTHER (blocked) | OTHER (blocked, explicit message) |

### Error Messages

Blocked queries will now include the specific blocked keyword:

- **Before**: "Only SELECT queries are allowed by default. DDL and other statements are not supported."
- **After**: "Query blocked: CREATE operations are not permitted."
