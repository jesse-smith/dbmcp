---
phase: 15
slug: unified-identifier-resolver-cross-dialect
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-28
audited: 2026-05-28
---

# Phase 15 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 9.0.3 + pytest-asyncio (asyncio_mode="auto") + pytest-cov |
| **Config file** | pyproject.toml `[tool.pytest.ini_options]` (testpaths=["tests"]) |
| **Quick run command** | `uv run pytest tests/unit/test_identifiers.py -x -q` (~1s) |
| **Full suite command** | `uv run pytest tests/ --cov=src` (verify ≥85% manually; floor not enforced via addopts) |
| **Measured runtime** | Full suite ~55s (1012 passed, 78 skipped, 2026-05-28); single unit file ~1s |

> Note: `tests/integration/test_azure_ad_auth.py::test_connect_without_credentials` fails in this environment due to a missing `azure-identity-broker` package (brokered auth) — PRE-EXISTING and unrelated to Phase 15. The phase gate evaluates the non-Azure suite.

---

## Sampling Rate

- **After every task commit:** Run that task's `<automated>` command (per-file unit run, ~1s).
- **After every plan wave:** Run `uv run pytest tests/ -q` (~55s) — catches cross-file regressions before the next wave starts.
- **Before `/gsd:verify-work`:** Full suite green (Phase-15 scope) + manual `--cov=src` ≥85%.
- **Max feedback latency:** ~55s (full suite); ~1s (per-task unit run).

---

## Per-Task Verification Map

| Task ID | Plan | Wave | Requirement | Threat Ref | Secure Behavior | Test Type | Automated Command | File Exists | Status |
|---------|------|------|-------------|------------|-----------------|-----------|-------------------|-------------|--------|
| 15-01-T1 | 01 | 1 | IDENT-03, IDENT-07 | T-15-01 | constant property values, no user input | unit | `uv run pytest tests/unit/test_mssql_dialect.py tests/unit/test_databricks_dialect.py tests/unit/test_generic_dialect.py -k "default_schema or max_identifier_depth"` (RED: expect fail) | ✅ extend | ✅ green |
| 15-01-T2 | 01 | 1 | IDENT-03, IDENT-07 | T-15-01 | property values correct per dialect | unit | `uv run pytest tests/unit/test_mssql_dialect.py tests/unit/test_databricks_dialect.py tests/unit/test_generic_dialect.py tests/unit/test_dialect_protocol.py -k "default_schema or max_identifier_depth or protocol" -x` | ✅ extend | ✅ green |
| 15-02-T1 | 02 | 1 | IDENT-07 | T-15-02, T-15-03 | no synthetic dbo; quote_identifier unchanged | unit + grep | `grep -nE 'schema_name: str = "dbo"' src/db/metadata.py src/db/query.py \| grep -c . \| grep -q '^0$' && uv run pytest tests/unit/test_metadata.py tests/unit/test_query.py -x -q` | ✅ extend | ✅ green |
| 15-02-T2 | 02 | 1 | IDENT-07 | T-15-02 | None default → inspector default schema | unit | `uv run pytest tests/unit/test_query.py tests/unit/test_metadata.py -x -q` | ✅ extend | ✅ green |
| 15-03-RED | 03 | 2 | IDENT-03, IDENT-04, IDENT-07 | T-15-04, T-15-05 | failing resolver matrix exists | unit | `uv run pytest tests/unit/test_identifiers.py` (expect ImportError/fail) | ❌ Wave 0 (NEW) | ✅ green |
| 15-03-GREEN | 03 | 2 | IDENT-03, IDENT-04, IDENT-07 | T-15-04, T-15-05, T-15-06 | depth via len(parts); ParseError→ValueError; no sanitize | unit | `uv run pytest tests/unit/test_identifiers.py -x` | ❌ Wave 0 (NEW) | ✅ green |
| 15-04-T1 | 04 | 3 | IDENT-03, IDENT-04, IDENT-07 | T-15-07, T-15-09 | resolver in _sync_work; dbo swept | unit + grep | `uv run pytest tests/unit/test_async_tools.py -x -q && grep -nE 'schema_name: str = "dbo"' src/mcp_server/schema_tools.py \| grep -c . \| grep -q '^0$'` | ⚠ extend | ✅ green |
| 15-04-T2 | 04 | 3 | IDENT-03, IDENT-04 | T-15-08, T-15-09 | shared catalog gate; backward-incompat tested | unit | `uv run pytest tests/unit/test_async_tools.py -x -q` | ⚠ extend | ✅ green |
| 15-05-T1 | 05 | 4 | IDENT-05 | T-15-10 | 3-part Databricks SQL via quote_identifier | unit | `uv run pytest tests/unit/test_query.py -x -q` | ⚠ extend | ✅ green |
| 15-05-T2 | 05 | 4 | IDENT-05, IDENT-06 | T-15-11, T-15-12, T-15-13 | catalog param + resolver routing; dbo swept | unit + grep | `uv run pytest tests/unit/test_async_tools.py -x -q && grep -nE 'schema_name: str = "dbo"' src/mcp_server/query_tools.py \| grep -c . \| grep -q '^0$'` | ⚠ extend | ✅ green |
| 15-05-T3 | 05 | 4 | IDENT-05, IDENT-06 | T-15-12, T-15-13 | catalog-gate + conflict + happy-path for 2 tools | unit | `uv run pytest tests/unit/test_async_tools.py -k "catalog or conflict or resolv" -x -q` | ⚠ extend | ✅ green |
| 15-06-T1 | 06 | 5 | IDENT-03, IDENT-04, IDENT-07 | T-15-14, T-15-15, T-15-16 | find_pk/fk dbo swept + resolver routing + catalog | unit + grep | `uv run pytest tests/unit/test_async_tools.py -x -q && grep -nE 'schema_name: str = "dbo"' src/mcp_server/analysis_tools.py \| grep -c . \| grep -q '^0$'` | ⚠ extend | ✅ green |
| 15-06-T2 | 06 | 5 | IDENT-03, IDENT-04 | T-15-15, T-15-16 | D-12 boundary matrix spans all 7 tools | unit | `uv run pytest tests/unit/test_async_tools.py -k "catalog or conflict or resolv" -x -q` | ⚠ extend | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

