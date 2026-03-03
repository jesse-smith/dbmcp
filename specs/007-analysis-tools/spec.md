# Feature Specification: Data-Exposure Analysis Tools

**Feature Branch**: `007-analysis-tools`
**Created**: 2026-03-03
**Status**: Draft

## Clarifications

### Session 2026-03-03

- Q: What qualifies as a "candidate primary key" column? → A: PK discovery should be a separate tool (`find_pk_candidates`) that identifies columns with PK/UNIQUE constraints or PK-like characteristics (unique, non-null, integer/UUID type). `find_fk_candidates` defaults to using this PK-filtered set but includes a toggle to disable the filter and compare against all columns.
- Q: Should FK candidate results be limited by default? → A: Yes, default limit of 100 candidates total across all target tables, with an optional parameter to override. Results are always scoped to specified target tables/schema/pattern — when no target filters are provided, the search defaults to the source column's schema (never a full-database scan).
- Q: What are the structural PK candidate qualification criteria? → A: All three properties required (unique, non-null, matching type), but the type filter is parameterized — defaults to integer/bigint/UUID-like types, with an optional parameter to specify alternative types.
- Q: What form should the value overlap metric take? → A: Both the raw count of overlapping distinct values and the percentage (fraction of source distinct values found in target).

**Input**: User description: "Rewrite disabled inference tools as data-exposure tools. Remove caching/documentation/inference infrastructure. Replace with raw analysis tools that expose column statistics and FK candidate metrics without pre-scored confidence or reasoning."

## Scope

### Out of Scope

The analysis tools expose raw data and statistics only. The system MUST NOT infer, interpret, or label meaning from the data it returns. Specifically:

- No "is enum" flags or categorical classification of columns — expose distinct value counts and row counts; the consumer decides what constitutes an enumeration.
- No similarity scores between column names — expose the actual names; the consumer judges similarity.
- No type compatibility judgments — expose the actual data types; the consumer decides compatibility.
- No confidence scores, weighted aggregates, or natural-language reasoning about relationships.
- No pattern-based labels (e.g., "looks like a junction table", "appears to be a status column").

The tools are data-exposure tools, not inference tools. All interpretation is the consumer's responsibility.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Explore Column Characteristics (Priority: P1)

An LLM consumer wants to understand the statistical profile of columns in a database table — distinct counts, null rates, row counts, and type-specific distributions — so it can make informed decisions about query strategies, data quality, or schema understanding.

**Why this priority**: Column-level statistics are the foundational building block. Every downstream analysis (including FK candidate discovery) depends on understanding individual column characteristics first.

**Independent Test**: Can be fully tested by requesting get_column_info for a known table and verifying that returned statistics (distinct count, null percentage, row count, type-specific stats) match expected values computed from the underlying data.

**Acceptance Scenarios**:

1. **Given** a connected database with a table containing numeric, string, datetime, and boolean columns, **When** the consumer requests get_column_info for all columns, **Then** each column returns its distinct count, total row count, null percentage, and type-appropriate statistics (min/max/mean/stddev for numeric, min/max/avg length and sample patterns for string, min/max/range for datetime).
2. **Given** a table with many columns, **When** the consumer requests get_column_info filtered by a name pattern, **Then** only columns matching the pattern are analyzed and returned.
3. **Given** a table with many columns, **When** the consumer requests get_column_info for a specific list of column names, **Then** only those named columns are analyzed and returned.
4. **Given** a request with no schema specified, **When** the consumer requests get_column_info, **Then** the default schema is used.
5. **Given** an invalid connection, table, or column name, **When** the consumer requests get_column_info, **Then** a clear error message is returned identifying what was not found.

---

### User Story 2 - Identify Primary Key Candidates (Priority: P2)

An LLM consumer wants to discover which columns in a table meet primary key candidacy criteria — either declared via constraints or exhibiting PK-like structural properties (unique, non-null, and matching a configurable set of types defaulting to integer/bigint/UUID) — so it can understand table identity structure and feed this into downstream FK discovery.

**Why this priority**: PK discovery is a prerequisite for efficient FK candidate search and independently useful for schema understanding. It bridges column-level stats (P1) and FK discovery (P3).

