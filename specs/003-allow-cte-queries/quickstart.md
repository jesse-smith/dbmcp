# Quickstart: Allow CTE Queries

**Feature**: 003-allow-cte-queries
**Date**: 2026-02-03

## What This Feature Does

Enables Common Table Expression (CTE) queries to execute through the MCP server. CTEs are SQL queries that start with the `WITH` keyword and are commonly used for:

- Recursive queries (organizational hierarchies, bill of materials)
- Breaking complex queries into readable steps
- Temporary result sets within a single query

## Before This Feature

```python
# This query was BLOCKED
query = """
WITH recent_orders AS (
    SELECT * FROM orders WHERE order_date > '2026-01-01'
)
SELECT * FROM recent_orders
"""

result = query_service.execute_query(
    connection_id="abc123",
    query_text=query,
    row_limit=100
)
# result.is_allowed = False
# result.error_message = "Only SELECT queries are allowed..."
```

## After This Feature

```python
# CTE queries now WORK
query = """
WITH recent_orders AS (
    SELECT * FROM orders WHERE order_date > '2026-01-01'
)
SELECT * FROM recent_orders
"""

result = query_service.execute_query(
    connection_id="abc123",
    query_text=query,
    row_limit=100
)
# result.is_allowed = True
# result.rows_affected = <number of rows>
```

## Usage Examples

### Simple CTE

```sql
WITH active_users AS (
    SELECT id, name FROM users WHERE status = 'active'
)
SELECT * FROM active_users
```

### Multiple CTEs

```sql
WITH
    orders_2026 AS (SELECT * FROM orders WHERE YEAR(order_date) = 2026),
    high_value AS (SELECT * FROM orders_2026 WHERE total > 1000)
SELECT COUNT(*) as count FROM high_value
```

### Recursive CTE (Hierarchies)

```sql
WITH org_hierarchy AS (
    -- Base case: top-level managers
    SELECT id, name, manager_id, 0 as level
    FROM employees
    WHERE manager_id IS NULL

    UNION ALL

    -- Recursive case: employees under each manager
    SELECT e.id, e.name, e.manager_id, h.level + 1
    FROM employees e
    INNER JOIN org_hierarchy h ON e.manager_id = h.id
)
SELECT * FROM org_hierarchy ORDER BY level, name
```

### CTE with INSERT (requires allow_write=True)

```sql
WITH source_data AS (
    SELECT * FROM staging_table WHERE validated = 1
)
INSERT INTO production_table
SELECT * FROM source_data
```

```python
# Must explicitly enable write operations
result = query_service.execute_query(
    connection_id="abc123",
    query_text=query,
    row_limit=100,
    allow_write=True  # Required for INSERT/UPDATE/DELETE
)
```

## What's Still Blocked

The following operations remain blocked for security:

| Operation | Example | Error Message |
|-----------|---------|---------------|
| CREATE | `CREATE TABLE ...` | "Query blocked: CREATE operations are not permitted" |
| DROP | `DROP TABLE ...` | "Query blocked: DROP operations are not permitted" |
| ALTER | `ALTER TABLE ...` | "Query blocked: ALTER operations are not permitted" |
| TRUNCATE | `TRUNCATE TABLE ...` | "Query blocked: TRUNCATE operations are not permitted" |
| EXEC | `EXEC sp_help` | "Query blocked: EXEC operations are not permitted" |
| GRANT/REVOKE | `GRANT SELECT ...` | "Query blocked: GRANT operations are not permitted" |

## Row Limits

Row limits are automatically applied to CTE queries ending in SELECT:

```python
# Row limit is applied to the final SELECT
result = query_service.execute_query(
    connection_id="abc123",
    query_text="WITH cte AS (SELECT * FROM big_table) SELECT * FROM cte",
    row_limit=100  # Only returns first 100 rows
)
```

## Testing Your CTEs

Run the unit tests to verify CTE handling:

```bash
pytest tests/unit/test_query.py -k "cte" -v
```
