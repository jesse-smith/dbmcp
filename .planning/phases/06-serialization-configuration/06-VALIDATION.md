---
phase: 6
slug: serialization-configuration
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-10
validated: 2026-03-10
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
| 06-01-01 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_type_registry.py -x` | ✅ | ✅ green |
| 06-01-02 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_type_registry.py::TestSubclassOrdering -x` | ✅ | ✅ green |
| 06-01-03 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_type_registry.py::TestUnknownType -x` | ✅ | ✅ green |
| 06-01-04 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_serialization.py -x` | ✅ | ✅ green |
| 06-01-05 | 01 | 1 | INFRA-01 | unit | `uv run pytest tests/unit/test_query.py -x` | ✅ | ✅ green |
| 06-02-01 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestLoadConfig::test_local_takes_precedence_over_home -x` | ✅ | ✅ green |
| 06-02-02 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestLoadConfig::test_home_config_used_when_no_local -x` | ✅ | ✅ green |
| 06-02-03 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestLoadConfig::test_local_takes_precedence_over_home -x` | ✅ | ✅ green |
| 06-02-04 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestLoadConfig::test_no_config_file_returns_defaults -x` | ✅ | ✅ green |
| 06-02-05 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestLoadConfig::test_malformed_toml_returns_defaults -x` | ✅ | ✅ green |
| 06-02-06 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestConnectionConfig -x` | ✅ | ✅ green |
| 06-02-07 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestResolveEnvVars -x` | ✅ | ✅ green |
| 06-02-08 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestResolveEnvVars::test_missing_var_raises -x` | ✅ | ✅ green |
| 06-02-09 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestValidateDefaults -x` | ✅ | ✅ green |
| 06-02-10 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestSPAllowlistValidation -x` | ✅ | ✅ green |
| 06-02-11 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestSPAllowlistValidation::test_invalid_sp_names_rejected -x` | ✅ | ✅ green |
| 06-02-12 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestSPAllowlistValidation -x` | ✅ | ✅ green |
| 06-02-13 | 02 | 2 | INFRA-02 | unit | `uv run pytest tests/unit/test_config.py::TestSingleton -x` | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_type_registry.py` — 46 tests covering all handlers, subclass ordering, edge cases
- [x] `tests/unit/test_config.py` — 32 tests covering config loading, validation, env vars, SP allowlist
- [x] No new framework install needed — pytest already configured

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Fallback logging for unknown types | INFRA-01 | Log output verification | Trigger unknown type, check stderr for warning |

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
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Total tests (type_registry) | 46 |
| Total tests (config) | 32 |
| Total tests (serialization) | 21 |
| All green | 99/99 |
