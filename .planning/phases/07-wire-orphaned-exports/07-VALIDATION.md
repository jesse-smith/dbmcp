---
phase: 7
slug: wire-orphaned-exports
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 7 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0.0 + pytest-asyncio >=0.21.0 |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 07-01-01 | 01 | 1 | INFRA-02 | unit | `uv run pytest tests/unit/test_query.py -x -k truncation_config` | ❌ W0 | ⬜ pending |
| 07-01-02 | 01 | 1 | INFRA-02 | unit | `uv run pytest tests/unit/test_query.py -x -k truncation_limit` | ❌ W0 | ⬜ pending |
| 07-01-03 | 01 | 1 | CONN-02 | unit | `uv run pytest tests/unit/test_async_tools.py -x -k classify` | ❌ W0 | ⬜ pending |
| 07-01-04 | 01 | 1 | CONN-02 | unit | `uv run pytest tests/unit/test_async_tools.py -x -k generic_error` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_query.py` — truncation config tests for INFRA-02
- [ ] `tests/unit/test_async_tools.py` — error classification wiring tests for CONN-02

*Existing infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
