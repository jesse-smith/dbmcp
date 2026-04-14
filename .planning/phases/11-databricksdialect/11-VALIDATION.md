---
phase: 11
slug: databricksdialect
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-14
---

# Phase 11 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml |
| **Quick run command** | `uv run pytest tests/ -x -q` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~30 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 30 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 11-01-01 | 01 | 1 | DIAL-03 | — | N/A | unit | `uv run pytest tests/test_databricks_dialect.py -x -q` | ❌ W0 | ⬜ pending |
| 11-02-01 | 02 | 1 | META-01 | — | N/A | unit | `uv run pytest tests/test_metadata.py -x -q` | ✅ | ⬜ pending |
| 11-02-02 | 02 | 1 | META-02 | — | N/A | unit | `uv run pytest tests/test_metadata.py -x -q` | ✅ | ⬜ pending |
| 11-02-03 | 02 | 2 | META-03 | — | N/A | unit | `uv run pytest tests/test_schema_tools.py -x -q` | ✅ | ⬜ pending |
| 11-02-04 | 02 | 2 | META-04 | — | N/A | unit | `uv run pytest tests/test_metadata.py -x -q` | ✅ | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/test_databricks_dialect.py` — stubs for DIAL-03 (DatabricksDialect unit tests)
- [ ] `tests/conftest.py` — Databricks mock fixtures (mock databricks-sqlalchemy, mock Inspector)

*Existing infrastructure covers most phase requirements. Wave 0 adds Databricks-specific test scaffolding.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Databricks live connection | DIAL-03 | Requires Databricks workspace | Connect via `connect_database` with real Databricks credentials, verify engine creation |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
