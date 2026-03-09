---
phase: 5
slug: security-hardening
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 5 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0.0 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/test_validation_edge_cases.py tests/unit/test_identifier_validation.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_validation_edge_cases.py tests/unit/test_identifier_validation.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 05-01-01 | 01 | 1 | SEC-02 | unit | `uv run pytest tests/unit/test_validation_edge_cases.py -x` | ❌ W0 | ⬜ pending |
| 05-01-02 | 01 | 1 | SEC-02 | unit | `uv run pytest tests/unit/test_validation_edge_cases.py::test_sqlglot_version -x` | ❌ W0 | ⬜ pending |
| 05-02-01 | 02 | 1 | SEC-01 | unit | `uv run pytest tests/unit/test_identifier_validation.py -x` | ❌ W0 | ⬜ pending |
| 05-02-02 | 02 | 1 | SEC-01 | unit | `uv run pytest tests/unit/test_identifier_validation.py::test_fail_open -x` | ❌ W0 | ⬜ pending |
| 05-02-03 | 02 | 1 | SEC-01 | unit | `uv run pytest tests/unit/test_identifier_validation.py::test_error_messages -x` | ❌ W0 | ⬜ pending |
| 05-03-01 | 03 | 2 | SEC-01 | unit | `uv run pytest tests/unit/test_query.py -x` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_validation_edge_cases.py` — stubs for SEC-02 (sqlglot edge cases + version pin)
- [ ] `tests/unit/test_identifier_validation.py` — stubs for SEC-01 (metadata-based identifier validation)
- [ ] No framework install needed — pytest already configured

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
