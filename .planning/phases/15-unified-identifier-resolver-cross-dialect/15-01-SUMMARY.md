---
phase: 15-unified-identifier-resolver-cross-dialect
plan: 01
subsystem: db/dialects
tags: [dialect-strategy, capability-properties, identifier-resolution]
requires: []
provides:
  - "DialectStrategy.default_schema property (str | None)"
  - "DialectStrategy.max_identifier_depth property (int)"
  - "MSSQL: default_schema='dbo', max_identifier_depth=2"
  - "Databricks: default_schema=None, max_identifier_depth=3"
  - "generic: default_schema=None, max_identifier_depth=1"
affects:
  - "src/db/identifiers.py (Plan 03) reads dialect.default_schema / dialect.max_identifier_depth"
tech-stack:
  added: []
  patterns: ["dialect-owned capability advertisement via @property"]
key-files:
  created: []
  modified:
    - src/db/dialects/protocol.py
    - src/db/dialects/mssql.py
    - src/db/dialects/databricks.py
    - src/db/dialects/generic.py
    - tests/unit/test_mssql_dialect.py
    - tests/unit/test_databricks_dialect.py
    - tests/unit/test_generic_dialect.py
    - tests/unit/test_dialect_protocol.py
decisions:
  - "Databricks default_schema returns None (not hardcoded 'main') — avoids Phase 14 anti-pattern; connection/catalog decides"
  - "generic max_identifier_depth/default_schema return literals directly, not threaded through __init__ (constant per dialect)"
metrics:
  duration: ~1 task-cycle
  completed: 2026-05-28
requirements: [IDENT-03, IDENT-07]
---

# Phase 15 Plan 01: Dialect Capability Properties Summary

Added two dialect-owned capability properties — `default_schema` and `max_identifier_depth` — to the `DialectStrategy` Protocol and all three implementations (MSSQL, Databricks, generic), so the Plan 03 resolver can read per-dialect depth limits and default-schema facts off any dialect instance instead of hardcoding `'dbo'` and scattered depth logic.

## What Was Built

- **Protocol (`src/db/dialects/protocol.py`):** Declared `default_schema(self) -> str | None` and `max_identifier_depth(self) -> int` as `@property` with docstrings + `...` body, matching the existing `sqlglot_dialect` shape. Extended the class-level `Properties:` docstring block to enumerate both.
- **MSSQL (`src/db/dialects/mssql.py`):** `default_schema` → `"dbo"`, `max_identifier_depth` → `2`.
- **Databricks (`src/db/dialects/databricks.py`):** `default_schema` → `None` (deliberately NOT `'main'`), `max_identifier_depth` → `3`.
- **generic (`src/db/dialects/generic.py`):** `default_schema` → `None`, `max_identifier_depth` → `1` (literals, not threaded through `__init__`).
- **Tests:** Added 6 dialect-property tests across the three dialect test files; updated `_StubDialect` in `test_dialect_protocol.py` to keep runtime-checkable Protocol conformance intact.

## TDD Cycle

| Gate  | Commit    | Description                                                              |
| ----- | --------- | ------------------------------------------------------------------------ |
| RED   | `d56cfc0` | `test(15-01)`: Protocol declarations + 6 failing dialect-property tests  |
| GREEN | `272c23b` | `feat(15-01)`: implement both properties on all 3 impls; fix stub        |

RED verified: all 6 tests failed with `AttributeError` (properties not yet on impls). GREEN verified: 122 passed across the four test files.

## Verification

- `uv run pytest tests/unit/test_mssql_dialect.py tests/unit/test_databricks_dialect.py tests/unit/test_generic_dialect.py tests/unit/test_dialect_protocol.py` → 122 passed.
- `grep -v '^#' src/db/dialects/databricks.py | grep -c "'main'"` → `0` (no hardcoded Databricks default schema).
- `uv run ruff check src/db/dialects/` → All checks passed (no new warnings).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Updated `_StubDialect` to restore Protocol conformance**
- **Found during:** Task 2 (GREEN)
- **Issue:** Adding two required members to the `DialectStrategy` Protocol caused `test_dialect_protocol.py::test_conforming_class_is_dialect_strategy` to fail — the in-test `_StubDialect` (the "conforming" stub) no longer satisfied the expanded Protocol via the `runtime_checkable` isinstance check.
- **Fix:** Added `default_schema` (→ `None`) and `max_identifier_depth` (→ `1`) `@property` members to `_StubDialect`. Left `_IncompleteDialect` unchanged — it is intentionally non-conforming.
- **Files modified:** tests/unit/test_dialect_protocol.py
- **Commit:** `272c23b`

## Known Stubs

None — both properties return concrete constant values; no placeholder/empty data flows downstream.

## Self-Check: PASSED

- Modified files present: protocol.py, mssql.py, databricks.py, generic.py, 4 test files — all on disk.
- Commits exist: `d56cfc0` (RED), `272c23b` (GREEN) confirmed in `git log`.
- 6 new dialect-property tests pass; Protocol conformance test passes; ruff clean.
