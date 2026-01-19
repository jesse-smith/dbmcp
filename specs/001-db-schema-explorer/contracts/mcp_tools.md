# MCP Tool Contracts: Database Schema Explorer

**Feature**: 001-db-schema-explorer
**Date**: 2026-01-19
**MCP Protocol Version**: 2025-11-25

## Overview

This document defines the MCP tool contracts for the Database Schema Explorer server. All tools follow the Model Context Protocol specification and are designed for AI agent consumption.

**Server Name**: `dbmcp`
**Transport**: stdio (JSON-RPC over stdin/stdout)

---

## Tool Catalog

| Tool Name | Priority | User Story | Description |
|-----------|----------|------------|-------------|
| `connect_database` | P1 | All | Establish connection to SQL Server database |
| `list_schemas` | P1 | US-1 | List all schemas in connected database |
| `list_tables` | P1 | US-1 | List tables in schema(s) with row counts |
| `get_table_schema` | P1 | US-2 | Get detailed table structure (columns, indexes, FKs) |
| `infer_relationships` | P1 | US-3 | Infer undeclared foreign key relationships |
| `get_sample_data` | P2 | US-4 | Retrieve sample rows from a table |
| `analyze_column` | P2 | US-5 | Analyze column purpose and value distribution |
| `execute_query` | P3 | US-7 | Execute SELECT query and return results |
| `export_documentation` | P2 | US-6 | Generate and export markdown documentation |
| `load_cached_docs` | P2 | US-6 | Load previously cached documentation |
| `check_drift` | P2 | US-6 | Check for schema drift since last cache |

---

## Tool Definitions

### 1. connect_database

**Description**: Establish connection to a SQL Server database. Required before any other operations.

**Priority**: P1
**Maps to**: All user stories (prerequisite)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "server": {
      "type": "string",
      "description": "SQL Server host (hostname or IP address)",
      "minLength": 1
    },
    "database": {
      "type": "string",
      "description": "Database name",
      "minLength": 1
    },
    "port": {
      "type": "integer",
      "description": "SQL Server port (default: 1433)",
      "minimum": 1,
      "maximum": 65535,
      "default": 1433
    },
    "authentication_method": {
      "type": "string",
      "enum": ["sql", "windows", "azure_ad"],
      "description": "Authentication method",
      "default": "sql"
    },
    "username": {
      "type": "string",
      "description": "Username (required for sql/azure_ad)",
      "minLength": 1
    },
    "password": {
      "type": "string",
      "description": "Password (required for sql/azure_ad)",
      "minLength": 1
    },
    "trust_server_cert": {
      "type": "boolean",
      "description": "Trust server certificate without validation",
      "default": false
    },
    "connection_timeout": {
      "type": "integer",
      "description": "Connection timeout in seconds",
      "minimum": 5,
      "maximum": 300,
      "default": 30
    }
  },
  "required": ["server", "database"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": {
      "type": "string",
      "description": "Unique connection identifier"
    },
    "status": {
      "type": "string",
      "enum": ["connected", "failed"],
      "description": "Connection status"
    },
    "message": {
      "type": "string",
      "description": "Human-readable status message"
    },
    "server_version": {
      "type": "string",
      "description": "SQL Server version"
    },
    "schema_count": {
      "type": "integer",
      "description": "Number of accessible schemas"
    },
    "has_cached_docs": {
      "type": "boolean",
      "description": "Whether cached documentation exists"
    }
  },
  "required": ["connection_id", "status", "message"]
}
```

**Error Conditions**:
- Invalid credentials → `status: "failed"`, `message: "Authentication failed"`
- Unreachable server → `status: "failed"`, `message: "Could not connect to server"`
- Network timeout → `status: "failed"`, `message: "Connection timeout after {N} seconds"`

**Example**:
```json
{
  "tool": "connect_database",
  "arguments": {
    "server": "myserver.database.windows.net",
    "database": "AdventureWorks",
    "authentication_method": "sql",
    "username": "analyst",
    "password": "SecurePass123"
  }
}
```

**Response**:
```json
{
  "connection_id": "abc123def",
  "status": "connected",
  "message": "Successfully connected to AdventureWorks",
  "server_version": "Microsoft SQL Server 2022 (RTM)",
  "schema_count": 8,
  "has_cached_docs": true
}
```

---

### 2. list_schemas

**Description**: List all accessible schemas in the connected database.

**Priority**: P1
**Maps to**: User Story 1 (Database Discovery)
**Fulfills**: FR-002 (enumerate schemas)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": {
      "type": "string",
      "description": "Connection ID from connect_database"
    }
  },
  "required": ["connection_id"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "schemas": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "schema_name": { "type": "string" },
          "table_count": { "type": "integer" },
          "view_count": { "type": "integer" }
        },
        "required": ["schema_name", "table_count", "view_count"]
      }
    },
    "total_schemas": { "type": "integer" }
  },
  "required": ["schemas", "total_schemas"]
}
```

