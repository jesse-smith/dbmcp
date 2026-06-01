---
phase: 4
slug: connection-management
status: complete
nyquist_compliant: true
wave_0_complete: true
created: 2026-03-09
validated: 2026-03-10
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | pyproject.toml [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/unit/test_connection.py tests/unit/test_server_lifecycle.py -x` |
| **Full suite command** | `uv run pytest tests/ -m "not integration and not performance" -x` |
| **Estimated runtime** | ~1.2 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_connection.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -m "not integration and not performance" -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 1.2 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | Test Classes/Functions | Status |
|---------|------|------|-------------|-----------|-------------------|----------------------|--------|
| 04-01-01 | 01 | 1 | CONN-01a | unit | `uv run pytest tests/unit/test_connection.py -x -k "AuthAwarePoolRecycle"` | TestAuthAwarePoolRecycle (7 tests) + test_pool_pre_ping_and_recycle_set | ✅ green |
| 04-01-02 | 01 | 1 | CONN-01b | unit | `uv run pytest tests/unit/test_connection.py -x -k "sql_auth_keeps or windows_auth_keeps or custom_pool_recycle_used"` | 3 tests in TestAuthAwarePoolRecycle | ✅ green |
| 04-01-03 | 01 | 1 | CONN-01d | unit | `uv run pytest tests/unit/test_connection.py -x -k "TokenFailureAutoDisconnect"` | TestTokenFailureAutoDisconnect (4 tests) | ✅ green |
| 04-02-01 | 02 | 1 | CONN-02a | unit | `uv run pytest tests/unit/test_server_lifecycle.py -x -k "atexit"` | TestAtexitRegistration (1 test) | ✅ green |
| 04-02-02 | 02 | 1 | CONN-02b | unit | `uv run pytest tests/unit/test_server_lifecycle.py -x -k "sigterm"` | TestSigtermHandler (2 tests) | ✅ green |
| 04-02-03 | 02 | 1 | CONN-02c | unit | `uv run pytest tests/unit/test_connection.py -x -k "DisconnectAllBestEffort"` | TestDisconnectAllBestEffort (4 tests) | ✅ green |
| 04-02-04 | 02 | 1 | CONN-02d | unit | `uv run pytest tests/unit/test_connection.py -x -k "ClassifyDbError"` | TestClassifyDbError (5 tests) | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_connection.py` — all CONN-01a, CONN-01b, CONN-01d, CONN-02c, CONN-02d tests exist and pass
- [x] `tests/unit/test_server_lifecycle.py` — CONN-02a and CONN-02b tests exist and pass
- [x] T020 updated to expect pool_recycle=2700 for Azure AD

*All Wave 0 requirements satisfied during execution (TDD red-green flow).*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SIGTERM fires atexit in real process | CONN-02 | Requires actual process signal delivery | Start server, send SIGTERM, verify no leftover DB connections |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 15s (actual: 1.2s)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** complete

---

## Validation Audit 2026-03-10

| Metric | Count |
|--------|-------|
| Requirements audited | 7 |
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |
| Total automated tests | 26 (across 2 test files) |
| Manual-only items | 1 (SIGTERM real-process test) |
