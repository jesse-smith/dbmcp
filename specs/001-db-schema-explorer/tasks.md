# Tasks: Database Schema Explorer MCP Server

**Input**: Design documents from `/specs/001-db-schema-explorer/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/, quickstart.md

**Tests**: Tests are NOT explicitly requested in the feature specification, so test tasks are omitted. Focus is on implementation.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root (per plan.md)

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [ ] T001 Create project directory structure per plan.md (src/{mcp_server,db,inference,cache,models}, tests/{unit,integration,fixtures}, docs/)
- [ ] T002 Initialize Python 3.11+ virtual environment and install core dependencies (mcp[cli], sqlalchemy, pyodbc)
- [ ] T003 [P] Configure logging infrastructure (never stdout, file + stderr only per research.md)
- [ ] T004 [P] Create .gitignore with Python and MCP server patterns

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY user story can be implemented

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [ ] T005 Create Connection data model in src/models/schema.py
- [ ] T006 Create Schema, Table, Column, Index data models in src/models/schema.py
- [ ] T007 Create Relationship data model in src/models/relationship.py
- [ ] T008 [P] Implement ConnectionManager with SQLAlchemy pooling in src/db/connection.py
- [ ] T009 [P] Implement MetadataService base class with inspector setup in src/db/metadata.py
- [ ] T010 Configure FastMCP server initialization in src/mcp_server/server.py
- [ ] T011 Implement connect_database MCP tool in src/mcp_server/server.py

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 1 - Initial Database Discovery (Priority: P1) 🎯 MVP

**Goal**: Enable AI agent to quickly understand database structure (schemas, tables, row counts) within configurable token budget

**Independent Test**: Connect to test database and verify structured overview of schemas and tables is returned with row counts and relevance sorting

### Implementation for User Story 1

- [ ] T012 [P] [US1] Implement list_schemas query in src/db/metadata.py using sys.schemas DMV
- [ ] T013 [P] [US1] Implement list_tables query in src/db/metadata.py using sys.tables and sys.dm_db_partition_stats
- [ ] T014 [US1] Implement list_schemas MCP tool in src/mcp_server/server.py with schema grouping
- [ ] T015 [US1] Implement list_tables MCP tool in src/mcp_server/server.py with filtering (schema_filter, name_pattern, min_row_count)
- [ ] T016 [US1] Add sorting logic (by name, row_count, last_modified) to list_tables in src/mcp_server/server.py
- [ ] T017 [US1] Add output_mode (summary vs detailed) for token efficiency in src/mcp_server/server.py
- [ ] T018 [US1] Add limit parameter enforcement (default 100, max 1000) in src/mcp_server/server.py
- [ ] T019 [US1] Handle access_denied case for tables without SELECT permission in src/db/metadata.py

**Checkpoint**: User Story 1 should be fully functional - agent can discover database structure efficiently

---

## Phase 4: User Story 2 - Table Structure Analysis (Priority: P1)

**Goal**: Enable analyst to understand specific table structure (columns, types, constraints, indexes, declared FKs)

**Independent Test**: Request schema for a known table and verify all columns, types, constraints, indexes, and relationships are returned consistently

### Implementation for User Story 2

- [ ] T020 [US2] Implement get_columns query using SQLAlchemy inspector in src/db/metadata.py
- [ ] T021 [US2] Implement get_indexes query using SQLAlchemy inspector in src/db/metadata.py
- [ ] T022 [US2] Implement get_foreign_keys query using SQLAlchemy inspector in src/db/metadata.py
- [ ] T023 [US2] Implement get_primary_key query using SQLAlchemy inspector in src/db/metadata.py
- [ ] T024 [US2] Combine metadata into structured table schema response in src/db/metadata.py
- [ ] T025 [US2] Implement get_table_schema MCP tool in src/mcp_server/server.py
- [ ] T026 [US2] Add include_indexes and include_relationships flags in src/mcp_server/server.py
- [ ] T027 [US2] Map column metadata to Column entity format in src/mcp_server/server.py
- [ ] T028 [US2] Add error handling for non-existent tables in src/mcp_server/server.py

**Checkpoint**: User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Relationship Inference (Priority: P1)

**Goal**: Infer likely join columns in legacy databases with undeclared foreign keys using naming patterns, type compatibility, and structural hints

**Independent Test**: Run inference on database with known (but undeclared) relationships and measure precision/recall meets 75-80% target

### Implementation for User Story 3

- [ ] T029 [P] [US3] Create InferredFK data class in src/models/relationship.py
- [ ] T030 [P] [US3] Implement name normalization (lowercase, remove underscores, strip suffixes) in src/inference/relationships.py
- [ ] T031 [US3] Implement name similarity scoring using difflib.SequenceMatcher in src/inference/relationships.py
- [ ] T032 [US3] Implement type compatibility check (group compatible types) in src/inference/relationships.py
- [ ] T033 [US3] Implement structural hints scoring (nullable, PK, unique index) in src/inference/relationships.py
- [ ] T034 [US3] Implement three-factor weighted scoring (40% name, 15% type, 45% structural) in src/inference/relationships.py
- [ ] T035 [US3] Create ForeignKeyInferencer class with threshold filtering in src/inference/relationships.py
- [ ] T036 [US3] Implement confidence score calculation and reasoning generation in src/inference/relationships.py
- [ ] T037 [US3] Query all tables and columns for candidate matching in src/inference/relationships.py
- [ ] T038 [US3] Return top N candidates sorted by confidence in src/inference/relationships.py
- [ ] T039 [US3] Implement infer_relationships MCP tool in src/mcp_server/server.py
- [ ] T040 [US3] Add confidence_threshold parameter (default 0.50) in src/mcp_server/server.py
- [ ] T041 [US3] Add max_candidates parameter (default 20) in src/mcp_server/server.py
- [ ] T042 [US3] Add include_value_overlap flag (Phase 2 feature, initially False) in src/mcp_server/server.py
- [ ] T043 [US3] Track analysis_time_ms and total_candidates_evaluated metrics in src/mcp_server/server.py

**Checkpoint**: All P1 user stories should now be independently functional - core MCP server complete

---

## Phase 6: User Story 4 - Sample Data Retrieval (Priority: P2)

**Goal**: Retrieve representative sample data to understand actual values, identify data quality issues, and understand cryptic columns

**Independent Test**: Request samples from various tables and verify returned data is representative, properly formatted, respects row limits, and handles binary/large text

### Implementation for User Story 4

- [ ] T044 [P] [US4] Create SampleData entity in src/models/schema.py
- [ ] T045 [P] [US4] Implement TOP sampling method (SELECT TOP N) in src/db/query.py
- [ ] T046 [US4] Implement distributed sampling method (TABLESAMPLE or modulo) in src/db/query.py
- [ ] T047 [US4] Implement binary column truncation (first 32 bytes as hex + size) in src/db/query.py
- [ ] T048 [US4] Implement large text truncation (>1000 chars) in src/db/query.py
- [ ] T049 [US4] Track truncated_columns list in sample response in src/db/query.py
- [ ] T050 [US4] Implement get_sample_data MCP tool in src/mcp_server/server.py
- [ ] T051 [US4] Add sample_size parameter (default 5, max 1000) in src/mcp_server/server.py
- [ ] T052 [US4] Add sampling_method parameter (top vs distributed) in src/mcp_server/server.py
- [ ] T053 [US4] Add columns filter for selective column sampling in src/mcp_server/server.py
- [ ] T054 [US4] Return structured JSON with rows as array of objects in src/mcp_server/server.py

**Checkpoint**: User Story 4 complete and testable independently

---

## Phase 7: User Story 5 - Column Purpose Inference (Priority: P2)

**Goal**: Infer purpose of cryptic columns (FLG_1, STATUS_CD, AMT_3) using data patterns, value distributions, and usage context

**Independent Test**: Provide known cryptic columns and verify system generates reasonable hypotheses about purpose

### Implementation for User Story 5

- [ ] T055 [US5] Implement distinct value count query in src/inference/columns.py
- [ ] T056 [US5] Implement null percentage calculation in src/inference/columns.py
- [ ] T057 [US5] Implement enum detection (distinct count <50 AND <10% of rows) in src/inference/columns.py
- [ ] T058 [US5] Implement numeric statistics (min, max, mean, median, std dev) in src/inference/columns.py
- [ ] T059 [US5] Implement numeric purpose heuristics (ID, percentage, amount, quantity) in src/inference/columns.py
- [ ] T060 [US5] Implement date/time analysis (range, patterns, business hours) in src/inference/columns.py
- [ ] T061 [US5] Implement string analysis (top values with frequencies) in src/inference/columns.py
- [ ] T062 [US5] Create ColumnAnalyzer class with purpose inference logic in src/inference/columns.py
- [ ] T063 [US5] Return inferred_purpose enum (id, enum, status, flag, amount, quantity, percentage, timestamp, unknown) in src/inference/columns.py
- [ ] T064 [US5] Calculate confidence score for inferred purpose in src/inference/columns.py
- [ ] T065 [US5] Implement analyze_column MCP tool in src/mcp_server/server.py
- [ ] T066 [US5] Return type-specific statistics (categorical top values, numeric min/max/mean, date ranges) in src/mcp_server/server.py

**Checkpoint**: User Story 5 complete and testable independently

---

## Phase 8: User Story 6 - Documentation Generation (Priority: P2)

**Goal**: Save exploration findings locally to avoid repeating discovery process, saving tokens and time across sessions

**Independent Test**: Generate docs, start new session, verify docs are loaded and reduce subsequent discovery queries by 50%

### Implementation for User Story 6

- [ ] T067 [P] [US6] Create DocumentationCache entity in src/models/schema.py
- [ ] T068 [P] [US6] Implement markdown file writer in src/cache/storage.py
- [ ] T069 [US6] Create cache directory structure (docs/[connection_id]/{overview,schemas,tables,relationships}.md) in src/cache/storage.py
- [ ] T070 [US6] Implement schema hash calculation (sorted table.column names) in src/cache/storage.py
- [ ] T071 [US6] Generate overview.md with database summary and schema list in src/cache/storage.py
- [ ] T072 [US6] Generate schema markdown files (tables per schema) in src/cache/storage.py
- [ ] T073 [US6] Generate table markdown files (full metadata per table) in src/cache/storage.py
- [ ] T074 [US6] Generate relationships.md (declared and inferred FKs) in src/cache/storage.py
- [ ] T075 [US6] Implement export_documentation MCP tool in src/mcp_server/server.py
- [ ] T076 [US6] Add output_dir parameter (default docs/[connection_id]) in src/mcp_server/server.py
- [ ] T077 [US6] Add include_sample_data flag in src/mcp_server/server.py
- [ ] T078 [US6] Add include_inferred_relationships flag in src/mcp_server/server.py
- [ ] T079 [US6] Return files_created list and total_size_bytes in src/mcp_server/server.py
- [ ] T080 [US6] Implement markdown file reader in src/cache/storage.py
- [ ] T081 [US6] Parse cached documentation back into entities in src/cache/storage.py
- [ ] T082 [US6] Implement load_cached_docs MCP tool in src/mcp_server/server.py
- [ ] T083 [US6] Return cache_age_days and entity counts in src/mcp_server/server.py
- [ ] T084 [US6] Check has_cached_docs in connect_database response in src/mcp_server/server.py
- [ ] T085 [US6] Implement drift detection logic (compare cached vs current hash) in src/cache/drift.py
- [ ] T086 [US6] Identify added, removed, modified tables in src/cache/drift.py
- [ ] T087 [US6] Generate human-readable drift summary in src/cache/drift.py
- [ ] T088 [US6] Implement check_drift MCP tool in src/mcp_server/server.py
- [ ] T089 [US6] Return drift_detected flag and changes breakdown in src/mcp_server/server.py
- [ ] T090 [US6] Auto-trigger drift check on connect (default behavior) in src/mcp_server/server.py

**Checkpoint**: User Story 6 complete - documentation caching and drift detection working

---

## Phase 9: User Story 7 - Query Execution (Priority: P3)

**Goal**: Execute ad-hoc SELECT queries to pull specific data after understanding database structure

**Independent Test**: Execute various SELECT queries and verify results returned correctly with formatting, limits, and read-only enforcement

### Implementation for User Story 7

- [ ] T091 [P] [US7] Create Query entity in src/models/schema.py
- [ ] T092 [P] [US7] Implement query type parser (detect SELECT, INSERT, UPDATE, DELETE) in src/db/query.py
- [ ] T093 [US7] Implement read-only enforcement (block non-SELECT by default) in src/db/query.py
- [ ] T094 [US7] Implement row limit injection (TOP clause) in src/db/query.py
- [ ] T095 [US7] Execute query and capture results with column headers in src/db/query.py
- [ ] T096 [US7] Track execution_time_ms and rows_affected metrics in src/db/query.py
- [ ] T097 [US7] Return structured result set (columns array + rows array) in src/db/query.py
- [ ] T098 [US7] Implement execute_query MCP tool in src/mcp_server/server.py
- [ ] T099 [US7] Add row_limit parameter (default 1000, max 10000) in src/mcp_server/server.py
- [ ] T100 [US7] Return blocked status with error message for write operations in src/mcp_server/server.py
- [ ] T101 [US7] Indicate rows_available vs rows_returned when limit applied in src/mcp_server/server.py
- [ ] T102 [US7] Add error handling and actionable error messages in src/mcp_server/server.py

**Checkpoint**: All user stories complete - full MCP server functional

---

## Phase 10: Polish & Cross-Cutting Concerns

**Purpose**: Improvements that affect multiple user stories

- [ ] T103 [P] Add comprehensive error handling across all MCP tools in src/mcp_server/server.py
- [ ] T104 [P] Ensure credentials never logged (NFR-005 compliance) in src/db/connection.py
- [ ] T105 [P] Add performance logging (track query times against NFR-001, NFR-002) across src/db/
- [ ] T106 [P] Create test fixtures (SQL scripts for test database) in tests/fixtures/
- [ ] T107 [P] Write unit tests for name similarity algorithm in tests/unit/test_relationships.py
- [ ] T108 [P] Write unit tests for type compatibility checks in tests/unit/test_relationships.py
- [ ] T109 [P] Write unit tests for column purpose inference in tests/unit/test_columns.py
- [ ] T110 [P] Write integration test for full discovery workflow in tests/integration/test_discovery.py
- [ ] T111 [P] Write integration test for FK inference accuracy in tests/integration/test_fk_inference.py
- [ ] T112 [P] Write integration test for caching and drift detection in tests/integration/test_caching.py
- [ ] T113 Add connection pooling configuration tuning (pool_size, max_overflow) in src/db/connection.py
- [ ] T114 Update quickstart.md with actual implementation details (if needed)
- [ ] T115 Create Claude for Desktop configuration example in docs/claude_config.json
- [ ] T116 Add README.md with installation and usage instructions in project root
- [ ] T117 Validate quickstart.md examples work end-to-end
- [ ] T118 Run pytest test suite and ensure all tests pass
- [ ] T119 Run ruff linting and fix any issues
- [ ] T120 Perform performance validation (metadata queries <30s for 1000 tables per NFR-001)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Story 1 (Phase 3)**: Depends on Foundational (Phase 2)
- **User Story 2 (Phase 4)**: Depends on Foundational (Phase 2) - independent of US1
- **User Story 3 (Phase 5)**: Depends on Foundational (Phase 2) - independent of US1/US2
- **User Story 4 (Phase 6)**: Depends on Foundational (Phase 2) - independent of other stories
- **User Story 5 (Phase 7)**: Depends on Foundational (Phase 2) and US4 (needs sample data methods)
- **User Story 6 (Phase 8)**: Depends on Foundational (Phase 2) and US1/US2/US3 (needs metadata to cache)
- **User Story 7 (Phase 9)**: Depends on Foundational (Phase 2) - independent of other stories
- **Polish (Phase 10)**: Depends on all desired user stories being complete

### User Story Dependencies

- **User Story 1 (P1)**: Can start after Foundational - No dependencies on other stories ✅ MVP
- **User Story 2 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 3 (P1)**: Can start after Foundational - No dependencies on other stories
- **User Story 4 (P2)**: Can start after Foundational - No dependencies on other stories
- **User Story 5 (P2)**: Soft dependency on US4 (shares query execution patterns)
- **User Story 6 (P2)**: Soft dependency on US1/US2/US3 (needs their outputs to cache)
- **User Story 7 (P3)**: Can start after Foundational - No dependencies on other stories

### Within Each User Story

- Tasks marked [P] within a story can run in parallel
- Implementation tasks typically follow: Models → Services → Tools → Integration
- Story complete before moving to next priority

### Parallel Opportunities

#### Phase 1 (Setup)
```bash
# All marked [P] can run together:
T003 + T004
```

#### Phase 2 (Foundational)
```bash
# Models can be created in parallel:
T005 + T006 + T007
# Services can be created in parallel:
T008 + T009
```

#### User Story 1
```bash
# Queries can be implemented in parallel:
T012 + T013
```

#### User Story 2
```bash
# All metadata queries in parallel:
T020 + T021 + T022 + T023
```

#### User Story 3
```bash
# Inference algorithms in parallel:
T029 + T030
```

#### User Story 4
```bash
# Sampling methods in parallel:
T044 + T045 + T046
```

#### User Story 7
```bash
# Query components in parallel:
T091 + T092
```

#### Phase 10 (Polish)
```bash
# Most polish tasks are independent:
T103 + T104 + T105 + T106 + T107 + T108 + T109 + T110 + T111 + T112
```

---

## Parallel Example: User Story 1

```bash
# Step 1: Launch both metadata queries in parallel
Task T012: "Implement list_schemas query in src/db/metadata.py using sys.schemas DMV"
Task T013: "Implement list_tables query in src/db/metadata.py using sys.tables and sys.dm_db_partition_stats"

