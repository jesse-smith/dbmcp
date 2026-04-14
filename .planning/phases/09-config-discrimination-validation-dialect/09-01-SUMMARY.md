---
phase: 09-config-discrimination-validation-dialect
plan: 01
subsystem: config
tags: [config, dialect, dataclass, dispatch, toml]
dependency_graph:
  requires: []
  provides: [MssqlConnectionConfig, DatabricksConnectionConfig, GenericConnectionConfig, ConnectionConfig-TypeAlias, _DIALECT_PARSERS]
  affects: [src/config.py, tests/unit/test_config.py]
tech_stack:
  added: []
  patterns: [dict-dispatch, frozen-dataclass-per-dialect, TypeAlias-union]
key_files:
  created: []
  modified: [src/config.py, tests/unit/test_config.py]
decisions:
  - Used dict-based dispatch (_DIALECT_PARSERS) matching existing registry pattern
  - ConnectionConfig becomes TypeAlias union rather than base class (composition over inheritance)
  - Warning log for unrecognized fields (silent ignore with visibility)
metrics:
  duration: 6min
  completed: 2026-04-14
  tasks: 1
  files: 2
  tests_added: 20
  tests_total: 658
---

# Phase 09 Plan 01: Per-Dialect Config Discrimination Summary

Frozen dataclass per dialect (MssqlConnectionConfig, DatabricksConnectionConfig, GenericConnectionConfig) with dict-dispatch parser replacing flat ConnectionConfig.

## What Was Done

### Task 1: Per-dialect config dataclasses and dispatch parser (TDD)

**RED:** Wrote 20 new tests covering dialect dispatch, error messages, field validation, backward compatibility, and unknown field warnings. Updated 2 existing tests to include required `dialect` field. Tests failed on import (expected).

**GREEN:** Replaced single `ConnectionConfig` dataclass with three per-dialect frozen dataclasses. Added `_DIALECT_PARSERS` dict for dispatch, `_warn_unknown_fields` helper, and per-dialect parser functions. `ConnectionConfig` is now a `TypeAlias` for the union of all three types. All 658 tests pass.

**Commits:**
- `2d51685` - test(09-01): add failing tests for per-dialect config dispatch (RED)
- `18a2caa` - feat(09-01): per-dialect config dataclasses and dispatch parser (GREEN)

## Key Changes

| File | Change |
|------|--------|
| `src/config.py` | Replaced `ConnectionConfig` class with `MssqlConnectionConfig`, `DatabricksConnectionConfig`, `GenericConnectionConfig` + TypeAlias union. Added `_DIALECT_PARSERS`, `_warn_unknown_fields`, and 3 per-dialect parser functions. |
| `tests/unit/test_config.py` | Added `TestDialectConfigDataclasses` (5 tests), `TestDialectDispatch` (8 tests), `TestBackwardCompat` (3 tests). Updated `TestConnectionConfig` (4 tests) for new types. |

## Decisions Made

1. **Dict-dispatch over if/elif chain** -- Mirrors existing registry pattern, extensible by adding entries to `_DIALECT_PARSERS`.
2. **TypeAlias union over inheritance** -- No shared behavior between dialects; union is simpler and more explicit for type checking.
3. **Warning log for unknown fields** -- Silently ignoring unknown fields would hide config typos; warning provides visibility without failing.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] caplog not capturing warnings due to propagate=False**
- **Found during:** Task 1 GREEN phase
- **Issue:** The `dbmcp` logger has `propagate = False`, so pytest's `caplog` fixture cannot capture log output.
- **Fix:** Replaced caplog-based test with monkeypatched logger.warning capture.
- **Files modified:** tests/unit/test_config.py
- **Commit:** 18a2caa

**2. [Rule 1 - Bug] Existing TOML tests missing dialect field**
- **Found during:** Task 1 RED phase
- **Issue:** `test_valid_toml_parsed` and `test_connection_with_env_var_password_not_resolved` had TOML fixtures without `dialect` field, which would fail with new required-dialect validation.
- **Fix:** Added `dialect = "mssql"` to existing TOML test fixtures.
- **Files modified:** tests/unit/test_config.py
- **Commit:** 2d51685

## Self-Check: PASSED