**Example Response**:
```json
{
  "schemas": [
    {"schema_name": "dbo", "table_count": 42, "view_count": 8},
    {"schema_name": "sales", "table_count": 15, "view_count": 3},
    {"schema_name": "hr", "table_count": 8, "view_count": 1}
  ],
  "total_schemas": 3
}
```

---

### 3. list_tables

**Description**: List tables in specified schema(s) with row counts and metadata.

**Priority**: P1
**Maps to**: User Story 1 (Database Discovery)
**Fulfills**: FR-002, FR-016 (enumerate tables, filtering)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "schema_filter": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Schema names to include (empty = all schemas)"
    },
    "name_pattern": {
      "type": "string",
      "description": "Table name filter (SQL LIKE pattern, e.g., 'Customer%')"
    },
    "min_row_count": {
      "type": "integer",
      "description": "Minimum row count threshold",
      "minimum": 0
    },
    "sort_by": {
      "type": "string",
      "enum": ["name", "row_count", "last_modified"],
      "description": "Sort criterion",
      "default": "row_count"
    },
    "sort_order": {
      "type": "string",
      "enum": ["asc", "desc"],
      "description": "Sort order",
      "default": "desc"
    },
    "limit": {
      "type": "integer",
      "description": "Max tables to return",
      "minimum": 1,
      "maximum": 1000,
      "default": 100
    },
    "output_mode": {
      "type": "string",
      "enum": ["summary", "detailed"],
      "description": "Summary (names+row counts) or detailed (includes columns)",
      "default": "summary"
    }
  },
  "required": ["connection_id"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "tables": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "schema_name": { "type": "string" },
          "table_name": { "type": "string" },
          "row_count": { "type": "integer", "nullable": true },
          "has_primary_key": { "type": "boolean" },
          "last_modified": { "type": "string", "format": "date-time", "nullable": true },
          "access_denied": { "type": "boolean" }
        },
        "required": ["schema_name", "table_name", "has_primary_key", "access_denied"]
      }
    },
    "total_tables": { "type": "integer" },
    "filtered_count": { "type": "integer" }
  },
  "required": ["tables", "total_tables", "filtered_count"]
}
```

**Example Request**:
```json
{
  "tool": "list_tables",
  "arguments": {
    "connection_id": "abc123def",
    "schema_filter": ["dbo", "sales"],
    "sort_by": "row_count",
    "sort_order": "desc",
    "limit": 20,
    "output_mode": "summary"
  }
}
```

**Example Response**:
```json
{
  "tables": [
    {
      "schema_name": "dbo",
      "table_name": "Orders",
      "row_count": 1543289,
      "has_primary_key": true,
      "last_modified": "2025-12-15T09:30:00Z",
      "access_denied": false
    },
    {
      "schema_name": "dbo",
      "table_name": "Customers",
      "row_count": 98234,
      "has_primary_key": true,
      "last_modified": "2026-01-10T14:22:00Z",
      "access_denied": false
    },
    {
      "schema_name": "hr",
      "table_name": "SalaryHistory",
      "row_count": null,
      "has_primary_key": true,
      "last_modified": null,
      "access_denied": true
    }
  ],
  "total_tables": 65,
  "filtered_count": 20
}
```

---

### 4. get_table_schema

**Description**: Get detailed schema for a specific table including columns, indexes, and declared foreign keys.

**Priority**: P1
**Maps to**: User Story 2 (Table Structure Analysis)
**Fulfills**: FR-003, FR-004 (column metadata, declared FKs)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "schema_name": { "type": "string" },
    "table_name": { "type": "string" },
    "include_indexes": {
      "type": "boolean",
      "description": "Include index information",
      "default": true
    },
    "include_relationships": {
      "type": "boolean",
      "description": "Include declared foreign keys",
      "default": true
    }
  },
  "required": ["connection_id", "table_name"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "table": {
      "type": "object",
      "properties": {
        "schema_name": { "type": "string" },
        "table_name": { "type": "string" },
        "row_count": { "type": "integer", "nullable": true },
        "columns": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "column_name": { "type": "string" },
              "ordinal_position": { "type": "integer" },
              "data_type": { "type": "string" },
              "max_length": { "type": "integer", "nullable": true },
              "is_nullable": { "type": "boolean" },
              "default_value": { "type": "string", "nullable": true },
              "is_identity": { "type": "boolean" },
              "is_computed": { "type": "boolean" },
              "is_primary_key": { "type": "boolean" },
              "is_foreign_key": { "type": "boolean" }
            }
          }
        },
        "indexes": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "index_name": { "type": "string" },
              "is_unique": { "type": "boolean" },
              "is_primary_key": { "type": "boolean" },
              "is_clustered": { "type": "boolean" },
              "columns": { "type": "array", "items": { "type": "string" } },
              "included_columns": { "type": "array", "items": { "type": "string" } }
            }
          }
        },
        "foreign_keys": {
          "type": "array",
          "items": {
            "type": "object",
            "properties": {
              "constraint_name": { "type": "string" },
              "source_column": { "type": "string" },
              "target_schema": { "type": "string" },
              "target_table": { "type": "string" },
              "target_column": { "type": "string" }
            }
          }
        }
      }
    }
  }
}
```

