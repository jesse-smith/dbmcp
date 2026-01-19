# Feature Specification: Database Schema Explorer MCP Server

**Feature Branch**: `001-db-schema-explorer`
**Created**: 2026-01-17
**Status**: Draft
**Input**: User description: "Build an MCP server for database exploration, structure understanding, relationship inference, and documentation generation"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Initial Database Discovery (Priority: P1)

An AI agent (or analyst using an AI agent) connects to an unfamiliar SQL Server database for the first time. They need to quickly understand what data exists without wading through hundreds of tables or spending tokens on irrelevant metadata.

**Why this priority**: This is the foundational capability - without efficient discovery, all other features are blocked. This directly addresses the "token-efficient" requirement.

**Independent Test**: Can be fully tested by connecting to a test database and verifying the agent receives a structured, scannable overview of available tables grouped by schema, with row counts and table descriptions where available.

**Acceptance Scenarios**:

1. **Given** a valid database connection, **When** the agent requests database overview, **Then** the system returns a hierarchical list of schemas and tables with row counts, sorted by relevance (largest tables, most recently modified, or user-specified criteria)
2. **Given** a database with 500+ tables, **When** the agent requests discovery, **Then** the response fits within a configurable token budget (default: summary mode with table names and row counts only)
3. **Given** a database connection, **When** the agent requests schema overview, **Then** tables are grouped by database schema (dbo, sales, hr, etc.) with optional filtering

---

### User Story 2 - Table Structure Analysis (Priority: P1)

An analyst needs to understand a specific table's structure: column names, data types, nullability, primary keys, indexes, and any foreign key relationships.

**Why this priority**: Understanding table structure is essential before any query can be written. This is core functionality.

**Independent Test**: Can be tested by requesting schema for a known table and verifying all columns, types, constraints, and relationships are returned in a consistent format.

**Acceptance Scenarios**:

1. **Given** a table name, **When** the agent requests table schema, **Then** the system returns column definitions including name, data type, nullability, default values, and constraints
2. **Given** a table with foreign keys, **When** the agent requests table schema, **Then** explicit foreign key relationships are included with referenced table and column
3. **Given** a table with indexes, **When** the agent requests table schema, **Then** index information is included (columns, uniqueness, clustering)

---

### User Story 3 - Relationship Inference (Priority: P1)

An analyst encounters a legacy database where foreign keys are not declared. They need the system to infer likely join columns based on naming conventions, data type compatibility, and value overlap.

**Why this priority**: The user explicitly stated "many join columns may not be foreign keys" - this is a core differentiator and essential for poorly-documented databases.

**Independent Test**: Can be tested by running inference on a database with known (but undeclared) relationships and measuring precision/recall of inferred joins.

**Acceptance Scenarios**:

1. **Given** two tables with columns sharing naming patterns (e.g., `CustomerID` and `Customer_ID`), **When** the agent requests relationship inference, **Then** the system suggests potential join columns with confidence scores (only relationships meeting configurable threshold, default 50%, are returned)
2. **Given** columns with matching data types and overlapping value sets, **When** relationship inference runs, **Then** these are flagged as candidate join columns even without naming similarity. Value overlap is determined via full value comparison by default, with option to use statistical sampling for large tables
3. **Given** a table, **When** the agent requests inferred relationships, **Then** the system returns both declared FKs and inferred relationships, clearly distinguished

---

### User Story 4 - Sample Data Retrieval (Priority: P2)

An analyst needs to see representative sample data from a table to understand what values actually exist, identify data quality issues, and understand cryptic column purposes.

**Why this priority**: Sample data is essential for understanding cryptic columns and data patterns, but requires the structural understanding from P1 stories first.

**Independent Test**: Can be tested by requesting samples from various tables and verifying returned data is representative, properly formatted, and respects row limits.

**Acceptance Scenarios**:

