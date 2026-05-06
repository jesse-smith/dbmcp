---
phase: 9
slug: config-discrimination-validation-dialect
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-14
updated: 2026-05-06
---

# Phase 9 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -q` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -q`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 09-01-01 | 01 | 1 | CONF-01 | — | dialect field required, ValueError on missing | unit | `uv run pytest tests/unit/test_config.py -x -q` | ✅ | ✅ |
| 09-01-02 | 01 | 1 | CONF-02 | — | typed per-dialect config models validate fields | unit | `uv run pytest tests/unit/test_config.py -x -q` | ✅ | ✅ |
| 09-02-01 | 02 | 2 | VALID-01 | — | validate_query accepts dialect param | unit | `uv run pytest tests/unit/test_validation.py -x -q` | ✅ | ✅ |
| 09-02-02 | 02 | 2 | VALID-02 | — | safe_procedures property on DialectStrategy | unit | `uv run pytest tests/unit/test_validation.py -x -q` | ✅ | ✅ |
| 09-02-03 | 02 | 2 | VALID-03 | — | denylist works across sqlglot dialects | unit | `uv run pytest tests/unit/test_validation.py -x -q` | ✅ | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

*Existing infrastructure covers all phase requirements.*

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

**Approval:** approved (2026-05-06)

---

## Validation Audit 2026-05-06

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

**Evidence:** 151 tests pass in `tests/unit/test_config.py` (51) and `tests/unit/test_validation.py` (90+ incl. cross-dialect denylist parametrized tests). All 5 requirements (CONF-01, CONF-02, VALID-01, VALID-02, VALID-03) satisfied per 09-VERIFICATION.md (16/16 observable truths).
