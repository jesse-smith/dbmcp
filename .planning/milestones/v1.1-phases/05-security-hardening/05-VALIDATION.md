---
phase: 5
slug: security-hardening
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-09
validated: 2026-03-10
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
| 05-01-01 | 01 | 1 | SEC-02 | unit | `uv run pytest tests/unit/test_validation_edge_cases.py -x` | ✅ | ✅ green |
| 05-01-02 | 01 | 1 | SEC-02 | unit | `uv run pytest tests/unit/test_validation_edge_cases.py::TestSqlglotVersionFloor -x` | ✅ | ✅ green |
| 05-02-01 | 02 | 1 | SEC-01 | unit | `uv run pytest tests/unit/test_identifier_validation.py -x` | ✅ | ✅ green |
| 05-02-02 | 02 | 1 | SEC-01 | unit | `uv run pytest tests/unit/test_identifier_validation.py::TestGetValidatedColumns::test_metadata_failure_falls_back_to_regex_with_warning -x` | ✅ | ✅ green |
| 05-02-03 | 02 | 1 | SEC-01 | unit | `uv run pytest tests/unit/test_identifier_validation.py::TestValidateIdentifier::test_error_message_format -x` | ✅ | ✅ green |
| 05-03-01 | 03 | 2 | SEC-01 | unit | `uv run pytest tests/unit/test_query.py -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_validation_edge_cases.py` — 28 parametrized tests for SEC-02 (sqlglot edge cases + version pin)
- [x] `tests/unit/test_identifier_validation.py` — 13 tests for SEC-01 (metadata-based identifier validation)
- [x] No framework install needed — pytest already configured

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

**Approval:** validated

---

## Validation Audit 2026-03-10

| Metric | Count |
|--------|-------|
| Tasks audited | 6 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Total tests | 41 (28 edge cases + 13 identifier validation) |