1. **Given** a table name, **When** the agent requests sample data, **Then** the system returns a configurable number of rows (default: 5) with all columns
2. **Given** a large table, **When** sample data is requested, **Then** the system uses efficient sampling (not just LIMIT, but distributed sampling for representativeness)
3. **Given** a column suspected to be an enum or status field, **When** the agent requests distinct values, **Then** the system returns unique values with counts, limited to top N by frequency

---

### User Story 5 - Column Purpose Inference (Priority: P2)

An analyst encounters columns with cryptic names (e.g., `FLG_1`, `STATUS_CD`, `AMT_3`). They need help inferring what these columns represent based on data patterns, value distributions, and usage context.

**Why this priority**: This directly addresses the user's concern about "inferring purposes of cryptic columns" but depends on sample data capability.

**Independent Test**: Can be tested by providing known cryptic columns and verifying the system generates reasonable hypotheses about their purpose.

**Acceptance Scenarios**:

1. **Given** a column with limited distinct values, **When** the agent requests column analysis, **Then** the system suggests it may be an enum/status/flag and lists the distinct values with frequencies
2. **Given** a numeric column, **When** column analysis is requested, **Then** the system returns min, max, mean, null percentage, and suggests data type (ID, amount, quantity, percentage, etc.)
3. **Given** a date/time column, **When** column analysis is requested, **Then** the system returns date range, null percentage, and common patterns (daily records, business hours only, etc.)

---

### User Story 6 - Documentation Generation (Priority: P2)

An analyst completes their database exploration and wants to save their findings locally so future sessions don't repeat the discovery process, saving tokens and time.

**Why this priority**: This is the "avoid repeating the onboarding process" requirement - critical for token efficiency across sessions.

**Independent Test**: Can be tested by generating docs, starting a new session, and verifying the docs are loaded and reduce subsequent discovery queries.

**Acceptance Scenarios**:

1. **Given** completed exploration of a database, **When** the agent requests documentation export, **Then** the system generates structured markdown files describing schemas, tables, relationships, and column interpretations
2. **Given** existing local documentation for a database, **When** the agent connects to that database, **Then** the system loads cached documentation, performs a drift check (by default on each connection), and uses cached data to reduce metadata queries
3. **Given** schema changes since last documentation, **When** the agent connects, **Then** the system detects drift and highlights what has changed. For long-running connections, drift is re-checked after a configurable interval (default 7 days). Manual drift check can be requested at any time

---

### User Story 7 - Query Execution (Priority: P3)

An analyst has understood the database structure and needs to execute ad-hoc queries to pull specific data for their research or report.

**Why this priority**: Query execution is important but is a lower priority than understanding the database structure - which is the primary goal stated.

**Independent Test**: Can be tested by executing various SELECT queries and verifying results are returned correctly with appropriate formatting.

**Acceptance Scenarios**:

1. **Given** a valid SELECT query, **When** the agent executes it, **Then** results are returned in a structured format with column headers and typed values
2. **Given** a query that would return more than the configured row limit, **When** executed, **Then** the system enforces the limit and indicates total available rows
3. **Given** a non-SELECT query (INSERT, UPDATE, DELETE), **When** attempted, **Then** the system blocks execution unless explicitly enabled in configuration

---

### Edge Cases

