# Tasks: Denylist Query Validation

> **STATUS: COMPLETE** | Merged: 2026-02-26 | Branch: `005-denylist-query-validation`

**Input**: Design documents from `/specs/005-denylist-query-validation/`
**Prerequisites**: plan.md (required), spec.md (required), research.md, data-model.md, contracts/

**Tests**: Included per Constitution Principle III (Test-First Development).

**Organization**: Tasks grouped by user story. US1 and US2 are both P1 and co-dependent (safe queries passing requires the denylist that defines denied queries), so they share a phase.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US3)
- Include exact file paths in descriptions

## Phase 1: Setup

**Purpose**: Add sqlglot dependency

- [x] T001 Add sqlglot dependency (pinned version range) to pyproject.toml and install

---

## Phase 2: Foundational (Model Types & Constants)

**Purpose**: Define new types and constants that all user stories depend on

- [x] T002 Add DenialCategory enum, DenialReason dataclass, and ValidationResult dataclass to src/models/schema.py
- [x] T003 Add denial_reasons field (list[DenialReason] | None) to Query dataclass in src/models/schema.py
- [x] T004 Define SAFE_PROCEDURES frozenset (22 stored procedure names) and DENIED_TYPES mapping (sqlglot expression types → DenialCategory) as module-level constants in src/db/query.py

**Checkpoint**: Foundation ready — all types and constants available for validation implementation

---

## Phase 3: User Story 1 + User Story 2 — Core Denylist Validation (Priority: P1) 🎯 MVP

**Goal**: Replace keyword-based blocklist with AST-based denylist. Safe queries pass (US1), denied queries are blocked with categorized reasons (US2).

**Independent Test**: Submit SELECT queries (including ones with keyword-overlapping column names like "create_date") and confirm they pass. Submit INSERT, DROP, GRANT, BACKUP, SELECT INTO, and CTE-wrapped writes and confirm each is denied with the correct DenialCategory.

### Tests for US1 + US2

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T005 [US1] Write tests for safe query validation: SELECT, SELECT with keyword-overlapping names (create_date, execute_count), CTE+SELECT, unknown/non-denied statement types → ValidationResult.is_safe=True in tests/unit/test_query.py
- [x] T006 [US2] Write tests for denied operations: INSERT, UPDATE, DELETE, MERGE → DenialCategory.DML; CREATE, ALTER, DROP, TRUNCATE, RENAME → DenialCategory.DDL; GRANT, REVOKE, DENY → DenialCategory.DCL; BACKUP, RESTORE, DBCC, KILL → DenialCategory.OPERATIONAL; SELECT INTO → DenialCategory.SELECT_INTO; CTE+INSERT/UPDATE/DELETE → DenialCategory.CTE_WRAPPED_WRITE; include case-variation tests (e.g., "drop table", "Grant", "TRUNCATE") to verify FR-013 in tests/unit/test_query.py
- [x] T007 [US1] [US2] Write tests for allow_write=True: DML operations (INSERT, UPDATE, DELETE, MERGE) pass when allow_write=True; DDL/DCL/Operational still denied with allow_write=True in tests/unit/test_query.py

### Implementation for US1 + US2

- [x] T008 [US1] [US2] Implement validate_query(sql, allow_write=False) -> ValidationResult pure function in src/db/query.py: parse with sqlglot(dialect='tsql'), check each statement against DENIED_TYPES via helper functions (_classify_statement(), _check_stored_procedure()), detect SELECT INTO, detect CTE-wrapped writes, apply allow_write DML bypass, return categorized ValidationResult. Keep validate_query() under 50 lines by extracting classification logic into focused helpers.
- [x] T009 [US1] [US2] Verify all T005-T007 tests pass green in tests/unit/test_query.py

**Checkpoint**: Core validation works — safe queries pass, all denial categories correctly classified, allow_write bypass functional

---

## Phase 4: User Story 3 — Known-Safe Stored Procedures (Priority: P2)

**Goal**: Allow execution of 22 curated read-only SQL Server system stored procedures while denying all other EXEC/EXECUTE statements.

**Independent Test**: Submit `EXEC sp_tables` and confirm it passes; submit `EXEC sp_executesql` and `EXEC user_defined_proc` and confirm denied.

### Tests for US3

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T010 [US3] Write tests for stored procedure allowlist: each of the 22 safe procedures passes validation; multi-part names (master.dbo.sp_help, dbo.sp_columns) resolve correctly; sp_executesql explicitly denied; unknown/user-defined procedures denied with DenialCategory.STORED_PROCEDURE; case-insensitive matching (SP_TABLES, Sp_Help) in tests/unit/test_query.py

### Implementation for US3

- [x] T011 [US3] Implement stored procedure allowlist checking in validate_query(): for Execute AST nodes, extract procedure name (last identifier part), check against SAFE_PROCEDURES frozenset (case-insensitive), explicitly deny sp_executesql, deny unknown procedures in src/db/query.py
- [x] T012 [US3] Verify all T010 tests pass green in tests/unit/test_query.py

**Checkpoint**: Stored procedure allowlist works — 22 safe procs allowed, sp_executesql and unknowns denied

---

## Phase 5: User Story 4 — Obfuscation Resistance (Priority: P2)

**Goal**: Detect and deny obfuscation attempts: denied operations hidden in control flow blocks, multi-statement batches, and unparseable queries.

