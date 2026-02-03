# Tasks: Allow CTE Queries

> **STATUS: COMPLETE** | Merged: 2026-02-03 | Branch: `003-allow-cte-queries`

**Input**: Design documents from `/specs/003-allow-cte-queries/`
**Prerequisites**: plan.md ✅, spec.md ✅, research.md ✅, data-model.md ✅, quickstart.md ✅

**Tests**: Included per constitution's Test-First Development principle (Principle III).

**Organization**: Tasks grouped by user story for independent implementation and testing.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (US1, US2, US3)
- Include exact file paths in descriptions

## Path Conventions

- **Single project**: `src/`, `tests/` at repository root (per plan.md)
- Primary modification target: `src/db/query.py`
- Test file: `tests/unit/test_query.py`

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: No new infrastructure needed - feature modifies existing code

- [x] T001 Verify existing test suite passes before changes: `pytest tests/unit/test_query.py -v`

**Checkpoint**: Baseline confirmed - no regressions from starting state

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Add BLOCKED_KEYWORDS constant and helper method that all user stories depend on

**⚠️ CRITICAL**: User stories depend on this shared infrastructure

- [x] T002 Add `BLOCKED_KEYWORDS` frozenset constant to `QueryService` class in `src/db/query.py`
- [x] T003 Add `_is_blocked_keyword(self, query_text: str) -> tuple[bool, str | None]` method in `src/db/query.py`

**Checkpoint**: Blocklist infrastructure ready - user story implementation can begin

---

## Phase 3: User Story 1 - Execute CTE-based SELECT Queries (Priority: P1) 🎯 MVP

**Goal**: Enable `WITH ... SELECT` queries to execute instead of being blocked as OTHER

**Independent Test**: Execute `WITH cte AS (SELECT 1 AS val) SELECT * FROM cte` and verify it returns results

### Tests for User Story 1

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T004 [P] [US1] Add test `test_parse_cte_select_query` for CTE+SELECT classification in `tests/unit/test_query.py`
- [x] T005 [P] [US1] Add test `test_parse_cte_multiple_ctes` for multiple CTEs in `tests/unit/test_query.py`
- [x] T006 [P] [US1] Add test `test_parse_cte_with_comments` for CTE queries containing SQL comments in `tests/unit/test_query.py`
- [x] T007 [P] [US1] Add test `test_cte_select_allowed` verifying CTE+SELECT is allowed by `is_query_allowed` in `tests/unit/test_query.py`
- [x] T008 [P] [US1] Add test `test_inject_row_limit_cte_sqlserver` for TOP injection in CTE queries in `tests/unit/test_query.py`
- [x] T009 [P] [US1] Add test `test_inject_row_limit_cte_sqlite` for LIMIT injection in CTE queries in `tests/unit/test_query.py`

### Implementation for User Story 1

- [x] T010 [US1] Modify `parse_query_type()` to detect `WITH` keyword and extract final operation in `src/db/query.py`
- [x] T011 [US1] Modify `inject_row_limit()` to handle CTE+SELECT queries (inject after final SELECT) in `src/db/query.py`
- [x] T012 [US1] Run US1 tests to verify CTE+SELECT works: `pytest tests/unit/test_query.py -k "cte" -v`

**Checkpoint**: CTE+SELECT queries now execute. User Story 1 is independently testable.

---

## Phase 4: User Story 2 - Block Dangerous Query Patterns (Priority: P1)

**Goal**: Ensure DDL and dangerous operations (CREATE, DROP, ALTER, TRUNCATE, EXEC, GRANT, etc.) are explicitly blocked with clear error messages

**Independent Test**: Execute `CREATE TABLE test (id INT)` and verify it's blocked with message mentioning "CREATE"

### Tests for User Story 2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T013 [P] [US2] Add test `test_blocked_create` in `tests/unit/test_query.py`
- [x] T014 [P] [US2] Add test `test_blocked_drop` in `tests/unit/test_query.py`
- [x] T015 [P] [US2] Add test `test_blocked_alter` in `tests/unit/test_query.py`
- [x] T016 [P] [US2] Add test `test_blocked_truncate` in `tests/unit/test_query.py`
- [x] T017 [P] [US2] Add test `test_blocked_exec` in `tests/unit/test_query.py`
- [x] T018 [P] [US2] Add test `test_blocked_grant_revoke_deny` in `tests/unit/test_query.py`
- [x] T019 [P] [US2] Add test `test_blocked_error_message_contains_keyword` verifying specific keyword in error in `tests/unit/test_query.py`
- [x] T019a [P] [US2] Add test `test_blocked_keyword_with_comment_obfuscation` verifying `/* SELECT */ CREATE TABLE` is still blocked (FR-005) in `tests/unit/test_query.py`

### Implementation for User Story 2

- [x] T020 [US2] Modify `is_query_allowed()` to call `_is_blocked_keyword()` before standard checks in `src/db/query.py`
- [x] T021 [US2] Update error message format to include blocked keyword name in `src/db/query.py`
- [x] T022 [US2] Run US2 tests to verify blocklist works: `pytest tests/unit/test_query.py -k "blocked" -v`

**Checkpoint**: DDL and dangerous operations blocked with clear messages. User Story 2 is independently testable.