---

### 5. infer_relationships

**Description**: Infer potential foreign key relationships based on naming patterns, data types, and value overlap.

**Priority**: P1
**Maps to**: User Story 3 (Relationship Inference)
**Fulfills**: FR-005 (infer join relationships)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "schema_name": { "type": "string" },
    "table_name": { "type": "string" },
    "confidence_threshold": {
      "type": "number",
      "description": "Minimum confidence score (0.0-1.0)",
      "minimum": 0.0,
      "maximum": 1.0,
      "default": 0.50
    },
    "include_value_overlap": {
      "type": "boolean",
      "description": "Perform value overlap analysis (slower, more accurate)",
      "default": false
    },
    "max_candidates": {
      "type": "integer",
      "description": "Maximum candidate relationships to return",
      "minimum": 1,
      "maximum": 100,
      "default": 20
    }
  },
  "required": ["connection_id", "table_name"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "inferred_relationships": {
      "type": "array",
      "items": {
        "type": "object",
        "properties": {
          "source_table": { "type": "string" },
          "source_column": { "type": "string" },
          "target_table": { "type": "string" },
          "target_column": { "type": "string" },
          "confidence_score": {
            "type": "number",
            "description": "Confidence score (0.0-1.0)"
          },
          "reasoning": {
            "type": "string",
            "description": "Human-readable explanation"
          },
          "factors": {
            "type": "object",
            "properties": {
              "name_similarity": { "type": "number" },
              "type_compatible": { "type": "boolean" },
              "structural_hints": { "type": "string" },
              "value_overlap": { "type": "number", "nullable": true }
            }
          }
        }
      }
    },
    "analysis_time_ms": { "type": "integer" },
    "total_candidates_evaluated": { "type": "integer" }
  }
}
```

**Example Response**:
```json
{
  "inferred_relationships": [
    {
      "source_table": "Orders",
      "source_column": "CustomerID",
      "target_table": "Customers",
      "target_column": "CustomerID",
      "confidence_score": 0.96,
      "reasoning": "Exact name match + type compatible (INT→INT) + source nullable + target PK",
      "factors": {
        "name_similarity": 1.0,
        "type_compatible": true,
        "structural_hints": "target_is_pk, source_nullable",
        "value_overlap": null
      }
    },
    {
      "source_table": "Orders",
      "source_column": "ShipCityCode",
      "target_table": "Cities",
      "target_column": "CityCode",
      "confidence_score": 0.82,
      "reasoning": "High name similarity (0.89) + type compatible (VARCHAR→VARCHAR) + target unique index",
      "factors": {
        "name_similarity": 0.89,
        "type_compatible": true,
        "structural_hints": "target_unique_index",
        "value_overlap": null
      }
    }
  ],
  "analysis_time_ms": 87,
  "total_candidates_evaluated": 245
}
```

---

### 6. get_sample_data

**Description**: Retrieve sample rows from a table for inspection.

**Priority**: P2
**Maps to**: User Story 4 (Sample Data Retrieval)
**Fulfills**: FR-006, FR-012 (retrieve sample data, enforce row limits)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "schema_name": { "type": "string" },
    "table_name": { "type": "string" },
    "sample_size": {
      "type": "integer",
      "description": "Number of rows to sample",
      "minimum": 1,
      "maximum": 1000,
      "default": 5
    },
    "sampling_method": {
      "type": "string",
      "enum": ["top", "distributed"],
      "description": "top=fast/not representative, distributed=slower/representative",
      "default": "top"
    },
    "columns": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Column names to include (empty = all columns)"
    }
  },
  "required": ["connection_id", "table_name"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "table_name": { "type": "string" },
    "sample_size": { "type": "integer" },
    "rows": {
      "type": "array",
      "description": "Array of row objects (column name → value)"
    },
    "truncated_columns": {
      "type": "array",
      "items": { "type": "string" },
      "description": "Columns with truncated values (binary/large text)"
    },
    "sampled_at": { "type": "string", "format": "date-time" }
  }
}
```

