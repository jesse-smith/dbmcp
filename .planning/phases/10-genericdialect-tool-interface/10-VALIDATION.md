---
phase: 10
slug: genericdialect-tool-interface
status: draft
nyquist_compliant: true
wave_0_complete: false
created: 2026-04-14
---

# Phase 10 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/ -x -q --tb=short` |
| **Full suite command** | `uv run pytest tests/ -v` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/ -x -q --tb=short`
- **After every plan wave:** Run `uv run pytest tests/ -v`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 10-01-01 | 01 | 1 | DIAL-04 | T-10-01 | GenericDialect implements DialectStrategy protocol | unit | `uv run pytest tests/unit/test_generic_dialect.py -v` | ❌ W0 | ⬜ pending |
| 10-01-02 | 01 | 1 | CONF-05 | T-10-02 | URL routing and lazy imports work correctly | unit | `uv run pytest tests/unit/test_url_routing.py tests/unit/test_optional_deps.py -v` | ❌ W0 | ⬜ pending |
| 10-02-01 | 02 | 2 | CONF-03 | T-10-03 | ConnectionManager generalized for multi-dialect | unit | `uv run pytest tests/unit/test_connection_manager.py -v` | ✅ | ⬜ pending |
| 10-02-02 | 02 | 2 | CONF-03 | T-10-04 | connect_database accepts connection_name or sqlalchemy_url only | unit | `uv run pytest tests/unit/test_connect_tool.py -v` | ❌ W0 | ⬜ pending |
| 10-03-01 | 03 | 2 | CONF-04 | T-10-06 | pyodbc in [mssql] extra, not core | unit | `uv run pytest tests/unit/test_pyproject_extras.py -v` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_generic_dialect.py` — stubs for DIAL-04 GenericDialect behavior
- [ ] `tests/unit/test_url_routing.py` — stubs for URL scheme routing
- [ ] `tests/unit/test_optional_deps.py` — stubs for CONF-05 lazy import error messages
- [ ] `tests/unit/test_connect_tool.py` — stubs for CONF-03 connect_database routing
- [ ] `tests/unit/test_pyproject_extras.py` — stubs for CONF-04 dependency separation

*Existing infrastructure covers connect_database tool testing.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| pip install dbmcp (core only) has no pyodbc | CONF-04 | Requires clean venv | `uv venv /tmp/test-core && uv pip install . && python -c "import pyodbc"` should fail |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
