# Feature Specification: Allow CTE Queries

> **STATUS: COMPLETE** | Merged: 2026-02-03 | Branch: `003-allow-cte-queries`

**Feature Branch**: `003-allow-cte-queries`
**Created**: 2026-02-03
**Status**: Complete
**Input**: User description: "The current version of the query execution disallows CTEs as an 'Other' query pattern; I'd like to allow them while still blocking create/update/delete/DDL queries. This should be a fairly simple modification."

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Execute CTE-based SELECT Queries (Priority: P1)

A user wants to execute a Common Table Expression (CTE) query that begins with `WITH` to perform complex data analysis involving recursive queries, data aggregation, or temporary result sets. Currently, these queries are blocked because the query parser classifies them as `OTHER` (non-SELECT) queries.

**Why this priority**: CTEs are fundamental SQL constructs used for readable complex queries, recursive data traversal (e.g., organizational hierarchies, bill of materials), and breaking down complex logic. Blocking CTEs severely limits the query execution functionality.

**Independent Test**: Can be fully tested by executing a `WITH ... SELECT` query and verifying it returns results instead of being blocked.

**Acceptance Scenarios**:

1. **Given** a user has an active database connection, **When** they execute a simple CTE query like `WITH cte AS (SELECT 1 AS val) SELECT * FROM cte`, **Then** the query executes successfully and returns results.

2. **Given** a user has an active database connection, **When** they execute a recursive CTE query to traverse hierarchical data, **Then** the query executes successfully and returns the hierarchy.

3. **Given** a user has an active database connection, **When** they execute a CTE with multiple common table expressions chained together, **Then** all CTEs are processed and the final SELECT returns results.

---

### User Story 2 - Block Dangerous Query Patterns (Priority: P1)

A user may attempt to execute DDL statements (CREATE, ALTER, DROP) or other dangerous operations (TRUNCATE, EXEC, GRANT). The system must continue to block these operations to maintain database integrity and security.

**Why this priority**: Security is critical. Allowing CTEs must not open a backdoor for DDL or other dangerous operations.

**Independent Test**: Can be tested by attempting various blocked query types and verifying each is rejected with an appropriate error message.

**Acceptance Scenarios**:

1. **Given** a user has an active database connection, **When** they attempt to execute `CREATE TABLE test (id INT)`, **Then** the query is blocked with a clear error message.

2. **Given** a user has an active database connection, **When** they attempt to execute `DROP TABLE users`, **Then** the query is blocked with a clear error message.

3. **Given** a user has an active database connection, **When** they attempt to execute `ALTER TABLE users ADD COLUMN email VARCHAR(255)`, **Then** the query is blocked with a clear error message.

4. **Given** a user has an active database connection, **When** they attempt to execute `TRUNCATE TABLE logs`, **Then** the query is blocked with a clear error message.

5. **Given** a user has an active database connection, **When** they attempt to execute `EXEC sp_executesql N'SELECT 1'`, **Then** the query is blocked with a clear error message.

---

### User Story 3 - Maintain Write Operation Controls (Priority: P1)

Write operations (INSERT, UPDATE, DELETE) must continue to be controlled by the existing `allow_write` parameter. These should remain blocked by default but allowed when explicitly enabled.

**Why this priority**: Preserving the existing security model for write operations is critical for maintaining backward compatibility and database safety.

**Independent Test**: Can be tested by verifying INSERT/UPDATE/DELETE behavior with and without the `allow_write` flag.

**Acceptance Scenarios**:

1. **Given** a user has an active database connection with `allow_write=False` (default), **When** they execute `INSERT INTO users VALUES (1, 'test')`, **Then** the query is blocked with a message about enabling `allow_write`.

2. **Given** a user has an active database connection with `allow_write=True`, **When** they execute `INSERT INTO users VALUES (1, 'test')`, **Then** the query executes successfully.

---

### Edge Cases

- What happens when a CTE is followed by INSERT/UPDATE/DELETE instead of SELECT?
  - These should follow the existing `allow_write` rules (blocked by default, allowed with flag)
- What happens when a CTE contains dangerous operations in its definition (e.g., `WITH cte AS (EXEC ...)`)?
  - This is invalid SQL syntax and will fail at the database level
- What happens when SQL comments are used to obfuscate query intent (e.g., `/* CREATE TABLE */ WITH ...`)?
  - The existing comment-stripping logic should handle this correctly
- What happens with malformed CTEs (missing SELECT)?
  - Database engine will return a syntax error

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST allow execution of queries beginning with the `WITH` keyword (CTEs) followed by a SELECT statement
- **FR-002**: System MUST continue to block DDL statements: CREATE, ALTER, DROP, TRUNCATE
- **FR-003**: System MUST continue to block dangerous operations: EXEC, EXECUTE, GRANT, REVOKE, DENY
- **FR-004**: System MUST continue to respect the `allow_write` parameter for INSERT, UPDATE, DELETE operations (including CTEs followed by write operations)
- **FR-005**: System MUST strip SQL comments before analyzing query type to prevent obfuscation attacks
- **FR-006**: System MUST apply row limits to CTE queries that end in SELECT, just as with regular SELECT queries
- **FR-007**: System MUST provide clear error messages when blocking queries, explaining why the query was rejected

### Key Entities

- **QueryType**: Existing enum that classifies queries. May need extension or alternative approach to handle CTEs.
- **Query**: Existing model representing query execution results and metadata.

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: All valid CTE queries (WITH...SELECT) execute successfully and return expected results
- **SC-002**: All DDL and dangerous operations continue to be blocked with zero false negatives
- **SC-003**: Existing write operation controls (INSERT/UPDATE/DELETE with allow_write flag) continue to function identically
- **SC-004**: Row limits are correctly applied to CTE queries that end in SELECT
- **SC-005**: Error messages clearly indicate why a query was blocked and what type of query is not allowed

## Assumptions

- CTE queries followed by SELECT are the primary use case; CTEs followed by INSERT/UPDATE/DELETE are edge cases handled by existing write controls
- The current comment-stripping logic is sufficient for preventing obfuscation
- The underlying database engine (SQL Server/SQLite) will handle malformed CTE syntax errors appropriately
- Performance impact of enhanced query parsing is negligible for typical query lengths
