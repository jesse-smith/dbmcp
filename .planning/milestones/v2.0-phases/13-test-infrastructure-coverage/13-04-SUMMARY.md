---
phase: 13
plan: 04
subsystem: test-infrastructure
tags: [coverage, pyproject, ratchet, test-infrastructure]
requirements: [TEST-03]
dependencies:
  requires: [13-02, 13-03]
  provides: [coverage-floor-85]
  affects: [pyproject.toml]
tech_stack:
  added: []
  patterns: [single global coverage floor, no per-module floors (D-12), no CI integration (D-13)]
key_files:
  created: []
  modified:
    - pyproject.toml
decisions:
  - "Raised fail_under from 70 to 85 (not higher) to preserve ~5pt headroom above measured 90.64% for normal churn"
  - "Strict ordering: plan landed last in phase 13 after 13-02 and 13-03 merged to avoid transient coverage drops tripping the floor mid-wave"
metrics:
  duration: ~2 min
  tasks: 1
  files_changed: 1
  tests_passing: 872
  tests_skipped: 78
  coverage_before: 90.64%
  coverage_after: 90.64%
  coverage_floor_before: 70
  coverage_floor_after: 85
  completed: 2026-04-27
requirements-completed: [TEST-03]
---

# Phase 13 Plan 04: Coverage Floor Ratchet Summary

One-liner: Raised pyproject.toml `[tool.coverage.report].fail_under` from 70 to 85, closing the TEST-03 ratchet gap with ~5 points of headroom over the measured 90.64% coverage baseline.

## What Was Built

Single-line configuration change to `pyproject.toml` line 102:

```diff
 [tool.coverage.report]
-fail_under = 70
+fail_under = 85
```

No source or test code was modified. No new dependencies. No CI configuration added. Per phase decisions D-11/D-12/D-13, this is a single global knob with no per-module floors.

## Verification

Pre-edit baseline measurement:
- `uv run pytest --cov=src`: 872 passed, 78 skipped
- Total coverage: 90.64% (well above the 85% target)

Post-edit verification:
- `uv run pytest --cov=src` exits 0
- Output line: `Required test coverage of 85.0% reached. Total coverage: 90.64%`
- `grep -c "fail_under = 85" pyproject.toml` → 1
- `grep -c "fail_under = 70" pyproject.toml` → 0
- `git diff pyproject.toml` → 1 line changed (+1/-1)

Acceptance criteria: all satisfied.

## Pre-flight Checks

- `.planning/phases/13-test-infrastructure-coverage/13-02-SUMMARY.md` exists — confirmed
- `.planning/phases/13-test-infrastructure-coverage/13-03-SUMMARY.md` exists — confirmed
- Wave 2 migrations merged before ratchet landed (strict ordering per Risk #5)

## Commits

- `7152fe2` — chore(13-04): raise coverage floor from 70 to 85

## Deviations from Plan

None — plan executed exactly as written. Single-line edit, no surprises.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: pyproject.toml (modified, fail_under = 85 present)
- FOUND: commit 7152fe2
- FOUND: .planning/phases/13-test-infrastructure-coverage/13-04-SUMMARY.md
