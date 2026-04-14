---
phase: 09-config-discrimination-validation-dialect
plan: 02
subsystem: validation
tags: [dialect-aware, validation, safe-procedures, protocol]
dependency_graph:
  requires: [08-01, 08-02]
  provides: [dialect-aware-validation, safe-procedures-protocol]
  affects: [query-service, validation-tests]
tech_stack:
  added: []
  patterns: [keyword-only-required-params, pure-functions, protocol-property]
key_files:
  created: []
  modified:
    - src/db/dialects/protocol.py
    - src/db/dialects/mssql.py
    - src/db/validation.py
    - src/db/query.py
    - tests/unit/test_validation.py
    - tests/unit/test_validation_edge_cases.py
    - tests/unit/test_query.py
    - tests/compliance/test_nfr_compliance.py
    - tests/unit/test_dialect_protocol.py
decisions:
  - "SAFE_PROCEDURES count is 21 (not 22 as plan stated) -- original frozenset had 21 unique entries"
  - "safe_procedures defaults to empty frozenset in validate_query, composed at caller level"
metrics:
  duration: 9min
  completed: 2026-04-14
  tasks: 2
  files: 9
---

# Phase 09 Plan 02: Dialect-Aware Query Validation Summary

Dialect-aware validate_query with required keyword-only dialect parameter, safe_procedures moved from module constant to DialectStrategy protocol property, validation.py made pure (no config dependency).

## What Was Done

### Task 1: Add safe_procedures to protocol and make validate_query dialect-aware
**Commit:** `2a0ed48` (RED), `095868c` (GREEN)

- Added `safe_procedures` property to `DialectStrategy` protocol returning `frozenset[str]`
- Implemented `MssqlDialect.safe_procedures` with 21 known-safe SQL Server system stored procedures
- Changed `validate_query` signature: `dialect` is required keyword-only (no default), `safe_procedures` defaults to empty frozenset
- Changed `sqlglot.parse(sql, dialect="tsql")` to `sqlglot.parse(sql, dialect=dialect)` -- no more hardcoded dialect
- Threaded `safe_procedures` parameter through all internal helpers: `_classify_statement`, `_check_execute`, `_check_control_flow`, `_check_command`, `_check_stored_procedure`
- Removed `SAFE_PROCEDURES` module constant and `get_allowed_procedures()` function
- Removed `from src.config import get_config` import -- validation.py is now fully pure (no side effects, no config dependency)
- Added 11 cross-dialect tests covering tsql/databricks SELECT, DML, DDL, EXEC behavior

### Task 2: Update all test call sites and production caller
**Commit:** `cb29e0a`

- Updated production caller in `QueryService._execute_query_internal()` to thread `dialect` from `self._dialect.sqlglot_dialect` and merge `self._dialect.safe_procedures` with `get_config().allowed_stored_procedures`
- Updated all validate_query calls across 5 test files:
  - `tests/unit/test_validation.py`: 30 calls with `dialect="tsql"`, SP tests with `safe_procedures=MSSQL_SAFE`
  - `tests/unit/test_validation_edge_cases.py`: 9 calls with `dialect="tsql"`
  - `tests/unit/test_query.py`: 8 calls with `dialect="tsql"`
  - `tests/compliance/test_nfr_compliance.py`: 7 calls with `dialect="tsql"`
  - `tests/unit/test_dialect_protocol.py`: added `safe_procedures` to `_StubDialect`
- Full test suite: 686 passed, 41 skipped, 0 failed

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] SAFE_PROCEDURES count is 21, not 22**
- **Found during:** Task 1 (TDD GREEN phase)
- **Issue:** Plan stated "22 sp_ procedures" but the original frozenset in validation.py contained 21 unique entries (counting error in plan/research)
- **Fix:** Corrected test assertion from `== 22` to `== 21`
- **Files modified:** tests/unit/test_validation.py
- **Commit:** 095868c

**2. [Rule 3 - Blocking] _StubDialect missing safe_procedures property**
- **Found during:** Task 2 (full test suite run)
- **Issue:** `_StubDialect` in test_dialect_protocol.py didn't implement `safe_procedures`, causing `isinstance()` check to fail with `runtime_checkable` protocol
- **Fix:** Added `safe_procedures` property returning `frozenset()` to `_StubDialect`
- **Files modified:** tests/unit/test_dialect_protocol.py
- **Commit:** cb29e0a

**3. [Rule 3 - Blocking] Missed validate_query call in test_validation_edge_cases.py**
- **Found during:** Task 2 (full test suite run)
- **Issue:** `test_xp_cmdshell_category` used a direct string literal `validate_query("EXEC xp_cmdshell 'dir'")` that wasn't caught by the `replace_all` pattern matching `validate_query(sql)`
- **Fix:** Added `dialect="tsql"` to the call
- **Files modified:** tests/unit/test_validation_edge_cases.py
- **Commit:** cb29e0a

## Threat Model Compliance

- T-09-04 (dialect parameter tampering): Mitigated -- callers get dialect from `DialectStrategy.sqlglot_dialect` (protocol-controlled); sqlglot.parse raises on invalid dialect names
- T-09-05 (safe_procedures bypass): Mitigated -- safe_procedures composed at QueryService level from `dialect.safe_procedures | config.allowed_stored_procedures`; validate_query cannot expand the set
- T-09-06 (EXEC in non-MSSQL dialect): Verified -- EXEC in databricks produces PARSE_FAILURE (test covers this)

## Self-Check: PASSED

All 9 modified files verified on disk. All 3 commits (2a0ed48, 095868c, cb29e0a) verified in git log.