**Independent Test**: Submit `BEGIN DROP TABLE x END`, a two-statement batch with one denied operation, and malformed SQL — confirm all denied.

### Tests for US4

> **NOTE: Write these tests FIRST, ensure they FAIL before implementation**

- [x] T013 [US4] Write tests for obfuscation resistance: multi-statement batch with one denied statement → entire batch denied with statement_index in DenialReason; denied operations inside BEGIN/END, IF/ELSE, WHILE blocks → detected and denied; parse failures (malformed SQL) → DenialCategory.PARSE_FAILURE; empty/whitespace-only queries → denied in tests/unit/test_query.py

### Implementation for US4

- [x] T014 [US4] Implement recursive AST walking using sqlglot .walk() to detect denied types nested inside control flow blocks in validate_query() in src/db/query.py
- [x] T015 [US4] Implement multi-statement batch handling: iterate all parsed statements, track statement_index in DenialReason, deny entire batch if any statement denied in src/db/query.py
- [x] T016 [US4] Implement parse failure handling: catch sqlglot.errors.ParseError, return ValidationResult with DenialCategory.PARSE_FAILURE; handle empty/whitespace input in src/db/query.py
- [x] T017 [US4] Verify all T013 tests pass green in tests/unit/test_query.py

**Checkpoint**: Obfuscation resistance works — nested operations, batches, and parse failures all handled

---

## Phase 6: Integration & Cleanup

**Purpose**: Wire new validation into execute_query(), remove old code, update existing tests

- [x] T018 Integrate validate_query() into execute_query() method: replace calls to _is_blocked_keyword(), parse_query_type(), and is_query_allowed() with single validate_query() call; populate Query.denial_reasons and Query.error_message from ValidationResult in src/db/query.py
- [x] T019 Update parse_query_type() to use sqlglot AST for query type detection (SELECT/INSERT/UPDATE/DELETE/OTHER) instead of keyword heuristic — this method is still needed for Query.query_type field in src/db/query.py
- [x] T020 Remove dead code: BLOCKED_KEYWORDS frozenset, _is_blocked_keyword(), _remove_sql_comments(), old is_query_allowed() from src/db/query.py
- [x] T021 Update existing tests in tests/unit/test_query.py: remove old keyword-based tests, update execute_query() integration tests to verify new denial behavior and Query.denial_reasons field
- [x] T022 Run full test suite (pytest) and linter (ruff check src/) — zero failures and zero warnings

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies — start immediately
- **Foundational (Phase 2)**: Depends on Phase 1 (sqlglot installed)
- **US1+US2 (Phase 3)**: Depends on Phase 2 (types and constants defined)
- **US3 (Phase 4)**: Depends on Phase 3 (validate_query() exists with Execute node handling)
- **US4 (Phase 5)**: Depends on Phase 3 (validate_query() exists for recursive extension)
- **Integration (Phase 6)**: Depends on Phases 3, 4, 5 (all validation logic complete)

### User Story Dependencies

- **US1+US2 (P1)**: Can start after Phase 2 — no dependencies on other stories
- **US3 (P2)**: Depends on US1+US2 (Execute node must be in the denied set before allowlist can exempt from it)
- **US4 (P2)**: Depends on US1+US2 — independent of US3 but shares same files (src/db/query.py, tests/unit/test_query.py)
- **US3 then US4 sequentially** (both modify the same files; parallel execution would cause merge conflicts)

### Within Each User Story

- Tests MUST be written and FAIL before implementation (TDD)
- Implementation makes tests pass (green)
- Verify step confirms all tests green before moving on

### Parallel Opportunities

- **Within Phase 5**: T014, T015, T016 are logically independent aspects of obfuscation resistance but share src/db/query.py — implement sequentially
- **No cross-phase parallelism**: Phases 4 and 5 both modify the same files (query.py, test_query.py)

---

## Execution Example: Sequential After Core

```bash
# After Phase 3 (US1+US2) completes:
# Step 1: US3 - Stored procedure allowlist
Task: "Write tests for stored procedure allowlist in tests/unit/test_query.py"
Task: "Implement stored procedure checking in src/db/query.py"

# Step 2: US4 - Obfuscation resistance (after US3 complete)
Task: "Write tests for obfuscation resistance in tests/unit/test_query.py"
Task: "Implement recursive walking, batch handling, parse failure in src/db/query.py"
```

---

## Implementation Strategy

### MVP First (US1 + US2)

1. Complete Phase 1: Setup (add sqlglot)
2. Complete Phase 2: Foundational (model types + constants)
3. Complete Phase 3: US1+US2 (core denylist validation)
4. **STOP and VALIDATE**: All denied categories work, safe queries pass, allow_write bypass functional
5. This is a functional MVP — the old keyword blocklist is replaced

### Incremental Delivery

1. Setup + Foundational → Types ready
2. US1+US2 → Core validation works (MVP!)
3. US3 → Stored procedures allowed
4. US4 → Obfuscation resistance hardened
5. Integration → Old code removed, everything wired up
6. Each phase adds value without breaking previous phases

---

## Notes

- [P] tasks = different files, no dependencies
- [Story] label maps task to specific user story for traceability
- US1+US2 share a phase because they're co-dependent (both P1, same function)
- US3 and US4 both depend on US1+US2; execute sequentially (shared files)
- Commit after each phase checkpoint
- validate_query() is a pure function — no mocking needed for unit tests
