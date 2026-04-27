---
phase: 13
slug: test-infrastructure-coverage
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-27
---

# Phase 13 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.x (with pytest-asyncio, pytest-cov) |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` + `[tool.coverage.report]` |
| **Quick run command** | `uv run pytest tests/unit/ -x --no-header -q` |
| **Full suite command** | `uv run pytest --cov=src` |
| **Estimated runtime** | ~40 seconds (full suite, current baseline) |

---

## Sampling Rate

- **After every task commit:** Run the quick command against the modified test file (`uv run pytest tests/unit/test_X.py -x`).
- **After every plan wave:** Run `uv run pytest --cov=src`.
- **Before `/gsd-verify-work`:** Full suite must pass AND coverage ≥ 85%.
- **Max feedback latency:** ~40 seconds.

---

## Per-Task Verification Map

*The planner will populate this table with one row per task. Because Phase 13 is itself test infrastructure, "Test Type" is meta — the deliverable IS tests/fixtures. Each migration task's automated command is a `pytest` invocation against the modified file asserting the three dialect-suffixed node IDs (`[mssql]`, `[databricks]`, `[generic]`) are collected and pass.*

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| {N}-01-01 | 01 | 1 | TEST-02 | — | N/A (test infrastructure) | infra | `uv run pytest --collect-only tests/unit/test_column_stats.py -q \| grep -E '\\[(mssql\|databricks\|generic)\\]' \| wc -l` | planner fills | ⬜ pending |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] `tests/conftest.py` — add `ALL_DIALECTS`, `DialectTestContext`, `dialect`, `dialect_inspector` fixtures (shared infrastructure; every migrated test depends on these).
- [ ] `tests/fixtures/sqlite_schema.py` — Python-driven SQLite schema builder used by `dialect_inspector`.
- [ ] `pyproject.toml` — register the `dialects(*names)` marker in `[tool.pytest.ini_options].markers`.

All three are prerequisites for migration tasks and should land in Wave 1 (not Wave 0 in the GSD sense — pytest is already installed and configured). "Wave 0" here means: the fixture + marker must exist before any test-file migration runs.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Node-ID failure attribution ergonomics | TEST-02 (D-01) | Ergonomic claim — "when a shared-behavior test fails under databricks, the failure clearly names `[databricks]`" — is verifiable only by reading pytest output. | Introduce an intentional failure in a parameterized test, run `uv run pytest`, confirm the failing node ID includes `[databricks]` (or whichever dialect was targeted). Revert the failure. |

*Automated coverage floor check (`fail_under=85`) is enforced by the pytest-cov plugin itself — no manual verification needed.*

---

## Validation Sign-Off

- [ ] All migration tasks have `<automated>` verify commands producing the three dialect-suffixed node IDs.
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify.
- [ ] Wave 1 fixture task precedes all migration tasks (`depends_on`).
- [ ] No watch-mode flags.
- [ ] Feedback latency < 60s.
- [ ] Coverage floor task runs LAST (after all migrations pass) to avoid transient drops.
- [ ] `nyquist_compliant: true` set in frontmatter after planner populates the per-task table.

**Approval:** pending