# Step 2: After T012/T013 complete, launch MCP tools in parallel
Task T014: "Implement list_schemas MCP tool in src/mcp_server/server.py with schema grouping"
Task T015: "Implement list_tables MCP tool in src/mcp_server/server.py with filtering"
```

---

## Implementation Strategy

### MVP First (P1 User Stories Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 1 (Database Discovery) → **First Demo Point**
4. Complete Phase 4: User Story 2 (Table Structure Analysis)
5. Complete Phase 5: User Story 3 (Relationship Inference)
6. **STOP and VALIDATE**: Test all P1 stories independently
7. Deploy/demo MVP with core exploration capabilities

**MVP Scope**: After Phase 5, the MCP server can:
- Connect to SQL Server databases
- List schemas and tables efficiently (token-aware)
- Provide detailed table structure
- Infer undeclared foreign key relationships
This fulfills the primary "database exploration and structure understanding" goal.

### Incremental Delivery (Add P2/P3 Features)

1. Add Phase 6: User Story 4 (Sample Data) → **Second Demo Point**
2. Add Phase 7: User Story 5 (Column Purpose) → **Third Demo Point**
3. Add Phase 8: User Story 6 (Documentation Caching) → **Fourth Demo Point**
4. Add Phase 9: User Story 7 (Query Execution) → **Fifth Demo Point**
5. Complete Phase 10: Polish & Testing

Each phase adds value without breaking previous functionality.

### Parallel Team Strategy

With multiple developers:

1. Team completes Phase 1 + Phase 2 together
2. Once Foundational is done:
   - Developer A: User Story 1 + User Story 4
   - Developer B: User Story 2 + User Story 5
   - Developer C: User Story 3 + User Story 7
   - Developer D: User Story 6
3. Stories complete and integrate independently

---

## Success Criteria Validation

| Success Criterion | Validated By | Target |
|-------------------|--------------|--------|
| **SC-001**: 3 tool calls to understand DB | US1 tasks (T012-T019) | list_schemas + list_tables + get_table_schema |
| **SC-002**: 50% fewer queries via caching | US6 tasks (T067-T090) | Documentation cache + drift detection |
| **SC-003**: 80%+ inference accuracy | US3 tasks (T029-T043) + Integration tests | FK inference algorithm |
| **SC-004**: 90%+ column purpose hypotheses | US5 tasks (T055-T066) | Column analysis heuristics |
| **SC-005**: Docs usable by different agent | US6 tasks (T067-T090) | Markdown export + load |
| **SC-006**: 60% token reduction | US1 (T017) + US6 | Summary mode + caching |
| **SC-007**: Query execution <10s | US7 tasks (T091-T102) + NFR-002 | Row limit enforcement |

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each user story should be independently completable and testable
- Commit after each task or logical group
- Stop at any checkpoint to validate story independently
- Research documents available in `/Users/jsmith79/Documents/Projects/Ongoing/dbmcp/research/` for FK inference implementation details
- Reference implementation for Phase 1 FK inference: `research/fk_inference_phase1_example.py`
