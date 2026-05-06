---
phase: 12-analysis-module-adaptation
fixed_at: 2026-04-15T14:35:00Z
review_path: .planning/phases/12-analysis-module-adaptation/12-REVIEW.md
iteration: 1
findings_in_scope: 5
fixed: 3
skipped: 2
status: partial
---

# Phase 12: Code Review Fix Report

**Fixed at:** 2026-04-15T14:35:00Z
**Source review:** .planning/phases/12-analysis-module-adaptation/12-REVIEW.md
**Iteration:** 1

**Summary:**
- Findings in scope: 5
- Fixed: 3
- Skipped: 2

## Fixed Issues

### WR-01: Unused parameter `data_type` in `get_basic_stats`

**Files modified:** `src/analysis/column_stats.py`, `tests/unit/test_column_stats.py`
**Commit:** 86f2f52
**Applied fix:** Removed the unused `data_type` parameter from `get_basic_stats` method signature and updated all 7 call sites (1 in source, 6 in tests).

### WR-02: `fetchall()[0][0]` without empty-list guard in `compute_overlap`

**Files modified:** `src/analysis/fk_candidates.py`
**Commit:** 977a21d
**Applied fix:** Replaced `fetchall()[0][0]` with `fetchone()` plus a None guard for both the source distinct count query (line 409) and the overlap count query (line 426).

### IN-01: Redundant `or 0` fallback after `safe_int`

**Files modified:** `src/analysis/column_stats.py`
**Commit:** 0fa1815
**Applied fix:** Replaced ambiguous `safe_int(...) or 0` pattern with explicit `if value is None: value = 0` checks for both `null_count` and `distinct_count` in `_build_stats_from_describe_extended`.

## Skipped Issues

### WR-03: Column/table names interpolated into SQL via f-strings

**File:** `src/analysis/column_stats.py:209-215`, `src/analysis/pk_discovery.py:274-280`, `src/analysis/fk_candidates.py:402-422`
**Reason:** Review explicitly states "No immediate code change required" -- this is a pre-existing codebase pattern tracked as technical debt for future hardening.
**Original issue:** Column names interpolated into SQL via f-strings with bracket quoting. A column name containing `]` could produce malformed SQL.

### IN-02: Dialect helper functions duplicated across test files

**File:** `tests/unit/test_fk_candidates.py:685-709`, `tests/unit/test_pk_discovery.py:448-471`
**Reason:** Low priority refactoring. The review marks this as minor duplication suitable for future extraction to shared test helpers. Not worth the churn in this iteration.
**Original issue:** Mock dialect factory functions duplicated across three test files.

---

_Fixed: 2026-04-15T14:35:00Z_
_Fixer: Claude (gsd-code-fixer)_
_Iteration: 1_
