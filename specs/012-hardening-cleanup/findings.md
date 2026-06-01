---
phase: 012-hardening-cleanup
reviewed: 2026-06-01
src_modules_total: 34
src_modules_reviewed: 0
findings: { critical: 0, warning: 0, info: 0, total: 0 }
dispositions: { fixed: 0, verified: 0, logged: 0 }
---

# Findings Ledger — 012 Hardening & Cleanup Pass

Review ledger for the two discovery sweeps (US2 `src/`, US3 `tests/`) plus the verification
record for the known TD-01/02/03 work. Follows the Phase-15.1 `15.1-REVIEW.md` precedent.

## Baseline (T002 — measured 2026-06-01, HEAD `a917f79`)

| Metric | Value |
|--------|-------|
| Tests passing | 1138 |
| Tests skipped | 146 |
| Coverage (total) | 91.33% |
| Coverage floor | 85.0% (SC-003) |

> Note: tasks.md anticipated 1119 passing (the v2.1-close figure in project memory); the suite
> has grown to 1138 since. 91.33% is well above the 85% floor — deltas at close are measured
> against these numbers (SC-003/SC-007).

## Live validation reachability (T003 — confirmed 2026-06-01)

| Environment | Connection | Status |
|-------------|-----------|--------|
| MSSQL | `stemsoftclinictest` (StemSoftClinicTest) | ✅ reachable (dialect mssql, 2 schemas) |
| Databricks | `databricks-test` (catalog `bmtct`) | ✅ reachable (dialect databricks, 22 schemas) |

Cross-catalog SC-008 target candidates: `samples.*` (e.g. `samples.tpch`, `samples.nyctaxi`)
— distinct from the default `bmtct` catalog. No `kinit`/Cloudflare re-auth needed this session.
**Reconnect `dbmcp-test` after merging any `src/` change before live-probing** (memory: MCP
server runs session-start code).

## Live validation evidence log

- **MSSQL regression (FR-014/SC-006, default path)** — 2026-06-01, StemSoftClinicTest via
  `dbmcp-test`. `get_column_info` on `dbo.PerformedActs` (21 cols) returned the full expected
  contract: numeric/datetime/string/BIT stats with correct shapes, `data_type` as uppercase
  `str(TypeEngine)` (e.g. `BIGINT`, `DATETIME`, `NVARCHAR(255) COLLATE ...`), null %s, sample
  values. The default Inspector path (untouched by this phase) is stable; WR-02's row-guard
  removal did not break the aggregate reads. ✅
