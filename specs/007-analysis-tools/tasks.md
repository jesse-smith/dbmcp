# Tasks: Data-Exposure Analysis Tools

**Input**: Design documents from `/specs/007-analysis-tools/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/mcp-tools.md

**Tests**: Included per constitution (Principle III: Test-First Development).

**Organization**: Tasks grouped by user story. US4 (cleanup) is foundational since it unblocks new tool development by removing conflicting code and models.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3, US4)
- Exact file paths included in descriptions

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Create new module structure and shared data models used by all analysis tools.

- [X] T001 Create `src/analysis/` directory with `src/analysis/__init__.py`
- [X] T002 Create analysis data models (NumericStats, DateTimeStats, StringStats, ColumnStatistics, PKCandidate, FKCandidateData, FKCandidateResult) with `to_dict()` methods in `src/models/analysis.py` per data-model.md
- [X] T003 Write unit tests for analysis data models (construction, `to_dict()` serialization, edge cases like all-None stats, zero rows) in `tests/unit/test_analysis_models.py`
- [X] T004 [P] Create `tests/performance/test_analysis_perf.py` with performance tests for NFR-001 (`get_column_info` <5s for 10M rows), NFR-002 (`find_pk_candidates` <5s for 10M rows), NFR-003 (`find_fk_candidates` <10s metadata-only, <30s with overlap for 100 candidates)

**Checkpoint**: New models importable, model tests pass.

---

## Phase 2: Foundational — Legacy Cleanup (US4)

**Purpose**: Remove all disabled inference tools, caching infrastructure, and related models. MUST complete before new tool implementation to avoid import conflicts.

**Goal**: Codebase has zero dead code paths, no orphan imports, no unused data structures from inference/cache infrastructure.

**Independent Test**: `uv run pytest tests/` passes with no import errors; `grep -r` for removed symbols finds zero matches in `src/`.

### Tests for US4

- [X] T005 [US4] Remove inference-related test files: `tests/unit/test_relationships.py`, `tests/unit/test_columns.py`, `tests/unit/test_value_overlap.py`
- [X] T006 [US4] Remove inference-related integration test files: `tests/integration/test_fk_inference.py`, `tests/integration/test_fk_inference_overlap.py`, `tests/integration/test_caching.py`
- [X] T007 [US4] Remove inference-related performance test files: `tests/performance/test_inference_scaling.py`; review `tests/performance/test_nfr003.py` for caching references and remove/update as needed

### Implementation for US4

- [X] T008 [US4] Delete `src/mcp_server/doc_tools.py` (entire file — export_documentation, load_cached_docs, check_drift tools)
- [X] T009 [P] [US4] Remove `infer_relationships` function and its imports from `src/mcp_server/schema_tools.py`
- [X] T010 [P] [US4] Remove `analyze_column` function and its inference-related imports from `src/mcp_server/query_tools.py`
- [X] T011 [US4] Update `src/mcp_server/server.py`: remove doc_tools import block, remove `infer_relationships` from schema_tools imports, remove `analyze_column` from query_tools imports
- [X] T012 [US4] Delete entire `src/inference/` directory (6 files: `__init__.py`, `columns.py`, `column_patterns.py`, `column_stats.py`, `relationships.py`, `scoring.py`, `value_overlap.py`)
- [X] T013 [US4] Delete entire `src/cache/` directory (4 files: `__init__.py`, `drift.py`, `doc_generator.py`, `storage.py`)
- [X] T014 [US4] Clean `src/models/schema.py`: remove `InferredPurpose` enum, remove `inferred_purpose` and `inferred_confidence` fields from `Column`, remove `distinct_count` and `null_percentage` fields from `Column` (these fields move from stored Column attributes to on-demand ColumnStatistics results), remove `DocumentationCache` dataclass
- [X] T015 [US4] Clean `src/models/relationship.py`: remove `InferenceFactors` dataclass, remove `InferredFK` dataclass, remove `RelationshipType.INFERRED` enum value
- [X] T016 [US4] Scan all remaining `src/` and `tests/` files for orphan imports referencing removed symbols (`InferredPurpose`, `InferredFK`, `InferenceFactors`, `DocumentationCache`, `ColumnAnalyzer`, `ForeignKeyInferencer`, `ConfidenceScorer`, `ValueOverlapAnalyzer`, `DocumentationStorage`, `DriftDetector`, `DocumentationGenerator`); fix any found
- [X] T017 [US4] Run full test suite (`uv run pytest tests/`) and verify all remaining tests pass with zero import errors

**Checkpoint**: Codebase clean of inference/cache code. All remaining tests pass. `grep -rn "InferredPurpose\|InferredFK\|InferenceFactors\|DocumentationCache\|src.inference\|src.cache" src/ tests/` returns zero matches.

---

## Phase 3: User Story 1 — Explore Column Characteristics (Priority: P1) 🎯 MVP

**Goal**: Consumers can retrieve per-column statistical profiles (distinct count, null rate, type-specific stats) via a single `get_column_info` MCP tool call.

**Independent Test**: Request column info for a known table and verify returned statistics match expected values.

### Tests for US1

> **Write these tests FIRST, ensure they FAIL before implementation**

- [X] T018 [P] [US1] Write unit tests for `ColumnStatsCollector` in `tests/unit/test_column_stats.py`: basic stats (distinct_count, null_count, total_rows), numeric stats (min/max/mean/stddev), datetime stats (min/max/range/has_time_component), string stats (min/max/avg length, sample_values), column existence check, column filtering by name list and by LIKE pattern, edge cases (all-NULL column, zero-row table, empty pattern match)
- [X] T019 [P] [US1] Write integration tests for `get_column_info` MCP tool in `tests/integration/test_get_column_info.py`: all-columns request, column name list filter, column pattern filter, default schema behavior, invalid connection/table/column error responses, columns-takes-precedence-over-pattern behavior

### Implementation for US1

- [X] T020 [US1] Implement `ColumnStatsCollector` class in `src/analysis/column_stats.py` — adapt SQL patterns from former `src/inference/column_stats.py` (basic stats, numeric stats, datetime stats, string stats, column existence) with support for batch column analysis and column filtering (name list or LIKE pattern); return `ColumnStatistics` model instances per data-model.md
- [X] T021 [US1] Implement `get_column_info` MCP tool function in `src/mcp_server/analysis_tools.py` per contracts/mcp-tools.md: parameters (connection_id, table_name, schema_name, columns, column_pattern), JSON response format, error handling for invalid connection/table/column
- [X] T022 [US1] Register `get_column_info` import in `src/mcp_server/server.py`
- [ ] T023 [US1] Run unit and integration tests for US1, verify all pass (`uv run pytest tests/unit/test_column_stats.py tests/integration/test_get_column_info.py tests/unit/test_analysis_models.py -v`)

**Checkpoint**: `get_column_info` tool functional end-to-end. All US1 acceptance scenarios (1-5) verified.

---

## Phase 4: User Story 2 — Identify Primary Key Candidates (Priority: P2)

**Goal**: Consumers can discover PK candidates (constraint-backed and structural) for any table via a single `find_pk_candidates` MCP tool call.

**Independent Test**: Request PK candidates for a table with a declared PK and verify the declared PK appears with correct metadata, plus any structural candidates.

### Tests for US2

> **Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T024 [P] [US2] Write unit tests for `PKDiscovery` in `tests/unit/test_pk_discovery.py`: constraint-backed PK detected, UNIQUE constraint detected, structural candidate (unique + non-null + type match), VARCHAR excluded by default type filter, custom type_filter override includes VARCHAR, no-candidates returns empty list, default schema behavior
- [ ] T025 [P] [US2] Write integration tests for `find_pk_candidates` MCP tool in `tests/integration/test_pk_discovery.py`: declared PK table, UNIQUE constraint table, structural candidate detection, type filter override, empty result, error responses

### Implementation for US2

- [ ] T026 [US2] Implement `PKDiscovery` class in `src/analysis/pk_discovery.py` — query PK/UNIQUE constraints via MetadataService/INFORMATION_SCHEMA, check structural candidacy (unique values via COUNT(DISTINCT)=COUNT(*) WHERE NOT NULL, non-null, type set match), return `PKCandidate` model instances per data-model.md; configurable `type_filter` parameter defaulting to `["int", "bigint", "smallint", "tinyint", "uniqueidentifier"]`
- [ ] T027 [US2] Implement `find_pk_candidates` MCP tool function in `src/mcp_server/analysis_tools.py` per contracts/mcp-tools.md: parameters (connection_id, table_name, schema_name, type_filter), JSON response with table/schema as top-level metadata, error handling
- [ ] T028 [US2] Register `find_pk_candidates` import in `src/mcp_server/server.py`
- [ ] T029 [US2] Run unit and integration tests for US2, verify all pass (`uv run pytest tests/unit/test_pk_discovery.py tests/integration/test_pk_discovery.py -v`)

**Checkpoint**: `find_pk_candidates` tool functional end-to-end. All US2 acceptance scenarios (1-7) verified.

---

## Phase 5: User Story 3 — Discover Foreign Key Candidates (Priority: P3)

**Goal**: Consumers can discover FK candidates for any source column, with optional PK filtering and value overlap, via a single `find_fk_candidates` MCP tool call.

**Independent Test**: Specify a known FK column and verify the true target appears with correct structural metadata and optional value overlap.

### Tests for US3

> **Write these tests FIRST, ensure they FAIL before implementation**

- [ ] T030 [P] [US3] Write unit tests for `FKCandidateSearch` in `tests/unit/test_fk_candidates.py`: known FK finds true target with PK filter on, PK filter disabled returns all columns, schema scoping (default to source schema), target table list filter, target table pattern filter, value overlap returns count+percentage, default limit of 100 with was_limited flag, high-cardinality column (>1M distinct values) times out after 30s and returns null overlap values with no error (NFR-006), empty result for no candidates, error cases
- [ ] T031 [P] [US3] Write integration tests for `find_fk_candidates` MCP tool in `tests/integration/test_fk_candidates.py`: end-to-end with default settings, PK filter toggle, schema/table/pattern scoping, value overlap enabled, limit enforcement, empty result, error responses

### Implementation for US3

- [ ] T032 [US3] Implement `FKCandidateSearch` class in `src/analysis/fk_candidates.py` — resolve target tables (apply schema/table/pattern filters, default to source schema), collect candidate columns (all or PK-only via `PKDiscovery`), gather structural metadata per candidate (constraints, indexes, nullability), optional value overlap via SQL INTERSECT (adapted from former `ValueOverlapAnalyzer._full_comparison`), apply limit, return `FKCandidateResult` per data-model.md
- [ ] T033 [US3] Implement `find_fk_candidates` MCP tool function in `src/mcp_server/analysis_tools.py` per contracts/mcp-tools.md: parameters (connection_id, table_name, column_name, schema_name, target_schema, target_tables, target_table_pattern, pk_candidates_only, include_overlap, limit), JSON response format, error handling
- [ ] T034 [US3] Register `find_fk_candidates` import in `src/mcp_server/server.py`
- [ ] T035 [US3] Run unit and integration tests for US3, verify all pass (`uv run pytest tests/unit/test_fk_candidates.py tests/integration/test_fk_candidates.py -v`)

**Checkpoint**: `find_fk_candidates` tool functional end-to-end. All US3 acceptance scenarios (1-9) verified.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Full validation, performance, and quality gates.

- [ ] T036 Run performance tests and verify NFR requirements met (`uv run pytest tests/performance/test_analysis_perf.py -v`)
- [ ] T037 Run full test suite across all phases (`uv run pytest tests/ -v`) and verify zero failures
- [ ] T038 Run linter (`uv run ruff check src/ tests/`) and verify zero warnings
- [ ] T039 Run complexity check (`uv run complexipy src/`) and verify all functions under thresholds (cyclomatic <10, file <400 lines, function <50 lines)
- [ ] T040 Verify existing active tools unchanged: run existing integration tests for connect_database, list_schemas, list_tables, get_table_schema, get_sample_data, execute_query (`uv run pytest tests/integration/test_discovery.py tests/integration/test_sample_data.py -v`)
- [ ] T041 Final orphan scan: `grep -rn "InferredPurpose\|InferredFK\|InferenceFactors\|DocumentationCache\|inferred_purpose\|inferred_confidence\|src\.inference\|src\.cache\|doc_tools" src/ tests/` returns zero matches
- [ ] T042 Manual code review: Verify analysis modules (`src/analysis/column_stats.py`, `src/analysis/pk_discovery.py`, `src/analysis/fk_candidates.py`) contain zero interpretive logic per FR-002 — no similarity scores, confidence calculations, categorical labels (e.g., "is_enum"), compatibility judgments, or pattern-based classifications; all returned data must be raw statistics and structural metadata only

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational/US4 (Phase 2)**: Depends on Phase 1 (needs analysis models for clean compile check)
- **US1 (Phase 3)**: Depends on Phase 2 (cleanup must complete first)
- **US2 (Phase 4)**: Depends on Phase 2; independent of US1
- **US3 (Phase 5)**: Depends on Phase 2 AND Phase 4 (uses `PKDiscovery` from US2)
- **Polish (Phase 6)**: Depends on all prior phases

### User Story Dependencies

```
Phase 1 (Setup)
    │
    ▼
