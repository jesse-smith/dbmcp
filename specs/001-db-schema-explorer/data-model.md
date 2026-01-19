# Data Model: Database Schema Explorer

**Feature**: 001-db-schema-explorer
**Date**: 2026-01-19
**Source**: Extracted from [spec.md](./spec.md) Requirements section

## Overview

This document defines the core entities for the Database Schema Explorer MCP Server. All entities are internal data structures - no persistent database storage required (except for local documentation cache files).

---

## Entities

### 1. Connection

Represents a database connection configuration.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `connection_id` | string | Yes | Unique | Hash of server+database+user |
| `server` | string | Yes | Non-empty | SQL Server host (hostname or IP) |
| `database` | string | Yes | Non-empty | Database name |
| `port` | integer | No | 1-65535 | Port (default: 1433) |
| `authentication_method` | enum | Yes | ['sql', 'windows', 'azure_ad'] | Auth method |
| `username` | string | Conditional | Non-empty if sql/azure_ad | Username for authentication |
| `password` | string | Conditional | Never logged | Password for authentication |
| `trust_server_cert` | boolean | No | - | Trust server cert (default: false) |
| `connection_timeout` | integer | No | 5-300 | Timeout in seconds (default: 30) |
| `created_at` | datetime | Yes | ISO 8601 | Connection creation time |

**Relationships:**
- One Connection → Many Schemas
- One Connection → One DocumentationCache

**State Transitions:**
```
disconnected → connecting → connected → disconnected
                     ↓
                  failed
```

**Validation Rules:**
- `password` MUST NOT be logged or exported to documentation (NFR-005)
- `connection_id` computed as: `sha256(server + database + username)`
- `authentication_method='sql'` requires `username` and `password`
- `authentication_method='windows'` requires neither username nor password

---

### 2. Schema

A namespace grouping of database objects (tables, views) within a database.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `schema_id` | string | Yes | Unique | connection_id + schema_name |
| `connection_id` | string | Yes | FK to Connection | Parent connection |
| `schema_name` | string | Yes | Non-empty | Schema name (e.g., 'dbo', 'sales') |
| `table_count` | integer | Yes | ≥0 | Number of tables in schema |
| `view_count` | integer | Yes | ≥0 | Number of views in schema |
| `last_scanned` | datetime | Yes | ISO 8601 | Last metadata scan time |

**Relationships:**
- Many Schemas → One Connection
- One Schema → Many Tables

**Validation Rules:**
- `schema_name` case-sensitive on Linux SQL Server, case-insensitive on Windows
- Default schema is 'dbo' if none specified

---

### 3. Table

A database table with columns, indexes, and relationships.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `table_id` | string | Yes | Unique | schema_id + table_name |
| `schema_id` | string | Yes | FK to Schema | Parent schema |
| `table_name` | string | Yes | Non-empty | Table name |
| `table_type` | enum | Yes | ['table', 'view'] | Object type |
| `row_count` | integer | No | ≥0 | Approximate row count (NULL if inaccessible) |
| `row_count_updated` | datetime | No | ISO 8601 | When row count last updated |
| `has_primary_key` | boolean | Yes | - | Whether table has PK |
| `last_modified` | datetime | No | ISO 8601 | Last DDL modification (if available) |
| `access_denied` | boolean | Yes | - | True if user lacks SELECT permission |

**Relationships:**
- Many Tables → One Schema
- One Table → Many Columns
- One Table → Many Indexes
- One Table → Many Relationships (as source or target)

**Validation Rules:**
- `row_count` computed via `SELECT COUNT(*)` or `sys.dm_db_partition_stats` for performance
- If `access_denied=true`, no metadata retrieval attempted (User Story edge case)
- Tables with 0 rows still valid (edge case)

---

### 4. Column

