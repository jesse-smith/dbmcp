---
phase: 11
slug: databricksdialect
status: active
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-14
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | DIAL-03 | — | N/A | unit | `uv run pytest tests/unit/test_databricks_dialect.py -x -q` | ✅ | ✅ green |
| 11-02-01 | 02 | 1 | META-01 | — | N/A | unit | `uv run pytest tests/unit/test_metadata.py -x -q` | ✅ | ✅ green |
| 11-02-02 | 02 | 1 | META-02 | — | N/A | unit | `uv run pytest tests/unit/test_metadata.py -x -q` | ✅ | ✅ green |
| 11-02-03 | 02 | 2 | META-03 | — | N/A | unit | `uv run pytest tests/unit/test_metadata.py -x -q -k Catalog` | ✅ | ✅ green |
| 11-02-04 | 02 | 2 | META-04 | — | N/A | unit | `uv run pytest tests/unit/test_metadata.py -x -q` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/test_databricks_dialect.py` — created by Plan 11-01 Task 1 (TDD: tests written before implementation)
- [x] `tests/conftest.py` — Databricks mock fixtures added by Plan 11-01 Task 1

*Wave 0 is satisfied by Plan 11-01's TDD approach — test stubs are created as the first step of Task 1 execution.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Databricks live connection | DIAL-03 | Requires Databricks workspace | Connect via `connect_database` with real Databricks credentials, verify engine creation |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-04-14

---

## Validation Audit 2026-05-06

| Metric | Count |
|--------|-------|
| Gaps found | 0 (all requirements already covered) |
| Path corrections | 5 (added `unit/` prefix, remapped META-03 to test_metadata.py) |
| Resolved | 5 (marked ✅ green) |
| Escalated | 0 |

Verified via `uv run pytest tests/unit/test_databricks_dialect.py tests/unit/test_metadata.py -q` — 111 passed.
