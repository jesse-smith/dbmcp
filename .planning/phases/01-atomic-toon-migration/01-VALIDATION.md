---
phase: 1
slug: atomic-toon-migration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-04
---

# Phase 1 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.0+ with pytest-asyncio |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd:verify-work`:** Full suite must be green + `uv run ruff check src/` clean
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 01-01-01 | 01 | 0 | SRLZ-01 | unit | `uv run pytest tests/unit/test_serialization.py::test_toon_import -x` | No — Wave 0 | ⬜ pending |
| 01-01-02 | 01 | 0 | SRLZ-02 | unit | `uv run pytest tests/unit/test_serialization.py::TestEncodeResponse -x` | No — Wave 0 | ⬜ pending |
| 01-01-03 | 01 | 0 | SRLZ-04 | unit | `uv run pytest tests/unit/test_serialization.py::TestPreSerialize -x` | No — Wave 0 | ⬜ pending |
| 01-01-04 | 01 | 0 | TEST-01 | unit | `uv run pytest tests/unit/test_helpers.py -x` | No — Wave 0 | ⬜ pending |
| 01-02-01 | 02 | 1 | SRLZ-03 | integration | `uv run pytest tests/integration/ -x` | Yes (needs update) | ⬜ pending |
| 01-02-02 | 02 | 1 | TEST-02 | compliance | grep-based (no json.loads on tool responses) | N/A | ⬜ pending |
| 01-02-03 | 02 | 1 | TEST-03 | integration | `uv run pytest tests/integration/ -x` | Yes (needs update) | ⬜ pending |
| 01-02-04 | 02 | 1 | DOCS-01 | compliance | grep-based (no "JSON string" in docstrings) | N/A | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_serialization.py` — stubs for SRLZ-01, SRLZ-02, SRLZ-04 (encode_response, _pre_serialize, TypeError on unknowns)
- [ ] `tests/unit/test_helpers.py` — stubs for TEST-01 (parse_tool_response roundtrip)
- [ ] `toon-format` dependency in pyproject.toml — SRLZ-01 prerequisite

---

## Manual-Only Verifications

*All phase behaviors have automated verification.*

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
