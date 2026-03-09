---
phase: 4
slug: connection-management
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-03-09
---

# Phase 4 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| **Config file** | pyproject.toml [tool.pytest.ini_options] |
| **Quick run command** | `uv run pytest tests/unit/test_connection.py -x` |
| **Full suite command** | `uv run pytest tests/ -m "not integration and not performance" -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_connection.py -x`
- **After every plan wave:** Run `uv run pytest tests/ -m "not integration and not performance" -x`
- **Before `/gsd:verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|-----------|-------------------|-------------|--------|
| 04-01-01 | 01 | 1 | CONN-01a | unit | `uv run pytest tests/unit/test_connection.py -x -k "pool_recycle and azure"` | Partially (T020 needs update) | ⬜ pending |
| 04-01-02 | 01 | 1 | CONN-01b | unit | `uv run pytest tests/unit/test_connection.py -x -k "pool_recycle and not azure"` | ❌ W0 | ⬜ pending |
| 04-01-03 | 01 | 1 | CONN-01d | unit | `uv run pytest tests/unit/test_connection.py -x -k "token_failure_disconnect"` | ❌ W0 | ⬜ pending |
| 04-02-01 | 02 | 1 | CONN-02a | unit | `uv run pytest tests/unit/test_connection.py -x -k "atexit"` | ❌ W0 | ⬜ pending |
| 04-02-02 | 02 | 1 | CONN-02b | unit | `uv run pytest tests/unit/test_connection.py -x -k "sigterm"` | ❌ W0 | ⬜ pending |
| 04-02-03 | 02 | 1 | CONN-02c | unit | `uv run pytest tests/unit/test_connection.py -x -k "disconnect_all_best_effort"` | ❌ W0 | ⬜ pending |
| 04-02-04 | 02 | 1 | CONN-02d | unit | `uv run pytest tests/unit/test_connection.py -x -k "classify_error"` | ❌ W0 | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/unit/test_connection.py` — stubs for CONN-01a (update T020), CONN-01b, CONN-01d, CONN-02a, CONN-02b, CONN-02c, CONN-02d
- [ ] Update existing T019 to verify creator callable token refresh pattern

*Existing infrastructure covers framework and fixture needs.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| SIGTERM fires atexit in real process | CONN-02 | Requires actual process signal delivery | Start server, send SIGTERM, verify no leftover DB connections |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
