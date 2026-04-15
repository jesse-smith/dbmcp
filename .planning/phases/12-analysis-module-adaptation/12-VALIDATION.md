---
phase: 12
slug: analysis-module-adaptation
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-04-15
---

# Phase 12 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.x |
| **Config file** | pyproject.toml [tool.pytest] |
| **Quick run command** | `uv run pytest tests/unit/test_column_stats.py tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py tests/unit/test_analysis_models.py -x -q` |
| **Full suite command** | `uv run pytest tests/ -x` |
| **Estimated runtime** | ~15 seconds |

---

## Sampling Rate

- **After every task commit:** Run `uv run pytest tests/unit/test_column_stats.py tests/unit/test_pk_discovery.py tests/unit/test_fk_candidates.py tests/unit/test_analysis_models.py -x -q`
- **After every plan wave:** Run `uv run pytest tests/ -x`
- **Before `/gsd-verify-work`:** Full suite must be green
- **Max feedback latency:** 15 seconds

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 12-01-01 | 01 | 1 | ANLYS-01 | T-12-01 | All identifiers quoted via dialect.quote_identifier() | unit | `uv run pytest tests/unit/test_column_stats.py -x` | Exists (needs dialect params) | ⬜ pending |
| 12-01-02 | 01 | 1 | ANLYS-02 | — | N/A | unit | `uv run pytest tests/unit/test_column_stats.py -k databricks -x` | ❌ W0 | ⬜ pending |
| 12-02-01 | 02 | 1 | ANLYS-03 | T-12-01 | All identifiers quoted via dialect.quote_identifier() | unit | `uv run pytest tests/unit/test_pk_discovery.py -x` | Exists (needs dialect params) | ⬜ pending |
| 12-02-02 | 02 | 1 | ANLYS-04 | T-12-01 | All identifiers quoted; index gated on supports_indexes | unit | `uv run pytest tests/unit/test_fk_candidates.py -x` | Exists (needs dialect params) | ⬜ pending |
| 12-XX-XX | — | — | ANLYS-05 | — | N/A | N/A | N/A | Already complete (Phase 11) | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Dialect-parameterized test fixtures (mock DialectStrategy with different sqlglot_dialect/supports_indexes values)
- [ ] Databricks DESCRIBE EXTENDED column stats mock data for fast path tests
- [ ] Updated mock setup: analysis class constructors will take dialect/inspector params
- [ ] PKCandidate model may need `constraint_enforced` field for Databricks informational constraint annotation

*Existing infrastructure covers most phase requirements — Wave 0 adds dialect parameterization and Databricks mocks.*

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Databricks DESCRIBE EXTENDED live output format | ANLYS-02 | Requires live Databricks cluster | Connect to Databricks, run DESCRIBE EXTENDED on analyzed table, verify stats keys match parser expectations |

---

## Validation Sign-Off

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 15s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
