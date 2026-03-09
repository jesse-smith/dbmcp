---
phase: 3
slug: code-quality-test-coverage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 3 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest >=7.0.0 with pytest-cov >=4.0.0 |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q -m "not integration"` |
| **Full suite command** | `uv run pytest -m "not integration" --cov --cov-report=term-missing` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q -m "not integration"`
- **After every plan wave:** Run `uv run pytest -m "not integration" --cov --cov-report=term-missing`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 03-01-01 | 01 | 1 | QUAL-01 | smoke | `test -f src/metrics.py && echo FAIL \|\| echo PASS` | N/A | ⬜ pending |
| 03-01-02 | 01 | 1 | QUAL-01 | smoke | `grep -rn "from src.metrics\|import metrics" src/ tests/` | N/A | ⬜ pending |
| 03-02-01 | 02 | 1 | QUAL-02 | smoke | `grep -rn "except Exception" src/ \| grep -v mcp_server/ \| wc -l` (expect 0) | N/A | ⬜ pending |
| 03-02-02 | 02 | 1 | QUAL-02 | unit | `uv run pytest tests/ -x -q -m "not integration"` | Existing | ⬜ pending |
| 03-03-01 | 01 | 2 | QUAL-03 | unit | `uv run pyright src/db/query.py` | N/A | ⬜ pending |
| 03-03-02 | 01 | 2 | QUAL-03 | unit | `grep -c "type: ignore" src/db/query.py` (expect 0) | N/A | ⬜ pending |
| 03-04-01 | 02 | 2 | TEST-01 | unit | `uv run pytest -m "not integration" --cov --cov-report=term-missing` | Existing + new | ⬜ pending |
| 03-05-01 | 02 | 2 | TEST-02 | smoke | `grep "fail_under" pyproject.toml` | N/A | ⬜ pending |
| 03-05-02 | 02 | 2 | TEST-02 | smoke | `grep "target: 70" codecov.yml` | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `pyright` — add to dev dependencies for QUAL-03 type checking
- [ ] New test stubs in `tests/` — for metadata.py coverage gaps (TEST-01)

*Existing infrastructure covers most phase requirements. Only pyright and metadata coverage tests are new.*

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
