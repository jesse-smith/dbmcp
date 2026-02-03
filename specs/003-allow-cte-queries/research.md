# Research: Allow CTE Queries

**Feature**: 003-allow-cte-queries
**Date**: 2026-02-03

## Executive Summary

No external research required. This feature involves well-understood SQL parsing patterns with clear implementation paths based on existing codebase analysis.

## Research Areas

### 1. CTE Syntax Recognition

**Decision**: Use regex to detect `WITH` keyword followed by CTE definition, then find final operation keyword.

**Rationale**:
- CTE syntax is standardized: `WITH cte_name AS (...) [, cte_name AS (...)]* final_statement`
- The final statement determines the operation type (SELECT, INSERT, UPDATE, DELETE)
- A regex pattern can skip past CTE definitions to find the final keyword

**Alternatives Considered**:
- Full SQL parser (e.g., sqlparse library): Rejected - adds dependency for simple use case
- Tokenization: Rejected - regex is simpler and sufficient for keyword detection

**Implementation Pattern**:
```python
# Detect CTE and extract final operation
CTE_PATTERN = re.compile(
    r'^\s*WITH\s+.*?\)\s*(SELECT|INSERT|UPDATE|DELETE)\b',
    re.IGNORECASE | re.DOTALL
)
```

### 2. DDL/Dangerous Operation Blocklist

**Decision**: Define explicit blocklist of keywords that should always be blocked.

**Rationale**:
- Explicit blocklist is more secure than allowlist for non-SELECT operations
- Clear error messages can reference the specific blocked keyword
- Easy to extend if new dangerous patterns are identified

**Blocklist**:
```python
BLOCKED_KEYWORDS = {
    # DDL
    'CREATE', 'ALTER', 'DROP', 'TRUNCATE',
    # Execution
    'EXEC', 'EXECUTE',
    # Permissions
    'GRANT', 'REVOKE', 'DENY',
    # Transactions (could interfere with connection state)
    'BEGIN', 'COMMIT', 'ROLLBACK',
    # SQL Server specific
    'BACKUP', 'RESTORE', 'DBCC',
}
```

**Alternatives Considered**:
- Allowlist only (SELECT + controlled writes): Current approach - CTEs require extension
- No blocklist (rely on QueryType.OTHER): Current broken approach - doesn't distinguish safe CTEs from dangerous DDL

### 3. CTE + Write Operations Handling

**Decision**: Extract final operation from CTE, apply existing `allow_write` controls.

**Rationale**:
- `WITH cte AS (...) INSERT INTO ...` is a valid pattern
- Should follow same security model as `INSERT INTO ...`
- Existing `allow_write` parameter already handles this logic

**Example**:
```sql
-- Should be blocked by default (INSERT)
WITH source AS (SELECT * FROM staging)
INSERT INTO target SELECT * FROM source

-- Should be allowed with allow_write=True
WITH source AS (SELECT * FROM staging)
INSERT INTO target SELECT * FROM source
```

### 4. Row Limit Injection for CTE+SELECT

**Decision**: Modify `inject_row_limit` to handle CTE queries.

**Rationale**:
- CTEs ending in SELECT should respect row limits
- Injection point is in the final SELECT, not the CTE definitions
- Pattern: `WITH ... SELECT ...` → `WITH ... SELECT TOP(N) ...`

**Implementation Pattern**:
```python
# For SQL Server: Inject TOP after final SELECT in CTE
# WITH cte AS (...) SELECT * FROM cte
# → WITH cte AS (...) SELECT TOP (100) * FROM cte
```

## Codebase Analysis

### Current Query Classification Flow

1. `execute_query()` calls `parse_query_type(query_text)`
2. `parse_query_type()` strips comments, checks first keyword
3. `is_query_allowed()` checks if QueryType is permitted
4. If allowed, query executes; if SELECT, row limit injected

### Required Changes

| Component | Current Behavior | Required Change |
|-----------|------------------|-----------------|
| `parse_query_type()` | Returns OTHER for WITH | Detect CTE, return final operation type |
| `is_query_allowed()` | Blocks OTHER entirely | Add blocklist check before allowing |
| `inject_row_limit()` | Skips non-SELECT start | Handle CTE+SELECT pattern |

### Test Coverage Analysis

Existing tests in `tests/unit/test_query.py`:
- `TestQueryTypeParser`: Tests SELECT/INSERT/UPDATE/DELETE/OTHER classification
- `TestReadOnlyEnforcement`: Tests allow/block behavior
- `TestRowLimitInjection`: Tests TOP/LIMIT injection

New tests needed:
- CTE query type parsing (WITH...SELECT, WITH...INSERT, etc.)
- Blocklist enforcement (CREATE, DROP, etc.)
- Row limit injection for CTEs
- Multiple CTEs chained together
- CTE with comments

## Conclusion

Implementation is straightforward with no external research needed. Changes are localized to `src/db/query.py` with ~50 lines of modifications to three existing methods plus a class-level blocklist constant.
