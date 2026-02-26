# Feature Specification: Denylist Query Validation

**Feature Branch**: `005-denylist-query-validation`
**Created**: 2026-02-26
**Status**: Draft
**Input**: User description: "Convert read-only query enforcement from keyword-based blocklist to comprehensive denylist approach, allowing known-safe read-only stored procedures"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Safe Read-Only Queries Execute Without False Positives (Priority: P1)

An MCP client submits a valid read-only query (SELECT, EXPLAIN, SHOW, USE, or any other non-mutating statement). The system validates the query against a comprehensive denylist rather than a fragile keyword allowlist, and the query executes successfully without false rejections.

**Why this priority**: The core value proposition — replacing a brittle keyword check with a robust denylist means fewer legitimate queries get blocked while maintaining safety.

**Independent Test**: Submit a variety of valid read-only queries including those that currently fail due to keyword false positives (e.g., a SELECT referencing a column named "create_date") and confirm they execute.

**Acceptance Scenarios**:

1. **Given** a valid SELECT query, **When** submitted for execution, **Then** the query passes validation and returns results
2. **Given** a SELECT query containing words that overlap with blocked keywords (e.g., column named "execute_count"), **When** submitted, **Then** the query is NOT falsely rejected
3. **Given** any non-mutating SQL statement type not explicitly on the denylist, **When** submitted, **Then** it is allowed by default

---

### User Story 2 - State-Modifying Operations Are Denied (Priority: P1)

An MCP client submits a query that would modify database state (DML writes, DDL, DCL, or operational commands). The system identifies the operation as denied and returns a clear, categorized rejection message without executing the query.

**Why this priority**: Equal priority to US1 — the denylist must correctly block all dangerous operations to maintain data safety.

**Independent Test**: Submit queries for each denial category (INSERT, DROP TABLE, GRANT, BACKUP, etc.) and confirm each is rejected with an appropriate reason.

**Acceptance Scenarios**:

1. **Given** a DML write query (INSERT, UPDATE, DELETE, MERGE), **When** submitted in read-only mode, **Then** it is denied with a "DML" category reason
2. **Given** a DDL query (CREATE, ALTER, DROP, TRUNCATE), **When** submitted, **Then** it is denied with a "DDL" category reason
3. **Given** a DCL query (GRANT, REVOKE, DENY, CREATE/ALTER USER/ROLE), **When** submitted, **Then** it is denied with a "DCL" category reason
4. **Given** an operational command (BACKUP, RESTORE, DBCC, KILL), **When** submitted, **Then** it is denied with an "Operational" category reason
5. **Given** a SELECT INTO statement, **When** submitted, **Then** it is denied (creates a table)
6. **Given** a CTE wrapping a write operation (WITH cte AS (...) INSERT INTO ...), **When** submitted, **Then** it is denied with a "CTE-wrapped write" category reason

---

### User Story 3 - Known-Safe Read-Only Stored Procedures Execute (Priority: P2)

An MCP client executes a well-known SQL Server system stored procedure that only reads metadata (e.g., sp_tables, sp_columns, sp_help). The system recognizes these as safe and allows execution, even though EXEC/EXECUTE are otherwise denied.

**Why this priority**: Stored procedures are a primary way to inspect SQL Server metadata. Blocking all EXEC statements forces users into less convenient workarounds.

**Independent Test**: Submit EXEC sp_tables and confirm it returns results; submit EXEC sp_executesql and confirm it is denied.

**Acceptance Scenarios**:

1. **Given** a query executing a known-safe stored procedure (e.g., EXEC sp_columns), **When** submitted, **Then** the query passes validation and executes
2. **Given** a known-safe procedure called with a multi-part name (e.g., EXEC master.dbo.sp_help), **When** submitted, **Then** the procedure name is correctly resolved and allowed
3. **Given** sp_executesql (which can execute arbitrary SQL), **When** submitted, **Then** it is explicitly denied despite matching the sp_ naming pattern
4. **Given** an unknown or user-defined stored procedure, **When** submitted, **Then** it is denied

---

### User Story 4 - Obfuscation Attempts Are Caught (Priority: P2)

A query attempts to bypass validation through SQL obfuscation: hiding denied operations inside comments, control flow blocks (BEGIN/END, IF/ELSE, WHILE), or multi-statement batches. The system detects and denies these.

**Why this priority**: Without obfuscation resistance, the denylist can be trivially bypassed.

**Independent Test**: Submit queries with denied operations hidden inside comments, transaction blocks, and multi-statement batches; confirm all are rejected.

**Acceptance Scenarios**:

