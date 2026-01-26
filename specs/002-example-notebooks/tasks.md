# Tasks: Example Notebooks

> **STATUS: ARCHIVED** | Date: 2026-01-26 | Branch: `002-example-notebooks`
>
> **Reason**: Workflow changed. See spec.md for details.

**Input**: Design documents from `/specs/002-example-notebooks/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: Tests are included for test database setup infrastructure (per constitution principle III)

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each notebook.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

Single project structure at repository root:
- `examples/` - New directory for notebooks and supporting files
- `tests/examples/` - Tests for example infrastructure
- Notebooks use existing `src/` for DBMCP functionality

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and basic structure

- [X] T001 Create examples directory structure (examples/notebooks, examples/test_database, examples/shared)
- [X] T002 [P] Add Jupyter to optional dependencies in pyproject.toml under [project.optional-dependencies.examples]
- [X] T003 [P] Create .gitignore entries for examples/test_database/example.db (generated file)

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core infrastructure that MUST be complete before ANY notebook can be created

**⚠️ CRITICAL**: No user story (notebook) work can begin until this phase is complete

- [X] T004 Copy test database schema from specs/002-example-notebooks/contracts/test_database_schema.sql to examples/test_database/schema.sql
- [X] T005 Create database setup script in examples/test_database/setup.py with SQLite support
- [X] T006 [P] Create notebook helper utilities in examples/shared/notebook_helpers.py (setup_connection, print_table, verify_notebook_environment functions)
- [X] T007 [P] Create test for database setup script in tests/examples/test_database_setup.py (verify 6 tables, foreign keys, sample data)
- [X] T008 Run database setup script to generate examples/test_database/example.db
- [X] T009 Verify test database setup by running pytest tests/examples/test_database_setup.py

**Checkpoint**: Foundation ready - notebook implementation can now begin in parallel

---

## Phase 3: User Story 1 - Quick Start with Basic Functionality (Priority: P1) 🎯 MVP

**Goal**: Create basic notebook demonstrating connection, list_schemas, and list_tables operations

**Independent Test**: Execute notebook from start to finish (<5 minutes), verify connection works, schemas displayed, tables listed with metadata

### Implementation for User Story 1

- [X] T010 [US1] Create 01_basic_connection.ipynb in examples/notebooks/ with metadata cell (version 1.0.0, compatible DBMCP 0.1.0+, last updated, test DB version 1.0)
- [X] T011 [US1] Add overview and prerequisites section to 01_basic_connection.ipynb (markdown cell with learning objectives)
- [X] T012 [US1] Add environment verification cell to 01_basic_connection.ipynb (check Python version, MCP, imports from notebook_helpers)
- [X] T013 [US1] Add Section 1 to 01_basic_connection.ipynb: Connection setup (markdown intro + code cell using setup_connection + explanation markdown)
- [X] T014 [US1] Add Section 2 to 01_basic_connection.ipynb: List schemas (markdown intro + code cell calling list_schemas + results explanation)
- [X] T015 [US1] Add Section 3 to 01_basic_connection.ipynb: List tables (markdown intro + code cell with filtering examples + results explanation)
- [X] T016 [US1] Add summary section to 01_basic_connection.ipynb (accomplishments checklist, key concepts, common pitfalls)
- [X] T017 [US1] Add next steps section to 01_basic_connection.ipynb (links to notebook 02, documentation, community resources)
- [X] T018 [US1] Execute all cells in 01_basic_connection.ipynb and save with outputs
- [X] T019 [US1] Verify 01_basic_connection.ipynb completes in under 5 minutes and meets acceptance criteria

**Checkpoint**: User Story 1 (basic notebook) should be fully functional and independently testable

---

## Phase 4: User Story 2 - Exploring Table Details and Relationships (Priority: P2)

**Goal**: Create intermediate notebook demonstrating get_table_schema and infer_relationships operations

**Independent Test**: Execute notebook independently, verify table schema details displayed (columns, indexes, constraints), relationship inference shows confidence scores

### Implementation for User Story 2

- [X] T020 [US2] Create 02_table_inspection.ipynb in examples/notebooks/ with metadata cell (version 1.0.0, compatible DBMCP 0.1.0+)
- [X] T021 [US2] Add overview and prerequisites section to 02_table_inspection.ipynb (references notebook 01, focuses on deep inspection)
- [X] T022 [US2] Add environment verification cell to 02_table_inspection.ipynb
- [X] T023 [US2] Add Section 1 to 02_table_inspection.ipynb: Connection setup (brief, references notebook 01)
- [X] T024 [US2] Add Section 2 to 02_table_inspection.ipynb: Get table schema (markdown intro + code cell with get_table_schema + column details explanation)
- [X] T025 [US2] Add Section 3 to 02_table_inspection.ipynb: Inspect indexes (code cell showing index information + explanation of index types)
- [X] T026 [US2] Add Section 4 to 02_table_inspection.ipynb: Inspect foreign keys (code cell showing declared FKs + relationship diagram explanation)
- [X] T027 [US2] Add Section 5 to 02_table_inspection.ipynb: Infer relationships (markdown intro + code cell with infer_relationships + confidence score explanation)
- [X] T028 [US2] Add Section 6 to 02_table_inspection.ipynb: Interpret inference results (explanation of reasoning, when to trust high vs low confidence)
- [X] T029 [US2] Add summary section to 02_table_inspection.ipynb (accomplishments, key concepts about schema inspection)
- [X] T030 [US2] Add next steps section to 02_table_inspection.ipynb (links to notebook 03, advanced patterns)
- [X] T031 [US2] Execute all cells in 02_table_inspection.ipynb and save with outputs
- [X] T032 [US2] Verify 02_table_inspection.ipynb completes in under 10 minutes and meets acceptance criteria

**Checkpoint**: User Stories 1 AND 2 should both work independently

---

## Phase 5: User Story 3 - Advanced Usage Patterns (Priority: P3)

**Goal**: Create advanced notebook demonstrating filtering, error handling, and optimization techniques

**Independent Test**: Execute notebook with advanced scenarios (filtering large tables, connection error handling, performance optimization), verify all patterns work

### Implementation for User Story 3

- [X] T033 [US3] Create 03_advanced_patterns.ipynb in examples/notebooks/ with metadata cell (version 1.0.0, compatible DBMCP 0.1.0+)
- [X] T034 [US3] Add overview and prerequisites section to 03_advanced_patterns.ipynb (references notebooks 01 and 02, focuses on production patterns)
- [X] T035 [US3] Add environment verification cell to 03_advanced_patterns.ipynb
- [X] T036 [US3] Add Section 1 to 03_advanced_patterns.ipynb: Filtering large result sets (markdown intro + code cells with schema_filter, name_pattern, limit parameters + performance comparison)
- [X] T037 [US3] Add Section 2 to 03_advanced_patterns.ipynb: Sorting and pagination (code cells showing sort_by parameter, combining with limits for pagination)
- [X] T038 [US3] Add Section 3 to 03_advanced_patterns.ipynb: Error handling patterns (markdown intro + try/except examples for connection failures + recovery guidance)
- [X] T039 [US3] Add Section 4 to 03_advanced_patterns.ipynb: Handle invalid credentials (try/except cell showing graceful error handling + user-friendly messages)
- [X] T040 [US3] Add Section 5 to 03_advanced_patterns.ipynb: Performance optimization (markdown intro + code cells comparing summary vs detailed output modes + token efficiency explanation)
- [X] T041 [US3] Add Section 6 to 03_advanced_patterns.ipynb: Selective metadata retrieval (code cells with include_indexes=False, include_relationships=False examples)
- [X] T042 [US3] Add Section 7 to 03_advanced_patterns.ipynb: Real-world workflow example (end-to-end scenario combining techniques for database documentation task)
- [X] T043 [US3] Add summary section to 03_advanced_patterns.ipynb (accomplishments, advanced patterns checklist, production best practices)
- [X] T044 [US3] Add next steps section to 03_advanced_patterns.ipynb (links to documentation, community, suggestions for customization)
- [X] T045 [US3] Execute all cells in 03_advanced_patterns.ipynb and save with outputs
- [X] T046 [US3] Verify 03_advanced_patterns.ipynb completes in under 15 minutes and meets acceptance criteria

**Checkpoint**: All three notebooks should now be independently functional and demonstrate complete feature set

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, validation, and finishing touches

- [X] T047 [P] Create examples/README.md with quick start instructions, notebook index table, prerequisites, troubleshooting section
- [X] T048 [P] Add notebook index table to examples/README.md listing all 3 notebooks with difficulty, time, features columns
- [X] T049 [P] Add "Using Your Own Database" section to examples/README.md (environment variable configuration instructions)
- [X] T050 [P] Add test database schema overview to examples/README.md (describe 6 tables and their purpose)
- [X] T051 Add examples section to main project README.md at repository root (link to examples/README.md, mention quick start)
- [X] T052 [P] Verify all notebooks follow contract from specs/002-example-notebooks/contracts/notebook_structure.md
- [X] T053 [P] Verify all notebooks use consistent emoji usage (✓ ⚠️ ℹ️ 📓 📖 🐛 💬 💡 per contract)
- [X] T054 [P] Verify all notebooks have proper metadata (version, compatibility, last updated, test DB version)
- [X] T055 Run manual execution test: Execute all 3 notebooks in sequence on fresh environment
- [X] T056 [P] Add CI configuration for notebook validation using nbval (if CI pipeline exists)
- [X] T057 Update CLAUDE.md to reflect completed examples feature (if not auto-updated)
- [X] T058 Create commit for completed examples feature

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all notebooks
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - Notebooks can then proceed in parallel (if multiple developers)
  - Or sequentially in priority order (P1 → P2 → P3)
- **Polish (Phase 6)**: Depends on all notebooks being complete

### User Story Dependencies

- **User Story 1 (P1) - Basic Notebook**: Can start after Foundational (Phase 2) - No dependencies on other notebooks
- **User Story 2 (P2) - Intermediate Notebook**: Can start after Foundational (Phase 2) - References US1 in content but is independently executable
- **User Story 3 (P3) - Advanced Notebook**: Can start after Foundational (Phase 2) - References US1/US2 in content but is independently executable

### Within Each User Story

- Metadata and structure cells before content
- Sections in order (environment check → connection → features → summary → next steps)
- Content complete before execution
- Execution and output saving before verification

### Parallel Opportunities

- T002 and T003 (Setup phase) can run in parallel
- T006 and T007 (Foundational phase) can run in parallel (different files)
- Once Foundational complete, all three notebooks (US1, US2, US3) can start in parallel
- T047, T048, T049, T050 (README sections) can be written in parallel
- T052, T053, T054 (verification tasks) can run in parallel
- T056 and T057 (CI and CLAUDE.md updates) can run in parallel

---

## Parallel Example: Foundational Phase

```bash
# Launch helper and test creation together:
Task: "Create notebook helper utilities in examples/shared/notebook_helpers.py"
Task: "Create test for database setup script in tests/examples/test_database_setup.py"
```

## Parallel Example: All Notebooks After Foundation

```bash
# Once Phase 2 complete, all notebooks can start simultaneously:
Task: "Create 01_basic_connection.ipynb" (Developer A)
Task: "Create 02_table_inspection.ipynb" (Developer B)
Task: "Create 03_advanced_patterns.ipynb" (Developer C)
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (3 tasks, ~5 minutes)
2. Complete Phase 2: Foundational (6 tasks, ~30 minutes) - CRITICAL
3. Complete Phase 3: User Story 1 - Basic Notebook (10 tasks, ~45 minutes)
4. **STOP and VALIDATE**: Test basic notebook independently
5. Demo to stakeholders - users can now get started with DBMCP