---

## Phase 5: User Story 3 - Maintain Write Operation Controls (Priority: P1)

**Goal**: Ensure INSERT/UPDATE/DELETE (including CTE+write) continue to respect `allow_write` parameter

**Independent Test**: Execute `WITH cte AS (...) INSERT INTO ...` and verify blocked by default, allowed with `allow_write=True`

### Tests for User Story 3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T023 [P] [US3] Add test `test_parse_cte_insert_query` for CTE+INSERT classification in `tests/unit/test_query.py`
- [x] T024 [P] [US3] Add test `test_parse_cte_update_query` for CTE+UPDATE classification in `tests/unit/test_query.py`
- [x] T025 [P] [US3] Add test `test_parse_cte_delete_query` for CTE+DELETE classification in `tests/unit/test_query.py`
- [x] T026 [P] [US3] Add test `test_cte_write_blocked_by_default` in `tests/unit/test_query.py`
- [x] T027 [P] [US3] Add test `test_cte_write_allowed_with_flag` in `tests/unit/test_query.py`
- [x] T028 [P] [US3] Add test `test_existing_write_controls_unchanged` regression test in `tests/unit/test_query.py`

### Implementation for User Story 3

- [x] T029 [US3] Verify `parse_query_type()` correctly returns INSERT/UPDATE/DELETE for CTE+write queries in `src/db/query.py`
- [x] T030 [US3] Verify existing `is_query_allowed()` logic handles CTE-detected write operations correctly in `src/db/query.py`
- [x] T031 [US3] Run US3 tests to verify write controls work: `pytest tests/unit/test_query.py -k "cte_write or existing_write" -v`

**Checkpoint**: Write operations maintain existing security model. All 3 user stories complete.

---

## Phase 6: Polish & Cross-Cutting Concerns

**Purpose**: Final validation and cleanup

- [x] T032 Run full test suite to verify no regressions: `pytest tests/unit/test_query.py -v`
- [x] T033 [P] Run integration tests if available: `pytest tests/integration/test_query_execution.py -v`
- [x] T034 [P] Run quickstart.md validation manually (execute example queries)
- [x] T035 Update docstrings for modified methods in `src/db/query.py`
- [x] T036 Run linting: `ruff check src/db/query.py`

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - baseline verification
- **Foundational (Phase 2)**: Depends on Setup - adds shared blocklist infrastructure
- **User Stories (Phase 3-5)**: All depend on Foundational phase completion
  - US1, US2, US3 can proceed in parallel after Foundational
  - Or sequentially for single developer
- **Polish (Phase 6)**: Depends on all user stories being complete

### User Story Dependencies

- **User Story 1 (CTE+SELECT)**: Depends only on Foundational (Phase 2)
- **User Story 2 (Blocklist)**: Depends only on Foundational (Phase 2)
- **User Story 3 (Write Controls)**: Depends only on Foundational (Phase 2); benefits from US1's CTE parsing being done first

### Within Each User Story

1. Tests MUST be written and FAIL before implementation
2. Implementation follows test requirements
3. Run story-specific tests to verify
4. Story complete when all tests pass

### Parallel Opportunities

Within Phase 2 (Foundational):
- T002 and T003 must be sequential (T003 uses constant from T002)

Within US1 (Phase 3):
- T004-T009 (all tests) can run in parallel
- T010-T011 (implementation) must be sequential

Within US2 (Phase 4):
- T013-T019 (all tests) can run in parallel
- T020-T021 (implementation) must be sequential

Within US3 (Phase 5):
- T023-T028 (all tests) can run in parallel
- T029-T030 (implementation) can be parallel (verification only)

---

## Parallel Example: All US1 Tests

```bash
# Launch all tests for User Story 1 together (will fail initially):
pytest tests/unit/test_query.py -k "test_parse_cte_select or test_parse_cte_multiple or test_parse_cte_with_comments or test_cte_select_allowed or test_inject_row_limit_cte" -v
```

---

## Implementation Strategy

### MVP First (User Story 1 Only)

1. Complete Phase 1: Setup (verify baseline)
2. Complete Phase 2: Foundational (blocklist constant + helper)
3. Complete Phase 3: User Story 1 (CTE+SELECT)
4. **STOP and VALIDATE**: CTE SELECT queries work independently
5. This alone provides significant value - CTEs are now usable

### Incremental Delivery

1. Setup + Foundational → Infrastructure ready
2. Add User Story 1 → CTE+SELECT works → MVP functional
3. Add User Story 2 → Blocklist active → Security hardened
4. Add User Story 3 → Write controls verified → Full feature complete
5. Each story adds security/functionality without breaking previous

### Single Developer Strategy

Execute sequentially: Phase 1 → Phase 2 → Phase 3 → Phase 4 → Phase 5 → Phase 6

Total estimated: ~50 lines of production code, ~150 lines of test code

---

## Notes

- [P] tasks = different test methods, no dependencies
- [Story] label maps task to specific user story for traceability
- All 3 user stories are P1 priority but can be implemented incrementally
- Constitution requires Test-First: write failing tests before implementation
- Primary file: `src/db/query.py` (all implementation changes)
- Test file: `tests/unit/test_query.py` (all new tests)
- Commit after each phase checkpoint