1. **Given** a query with a denied operation inside a SQL comment (e.g., `/* safe */ DROP TABLE x`), **When** submitted, **Then** the actual DROP is detected and denied
2. **Given** a multi-statement batch with one denied operation among safe ones, **When** submitted, **Then** the entire batch is denied
3. **Given** a denied operation nested inside BEGIN/END, IF/ELSE, or WHILE blocks, **When** submitted, **Then** the nested operation is detected and denied
4. **Given** an unparseable query, **When** submitted, **Then** it is denied rather than allowed (fail-safe)

---

### Edge Cases

- What happens when the query is empty or whitespace-only? (Reject with validation error)
- What happens when the query uses non-standard T-SQL syntax that the parser doesn't recognize? (Deny — fail-safe)
- How are case variations handled (e.g., "Drop", "DROP", "drop")? (Case-insensitive matching)
- What happens with dynamically constructed SQL inside allowed procedures? (Out of scope — the procedure allowlist is curated to exclude procedures that execute dynamic SQL)

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST deny DML write operations: INSERT, UPDATE, DELETE, MERGE
- **FR-002**: System MUST deny DDL operations: CREATE, ALTER, DROP, TRUNCATE, RENAME (all object types)
- **FR-003**: System MUST deny DCL operations: GRANT, REVOKE, DENY, CREATE/ALTER USER, CREATE/ALTER ROLE
- **FR-004**: System MUST deny operational commands: BACKUP, RESTORE, DBCC, KILL, COPY, LOAD DATA
- **FR-005**: System MUST deny SELECT INTO (which creates tables)
- **FR-006**: System MUST deny CTE-wrapped write operations
- **FR-007**: System MUST deny EXEC/EXECUTE by default, except for a curated allowlist of known-safe read-only SQL Server system stored procedures
- **FR-008**: System MUST allow any statement type not explicitly on the denylist (allow-by-default for unknown types)
- **FR-009**: System MUST recursively check nested statements inside control flow blocks (BEGIN/END, IF/ELSE, WHILE)
- **FR-010**: System MUST reject the entire batch if any statement in a multi-statement batch is denied
- **FR-011**: System MUST deny queries that fail to parse (fail-safe behavior)
- **FR-012**: System MUST return categorized denial reasons (DML, DDL, DCL, Operational, StoredProcedure, SelectInto, CteWrappedWrite, ParseFailure)
- **FR-013**: System MUST perform case-insensitive validation
- **FR-014**: System MUST resolve multi-part stored procedure names (e.g., master.dbo.sp_help) when checking the allowlist
- **FR-015**: System MUST explicitly deny sp_executesql regardless of the safe procedure allowlist

### Safe Stored Procedure Allowlist

The following SQL Server system procedures are known to be read-only metadata queries:

- **Catalog/ODBC**: sp_column_privileges, sp_columns, sp_databases, sp_fkeys, sp_pkeys, sp_server_info, sp_special_columns, sp_sproc_columns, sp_statistics, sp_stored_procedures, sp_table_privileges, sp_tables
- **Object/Metadata**: sp_help, sp_helptext, sp_helpindex, sp_helpconstraint
- **Session/Server Info**: sp_who, sp_who2, sp_spaceused
- **Result Set Metadata**: sp_describe_first_result_set, sp_describe_undeclared_parameters

### Key Entities

- **DenialCategory**: Classification of why a query was denied (DML, DDL, DCL, Operational, StoredProcedure, SelectInto, CteWrappedWrite, ParseFailure)
- **ValidationResult**: Outcome of query validation — either Safe or Denied with one or more categorized reasons

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All previously allowed read-only queries continue to work without regression
- **SC-002**: Zero false positives on SELECT queries containing words that overlap with denied operation names
- **SC-003**: 100% of denial categories (DML, DDL, DCL, Operational, SelectInto, CteWrappedWrite, StoredProcedure, ParseFailure) return correct categorized rejection messages
- **SC-004**: All 22 safe stored procedures execute successfully; sp_executesql and unknown procedures are denied
- **SC-005**: Obfuscation via comments, control flow nesting, and multi-statement batches is detected and denied in all tested cases
- **SC-006**: Unparseable queries are denied (fail-safe) in 100% of tested cases

## Clarifications

### Session 2026-02-26

- Q: Does `allow_write` bypass MERGE operations? → A: Yes — `allow_write` bypasses MERGE just like INSERT/UPDATE/DELETE

## Assumptions

- The existing `allow_write` flag behavior is preserved — when enabled, DML writes (INSERT, UPDATE, DELETE, MERGE) bypass the denylist
- The safe stored procedure allowlist is SQL Server-specific; if other backends are added later, they would have their own allowlists
- The current comment-stripping logic is subsumed by the new validation approach
- The existing QueryType enum and Query dataclass may need to be extended to support denial categories
