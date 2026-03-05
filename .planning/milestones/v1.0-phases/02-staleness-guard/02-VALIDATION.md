---
phase: 2
slug: staleness-guard
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 2 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest + pytest-asyncio (existing) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/test_staleness.py -x` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~5 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_staleness.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 10 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 02-01-01 | 01 | 0 | DOCS-02a | unit | `uv run pytest tests/unit/test_staleness.py -x` | ❌ W0 | ⬜ pending |
| 02-01-02 | 01 | 1 | DOCS-02a | unit | `uv run pytest tests/unit/test_staleness.py -x` | ❌ W0 | ⬜ pending |
| 02-01-03 | 01 | 1 | DOCS-02b | unit | `uv run pytest tests/unit/test_staleness.py -x` | ❌ W0 | ⬜ pending |
| 02-01-04 | 01 | 2 | DOCS-02c | unit | `uv run pytest tests/ -x` | ❌ W0 | ⬜ pending |
| 02-01-05 | 01 | 2 | DOCS-02d | unit | `uv run pytest tests/unit/test_staleness.py --cov -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_staleness.py` — stubs for DOCS-02a/b/c
- [ ] Parser/comparison utility module(s) — docstring parsing + field comparison logic
- [ ] Meta-tests for parser logic — needed for 90%+ coverage (DOCS-02d)
- [ ] pytest-cov — verify available as dev dependency for coverage measurement

*Existing infrastructure covers: mock patterns, async fixtures, TOON decoder, conftest.py*

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 10s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
