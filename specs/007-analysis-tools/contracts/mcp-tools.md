# MCP Tool Contracts: Data-Exposure Analysis Tools

**Feature**: 007-analysis-tools | **Date**: 2026-03-03

## Tool 1: `get_column_info`

Retrieve per-column statistical profiles for a table.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| connection_id | `str` | Yes | — | Connection ID from `connect_database` |
| table_name | `str` | Yes | — | Table name to analyze |
| schema_name | `str` | No | `"dbo"` | Schema name |
| columns | `list[str] \| None` | No | `None` | Explicit list of column names to analyze. When provided, only these columns are analyzed. |
| column_pattern | `str \| None` | No | `None` | SQL LIKE pattern to filter column names (e.g., `"%_id"`). When provided, only matching columns are analyzed. |
| sample_size | `int` | No | `10` | Number of top frequent value samples to return for string columns. |

**Constraint**: If both `columns` and `column_pattern` are provided, `columns` takes precedence (pattern ignored).

### Return Value

JSON string containing:

```json
{
  "status": "success",
  "table_name": "orders",
  "schema_name": "dbo",
  "total_columns_analyzed": 3,
  "columns": [
    {
      "column_name": "order_id",
      "data_type": "int",
      "total_rows": 10000,
      "distinct_count": 10000,
      "null_count": 0,
      "null_percentage": 0.0,
      "numeric_stats": {
        "min_value": 1.0,
        "max_value": 10000.0,
        "mean_value": 5000.5,
        "std_dev": 2886.89
      }
    },
    {
      "column_name": "order_date",
      "data_type": "datetime",
      "total_rows": 10000,
      "distinct_count": 365,
      "null_count": 0,
      "null_percentage": 0.0,
      "datetime_stats": {
        "min_date": "2025-01-01T00:00:00",
        "max_date": "2025-12-31T23:59:59",
        "date_range_days": 364,
        "has_time_component": true
      }
    },
    {
      "column_name": "customer_name",
      "data_type": "varchar(100)",
      "total_rows": 10000,
      "distinct_count": 850,
      "null_count": 12,
      "null_percentage": 0.12,
      "string_stats": {
        "min_length": 3,
        "max_length": 87,
        "avg_length": 24.5,
        "sample_values": [["Smith", 42], ["Johnson", 38], ["Williams", 35]]
      }
    }
  ]
}
```

### Error Responses

| Condition | Response |
|-----------|----------|
| Invalid connection_id | `{"status": "error", "error_message": "Connection '...' not found"}` |
| Table not found | `{"status": "error", "error_message": "Table '...' not found in schema '...'"}` |
| Column not found (explicit list) | `{"status": "error", "error_message": "Column(s) not found: ..."}` |
| No columns match pattern | `{"status": "success", "columns": [], "total_columns_analyzed": 0}` (not an error) |

---

## Tool 2: `find_pk_candidates`

Identify columns that meet primary key candidacy criteria.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| connection_id | `str` | Yes | — | Connection ID from `connect_database` |
| table_name | `str` | Yes | — | Table to search for PK candidates |
| schema_name | `str` | No | `"dbo"` | Schema name |
| type_filter | `list[str] \| None` | No | `["int", "bigint", "smallint", "tinyint", "uniqueidentifier"]` | SQL types considered for structural PK candidacy. Set to empty list to disable type filtering. |

### Return Value

JSON string containing:

```json
{
  "status": "success",
  "table_name": "orders",
  "schema_name": "dbo",
  "candidates": [
    {
      "column_name": "order_id",
      "data_type": "int",
      "is_constraint_backed": true,
      "constraint_type": "PRIMARY KEY",
      "is_unique": true,
      "is_non_null": true,
      "is_pk_type": true
    },
    {
      "column_name": "tracking_number",
      "data_type": "bigint",
      "is_constraint_backed": false,
      "constraint_type": null,
      "is_unique": true,
      "is_non_null": true,
      "is_pk_type": true
    }
  ]
}
```

### Error Responses

| Condition | Response |
|-----------|----------|
| Invalid connection_id | `{"status": "error", "error_message": "Connection '...' not found"}` |
| Table not found | `{"status": "error", "error_message": "Table '...' not found in schema '...'"}` |
| No candidates found | `{"status": "success", "candidates": []}` (not an error) |

---

## Tool 3: `find_fk_candidates`

Discover potential foreign key relationships for a source column.

### Parameters

| Parameter | Type | Required | Default | Description |
|-----------|------|----------|---------|-------------|
| connection_id | `str` | Yes | — | Connection ID from `connect_database` |
| table_name | `str` | Yes | — | Source table name |
| column_name | `str` | Yes | — | Source column name |
| schema_name | `str` | No | `"dbo"` | Source schema name |
| target_schema | `str \| None` | No | `None` | Filter targets to this schema. When None and no other target filters, defaults to source schema. |
| target_tables | `list[str] \| None` | No | `None` | Explicit list of target table names |
| target_table_pattern | `str \| None` | No | `None` | SQL LIKE pattern for target table names |
| pk_candidates_only | `bool` | No | `True` | Only compare against PK-candidate columns in targets |
| include_overlap | `bool` | No | `False` | Compute value overlap metrics |
| limit | `int` | No | `100` | Maximum candidates to return (0 = no limit) |

### Return Value

JSON string containing:

```json
{
  "status": "success",
  "source": {
    "column_name": "customer_id",
    "table_name": "orders",
    "schema_name": "dbo",
    "data_type": "int"
  },
  "candidates": [
    {
      "source_column": "customer_id",
      "source_table": "orders",
      "source_schema": "dbo",
      "source_data_type": "int",
      "target_column": "id",
      "target_table": "customers",
      "target_schema": "dbo",
      "target_data_type": "int",
      "target_is_primary_key": true,
      "target_is_unique": true,
      "target_is_nullable": false,
      "target_has_index": true,
      "overlap_count": 950,
      "overlap_percentage": 95.0
    }
  ],
  "total_found": 1,
  "was_limited": false,
  "search_scope": "schema: dbo, pk_candidates_only: true"
}
```

### Error Responses

| Condition | Response |
|-----------|----------|
| Invalid connection_id | `{"status": "error", "error_message": "Connection '...' not found"}` |
| Table not found | `{"status": "error", "error_message": "Table '...' not found in schema '...'"}` |
| Column not found | `{"status": "error", "error_message": "Column '...' not found in table '...'"}` |
| No candidates found | `{"status": "success", "candidates": [], "total_found": 0, "was_limited": false}` (not an error) |

---

## Removed Tools

The following tools are removed (currently hidden/commented out):

| Tool | Source File | Action |
|------|------------|--------|
| `infer_relationships` | schema_tools.py | Remove function |
| `analyze_column` | query_tools.py | Remove function |
| `export_documentation` | doc_tools.py | Delete entire file |
| `load_cached_docs` | doc_tools.py | Delete entire file |
| `check_drift` | doc_tools.py | Delete entire file |

## Unchanged Tools

These active tools remain exactly as-is:

- `connect_database`
- `list_schemas`
- `list_tables`
- `get_table_schema`
- `get_sample_data`
- `execute_query`