New test file (created RED-first in Plan 03, Wave 2):
- [x] `tests/unit/test_identifiers.py` — exhaustive parametrized matrix per D-12: `TestDepthParsing`, `TestConflictDetection`, `TestCatalogGate` (incl. direct `_assert_catalog_allowed`), `TestDefaultSchema`, `TestMalformedInput`. Covers IDENT-03 + IDENT-04 + the shared catalog gate. Uses real dialect instances (`MssqlDialect()`, `DatabricksDialect()`, `GenericDialect()`). **29 tests passing.**

Extensions to existing test files (no new framework, no new file):
- [x] `tests/unit/test_mssql_dialect.py` / `test_databricks_dialect.py` / `test_generic_dialect.py` — add `test_default_schema_*` + `test_max_identifier_depth_*` (Plan 01).
- [x] `tests/unit/test_query.py` + `tests/unit/test_metadata.py` — None-default behavior + signature assertion (Plan 02). Includes real-dialect `schema_name=None` regression test (CR-01/SC3 fix, `test_query.py:1095`).
- [x] `tests/unit/test_async_tools.py` — D-12 boundary matrix (catalog-gate + conflict + happy-path) spans all 7 tools (`TestCatalogGateBoundary` now covers list_schemas + list_tables after the T-15-08/T-15-12 quick-task fix). The `_TOOL_PARAMS` list enumerates all 7 tools for the safety-net tests.

No framework install needed (pytest 9.0.3 present).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Status | Test Instructions |
|----------|-------------|------------|--------|-------------------|
| Databricks `bmtct.ml_infections_ref.mv_fever_episodes` end-to-end without `USE CATALOG` | IDENT-05 (SC3) | Requires live Databricks connection (`dbmcp-test` → `databricks-test`, catalog `bmtct`) | ✅ VERIFIED 2026-05-28 | Connect to Databricks; call get_sample_data with the 3-part table_name; confirm rows return without a catalog workaround. |

*All resolver/routing/gate behaviors have automated unit coverage via the resolver matrix + the 7-tool boundary matrix. The live-Databricks SC3 item was executed against `dbmcp-test` (see Live Verification below).*

### Live Verification 2026-05-28

Executed against the `databricks-test` connection (catalog `bmtct`) via the `dbmcp-test` MCP server:

| Probe | Input | Result |
|-------|-------|--------|
| SC3 3-part dotted | `get_sample_data(table_name="bmtct.ml_infections_ref.mv_fever_episodes")` | ✅ 3 rows returned, no `USE CATALOG` / no `catalog=` param |
| IDENT-05 explicit catalog | `get_sample_data(table_name="ml_infections_ref.mv_fever_episodes", catalog="bmtct")` | ✅ same rows returned |

Both paths return real data end-to-end, confirming the resolver + Databricks 3-part `quote_identifier` SQL building works against a live cluster.

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify (every task has an automated command; Plan 02 Task 1 now runs metadata+query unit tests, not grep-only)
- [x] Wave 0 covers all MISSING references (`tests/unit/test_identifiers.py` created RED-first in Plan 03)
- [x] No watch-mode flags
- [x] Feedback latency measured (~1s per-task, ~55s per-wave full suite)
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** approved 2026-05-28

---

## Validation Audit 2026-05-28

Post-execution audit of Nyquist coverage against the executed codebase (State A). All planned tests exist and pass; the two blockers surfaced in `15-VERIFICATION.md` were closed by follow-up quick tasks before this audit:
- **CR-01 (SC3 None-schema corrupt SQL)** → fixed in `b303326`/`c4cd61f`; covered by `test_query.py:1095` real-dialect regression test.
- **T-15-08 / T-15-12 (list_schemas/list_tables catalog gate)** → fixed in `c9252df`/`ed1c0e6`; covered by `TestCatalogGateBoundary` (now 6 tools + 7th param-list entry).

| Metric | Count |
|--------|-------|
| Gaps found | 0 |
| Resolved | 0 |
| Escalated | 0 |

Evidence: `test_identifiers.py` 29 passed; dialect-property + protocol 31 passed; `test_async_tools.py` boundary matrix 13 passed; full suite **1069 passed, 78 skipped, 91% coverage** (≥85% floor). All IDENT-03/04/05/06/07 requirements have green automated coverage. Only live-Databricks SC3 end-to-end remains Manual-Only (requires a live connection).