**Example Response**:
```json
{
  "table_name": "Customers",
  "sample_size": 5,
  "rows": [
    {"CustomerID": 1, "Name": "Acme Corp", "Status": "Active", "CreditLimit": 50000.00},
    {"CustomerID": 42, "Name": "BigCo LLC", "Status": "Inactive", "CreditLimit": 25000.00},
    {"CustomerID": 103, "Name": "Widgets Inc", "Status": "Active", "CreditLimit": 75000.00}
  ],
  "truncated_columns": [],
  "sampled_at": "2026-01-19T14:45:00Z"
}
```

---

### 7. analyze_column

**Description**: Analyze column purpose and value distribution to infer what the column represents.

**Priority**: P2
**Maps to**: User Story 5 (Column Purpose Inference)
**Fulfills**: FR-007 (analyze column distributions)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "schema_name": { "type": "string" },
    "table_name": { "type": "string" },
    "column_name": { "type": "string" }
  },
  "required": ["connection_id", "table_name", "column_name"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "column_name": { "type": "string" },
    "data_type": { "type": "string" },
    "distinct_count": { "type": "integer" },
    "null_count": { "type": "integer" },
    "null_percentage": { "type": "number" },
    "inferred_purpose": {
      "type": "string",
      "enum": ["id", "enum", "status", "flag", "amount", "quantity", "percentage", "timestamp", "unknown"]
    },
    "confidence": { "type": "number" },
    "statistics": {
      "type": "object",
      "description": "Type-specific stats (numeric: min/max/mean, date: range, string: top values)"
    }
  }
}
```

**Example Response (Enum Column)**:
```json
{
  "column_name": "Status",
  "data_type": "VARCHAR(20)",
  "distinct_count": 4,
  "null_count": 0,
  "null_percentage": 0.0,
  "inferred_purpose": "enum",
  "confidence": 0.95,
  "statistics": {
    "type": "categorical",
    "top_values": [
      {"value": "Active", "count": 12453, "percentage": 78.2},
      {"value": "Inactive", "count": 2891, "percentage": 18.1},
      {"value": "Suspended", "count": 412, "percentage": 2.6},
      {"value": "Pending", "count": 178, "percentage": 1.1}
    ]
  }
}
```

---

### 8. execute_query

**Description**: Execute a SELECT query and return structured results.

**Priority**: P3
**Maps to**: User Story 7 (Query Execution)
**Fulfills**: FR-011, FR-012, NFR-004 (execute queries, enforce limits, read-only default)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "query": {
      "type": "string",
      "description": "SQL query (SELECT only by default)"
    },
    "row_limit": {
      "type": "integer",
      "description": "Maximum rows to return",
      "minimum": 1,
      "maximum": 10000,
      "default": 1000
    }
  },
  "required": ["connection_id", "query"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "query": { "type": "string" },
    "status": {
      "type": "string",
      "enum": ["success", "blocked", "error"]
    },
    "rows_returned": { "type": "integer" },
    "rows_available": { "type": "integer", "nullable": true },
    "execution_time_ms": { "type": "integer" },
    "columns": {
      "type": "array",
      "items": { "type": "string" }
    },
    "rows": { "type": "array" },
    "error_message": { "type": "string", "nullable": true }
  }
}
```

