---
phase: 13
slug: test-infrastructure-coverage
status: active
nyquist_compliant: true
wave_0_complete: true
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
| 13-01-01 | 01 | 1 | TEST-02 | — | N/A (test infrastructure) | infra | `uv run pytest tests/unit/test_column_stats.py tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py tests/unit/test_metadata.py -q` (exercises conftest fixtures) | ✅ | ✅ green |
| 13-02-01 | 02 | 2 | TEST-02 | — | N/A (test infrastructure) | infra | `uv run pytest --collect-only tests/unit/test_column_stats.py -q \| grep -cE '\\[(mssql\|databricks\|generic)\\]'` → 21 | ✅ | ✅ green |
| 13-02-02 | 02 | 2 | TEST-02 | — | N/A | infra | `uv run pytest tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py -q` | ✅ | ✅ green |
| 13-03-01 | 03 | 2 | TEST-02 | — | N/A | infra | `uv run pytest tests/unit/test_metadata.py -q -k SharedMetadataBehavior` | ✅ | ✅ green |
| 13-04-01 | 04 | 3 | TEST-03 | — | N/A | gate | `grep '^fail_under = 85' pyproject.toml` + `uv run pytest --cov=src` (enforced by pytest-cov) | ✅ | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/conftest.py` — `ALL_DIALECTS`, `DialectTestContext`, `dialect`, `dialect_inspector` fixtures (Plan 13-01).
- [x] `tests/fixtures/sqlite_schema.py` — Python-driven SQLite schema builder (Plan 13-01).
- [x] `pyproject.toml` — `dialects(*names)` marker registered in `[tool.pytest.ini_options].markers` (Plan 13-01).

All three are prerequisites for migration tasks and should land in Wave 1 (not Wave 0 in the GSD sense — pytest is already installed and configured). "Wave 0" here means: the fixture + marker must exist before any test-file migration runs.

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Node-ID failure attribution ergonomics | TEST-02 (D-01) | Ergonomic claim — "when a shared-behavior test fails under databricks, the failure clearly names `[databricks]`" — is verifiable only by reading pytest output. | Introduce an intentional failure in a parameterized test, run `uv run pytest`, confirm the failing node ID includes `[databricks]` (or whichever dialect was targeted). Revert the failure. |

*Automated coverage floor check (`fail_under=85`) is enforced by the pytest-cov plugin itself — no manual verification needed.*

---

## Validation Sign-Off

- [x] All migration tasks have `<automated>` verify commands producing the three dialect-suffixed node IDs.
- [x] Sampling continuity: no 3 consecutive tasks without automated verify.
- [x] Wave 1 fixture task precedes all migration tasks (`depends_on`).
- [x] No watch-mode flags.
- [x] Feedback latency < 60s.
- [x] Coverage floor task runs LAST (after all migrations pass) to avoid transient drops.
- [x] `nyquist_compliant: true` set in frontmatter.

**Approval:** approved 2026-05-06

---

## Validation Audit 2026-05-06

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 5 per-task rows populated (TEST-02 × 4 + TEST-03 × 1), all ✅ green |
| Escalated | 0 |

Verified via `uv run pytest tests/unit/test_column_stats.py tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py tests/unit/test_metadata.py -q` (202 passed, 37 skipped) and `uv run pytest --collect-only tests/unit/test_column_stats.py -q | grep -cE '\[(mssql|databricks|generic)\]'` → 21. `fail_under = 85` confirmed in pyproject.toml.
