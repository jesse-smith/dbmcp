# Quickstart: Hardening & Cleanup Pass

How to execute, validate, and gate this phase. All Python tooling runs through `uv run`.

## Prerequisites

- On branch `012-hardening-cleanup`.
- `.venv` active (Python 3.13.1 via `uv`).
- Live validation: `dbmcp-test` MCP server reachable (StemSoftClinicTest + Databricks
  warehouse). **Reconnect `dbmcp-test` after merging any `src/` change mid-session** — the MCP
  server runs session-start code, so probes otherwise show pre-merge behavior.

## The gates (run before every commit)

```bash
uv run pytest tests/                              # full suite — must stay green
uv run pytest --cov=src --cov-report=term-missing # coverage — must stay ≥85% (SC-003)
uv run ruff check src/                            # lint — src/ only (CI parity), zero warnings
uv run python scripts/check_complexity.py         # complexity ≤15 (NOT bare complexipy) (SC-004)
```

A fix is not "done" until all four pass. A touched function that would cross complexity 15 is
refactored under the gate, never bypassed (Edge Cases / SC-004).

## Execution order

Known fixes first (highest confidence), then sweeps. Each numbered item = one logical commit,
red-green-refactor where code changes (FR-018).

### 1. TD-02 — URL-mode probe `ca_bundle` (operator-facing, do first)
- Forward `ca_bundle` from `_kwargs_from_url(...)` into the `_require_databricks_catalog(...)`
  call in `connect_with_url` (`src/db/connection.py:371-378`), mirroring the config path.
- Test: assert the probe engine receives `ca_bundle` when the URL carries `?ca_bundle=`.
- Live: **deferred** to corp-MITM UAT (FR-017) — the only sanctioned deferral.

### 2. TD-01 — regression tests (test-only)
- Add to `tests/unit/test_connect_with_config_databricks.py` (reuse `_make_engine_spy`):
  env-var substitution of `catalog`/`schema_name`; `SQLAlchemyError`→`ConnectionError` wrap
  with host in message.
- Sanity: each test would fail if its target production line were deleted.

### 3. TD-03 robustness — WR-01, WR-02 (`column_stats.py`)
- WR-01: narrow `_try_describe_extended_stats` except to `SQLAlchemyError`; confirm
  "DESCRIBE EXTENDED unsupported" still degrades to Tier-2 (test a propagating infra error).
- WR-02: drop/repair the misleading `row[1] if row else 0` guards in `get_basic_stats` /
  `get_numeric_stats` / siblings.

### 4. TD-03 consistency — IN-01, IN-02/03/04
- IN-01: fail-fast on the `list_tables` row shape (`_sql.py:178`).
- IN-02/03/04: **verify** the shared `_check_table_exists`/`_is_cross_catalog` already removes
  the duplication (it does — D-04); unify any residual not-found message divergence only if
  local. Record as `verified`/`fixed` in the ledger.

### 5. TD-03 behavioral — WR-05 Option B (the one perf change)
- Make `get_column_data_type` return a `TypeEngine` on the cross-catalog branch
  (`NullType()` fallback for unknown type tokens) so the DESCRIBE EXTENDED fast path fires
  cross-catalog. Update docstrings to match the now-true behavior.
- Test: cross-catalog fast path fires (isinstance gate True); result keys/shape unchanged.
- **Live (SC-008)**: `get_column_info` on a cross-catalog Databricks table returns the same
  response contract via precomputed stats that it previously returned via Tier-2 — capture
  before/after for one numeric + one string column.

### 6. TD-03 closure
- Strike TD-01/02/03 from `specs/TECH-DEBT.md` per its convention (FR-009/SC-001).

### 7. `src/` sweep (US2)
- Open `specs/012-hardening-cleanup/findings.md` with the module checklist
  (`find src -name '*.py'`).
- Review every module; record `SRC-NN` findings; disposition each (`fixed`/`verified`/`logged`)
  per the triage bar. Fix correctness bugs always; fix simplifications only when local to
  TD-touched code; log the rest with provenance.

### 8. `tests/` sweep (US3) — last
- Review `tests/` for redundancy, shallow coverage, intent-vs-implementation drift; record
  `TST-NN` findings. Consolidate redundant tests without dropping coverage <85%. Refactor
  implementation-coupled tests to intent. Treat hard-to-write tests as design signals (fix if
  in scope, else log). Record before/after counts (SC-007).

## Live validation cheatsheet (dbmcp-test)

| Check | Tool call | Expectation |
|-------|-----------|-------------|
| SC-008 fast path fires | `get_column_info` on a cross-catalog Databricks table | Same keys/shape as Tier-2; sourced from DESCRIBE EXTENDED |
| MSSQL regression | analysis tools against StemSoftClinicTest | Unchanged behavior |
| Contract stability (FR-014) | each of the 9 tools, before vs after | Identical response keys/shape |

## Definition of done (maps to Success Criteria)

- [ ] TD-01/02/03 struck from TECH-DEBT.md, fixes landed + tested (SC-001)
- [ ] `findings.md`: 100% modules reviewed, 100% findings dispositioned (SC-002)
- [ ] Suite green, coverage ≥85% (SC-003)
- [ ] Every touched function ≤15 complexity (SC-004)
- [ ] No tool contract changed without documented rationale (SC-005)
- [ ] Every reachable fix live-validated; only TD-02 corp-MITM probe deferred (SC-006)
- [ ] WR-05 fast path confirmed firing cross-catalog, result-preserving, live (SC-008)
- [ ] `tests/` measurably leaner/clearer where drift found, no net coverage loss (SC-007)