- **SC-008 cross-catalog fast path (✅ CONFIRMED after server restart)** — 2026-06-01,
  `samples.tpch.customer` (cross-catalog vs default `bmtct`) via `dbmcp-test`. After the MCP
  server restart reimported `src/`, the diagnostic flipped exactly as predicted:

  | Field | Before (Tier-2, pre-edit) | After (fast path fired) |
  |-------|---------------------------|-------------------------|
  | `c_custkey` data_type | `bigint` | **`BIGINT`** (str(TypeEngine)) |
  | `c_name` data_type | `string` | **`VARCHAR`** |
  | `c_acctbal` data_type | `decimal(18,2)` | **`NUMERIC(18, 2)`** |
  | `total_rows` | 750000 (computed) | **0** (fast path doesn't compute) |
  | numeric mean/std | full values | **null** (DESCRIBE EXTENDED omits them) |

  Result keys/shape preserved; values now sourced from precomputed DESCRIBE EXTENDED stats.
  Expected fast-path nuance: `c_custkey` distinct_count 750000→725800 (DESCRIBE EXTENDED's
  `distinct_count` is an approximate/HLL stat vs Tier-2's exact `COUNT(DISTINCT)`) — the
  *contract* is unchanged, the source differs. **SC-008 met.**
- **SC-006 WR-01 degrade path (unit-covered; live "unsupported" branch not forceable)** —
  2026-06-01. The WR-01 narrowing is unit-proven (ProgrammingError→None degrade;
  PermissionError→propagate). Live, the specific "DESCRIBE EXTENDED unsupported →
  SQLAlchemyError → graceful Tier-2" scenario could NOT be forced: modern UC broadly supports
  DESCRIBE EXTENDED (even `bmtct.playground.caboodle_tests`, default catalog, fast-pathed with
  computed stats). The live assurance is regression-absence: MSSQL-default, Databricks-default,
  and cross-catalog probes all returned clean responses with no swallowed or propagated errors
  after the narrowing. The "unsupported" branch stays unit-only by warehouse capability, not by
  deferral.

## Disposition legend

- **fixed** — correctness bug (any location), or a simplification local to TD-01/02/03 code
  being touched. Cites commit SHA + test name.
- **verified** — reviewed, found already-correct / already-refactored; no change needed. Cites
  a note explaining why.
- **logged** — larger/standalone refactor or out-of-scope cleanup. Cites the
  `TECH-DEBT.md`/`BACKLOG.md` ID it was moved to.

---

## src/ module coverage checklist

(SC-002 evidence — unchecked = unreviewed. Reviewed in the US2 sweep, T017-T020.)

- [ ] src/__init__.py
- [ ] src/analysis/__init__.py
- [ ] src/analysis/_sql.py
- [ ] src/analysis/column_stats.py
- [ ] src/analysis/fk_candidates.py
- [ ] src/analysis/pk_discovery.py
- [ ] src/config.py
- [ ] src/db/__init__.py
- [ ] src/db/azure_auth.py
- [ ] src/db/connection.py
- [ ] src/db/dialects/__init__.py
- [ ] src/db/dialects/azure_auth.py
- [ ] src/db/dialects/databricks.py
- [ ] src/db/dialects/generic.py
- [ ] src/db/dialects/mssql.py
- [ ] src/db/dialects/protocol.py
- [ ] src/db/dialects/registry.py
- [ ] src/db/identifiers.py
- [ ] src/db/metadata.py
- [ ] src/db/query.py
- [ ] src/db/validation.py
- [ ] src/logging_config.py
- [ ] src/mcp_server/__init__.py
- [ ] src/mcp_server/_errors.py
- [ ] src/mcp_server/analysis_tools.py
- [ ] src/mcp_server/query_tools.py
- [ ] src/mcp_server/schema_tools.py
- [ ] src/mcp_server/server.py
- [ ] src/models/__init__.py
- [ ] src/models/analysis.py
- [ ] src/models/relationship.py
- [ ] src/models/schema.py
- [ ] src/serialization.py
- [ ] src/type_registry.py

---

## Known tech-debt verification record (US1 — TD-01/02/03)

(Not discovery findings; tracked here for the SC-001 audit trail. Populated as US1 lands.)

| Item | Resolution | Commit / Test | Notes |
|------|-----------|---------------|-------|
| TD-02 (ca_bundle) | **fixed** | commit `76d48c0`, test `test_connect_with_url_databricks_probe_inherits_ca_bundle` | URL-mode probe now forwards `ca_bundle` into `_require_databricks_catalog` (connection.py:369-383), mirroring the config path. D-02: `_tls_trusted_ca_file` is derived from `ca_bundle` inside `create_engine`, so forwarding `ca_bundle` alone is sufficient — FR-003's mention of threading `_tls_trusted_ca_file` separately was an over-spec, corrected here. Live corp-MITM probe **deferred** to UAT (FR-017, sole sanctioned deferral). RED→GREEN verified. |
| TD-01 (regression tests) | **verified** | `test_env_var_substitution_for_catalog_and_schema`, `test_sqlalchemy_error_wrapped_as_connection_error` (both in `tests/unit/test_connect_with_config_databricks.py`, commit `48a2c5b`, tag v2.1) | FR-001/002 already satisfied — tests predate this branch. Mutation-checked 2026-06-01: each FAILS when its target line (`connection.py:580` catalog resolve / `:634` SQLAlchemyError→ConnectionError wrap) is removed, PASSES when restored. No production change; no new test needed (re-verify payoff, cf. D-04). |
| WR-01 | **fixed** | commit `280a874`, tests `test_fast_path_sqlalchemy_error_degrades_to_none`, `test_fast_path_non_sqlalchemy_error_propagates` | Narrowed `_try_describe_extended_stats` (column_stats.py:436) from bare `except Exception` to `except SQLAlchemyError`. `ProgrammingError` (unsupported syntax) is a `SQLAlchemyError` subclass → still degrades to Tier-2; non-SQLAlchemy errors (auth/network/injection) now propagate. RED→GREEN verified. Live Databricks degrade-path check: see SC-006 note below. |
| WR-02 | **fixed** | commit `280a874`, test `test_basic_stats_trusts_full_width_aggregate_row` | Dropped dead/misleading `row[N] if row else 0` guards in get_basic_stats/get_numeric_stats/get_string_stats and the dead `not row` disjunct in get_datetime_stats (kept its load-bearing `row[0] is None` all-NULL check). No-GROUP-BY aggregate always returns one full-width row (D-06). This is a refactor: the removed branches were unreachable, so the "red" is nominal — the existing normal/all-null/zero-row tests (TestBasicStats/Numeric/String/DateTime) are the regression net and stay green. |
| IN-01 | **fixed** | commit `21d738d`, test `test_unexpected_row_shape_fails_fast` | `list_tables` (_sql.py:178) now fails fast (`ValueError`) on a SHOW TABLES row of width < 2 instead of silently returning `row[0]` (a database name) as a table name. Sibling `reflect_columns` `len(row) > 1` idiom (_sql.py:110) reviewed → **verified** (genuinely defensive: DESCRIBE TABLE rows can be short at section markers; defaults `data_type` to `""` rather than returning wrong data — distinct from the list_tables case). RED→GREEN verified. |
| IN-02/03/04 | **verified** | no change — see note | D-04 confirmed against current `main`: `_is_cross_catalog` (analysis_tools.py:27) + `_check_table_exists` (line 41) are single shared module-level helpers; all three tools call them (`get_column_info` :206, `find_pk_candidates` :314, `find_fk_candidates` :441); the lazy `MetadataService` import is hoisted to one site (line 49); no inline duplication in PKDiscovery/FKCandidateSearch/ColumnStatsCollector. **IN-04 residue → logged (TD-04)**: the two not-found templates (`'schema.table' not found` cross-catalog vs `'table' not found in schema 'schema'` default) differ, but unifying is NOT a one-line local change (both pinned by tests in `test_analysis_tools_helpers.py`, touches two production branches, nudges an observable `error_message` per FR-014, and the divergence is contextually justified). Logged to TECH-DEBT.md as TD-04 at T016. |
| WR-05 (Option B) | **fixed + live SC-008 confirmed** | commit `1dedd71`, tests `TestCrossCatalogTypeEngine` (7) | Code merged + 7 RED→GREEN unit tests (gate-firing, NullType fallback, decimal precision, converged `data_type`). Live SC-008 **confirmed** after server restart: `samples.tpch.customer` cross-catalog now returns uppercase `str(TypeEngine)` `data_type` (`BIGINT`/`VARCHAR`/`NUMERIC(18, 2)`) + `total_rows=0` + null mean/std — fast path fired via precomputed DESCRIBE EXTENDED stats, keys/shape preserved. See the live evidence log above for the before/after table. |

---

## src/ findings (SRC-NN)

_(none yet — populated during the US2 sweep, T017-T021)_

---

## tests/ findings (TST-NN)

_(none yet — populated during the US3 sweep, T022-T024)_