- What happens when connection credentials are invalid or the database is unreachable?
- How does the system handle databases with 1000+ tables efficiently?
- What happens when a table has no rows (empty table)?
- How are binary/blob columns handled in sample data? → Truncated preview: first 32 bytes as hex plus total size displayed
- What happens when the user lacks SELECT permission on certain tables? → Table is listed with "access denied" marker; no metadata retrieval attempted for that table
- How are views, stored procedures, and functions represented vs tables?
- What happens when relationship inference takes longer than expected?

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST connect to SQL Server databases using provided connection strings or credential sets
- **FR-002**: System MUST enumerate all accessible schemas, tables, and views in a database
- **FR-003**: System MUST retrieve complete column metadata (name, type, nullability, constraints, defaults)
- **FR-004**: System MUST identify declared foreign key relationships
- **FR-005**: System MUST infer potential join relationships based on column naming patterns and data type compatibility
- **FR-006**: System MUST retrieve sample data from tables with configurable row limits
- **FR-007**: System MUST analyze column value distributions (distinct count, min, max, null percentage)
- **FR-008**: System MUST generate and export structured documentation in markdown format
- **FR-009**: System MUST load and utilize previously generated documentation to reduce redundant queries
- **FR-010**: System MUST detect schema drift between cached documentation and current database state
- **FR-011**: System MUST execute read-only queries (SELECT) and return structured results
- **FR-012**: System MUST enforce configurable row limits on query results and sample data
- **FR-013**: System MUST respect a configurable token budget, providing summary or detailed responses accordingly
- **FR-014**: System MUST expose functionality via MCP protocol tools callable by AI agents
- **FR-015**: System MUST handle connection errors gracefully with actionable error messages
- **FR-016**: System MUST support filtering tables by schema, name pattern, or row count thresholds

### Non-Functional Requirements

- **NFR-001**: Metadata queries MUST complete within 30 seconds for databases with up to 1000 tables
- **NFR-002**: Sample data retrieval MUST complete within 10 seconds per table
- **NFR-003**: Documentation generation MUST produce files under 1MB for databases with up to 500 tables
- **NFR-004**: System MUST NOT execute data-modifying statements (INSERT, UPDATE, DELETE, DROP) unless explicitly configured
- **NFR-005**: Connection credentials MUST NOT be logged or included in documentation output

### Key Entities

- **Connection**: Represents a database connection configuration (server, database, authentication method, credentials reference)
- **Schema**: A namespace grouping of database objects (tables, views) within a database
- **Table**: A database table with columns, indexes, and relationships
- **Column**: A table column with name, data type, nullability, constraints, and inferred purpose
- **Relationship**: A join relationship between tables (declared FK or inferred)
- **Documentation**: Cached knowledge about a database including schemas, tables, relationships, and column interpretations
- **Query**: A SQL query submitted for execution with associated result set

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Agent can understand a new database's structure (schemas, key tables, relationships) within 3 tool calls
- **SC-002**: Subsequent sessions on a previously-explored database require 50% fewer metadata queries due to cached documentation
- **SC-003**: Relationship inference correctly identifies 80%+ of actual join columns in test databases with undeclared foreign keys
- **SC-004**: Column purpose inference provides actionable hypotheses for 90%+ of analyzed columns
- **SC-005**: Documentation generated for a database can be used by a different agent instance to immediately understand the database without re-exploration
- **SC-006**: Total tokens consumed for complete database onboarding reduced by 60%+ compared to ad-hoc exploration without the tool
- **SC-007**: Users can execute data retrieval queries and receive results within expected response times for datasets up to 10,000 rows

## Clarifications

### Session 2026-01-19

- Q: How should the system determine value overlap for relationship inference? → A: Configurable per-inference, with full value comparison as default
- Q: What minimum confidence threshold for showing inferred relationships? → A: Configurable, with 50% default
- Q: When should cached documentation trigger schema drift check? → A: Hybrid - on each connection (default), time-based refresh for long connections (default 7 days), plus manual on-demand check
- Q: How to handle tables where user lacks SELECT permission? → A: List table with "access denied" marker, no metadata retrieval attempted
- Q: How to handle binary/blob columns in sample data? → A: Truncated preview showing first N bytes as hex plus total size (default N=32 bytes)

## Assumptions

- SQL Server is the primary target database; other databases (PostgreSQL, MySQL) may be added later but are not in initial scope
- The agent has network access to the target database server
- Connection credentials will be provided via secure configuration, not hardcoded
- Read-only access is the default; write operations require explicit opt-in
- Documentation will be stored in the local filesystem in markdown format
- The MCP server will run as a local process that the AI agent connects to
- Token efficiency is measured by the size of responses returned to the agent, not internal processing
- "Cryptic columns" are common in legacy databases and inferring their purpose adds significant value
- Users accept that inferred relationships and column purposes are suggestions requiring human validation