**MVP Delivery**: ~1.5 hours, delivers core value (basic quick start)

### Incremental Delivery

1. Setup + Foundational → Foundation ready (~35 minutes)
2. Add User Story 1 → Test independently → Commit/Deploy (MVP! ~45 minutes)
3. Add User Story 2 → Test independently → Commit/Deploy (~60 minutes)
4. Add User Story 3 → Test independently → Commit/Deploy (~75 minutes)
5. Add Polish → Final validation → Commit/Deploy (~30 minutes)

**Total**: ~3.5-4 hours for complete feature

### Parallel Team Strategy

With 3 developers:

1. Team completes Setup + Foundational together (~35 minutes)
2. Once Foundational done:
   - Developer A: User Story 1 (Basic) - T010-T019
   - Developer B: User Story 2 (Intermediate) - T020-T032
   - Developer C: User Story 3 (Advanced) - T033-T046
3. All notebooks developed in parallel (~75 minutes max)
4. Team collaborates on Polish phase (~30 minutes)

**Total with parallelization**: ~2 hours

---

## Task Statistics

- **Total Tasks**: 58
- **Setup Phase**: 3 tasks
- **Foundational Phase**: 6 tasks (BLOCKING)
- **User Story 1 (P1)**: 10 tasks (MVP)
- **User Story 2 (P2)**: 13 tasks
- **User Story 3 (P3)**: 14 tasks
- **Polish Phase**: 12 tasks
- **Parallel Opportunities**: 14 tasks marked [P]

---

## Notes

- [P] tasks = different files, no dependencies, can run in parallel
- [Story] label maps task to specific user story for traceability
- Each notebook is independently executable (can run without others)
- Notebooks saved WITH outputs (pre-executed, per research.md decision)
- Test database uses SQLite for portability (per plan.md)
- Helper functions kept under 20 lines each (constitution principle I)
- Manual verification appropriate for notebook content (constitution principle III modified)
- Commit after each user story phase completion
- Stop at any checkpoint to validate notebook independently
- Follow notebook_structure.md contract for all cell layouts