A table column with name, data type, nullability, constraints, and inferred purpose.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `column_id` | string | Yes | Unique | table_id + column_name |
| `table_id` | string | Yes | FK to Table | Parent table |
| `column_name` | string | Yes | Non-empty | Column name |
| `ordinal_position` | integer | Yes | ≥1 | Column position in table |
| `data_type` | string | Yes | Non-empty | SQL Server data type (e.g., 'INT', 'VARCHAR(50)') |
| `max_length` | integer | No | ≥0 | Max length for strings/binary |
| `is_nullable` | boolean | Yes | - | Whether NULL values allowed |
| `default_value` | string | No | - | Default value expression |
| `is_identity` | boolean | Yes | - | Whether auto-increment identity |
| `is_computed` | boolean | Yes | - | Whether computed column |
| `is_primary_key` | boolean | Yes | - | Whether part of PK |
| `is_foreign_key` | boolean | Yes | - | Whether declared FK |
| `distinct_count` | integer | No | ≥0 | Number of distinct values (if analyzed) |
| `null_percentage` | float | No | 0.0-100.0 | Percentage of NULL values (if analyzed) |
| `inferred_purpose` | string | No | - | Inferred purpose (e.g., 'enum', 'id', 'amount') |
| `inferred_confidence` | float | No | 0.0-1.0 | Confidence in inferred purpose |

**Relationships:**
- Many Columns → One Table
- One Column → Many Relationships (as source or target column)

**Validation Rules:**
- `data_type` includes precision/scale for numeric types (e.g., 'DECIMAL(10,2)')
- `is_primary_key=true` implies `is_nullable=false`
- `distinct_count` and `null_percentage` only populated after column analysis (User Story 5)
- `inferred_purpose` values: 'id', 'enum', 'status', 'flag', 'amount', 'quantity', 'percentage', 'timestamp', 'unknown'

---

### 5. Index

A database index on one or more columns.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `index_id` | string | Yes | Unique | table_id + index_name |
| `table_id` | string | Yes | FK to Table | Parent table |
| `index_name` | string | Yes | Non-empty | Index name |
| `is_unique` | boolean | Yes | - | Whether unique index |
| `is_primary_key` | boolean | Yes | - | Whether PK constraint |
| `is_clustered` | boolean | Yes | - | Whether clustered index |
| `columns` | array[string] | Yes | Non-empty | Ordered list of column names |
| `included_columns` | array[string] | No | - | Included (non-key) columns |

**Relationships:**
- Many Indexes → One Table

**Validation Rules:**
- `columns` order matters (composite index column order)
- `is_primary_key=true` implies `is_unique=true`
- Clustered index can be non-unique on SQL Server

---

### 6. Relationship

A join relationship between tables (declared FK or inferred).

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `relationship_id` | string | Yes | Unique | Generated hash of source+target |
| `source_table_id` | string | Yes | FK to Table | Source table (foreign key side) |
| `source_column` | string | Yes | Non-empty | Source column name |
| `target_table_id` | string | Yes | FK to Table | Target table (referenced side) |
| `target_column` | string | Yes | Non-empty | Target column name |
| `relationship_type` | enum | Yes | ['declared', 'inferred'] | How relationship discovered |
| `confidence_score` | float | Conditional | 0.0-1.0 | Required if inferred |
| `inference_reasoning` | string | Conditional | - | Human-readable explanation if inferred |
| `constraint_name` | string | Conditional | - | FK constraint name (if declared) |

**Relationships:**
- Many Relationships → One Table (as source)
- Many Relationships → One Table (as target)

**Validation Rules:**
- If `relationship_type='declared'`, `constraint_name` MUST be populated
- If `relationship_type='inferred'`, `confidence_score` and `inference_reasoning` MUST be populated
- `confidence_score` only returned if ≥ threshold (default 0.50, configurable)
- `source_table_id ≠ target_table_id` (self-joins not initially supported)

**Inference Reasoning Examples:**
- "Exact name match + type compatible + source nullable + target PK"
- "Name similarity 0.87 + type compatible + target unique index"
- "Type compatible + value overlap 92%"

---

### 7. DocumentationCache

