---
phase: 3
slug: code-quality-test-coverage
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-09
validated: 2026-03-10
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
| 03-01-01 | 01 | 1 | QUAL-01 | smoke | `test -f src/metrics.py && echo FAIL \|\| echo PASS` | N/A | ✅ green |
| 03-01-02 | 01 | 1 | QUAL-01 | smoke | `grep -rn "from src.metrics\|import metrics" src/ tests/` | N/A | ✅ green |
| 03-02-01 | 02 | 1 | QUAL-02 | smoke | `grep -rn "except Exception" src/ \| grep -v mcp_server/ \| wc -l` (expect 0 in db/) | N/A | ✅ green |
| 03-02-02 | 02 | 1 | QUAL-02 | unit | `uv run pytest tests/ -x -q -m "not integration"` | Existing | ✅ green |
| 03-03-01 | 01 | 2 | QUAL-03 | smoke | `grep -c "type: ignore" src/db/query.py` (expect 0) | N/A | ✅ green |
| 03-03-02 | 01 | 2 | QUAL-03 | unit | `uv run pytest tests/unit/test_query_dataclass_fields.py -q` | Existing | ✅ green |
| 03-04-01 | 03 | 2 | TEST-01 | unit | `uv run pytest -m "not integration" --cov --cov-report=term-missing` | Existing + new | ✅ green |
| 03-05-01 | 03 | 2 | TEST-02 | smoke | `grep "fail_under" pyproject.toml` | N/A | ✅ green |
| 03-05-02 | 03 | 2 | TEST-02 | smoke | `grep "target: 70" codecov.yml` | N/A | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `pyright` — added to dev dependencies (Plan 01, commit `0055bbb`)
- [x] New test stubs in `tests/` — metadata.py error-path tests added (Plan 03, commit `b4410d1`)

*All wave 0 dependencies resolved.*

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

## Validation Audit 2026-03-10

| Metric | Count |
|--------|-------|
| Tasks audited | 9 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

All 9 per-task verifications ran green. 634 unit tests pass, 87.74% total coverage, all modules at 70%+. No gaps to fill.