Phase 2 (US4 Cleanup)
    │
    ├──────────────┬──────────────┐
    ▼              ▼              │
Phase 3 (US1)   Phase 4 (US2)   │
    │              │              │
    │              ▼              │
    │          Phase 5 (US3) ◄───┘
    │              │
    ▼              ▼
Phase 6 (Polish)
```

- **US1 (P1)** and **US2 (P2)**: Can run in parallel after Phase 2
- **US3 (P3)**: Must wait for US2 (PK discovery is a dependency for FK candidate search)
- **US1 and US3**: No dependency — US1 column stats are not required by FK candidates

### Within Each User Story

1. Tests written FIRST (Red)
2. Implementation to make tests pass (Green)
3. MCP tool registration
4. Verification run

### Parallel Opportunities

- T002 and T003 (models and model tests) can be written in parallel
- T004, T005, T007 (test file removals) can run in parallel
- T007, T008, T010 (tool removals) can partially run in parallel
- T017, T019 (US1 tests) can run in parallel
- T023, T025 (US2 tests) can run in parallel
- T029, T031 (US3 tests) can run in parallel
- **US1 and US2 entire phases** can run in parallel after Phase 2

---

## Parallel Example: After Phase 2 Cleanup

```
# US1 and US2 can proceed simultaneously:

Stream A (US1 - Column Stats):
  T018 → T019 → T020 → T021 → T022 → T022

Stream B (US2 - PK Candidates):
  T024 → T025 → T026 → T027 → T028 → T028

# Then US3 starts after US2 completes:
Stream C (US3 - FK Candidates):
  T030 → T031 → T032 → T033 → T034 → T034
```

---

## Implementation Strategy

### MVP First (US1 Only)

1. Complete Phase 1: Setup (T001–T003)
2. Complete Phase 2: Cleanup (T004–T016)
3. Complete Phase 3: US1 Column Stats (T017–T022)
4. **STOP and VALIDATE**: `get_column_info` works end-to-end
5. Deployable MVP — consumers can explore column characteristics

### Incremental Delivery

1. Setup + Cleanup → Clean codebase ready
2. Add US1 (column stats) → Test independently → MVP
3. Add US2 (PK candidates) → Test independently → Enhanced
4. Add US3 (FK candidates) → Test independently → Full feature
5. Polish → Quality gates verified → Release

---

## Notes

- [P] tasks = different files, no dependencies on incomplete tasks
- [Story] label maps task to specific user story for traceability
- Constitution Principle III: All tests written before implementation (Red-Green-Refactor)
- Research decisions R1 (adapt SQL patterns), R2 (INTERSECT overlap), R7 (stat field cleanup) inform implementation tasks
- Value overlap in US3 adapts `_full_comparison` SQL pattern from former `ValueOverlapAnalyzer` — no Jaccard, raw count + percentage only