Cached knowledge about a database including schemas, tables, relationships, and column interpretations.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `cache_id` | string | Yes | Unique | Same as connection_id |
| `connection_id` | string | Yes | FK to Connection | Connection this cache represents |
| `cache_dir` | string | Yes | Valid path | Local directory for markdown files |
| `created_at` | datetime | Yes | ISO 8601 | Initial cache creation |
| `last_updated` | datetime | Yes | ISO 8601 | Last cache update |
| `schema_hash` | string | Yes | SHA-256 | Hash of all table/column names |
| `drift_detected` | boolean | Yes | - | True if schema differs from cached |
| `drift_summary` | string | No | - | Human-readable drift description |

**Relationships:**
- One DocumentationCache → One Connection

**Validation Rules:**
- `cache_dir` structure: `docs/[connection_id]/`
- `schema_hash` computed from sorted list of all table.column names
- Drift check triggered on connect (default) or configurable interval (default: 7 days)

**Cache File Structure:**
```
docs/[connection_id]/
├── overview.md           # Database summary, schema list
├── schemas/
│   ├── dbo.md           # Tables in dbo schema
│   └── sales.md
├── tables/
│   ├── Customers.md     # Full table metadata (columns, indexes, relationships)
│   └── Orders.md
└── relationships.md      # All inferred and declared relationships
```

**Drift Detection Logic:**
```python
def detect_drift(cached_hash: str, current_hash: str) -> tuple[bool, str]:
    """
    Compare cached schema hash to current database schema.
    Returns (drift_detected: bool, drift_summary: str)
    """
    if cached_hash == current_hash:
        return (False, "No changes detected")

    # Detect specific changes
    cached_tables = load_cached_table_list()
    current_tables = query_current_table_list()

    added = current_tables - cached_tables
    removed = cached_tables - current_tables

    summary = []
    if added:
        summary.append(f"Added tables: {', '.join(added)}")
    if removed:
        summary.append(f"Removed tables: {', '.join(removed)}")

    return (True, "; ".join(summary))
```

---

### 8. Query

A SQL query submitted for execution with associated result set.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `query_id` | string | Yes | Unique | UUID |
| `connection_id` | string | Yes | FK to Connection | Connection to execute on |
| `query_text` | string | Yes | Non-empty | SQL query text |
| `query_type` | enum | Yes | ['select', 'insert', 'update', 'delete', 'other'] | Parsed query type |
| `is_allowed` | boolean | Yes | - | Whether execution permitted |
| `row_limit` | integer | No | 1-10000 | Max rows to return (default: 1000) |
| `execution_time_ms` | integer | No | ≥0 | Query execution time (if executed) |
| `rows_affected` | integer | No | ≥0 | Rows returned/affected (if executed) |
| `error_message` | string | No | - | Error if query failed |
| `executed_at` | datetime | No | ISO 8601 | When query was executed |

**Relationships:**
- Many Queries → One Connection

**Validation Rules:**
- `query_type` determined by parsing first keyword in `query_text`
- `is_allowed = (query_type == 'select')` unless write operations explicitly enabled (NFR-004)
- If `query_type` in ['insert', 'update', 'delete'] and not allowed, return error immediately
- `row_limit` enforced server-side via `TOP` clause injection (User Story 7)

**Example Blocked Query:**
```json
{
  "query_text": "DELETE FROM Users WHERE ID=1",
  "query_type": "delete",
  "is_allowed": false,
  "error_message": "Write operations are disabled. Enable in configuration to allow DELETE."
}
```

---

### 9. SampleData

Represents sample rows from a table for inspection.

**Fields:**
| Field | Type | Required | Validation | Description |
|-------|------|----------|------------|-------------|
| `sample_id` | string | Yes | Unique | table_id + timestamp |
| `table_id` | string | Yes | FK to Table | Source table |
| `sample_size` | integer | Yes | 1-1000 | Number of rows requested (default: 5) |
| `sampling_method` | enum | Yes | ['top', 'distributed'] | How rows sampled |
| `rows` | array[object] | Yes | - | Array of row objects (column→value) |
| `truncated_columns` | array[string] | No | - | Columns with truncated values |
| `sampled_at` | datetime | Yes | ISO 8601 | When sample taken |

