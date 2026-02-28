# Tasks: Codebase Refactor

> **STATUS: COMPLETE** | Merged: 2026-02-27 | Branch: `006-codebase-refactor`

**Input**: Design documents from `/specs/006-codebase-refactor/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md

**Tests**: Existing tests serve as the regression suite. No new test-first tasks — this is a behavior-preserving refactor. The only new test file (test_validation.py) is a relocation of existing tests.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Record baselines before any changes

- [x] T001 Record source line count baseline: `find src/ -name '*.py' | xargs wc -l`
- [x] T002 Record test count and coverage baseline: `uv run pytest tests/ --cov=src --cov-report=term-missing -q`
- [x] T003 Record per-module line counts and class method counts for the 5 target modules (src/db/query.py, src/mcp_server/server.py, src/inference/columns.py, src/inference/relationships.py, src/cache/storage.py)

**Checkpoint**: Baselines recorded. All subsequent tasks can compare against these.

---

## Phase 2: User Story 1 — Developer Navigates and Modifies Source Code (Priority: P1)

**Goal**: Decompose 5 oversized source modules into focused, navigable units. No module >400 lines (constitution limit), no class >15 public methods.

**Independent Test**: All existing tests pass after each split. `uv run pytest tests/` and `uv run ruff check src/` clean after each task.

### Split 1: query.py → query.py + validation.py

- [x] T004 [US1] Extract `validate_query()` and all helper functions (`_classify_statement`, `_check_execute`, `_check_control_flow`, `_check_command`, `_check_stored_procedure`) plus constants (`DENIED_TYPES`, `SAFE_PROCEDURES`, `DenialCategory`) from src/db/query.py into new src/db/validation.py
- [x] T005 [US1] Update all imports of `validate_query` across the codebase (src/mcp_server/server.py, tests/unit/test_query.py, and any other consumers) to import from src/db/validation.py
- [x] T006 [US1] Run tests and linter to verify no regressions after query.py split
- [x] T007 [US1] Use code-simplifier agent on src/db/query.py and src/db/validation.py to clean up remaining code (simplify God methods like `execute_query`, reduce conditional nesting in `inject_row_limit`)

### Split 2: server.py → server.py + schema_tools.py + query_tools.py + doc_tools.py

- [x] T008 [US1] Extract schema-related tool functions (`connect_database`, `list_schemas`, `list_tables`, `get_table_schema`, and hidden `infer_relationships`) from src/mcp_server/server.py into new src/mcp_server/schema_tools.py. Preserve commented-out `@mcp.tool()` decorator on `infer_relationships`.
- [x] T009 [US1] Extract query/data tool functions (`get_sample_data`, `execute_query`, and hidden `analyze_column`) from src/mcp_server/server.py into new src/mcp_server/query_tools.py. Preserve commented-out decorator on `analyze_column`.
- [x] T010 [US1] Extract documentation tool functions (hidden `export_documentation`, `load_cached_docs`, `check_drift`) from src/mcp_server/server.py into new src/mcp_server/doc_tools.py. Preserve all commented-out decorators.
- [x] T011 [US1] Update src/mcp_server/server.py to be thin orchestration: FastMCP init + imports from the 3 tool modules. Ensure `mcp` instance is shared correctly.
- [x] T012 [US1] Run tests and linter to verify no regressions after server.py split
- [x] T013 [US1] Use code-simplifier agent on all 4 server files to reduce boilerplate in tool wrappers (error handling, JSON serialization patterns)

### Split 3: columns.py → columns.py + column_stats.py + column_patterns.py

- [x] T014 [US1] Extract database statistics collection methods (`_get_basic_stats`, `_get_column_type`, `_get_numeric_stats`, `_get_datetime_stats`, `_check_has_time_component`, `_get_string_stats`, `_column_exists`) from src/inference/columns.py into new src/inference/column_stats.py as a `ColumnStatsCollector` class
- [x] T015 [US1] Extract purpose pattern matching methods (`_categorize_type`, `_is_enum`, `_is_likely_id`, `_is_likely_flag`, `_is_likely_status`, `_is_likely_amount`, `_is_likely_quantity`, `_is_likely_percentage`) and type constants from src/inference/columns.py into new src/inference/column_patterns.py as a `PurposePatternMatcher` class
- [x] T016 [US1] Refactor src/inference/columns.py ColumnAnalyzer to delegate to ColumnStatsCollector and PurposePatternMatcher. Simplify `_infer_purpose` God method (currently 126 lines).
- [x] T017 [US1] Update imports in src/mcp_server/ tool files and tests/unit/test_columns.py
- [x] T018 [US1] Run tests and linter to verify no regressions after columns.py split
- [x] T019 [US1] Use code-simplifier agent on src/inference/columns.py, src/inference/column_stats.py, and src/inference/column_patterns.py

### Split 4: relationships.py → relationships.py + scoring.py

- [x] T020 [US1] Extract confidence scoring methods (`_calculate_confidence`, `_check_type_compatibility`, `_calculate_name_similarity`, `_calculate_structural_score`) and weight constants from src/inference/relationships.py into new src/inference/scoring.py as a `ConfidenceScorer` class
- [x] T021 [US1] Refactor src/inference/relationships.py ForeignKeyInferencer to delegate to ConfidenceScorer. Simplify `infer_relationships` God method (currently 188 lines) by extracting `_evaluate_single_candidate` and timeout logic.
- [x] T022 [US1] Update imports in tests/unit/test_relationships.py and tests/integration/test_fk_inference*.py
- [x] T023 [US1] Run tests and linter to verify no regressions after relationships.py split
- [x] T024 [US1] Use code-simplifier agent on src/inference/relationships.py and src/inference/scoring.py

### Split 5: storage.py → storage.py + doc_generator.py

- [x] T025 [US1] Extract markdown generation methods (`_generate_overview`, `_generate_schema_doc`, `_generate_table_doc`, `_generate_relationships_doc`) from src/cache/storage.py into new src/cache/doc_generator.py as a `DocumentationGenerator` class
- [x] T026 [US1] Refactor src/cache/storage.py DocumentationStorage to delegate generation to DocumentationGenerator. Simplify `export_documentation` God method (currently 153 lines).
- [x] T027 [US1] Update imports in src/mcp_server/ tool files and tests/integration/test_caching.py
- [x] T028 [US1] Run tests and linter to verify no regressions after storage.py split
- [x] T029 [US1] Use code-simplifier agent on src/cache/storage.py and src/cache/doc_generator.py

### Remaining Source Simplification

- [x] T030 [US1] Use code-simplifier agent on src/db/metadata.py to simplify God methods (708 lines)
- [x] T031 [US1] Use code-simplifier agent on src/inference/value_overlap.py to simplify within module (421 lines)
- [x] T032 [US1] Audit all 19 dataclasses (10 in models/schema.py, 3 in models/relationship.py, 1 in metrics.py, 4 in inference/columns.py, 1 in inference/relationships.py) for redundancy or unused fields. Document conclusion. Standardize `ColumnInfo.is_pk` → `is_primary_key` in src/inference/relationships.py (and new src/inference/scoring.py) and update all references in tests.
- [x] T033 [US1] Run full test suite and linter to verify US1 completion: `uv run pytest tests/ && uv run ruff check src/`
- [x] T034 [US1] Verify no module in src/ exceeds 400 lines (constitution limit; slight exceptions require documented justification) and no class exceeds 15 public methods

**Checkpoint**: All source modules decomposed. Code is navigable and focused. All tests pass.

---

## Phase 3: User Story 2 — Developer Runs and Maintains the Test Suite (Priority: P2)

**Goal**: Consolidate duplicate tests via parametrize, centralize integration fixtures, maintain or improve coverage.

**Independent Test**: `uv run pytest tests/ --cov=src` shows coverage ≥ baseline. Test count reduced. All tests pass.

### Coverage Baseline

- [x] T035 [US2] Record post-US1 coverage baseline (may differ from T002 due to import restructuring): `uv run pytest tests/ --cov=src --cov-report=term-missing -q`

### Parametrize Duplicate Tests in test_query.py

- [x] T036 [US2] Parametrize denial category tests in tests/unit/test_query.py: consolidate ~25 individual DDL/DML/DCL denial tests across TestDeniedOperations and TestValidateQueryDenied into ~4 parametrized tests grouped by category
- [x] T037 [P] [US2] Parametrize query type parsing tests in tests/unit/test_query.py: consolidate TestQueryTypeParser methods (5 tests for SELECT/INSERT/UPDATE/DELETE/OTHER) into 1-2 parametrized tests
- [x] T038 [P] [US2] Parametrize CTE tests in tests/unit/test_query.py: consolidate TestCTEQueryParsing methods (13 tests) into ~3 parametrized tests covering parse/validate/inject behaviors
- [x] T039 [P] [US2] Parametrize row limit injection tests in tests/unit/test_query.py: consolidate dialect-variant tests (~6 tests) into ~2 parametrized tests
- [x] T040 [US2] Run tests to verify parametrization preserved all behavioral coverage

### Relocate Validation Tests

- [x] T041 [US2] Create tests/unit/test_validation.py and move validation-specific tests from tests/unit/test_query.py (tests for `validate_query`, denial categories, allowed operations) to match the src/db/validation.py extraction from T004
- [x] T042 [US2] Run tests to verify relocation preserved all test coverage

### Centralize Integration Fixtures

- [x] T043 [US2] Create tests/integration/conftest.py with centralized versions of `sample_schemas`, `sample_tables`, `sample_columns` fixtures (currently duplicated in test_caching.py, test_sample_data.py, test_fk_inference.py)
- [x] T044 [US2] Remove duplicate `mock_engine` fixture definitions (3 sites: test_fk_inference_overlap.py x3) — use the one in tests/conftest.py
- [x] T045 [US2] Remove duplicate `sample_schemas`, `sample_tables`, `sample_columns` definitions from individual integration test files now that they're centralized
- [x] T046 [US2] Run full test suite to verify fixture centralization: `uv run pytest tests/`

### Coverage Verification

- [x] T047 [US2] Compare post-refactor coverage against baseline from T035. Verify coverage is maintained or improved. If any lines lost coverage, add targeted tests.
- [x] T048 [US2] Verify test count reduced from baseline (T002). Document final count.

**Checkpoint**: Test suite is lean, non-duplicative, and well-organized. Coverage maintained. Fixtures centralized.

---

## Phase 4: User Story 3 — Developer Re-enables Hidden Tools (Priority: P3)

**Goal**: Verify all 5 hidden tools can be re-enabled by uncommenting their `@mcp.tool()` decorator with no additional code changes.

**Independent Test**: Uncomment each decorator individually → server imports cleanly → associated tests pass → re-comment.

- [x] T049 [US3] Verify hidden tool `infer_relationships` in src/mcp_server/schema_tools.py: uncomment decorator, run `uv run python -c "import src.mcp_server.server"`, run associated tests, re-comment
- [x] T050 [US3] Verify hidden tool `analyze_column` in src/mcp_server/query_tools.py: uncomment decorator, run import check, run associated tests, re-comment
- [x] T051 [US3] Verify hidden tool `export_documentation` in src/mcp_server/doc_tools.py: uncomment decorator, run import check, run associated tests, re-comment
- [x] T052 [US3] Verify hidden tool `load_cached_docs` in src/mcp_server/doc_tools.py: uncomment decorator, run import check, run associated tests, re-comment
- [x] T053 [US3] Verify hidden tool `check_drift` in src/mcp_server/doc_tools.py: uncomment decorator, run import check, run associated tests, re-comment

**Checkpoint**: All 5 hidden tools confirmed re-enableable. No code changes needed beyond uncommenting.

---

## Phase 5: Polish & Verification

**Purpose**: Final validation, metrics comparison, and collaborative manual testing

- [x] T054 Run full test suite with verbose output: `uv run pytest tests/ -v`
- [x] T055 Run linter on all source and test files: `uv run ruff check src/ tests/`
- [x] T056 Verify no circular import dependencies: `uv run python -c "import src.mcp_server.server; import src.db.query; import src.db.validation; import src.inference.columns; import src.inference.relationships; import src.cache.storage"`
- [x] T057 Compare final metrics against baselines (T001-T003): source line counts, test counts, coverage, per-module sizes, class method counts
- [x] T058 Verify SC-001: total source lines ≤ 7,100 (hard gate: no increase)
- [x] T059 Verify SC-002: no source module exceeds 400 lines (confirm T034 results still hold after US2/US3 changes)
- [x] T060 Verify SC-003: no class exceeds 15 public methods (confirm T034 results still hold after US2/US3 changes)
- [x] T061 Verify SC-008: no circular import dependencies (confirmed by T056)
- [x] T062 **COLLABORATIVE**: Manual integration testing — restart MCP server and jointly verify all 6 active tools work end-to-end against a live database (requires user participation)

**Checkpoint**: All success criteria verified. Feature complete.

---

## Phase 6: Cognitive Complexity Reduction (Bonus)

**Purpose**: Post-verification complexipy analysis found 5 active functions with cognitive complexity >15. These are behavior-preserving simplifications — no new files, no new abstractions, just clearer control flow.

**Justification**: FR-013 (added post-analysis). The original refactor addressed structural complexity (module sizes, class sizes) but not within-function cognitive complexity. complexipy revealed that the 5 highest-scoring active functions all suffer from deep nesting and interleaved concerns, which harms readability even in correctly-sized modules.

**Independent Test**: All existing tests pass after each simplification. `uv run pytest tests/ && uv run ruff check src/` clean after each task. Complexipy scores decrease.

- [x] T063 [US1] Simplify `QueryService.execute_query` (score: 43→6) in src/db/query.py: extract SELECT result processing and total-row-count logic into helper methods to reduce nesting depth
- [x] T064 [P] [US1] Simplify `MetadataService._list_tables_generic` (score: 42→15) in src/db/metadata.py: extract table collection and view collection loops into helper methods to flatten nesting
- [x] T065 [P] [US1] Simplify `ConnectionManager.connect` (score: 22→14) in src/db/connection.py: extract engine creation into a helper method to separate auth-method branching from connection lifecycle
- [x] T066 [P] [US1] Simplify `list_tables` MCP tool wrapper (score: 19→6) in src/mcp_server/schema_tools.py: extract parameter validation and response building into helpers
- [x] T067 [P] [US1] Simplify `QueryService.inject_row_limit` (score: 16→10) in src/db/query.py: flatten conditional branches with early returns
- [x] T068 Run tests, linter, and complexipy to verify all 5 functions now score ≤15: `uv run pytest tests/ && uv run ruff check src/ && uv run complexipy src/`

**Checkpoint**: All 5 active functions at or below cognitive complexity threshold. Conciseness maintained or improved.

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **US1 (Phase 2)**: Depends on Setup baselines (T001-T003)
- **US2 (Phase 3)**: Depends on US1 completion (source splits affect import paths in tests)
- **US3 (Phase 4)**: Depends on US1 completion (hidden tools moved to new files)
- **Polish (Phase 5)**: Depends on US1, US2, US3 all complete

### Within US1: Module Split Order

- **Split 1 (query.py)**: First — cleanest separation, establishes the pattern
- **Split 2 (server.py)**: Second — depends on knowing where services live post-split
- **Splits 3, 4, 5 (columns.py, relationships.py, storage.py)**: After Split 2 — independent of each other, could theoretically parallelize but sequential is safer for a solo developer
- **Remaining (T030-T034)**: After all splits complete

### Within US2: Test Refactoring Order

- **T035**: First — record post-US1 baseline
- **T036-T039**: Parametrize tasks — T036 first (largest impact), T037-T039 parallelizable
- **T041-T042**: After parametrization — relocate validation tests
- **T043-T046**: After relocation — centralize fixtures
- **T047-T048**: Last — verify coverage

### Parallel Opportunities

- T037, T038, T039 can run in parallel (different test categories, no overlap)
- T049-T053 can run in parallel (independent hidden tool verifications)
- T054-T061 are independent verification checks (can parallel)

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (record baselines)
2. Complete Phase 2: US1 (all 5 module splits)
3. **STOP and VALIDATE**: All tests pass, modules under 500 lines
4. This alone delivers the core value of the refactor

### Incremental Delivery

1. Setup → baselines recorded
2. US1 → source modules decomposed → validate
3. US2 → tests consolidated → validate coverage
4. US3 → hidden tools verified → validate re-enablement
5. Polish → final metrics comparison → collaborative manual testing

### Code-Simplifier Agent Usage

After each structural split (T007, T013, T019, T024, T029), and for standalone simplification (T030, T031), use the code-simplifier agent. The agent receives the already-split files and simplifies within them — it does not perform the structural splits themselves.

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- Each split follows: extract → update imports → test → simplify → test
- Commit after each completed split (T004-T007 = one commit, etc.)
- Run `uv run pytest tests/ && uv run ruff check src/` as the verification command after every task group
- T062 (manual integration testing) requires user participation to restart the MCP server
