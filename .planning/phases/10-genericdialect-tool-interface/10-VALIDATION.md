---
phase: 10
slug: genericdialect-tool-interface
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-14
updated: 2026-05-06
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
| 10-01-01 | 01 | 1 | DIAL-04 | T-10-01 | GenericDialect implements DialectStrategy protocol | unit | `uv run pytest tests/unit/test_generic_dialect.py -v` | ✅ | ✅ |
| 10-01-02 | 01 | 1 | CONF-05 | T-10-02 | URL routing and lazy imports work correctly | unit | `uv run pytest tests/unit/test_url_routing.py tests/unit/test_optional_deps.py -v` | ✅ | ✅ |
| 10-02-01 | 02 | 2 | CONF-03 | T-10-03 | ConnectionManager generalized for multi-dialect | unit | `uv run pytest tests/unit/test_connection.py -v` | ✅ | ✅ |
| 10-02-02 | 02 | 2 | CONF-03 | T-10-04 | connect_database accepts connection_name or sqlalchemy_url only | unit | `uv run pytest tests/unit/test_connect_tool.py -v` | ✅ | ✅ |
| 10-03-01 | 03 | 2 | CONF-04 | T-10-06 | pyodbc in [mssql] extra, not core | unit | `uv run pytest tests/unit/test_pyproject_extras.py -v` | ✅ | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_generic_dialect.py` — DIAL-04 GenericDialect behavior (17 tests)
- [x] `tests/unit/test_url_routing.py` — URL scheme routing (8 tests)
- [x] `tests/unit/test_optional_deps.py` — CONF-05 lazy import error messages (2 tests)
- [x] `tests/unit/test_connect_tool.py` — CONF-03 connect_database routing (12 tests)
- [x] `tests/unit/test_pyproject_extras.py` — CONF-04 dependency separation (9 tests)

*Existing infrastructure covers connect_database tool testing.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| pip install dbmcp (core only) has no pyodbc | CONF-04 | Requires clean venv | `uv venv /tmp/test-core && uv pip install . && python -c "import pyodbc"` should fail |

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
| Escalated | 1 (already manual-only: core-install no-pyodbc) |

**Evidence:** 48 tests pass across the 5 Wave-0 test files (generic_dialect, url_routing, optional_deps, connect_tool, pyproject_extras). All 4 requirements (DIAL-04, CONF-03, CONF-04, CONF-05) satisfied per 10-VERIFICATION.md. Manual-only item for clean-venv install verification remains (requires external venv setup).