**Independent Test**: Can be fully tested by requesting PK candidates for a table with a declared PK and verifying the declared PK column appears, along with any other columns that meet the structural candidacy criteria.

**Acceptance Scenarios**:

1. **Given** a table with a declared primary key, **When** the consumer requests PK candidates, **Then** the declared PK column is included in results and identified as constraint-backed.
2. **Given** a table with columns that have UNIQUE constraints, **When** the consumer requests PK candidates, **Then** those columns are included and identified as constraint-backed.
3. **Given** a table with columns that have no PK/UNIQUE constraints but exhibit PK-like structural properties (unique values, non-null, and matching the default type set), **When** the consumer requests PK candidates, **Then** those columns are included and marked as structural (not constraint-backed), with the raw properties that qualified them.
4. **Given** a table with a unique non-null VARCHAR column, **When** the consumer requests PK candidates with default type filter, **Then** that column is NOT included (VARCHAR is not in the default type set). **When** the consumer requests PK candidates with types overridden to include VARCHAR, **Then** the column IS included as a structural candidate.
5. **Given** a request with no schema specified, **When** the consumer requests PK candidates, **Then** the default schema is used.
6. **Given** a table where no columns qualify as PK candidates, **When** the consumer requests PK candidates, **Then** an empty result set is returned (not an error).
7. **Given** an invalid connection, table, or schema, **When** the consumer requests PK candidates, **Then** a clear error message is returned.

---

### User Story 3 - Discover Foreign Key Candidates (Priority: P3)

An LLM consumer wants to identify potential foreign key relationships for a given source column by comparing it against candidate columns across the database. By default, the tool compares only against PK-candidate columns (declared or PK-like), but this filter can be toggled off to compare against all columns. The consumer receives raw data for each candidate — column/table names, data types, structural metadata, and optionally value overlap — and decides for itself how to interpret the data, without the system pre-scoring or ranking candidates.

**Why this priority**: FK discovery is the primary use case for relationship exploration, but it builds on column-level understanding (P1) and PK discovery (P2), and is the most complex operation involving cross-table comparisons.

**Independent Test**: Can be fully tested by specifying a known FK column (e.g., an `order_id` column that references `orders.id`) and verifying the true target appears in results with its column/table names, data types, structural metadata, and optionally value overlap.

**Acceptance Scenarios**:

1. **Given** a source column that is a known FK, **When** the consumer requests FK candidates with default settings, **Then** the results include the true target PK with raw data: source and target column/table names, source and target data types, structural metadata (constraints, indexes, nullability), and only PK-candidate columns are considered as targets.
2. **Given** a source column, **When** the consumer requests FK candidates with PK filtering disabled, **Then** all columns in target tables are considered as candidates (not just PK-candidate columns).
3. **Given** a source column, **When** the consumer requests FK candidates scoped to a specific target schema or table list, **Then** only candidates from those targets are returned.
4. **Given** a source column, **When** the consumer requests FK candidates filtered by a target table name pattern, **Then** only candidates from matching tables are returned.
5. **Given** a source column, **When** the consumer requests FK candidates with value overlap enabled, **Then** each candidate also includes the raw count of overlapping distinct values and the percentage of source distinct values found in the candidate column.
6. **Given** a source column and no target filters specified, **When** the consumer requests FK candidates, **Then** the search is scoped to the source column's schema only (not the entire database).
7. **Given** a search that would match more than 100 candidates, **When** the consumer requests FK candidates with default settings, **Then** at most 100 candidates are returned, with an indication that results were limited.
8. **Given** a source column with no plausible FK targets, **When** the consumer requests FK candidates, **Then** an empty result set is returned (not an error).
9. **Given** an invalid connection, table, schema, or column, **When** the consumer requests FK candidates, **Then** a clear error message is returned.

---

### User Story 4 - Clean Removal of Legacy Infrastructure (Priority: P4)

A developer maintaining the codebase wants all disabled inference tools, documentation caching, and related data models fully removed so the codebase has no dead code paths, no orphan imports, and no unused data structures.

**Why this priority**: Cleanup is necessary for codebase health but delivers no new user-facing capability. It unblocks the new analysis tools by removing conflicting code.

