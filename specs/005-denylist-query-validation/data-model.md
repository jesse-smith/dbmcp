# Data Model: Denylist Query Validation

**Feature**: 005-denylist-query-validation
**Date**: 2026-02-26

## Entities

### DenialCategory (Enum)

Classification of why a query was denied. Replaces the current implicit categorization.

| Value | Description | Examples |
|-------|-------------|----------|
| DML | Data manipulation writes | INSERT, UPDATE, DELETE, MERGE |
| DDL | Data definition changes | CREATE, ALTER, DROP, TRUNCATE, RENAME |
| DCL | Data control / permissions | GRANT, REVOKE, DENY, CREATE/ALTER USER/ROLE |
| OPERATIONAL | Server operational commands | BACKUP, RESTORE, DBCC, KILL, COPY, LOAD DATA |
| STORED_PROCEDURE | Denied stored procedure execution | EXEC user_proc, EXEC sp_executesql |
| SELECT_INTO | SELECT INTO (creates table) | SELECT * INTO new_table FROM ... |
| CTE_WRAPPED_WRITE | CTE containing a write operation | WITH cte AS (...) INSERT INTO ... |
| PARSE_FAILURE | Query could not be parsed | Malformed SQL, unsupported syntax |

### DenialReason (Dataclass)

A single reason why a query (or statement within a batch) was denied.

| Field | Type | Description |
|-------|------|-------------|
| category | DenialCategory | The denial classification |
| detail | str | Human-readable explanation (e.g., "INSERT operations are not permitted") |
| statement_index | int | Zero-based index of the denied statement in a multi-statement batch |

### ValidationResult (Dataclass)

Outcome of query validation. Replaces the current `(bool, str | None)` return pattern.

| Field | Type | Description |
|-------|------|-------------|
| is_safe | bool | True if query is allowed, False if denied |
| reasons | list[DenialReason] | Empty if safe; one or more reasons if denied |

### SafeProcedure Allowlist (Constant)

A frozenset of 22 canonical stored procedure names (lowercase, unqualified).

Categories:
- Catalog/ODBC (12): sp_column_privileges, sp_columns, sp_databases, sp_fkeys, sp_pkeys, sp_server_info, sp_special_columns, sp_sproc_columns, sp_statistics, sp_stored_procedures, sp_table_privileges, sp_tables
- Object/Metadata (4): sp_help, sp_helptext, sp_helpindex, sp_helpconstraint
- Session/Server (3): sp_who, sp_who2, sp_spaceused
- Result Set Metadata (2): sp_describe_first_result_set, sp_describe_undeclared_parameters

Explicitly excluded: sp_executesql

## Relationships to Existing Model

### QueryType (existing, unchanged)

The existing `QueryType` enum (SELECT, INSERT, UPDATE, DELETE, OTHER) is preserved for the `Query.query_type` field. The new `DenialCategory` is a separate concern — it classifies *why* something was denied, while `QueryType` classifies *what kind of query* it is.

### Query (existing, extended)

The existing `Query` dataclass gains one optional field:

| New Field | Type | Description |
|-----------|------|-------------|
| denial_reasons | list[DenialReason] \| None | Populated when `is_allowed=False`; None when allowed |

The existing `error_message` field continues to hold a human-readable summary string for backward compatibility.

## State Transitions

No state machines. Validation is a pure function: SQL text in → ValidationResult out.