**Relationships:**
- Many SampleData → One Table

**Validation Rules:**
- `sampling_method='top'`: Simple `SELECT TOP N` (fast, not representative)
- `sampling_method='distributed'`: Use `TABLESAMPLE` or modulo sampling (slower, more representative)
- Binary/blob columns truncated to first 32 bytes as hex + total size (edge case clarification)
- Large text columns (>1000 chars) truncated with indicator

**Example SampleData:**
```json
{
  "table_id": "dbo.Customers",
  "sample_size": 5,
  "sampling_method": "distributed",
  "rows": [
    {"CustomerID": 1, "Name": "Acme Corp", "Status": "Active"},
    {"CustomerID": 42, "Name": "BigCo", "Status": "Inactive"},
    ...
  ],
  "truncated_columns": ["ProfileImage"],  // Binary column truncated
  "sampled_at": "2026-01-19T14:30:00Z"
}
```

---

## Entity Relationships Diagram

```
Connection (1) ─────< (N) Schema (1) ─────< (N) Table
    │                                          │
    │                                          ├──< (N) Column
    │                                          ├──< (N) Index
    │                                          ├──< (N) Relationship (source)
    │                                          ├──< (N) Relationship (target)
    │                                          └──< (N) SampleData
    │
    ├──< (N) Query
    └──── (1) DocumentationCache
```

---

## Data Flow

### Metadata Discovery Flow
```
1. User connects → Connection created
2. List schemas → Schema entities populated
3. List tables → Table entities populated with row counts
4. Get table details → Column and Index entities populated
5. Infer relationships → Relationship entities created (confidence scores)
6. Cache documentation → DocumentationCache entity updated
```

### Subsequent Session Flow
```
1. User connects → Connection created
2. Load cache → DocumentationCache loaded
3. Drift check → Compare schema_hash
4. If drift detected → Highlight changes, optionally refresh
5. If no drift → Use cached entities (SC-002: 50% fewer queries)
```

---

## Performance Considerations

| Entity | Query Cost | Optimization |
|--------|------------|-------------|
| Schema | Low (1 query) | Cache 1 hour |
| Table list | Low (1 query) | Cache 1 hour |
| Column metadata | Medium (1 query/table) | Batch via INFORMATION_SCHEMA |
| Row counts | High (N queries) | Use sys.dm_db_partition_stats |
| Relationship inference | Very High (O(n*m)) | Cache after first run, background job |
| Sample data | Medium (1 query/table) | On-demand only, not cached |

**Caching Strategy:**
- Metadata (schemas, tables, columns): Cache indefinitely until drift detected
- Row counts: Cache 1 hour (can change frequently)
- Inferred relationships: Cache indefinitely (recompute on explicit request)
- Sample data: Never cached (always fresh)

---

## Mapping to Success Criteria

| Success Criterion | Entities Involved |
|-------------------|-------------------|
| **SC-001**: 3 tool calls to understand DB | Connection, Schema, Table |
| **SC-002**: 50% fewer queries via caching | DocumentationCache |
| **SC-003**: 80%+ inference accuracy | Relationship (confidence_score) |
| **SC-004**: 90%+ column purpose hypotheses | Column (inferred_purpose) |
| **SC-005**: Docs usable by different agent | DocumentationCache (markdown files) |
| **SC-006**: 60% token reduction | All entities (summary vs detailed modes) |
| **SC-007**: Query execution <10s | Query (row_limit enforcement) |

---

## Next Steps

1. ✅ Data model defined
2. → Phase 1: Generate contracts/ (MCP tool definitions based on these entities)
3. → Phase 1: Generate quickstart.md
4. → Phase 1: Update agent context
