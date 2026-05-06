---
phase: 8
slug: dialect-protocol-mssql-extraction
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-04-13
updated: 2026-05-06
---

# Phase 8 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.x |
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

| Task ID | Plan | Wave | Requirement | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------------|-----------|-------------------|-------------|--------|
| 08-01-T1 | 01 | 0 | DIAL-01 | Protocol conformance enforced via runtime_checkable | unit | `uv run pytest tests/unit/test_dialect_protocol.py -q` | ✅ | ✅ |
| 08-01-T2 | 01 | 0 | DIAL-05 | Fail-fast ValueError on unknown dialect name | unit | `uv run pytest tests/unit/test_dialect_registry.py -q` | ✅ | ✅ |
| 08-02-T1 | 02 | 1 | DIAL-02, META-05 | MssqlDialect implements protocol; bracket quoting; ODBC auth paths isolated | unit | `uv run pytest tests/unit/test_mssql_dialect.py -q` | ✅ | ✅ |
| 08-02-T2 | 02 | 1 | DIAL-02 | Azure AD auth relocation with backward-compat shim | unit | `uv run pytest tests/unit/test_azure_auth.py -q` | ✅ | ✅ |
| 08-03-T1 | 03 | 2 | DIAL-02, TEST-01 | ConnectionManager delegates engine creation to dialect | unit | `uv run pytest tests/unit/test_connection.py tests/unit/test_query_timeout.py -q` | ✅ | ✅ |
| 08-03-T2 | 03 | 2 | META-05, TEST-01 | Metadata/Query services use dialect capability flags + quote_identifier | compliance+unit | `uv run pytest tests/compliance/test_nfr_compliance.py tests/unit/test_query.py -q` | ✅ | ✅ |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_dialect_protocol.py` — DIAL-01 (10 tests)
- [x] `tests/unit/test_dialect_registry.py` — DIAL-05 (6 tests)
- [x] `tests/unit/test_mssql_dialect.py` — DIAL-02, META-05 (32 tests)

*All Wave 0 test files created and green.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| (none) | — | All phase requirements have automated coverage | — |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved (2026-05-06)

---

## Validation Audit 2026-05-06

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

**Evidence:** 48 dialect-specific tests pass (`tests/unit/test_dialect_protocol.py`, `test_dialect_registry.py`, `test_mssql_dialect.py`). All 5 requirements (DIAL-01, DIAL-02, DIAL-05, META-05, TEST-01) map to passing automated tests per 08-VERIFICATION.md (score 7/7). TEST-01 zero-regression is covered by full suite (872 tests green).
