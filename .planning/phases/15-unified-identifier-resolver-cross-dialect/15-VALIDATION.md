---
phase: 15
slug: unified-identifier-resolver-cross-dialect
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-28
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ --cov=src --cov-fail-under=85` |
| **Estimated runtime** | ~TBD seconds (planner/executor to confirm) |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ --cov=src --cov-fail-under=85`
- **Before `/gsd:verify-work`:** Full suite must be green at ≥85% coverage
- **Max feedback latency:** TBD seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| (planner fills per-task rows) | | | IDENT-03..07 | | | unit | `uv run pytest tests/...` | | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Planner to specify. Existing pytest infrastructure covers all phase requirements; new resolver module (`src/db/identifiers.py`) needs a new test file + parametrized matrix per D-12.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Databricks `bmtct.ml_infections_ref.mv_fever_episodes` end-to-end without `USE CATALOG` | IDENT-05 (SC3) | Requires live Databricks connection | Connect to Databricks; call get_sample_data with 3-part table_name |

*Most behaviors have automated unit coverage via the resolver matrix; live-Databricks SC3 is manual.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < TBD s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