**Independent Test**: Can be verified by confirming that no references to removed modules, classes, enums, or fields exist anywhere in the codebase, all existing tests pass (with removed-code tests also removed), and no import errors occur.

**Acceptance Scenarios**:

1. **Given** the current codebase with disabled inference/cache code, **When** the cleanup is complete, **Then** the documentation caching module, documentation generation module, drift detection module, documentation MCP tools, inference module, and all associated test files are fully removed.
2. **Given** the Column data model currently has inference-related fields, **When** the cleanup is complete, **Then** the `inferred_purpose` field, `inferred_confidence` field, and `InferredPurpose` enum are removed from the Column model.
3. **Given** the relationship model has inference-specific types, **When** the cleanup is complete, **Then** `InferredFK` and `InferenceFactors` are removed, while `DeclaredFK` remains unchanged.
4. **Given** the server registration file references hidden tools, **When** the cleanup is complete, **Then** all commented-out tool registrations and their imports are removed.
5. **Given** the full test suite, **When** run after cleanup, **Then** all remaining tests pass with no import errors, no missing reference warnings, and no dead code paths.

---

### Edge Cases

- What happens when a column has all NULL values? Column info should still return valid statistics (100% null rate, 0 distinct values).
- What happens when a table has zero rows? Column info should return zeroed statistics without error.
- What happens when the source column for FK candidate search has no non-null values? The tool should return an empty candidate list or a meaningful empty result.
- What happens when value overlap analysis is requested but the source column has very high cardinality (>1M distinct values)? Per NFR-006, the operation may skip overlap computation or time out after 30 seconds, returning null values for `overlap_count` and `overlap_percentage` with no error raised.
- What happens when multiple columns share the same name across different schemas? FK candidate search should distinguish candidates by schema.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: System MUST provide a tool that returns per-column statistical profiles including distinct count, total row count, null percentage, and type-specific statistics. Type-specific statistics are: numeric types (min/max/mean/stddev), string types (min/max/avg length and top N value samples with frequency counts where N defaults to 10 and MUST be configurable), datetime types (min/max/date range in days, and whether non-midnight times exist).
- **FR-002**: All analysis tools MUST return raw statistics and metadata only. The system MUST NOT interpret, infer, or label meaning from data. Specifically prohibited: similarity scores, type compatibility judgments, confidence scores, weighted aggregates, natural-language reasoning, categorical classifications (e.g., "is_enum" flags), and pattern-based labels (e.g., "looks like a junction table"). All interpretation is the consumer's responsibility.
- **FR-003**: The `get_column_info` tool MUST support filtering by an explicit list of column names or by a name pattern (SQL LIKE syntax), returning info for only matching columns. When no schema is provided, the default schema MUST be used.
- **FR-004**: System MUST provide a tool that identifies primary key candidate columns in a given table — columns with declared PK or UNIQUE constraints, as well as columns meeting all three structural criteria (unique values, non-null, and matching a configurable type set). The type set MUST default to integer, bigint, smallint, tinyint, and uniqueidentifier types and MUST accept an optional parameter to override it. The tool MUST distinguish constraint-backed candidates from structural (not constraint-backed) ones. When no schema is provided, the default schema MUST be used.
- **FR-005**: The FK candidate tool MUST, given a single source column, return raw data for each candidate: source and target column names, source and target table names, source and target data types, and structural metadata (constraints, indexes, nullability). Compliance with FR-002 raw-data constraint is mandatory.
- **FR-006**: The FK candidate tool MUST default to comparing only against PK-candidate columns (as defined by FR-004) and MUST provide a toggle to disable this filter and compare against all columns in target tables.
- **FR-007**: The FK candidate tool MUST support scoping candidate targets by schema, by an explicit list of table names, or by a table name pattern. When no target filters are provided, the search MUST default to the source column's schema (never a full-database scan).
- **FR-008**: The FK candidate tool MUST return a default maximum of 100 candidates total across all target tables, with an optional parameter to override or remove the limit.
- **FR-009**: The FK candidate tool MUST support an optional value overlap mode that adds two data-level overlap values per candidate: the raw count of source distinct values found in the candidate column, and the percentage of source distinct values found in the candidate column.
- **FR-010**: System MUST remove all documentation caching infrastructure (storage, drift detection, document generation), the documentation MCP tools, the `DocumentationCache` model, the `InferredPurpose` enum, inference-related fields on `Column`, the `InferredFK` and `InferenceFactors` types, the entire inference module, and all associated tool registrations and imports.
- **FR-011**: System MUST introduce a data structure to hold raw FK candidate data (source/target names, data types, structural metadata, optional value overlap count and percentage) that replaces the removed `InferredFK`/`InferenceFactors`.
- **FR-012**: The `DeclaredFK` model and its behavior MUST remain unchanged.
- **FR-013**: All existing tests that reference removed code MUST be removed or updated, and the full test suite MUST pass after changes.

