---
phase: 6
slug: serialization-configuration
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-10
---

# Phase 6 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.0+ with pytest-asyncio 0.21+ |
| **Config file** | `pyproject.toml` [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/unit/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v --tb=short` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v --tb=short`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 06-01-01 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_type_registry.py -x` | ❌ W0 | ⬜ pending |
| 06-01-02 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_type_registry.py::test_subclass_ordering -x` | ❌ W0 | ⬜ pending |
| 06-01-03 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_type_registry.py::test_unknown_type_raises -x` | ❌ W0 | ⬜ pending |
| 06-01-04 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_serialization.py -x` | ✅ | ⬜ pending |
| 06-01-05 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_query.py -x` | ✅ | ⬜ pending |
| 06-02-01 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_local_config -x` | ❌ W0 | ⬜ pending |
| 06-02-02 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_global_config -x` | ❌ W0 | ⬜ pending |
| 06-02-03 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_local_overrides_global -x` | ❌ W0 | ⬜ pending |
| 06-02-04 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_missing_config -x` | ❌ W0 | ⬜ pending |
| 06-02-05 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_malformed_config -x` | ❌ W0 | ⬜ pending |
| 06-02-06 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_named_connection -x` | ❌ W0 | ⬜ pending |
| 06-02-07 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_env_var_resolution -x` | ❌ W0 | ⬜ pending |
| 06-02-08 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_unresolved_env_var -x` | ❌ W0 | ⬜ pending |
| 06-02-09 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_bounds_validation -x` | ❌ W0 | ⬜ pending |
| 06-02-10 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_sp_allowlist_merge -x` | ❌ W0 | ⬜ pending |
| 06-02-11 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_sp_name_validation -x` | ❌ W0 | ⬜ pending |
| 06-02-12 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_hardcoded_sp_preserved -x` | ❌ W0 | ⬜ pending |
| 06-02-13 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::test_precedence -x` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_type_registry.py` — stubs for INFRA-01a through INFRA-01d
- [ ] `tests/unit/test_config.py` — stubs for INFRA-02a through INFRA-02m
- [ ] No new framework install needed — pytest already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fallback logging for unknown types | INFRA-01 | Log output verification | Trigger unknown type, check stderr for warning |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