---

### 9. export_documentation

**Description**: Generate and export structured markdown documentation for the database.

**Priority**: P2
**Maps to**: User Story 6 (Documentation Generation)
**Fulfills**: FR-008, FR-009 (generate docs, reduce redundant queries)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" },
    "output_dir": {
      "type": "string",
      "description": "Directory for markdown files (default: docs/[connection_id]/)"
    },
    "include_sample_data": {
      "type": "boolean",
      "description": "Include sample data in table docs",
      "default": false
    },
    "include_inferred_relationships": {
      "type": "boolean",
      "description": "Include inferred FKs in relationship docs",
      "default": true
    }
  },
  "required": ["connection_id"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "status": { "type": "string", "enum": ["success", "error"] },
    "output_dir": { "type": "string" },
    "files_created": {
      "type": "array",
      "items": { "type": "string" }
    },
    "total_size_bytes": { "type": "integer" },
    "generation_time_ms": { "type": "integer" }
  }
}
```

---

### 10. load_cached_docs

**Description**: Load previously generated documentation to avoid redundant metadata queries.

**Priority**: P2
**Maps to**: User Story 6 (Documentation Generation)
**Fulfills**: FR-009, SC-002 (utilize cached docs, 50% fewer queries)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" }
  },
  "required": ["connection_id"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "status": { "type": "string", "enum": ["loaded", "not_found"] },
    "cache_age_days": { "type": "integer", "nullable": true },
    "schema_count": { "type": "integer", "nullable": true },
    "table_count": { "type": "integer", "nullable": true }
  }
}
```

---

### 11. check_drift

**Description**: Check for schema drift between cached documentation and current database state.

**Priority**: P2
**Maps to**: User Story 6 (Documentation Generation)
**Fulfills**: FR-010 (detect schema drift)

**Input Schema**:
```json
{
  "type": "object",
  "properties": {
    "connection_id": { "type": "string" }
  },
  "required": ["connection_id"],
  "additionalProperties": false
}
```

**Output Schema**:
```json
{
  "type": "object",
  "properties": {
    "drift_detected": { "type": "boolean" },
    "drift_summary": { "type": "string" },
    "changes": {
      "type": "object",
      "properties": {
        "added_tables": { "type": "array", "items": { "type": "string" } },
        "removed_tables": { "type": "array", "items": { "type": "string" } },
        "modified_tables": { "type": "array", "items": { "type": "string" } }
      }
    }
  }
}
```

---

## Success Criteria Mapping

| Tool | Success Criterion |
|------|-------------------|
| `list_schemas`, `list_tables`, `get_table_schema` | SC-001 (3 calls to understand DB) |
| `export_documentation`, `load_cached_docs` | SC-002 (50% fewer queries), SC-006 (60% token reduction) |
| `infer_relationships` | SC-003 (80%+ inference accuracy) |
| `analyze_column` | SC-004 (90%+ column purpose hypotheses) |
| `export_documentation` | SC-005 (docs usable by different agent) |
| `execute_query` | SC-007 (<10s query execution) |

---

## Implementation Notes

- All tools use async/await patterns in FastMCP
- Error handling follows MCP error schema (code, message, data)
- Credentials never logged or exported (NFR-005)
- Write operations blocked unless explicitly enabled (NFR-004)
- Token efficiency via summary/detailed output modes (FR-013)