### Non-Functional Requirements

**Test Environment Baseline**: Performance requirements measured on SQL Server 2019+ with 4-core CPU, 16GB RAM, SSD storage, under idle query load (no concurrent queries).

- **NFR-001**: The `get_column_info` tool MUST return results within 5 seconds for tables up to 10 million rows under the test environment baseline.
- **NFR-002**: The `find_pk_candidates` tool MUST complete within 5 seconds for tables up to 10 million rows under the test environment baseline.
- **NFR-003**: The `find_fk_candidates` tool MUST complete within 10 seconds (metadata-only mode) or 30 seconds (with value overlap enabled) for searches that evaluate up to 100 candidate columns under the test environment baseline.
- **NFR-004**: The `find_fk_candidates` tool MUST use a default result limit of 100 candidates to prevent unbounded result sets and excessive query times.
- **NFR-005**: When no explicit target filters are provided, the `find_fk_candidates` tool MUST default to searching only the source column's schema to prevent expensive full-database scans.
- **NFR-006**: Value overlap computation for high-cardinality columns (>1 million distinct values) MAY be skipped or time out after 30 seconds, with the tool returning null overlap values and an indication that overlap was not computed.

### Key Entities

- **Column Statistics**: Per-column statistical profile including distinct count, total row count, null percentage, and type-specific metrics (numeric, string, datetime). No interpretive labels.
- **PK Candidate**: A column meeting PK candidacy criteria, either constraint-backed (declared PK or UNIQUE) or structural (not constraint-backed) — requiring all three of: unique values, non-null, and matching the configured type set (default: integer/bigint/UUID). Includes the basis for candidacy and which properties qualified the column.
- **FK Candidate Data**: Raw data for a single source-to-target pair: source and target column/table names, data types, structural metadata (constraints, indexes, nullability), and optional value overlap (raw count of overlapping distinct values plus percentage of source distinct values found in target). No similarity scores or compatibility judgments.
- **Declared FK**: Existing schema-defined foreign key relationship (unchanged by this feature).

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Consumers can retrieve statistical profiles for any column in a connected database within a single tool call, receiving distinct count, null rate, and type-appropriate metrics.
- **SC-002**: Consumers can discover PK candidates for any table in a single tool call, receiving constraint-backed and structural candidates with the raw properties that qualified each.
- **SC-003**: Consumers can discover FK candidates for any column and receive raw comparison data in a single tool call, with results scoped by schema, table list, or name pattern as needed.
- **SC-004**: The codebase contains zero references to removed modules, classes, enums, or fields after cleanup — verified by automated search and a passing test suite.
- **SC-005**: All analysis tools comply with FR-002 raw-data constraint: zero interpretive output across all tool responses.
- **SC-006**: Existing active tools (connect, list schemas, list tables, get table schema, get sample data, execute query) continue to function identically after all changes.

## Assumptions

- The `get_column_info` tool reuses existing statistical query logic from the existing (to-be-removed) inference module, adapted for direct exposure rather than internal scoring.
- The FK candidate tool reuses existing data-gathering logic (column metadata, value overlap) from the existing inference module, but exposes raw data instead of computed scores or interpretive labels.
- Value overlap computation for FK candidates is opt-in because it involves cross-table data queries that may be expensive on large datasets.
- The system does not need to persist analysis results — all tools return results on demand per invocation.
- "Default schema" means the database's standard default schema (e.g., `dbo` for SQL Server), consistent with existing tool behavior.
