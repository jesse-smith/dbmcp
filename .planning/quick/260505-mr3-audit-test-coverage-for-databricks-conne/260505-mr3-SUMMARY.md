---
phase: quick-260505-mr3
plan: 01
subsystem: testing
tags: [audit, databricks, test-coverage]
requires: []
provides: [databricks-coverage-audit]
affects: []
tech-stack:
  added: []
  patterns: []
key-files:
  created:
    - .planning/quick/260505-mr3-audit-test-coverage-for-databricks-conne/260505-mr3-AUDIT.md
    - .planning/todos/pending/2026-05-05-add-databricks-integration-tests.md
  modified: []
decisions:
  - "Verdict: NOT a blocker — post-fix coverage from 4fdaa90 closes the structural gap"
  - "Task 3 checkpoint: defer-via-todo (per preset decision — 2 tests + fixtures >20 lines trivial threshold)"
metrics:
  duration: ~15min
  completed: 2026-05-05
---

# Quick Task 260505-mr3: Databricks connect_with_config Test Coverage Audit Summary

**One-liner:** Audited why Phase-11's 607-test suite missed the Databricks `create_engine` signature drift (bug 4fdaa90); root cause is bucket-B mocking of `connect_with_url` across all Phase-11 Databricks tests. Verdict: not a blocker — post-fix regression tests close the hole.

## Deliverable

`.planning/quick/260505-mr3-audit-test-coverage-for-databricks-conne/260505-mr3-AUDIT.md` — full audit with Q1/Q2/Q3 answers (file:line citations), coverage map, gap list, and NO-blocker verdict.

## Key Findings

1. **Q1 (integration-style coverage):** NO at Phase 11 merge; YES post-fix (`tests/unit/test_connect_with_config_databricks.py:44,90`).
2. **Q2 (why not caught):** Every Phase-11 Databricks `connect_with_config` test used `patch.object(cm, "connect_with_url")` — mocking the caller, not the callee. The URL→kwargs mismatch lived across a mocked seam. Smoking gun at `tests/unit/test_connect_tool.py:278` in commit `551b99d`.
3. **Q3 (env-var substitution):** NO at Phase 11 (only `token` was tested and only `token` was resolved — test and bug agreed); YES post-fix at `tests/unit/test_connect_tool.py:323` and `test_connect_with_config_databricks.py:44`.

## Task 3 Decision

**Decision:** `defer-via-todo` (per `<task_3_preset_decision>` directive).

**Rationale:** The three residual gaps total two tests + a plan-hygiene note. That exceeds the "single new test ≤20 lines" inline threshold. Follow-up todo created at `.planning/todos/pending/2026-05-05-add-databricks-integration-tests.md`.

## Deviations from Plan

**One observation, not a deviation:** The plan's `<interfaces>` block described the live Databricks call path as `connect_with_config → connect_with_url → dialect.create_engine(sqlalchemy_url=…)`. That was accurate pre-fix but not post-fix — the current Databricks branch at `src/db/connection.py:462-513` bypasses `connect_with_url` and calls `dialect.create_engine(**kwargs)` directly at lines 487-493. Documented in AUDIT.md Gap 2 and the follow-up todo.

No auto-fixes (Rules 1-3) applied — this was a pure investigation task with no code changes.

## Files Created

- `.planning/quick/260505-mr3-audit-test-coverage-for-databricks-conne/260505-mr3-AUDIT.md` (the deliverable)
- `.planning/todos/pending/2026-05-05-add-databricks-integration-tests.md` (follow-up for residual gaps)

## Commits

None. Per quick-task constraints, the orchestrator handles the docs commit.

## Self-Check: PASSED

- `.planning/quick/260505-mr3-audit-test-coverage-for-databricks-conne/260505-mr3-AUDIT.md` — FOUND
- `.planning/todos/pending/2026-05-05-add-databricks-integration-tests.md` — FOUND
- All required AUDIT.md sections present: Summary, Q1/Q2/Q3, Coverage Map, Gaps, Verdict, Closure — FOUND
- Every test-reference claim carries a file:line citation — VERIFIED
