# Phase 11: DatabricksDialect - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-14
**Phase:** 11-DatabricksDialect
**Areas discussed:** Engine & Auth, Table Properties, Catalog Namespace, Metadata Gating

---

## Engine & Auth

| Option | Description | Selected |
|--------|-------------|----------|
| databricks-sqlalchemy + databricks-sql-connector | Official SQLAlchemy dialect + connector. Token auth via URL, catalog/schema in connection string, lazy import pattern. | ✓ |
| Custom DBAPI wrapper | Build directly on databricks-sql-connector without SQLAlchemy dialect layer. Not viable for dbmcp's architecture. | |

**User's choice:** databricks-sqlalchemy (Recommended)
**Notes:** Only viable option for dbmcp's SQLAlchemy-based architecture. Fits DialectStrategy.create_engine() contract.

---

## Table Properties

| Option | Description | Selected |
|--------|-------------|----------|
| Extend get_table_schema | Add optional fields (owner, storage_format, table_type, created_time, partition_columns) to existing get_table_schema response. Single source of truth. | ✓ |
| New get_table_properties tool | Separate MCP tool for operational metadata. Clean separation but forces two calls for complete picture. | |

**User's choice:** Extend get_table_schema (Recommended)
**Notes:** Keeps all table metadata in one place. New fields are small in TOON encoding and backward compatible.

---

## Catalog Namespace

| Option | Description | Selected |
|--------|-------------|----------|
| Connection-scoped catalog (original recommendation) | Catalog fixed at connect time, no tool signature changes. | |
| Optional catalog parameter on schema tools | list_schemas, list_tables, get_table_schema gain optional catalog param. Defaults to connection's configured catalog. MSSQL/generic ignore it. | ✓ |
| Per-query catalog everywhere | Full three-level namespace restructuring across entire codebase. | |

**User's choice:** Optional catalog parameter (user-proposed refinement)
**Notes:** User correctly identified that cross-catalog queries are common in Databricks and connection-scoped would be too limiting. The middle ground — optional catalog param defaulting to connection's catalog, ignored by MSSQL/generic — gives flexibility without breaking existing dialects. Full cross-catalog discovery (ENRICH-02) remains deferred.

---

## Metadata Gating

| Option | Description | Selected |
|--------|-------------|----------|
| Omit key entirely | When supports_indexes=False, indexes key is absent from response. Clearer signal for LLM agents: missing = unsupported, empty list = none exist. | ✓ |
| Always include (empty list) | Always include indexes key, return [] when unsupported. Consistent schema but ambiguous semantics. | |

**User's choice:** Omit key entirely (Recommended)
**Notes:** Clearer semantic distinction for LLM agents. Partition columns added as separate list for Databricks tables.

---

## Claude's Discretion

- D-15: DatabricksDialect internal structure (DESCRIBE EXTENDED parsing, error handling)
- D-16: MetadataService routing to DESCRIBE EXTENDED vs Inspector
- D-17: Catalog parameter threading through MetadataService
- D-18: ConnectionManager.connect_with_config() routing for DatabricksConnectionConfig

## Deferred Ideas

- ENRICH-02: Full cross-catalog schema discovery — future milestone
- ENRICH-01: Unity Catalog tag metadata — future milestone
