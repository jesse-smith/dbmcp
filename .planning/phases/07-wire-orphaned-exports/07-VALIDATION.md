---
phase: 7
slug: wire-orphaned-exports
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-10
validated: 2026-03-10
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
| 07-01-01 | 01 | 1 | INFRA-02 | unit | `uv run pytest tests/unit/test_query.py::TestTruncationConfig::test_truncation_uses_config_limit_500 -x` | ✅ | ✅ green |
| 07-01-02 | 01 | 1 | INFRA-02 | unit | `uv run pytest tests/unit/test_query.py::TestTruncationConfig::test_truncation_default_limit_preserves_short_strings -x` | ✅ | ✅ green |
| 07-01-03 | 01 | 1 | CONN-02 | unit | `uv run pytest tests/unit/test_async_tools.py -x -k safety_net_sqlalchemy_error_classified` | ✅ | ✅ green |
| 07-01-04 | 01 | 1 | CONN-02 | unit | `uv run pytest tests/unit/test_async_tools.py -x -k safety_net_generic_error_fallback` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_query.py` — truncation config tests for INFRA-02 (2 tests, green)
- [x] `tests/unit/test_async_tools.py` — error classification wiring tests for CONN-02 (18 parametrized tests, green)

*Existing infrastructure covers framework and fixtures.*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved

---

## Validation Audit 2026-03-10

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 4 tasks had existing automated tests confirmed green. No auditor agent needed.
