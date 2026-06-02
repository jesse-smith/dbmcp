---
phase: 012-hardening-cleanup
reviewed: 2026-06-01
src_modules_total: 34
src_modules_reviewed: 34
findings: { critical: 0, warning: 16, info: 36, total: 52 }
dispositions: { fixed: 8, verified: 0, logged: 44 }
us3_test_counts: { before: "1150p/166s/91.92%", after: "1149p/166s/91.92%" }
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

- [x] src/__init__.py
- [x] src/analysis/__init__.py
- [x] src/analysis/_sql.py
- [x] src/analysis/column_stats.py
- [x] src/analysis/fk_candidates.py
- [x] src/analysis/pk_discovery.py
- [x] src/config.py
- [x] src/db/__init__.py
- [x] src/db/azure_auth.py
- [x] src/db/connection.py
- [x] src/db/dialects/__init__.py
- [x] src/db/dialects/azure_auth.py
- [x] src/db/dialects/databricks.py
- [x] src/db/dialects/generic.py
- [x] src/db/dialects/mssql.py
- [x] src/db/dialects/protocol.py
- [x] src/db/dialects/registry.py
- [x] src/db/identifiers.py
- [x] src/db/metadata.py
- [x] src/db/query.py
- [x] src/db/validation.py
- [x] src/logging_config.py
- [x] src/mcp_server/__init__.py
- [x] src/mcp_server/_errors.py
- [x] src/mcp_server/analysis_tools.py
- [x] src/mcp_server/query_tools.py
- [x] src/mcp_server/schema_tools.py
- [x] src/mcp_server/server.py
- [x] src/models/__init__.py
- [x] src/models/analysis.py
- [x] src/models/relationship.py
- [x] src/models/schema.py
- [x] src/serialization.py
- [x] src/type_registry.py

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

US2 sweep — all 34 modules reviewed (4 parallel reviewers, T017-T020). **Result: 0 critical, 0
reachable correctness bug.** Every actionable item is outside the US1-touched spots, so per the
triage bar (correctness fixed always; simplifications fixed only when *local to TD-touched code*)
all 30 are **logged** — US2 lands no `src/` change. Grouped into TD-05…TD-09 in `TECH-DEBT.md`.

> **Two reviewer claims corrected on verification** (debugging directive — don't pass uncertainty
> downstream as fact): (1) `src/metrics.py` was reported "still has the `Generator` nit" — it was
> **deleted** (commit `1fda3e7`); the nit is fully resolved, project memory is stale on this. (2)
> `CredentialFilter` was reported "unattached / dead code / false redaction" — it **IS** wired
> (`server.py:26 logger.addFilter(CredentialFilter())`). The real, narrower finding (SRC-19) is
> that it inspects `record.msg` only, not `record.args`.

| ID | Sev | Location | Finding | Disp → group |
|----|-----|----------|---------|--------------|
| SRC-01 | warning | `db/connection.py:391-408,643-652` (+MSSQL `connect()`) | Engine created then orphaned (never `dispose()`d) when `_test_connection` raises `SQLAlchemyError` before `_register_engine` stores it — leaks a pool until GC. Uncommon path (probe is `SELECT 1` post-`create_engine`). | logged → TD-07 |
| SRC-02 | warning | `db/connection.py:231-239` (`connect()`) | Builds `Connection(...)` without `dialect_name`, relying on model default `"mssql"`, though `connect()` accepts a `dialect` param. Latent mislabel if a non-MSSQL dialect is ever routed through `connect()` (only MSSQL reaches it today). `_register_engine` does it right. | logged → TD-07 |
| SRC-03 | warning | `mcp_server/schema_tools.py:358-399` (`list_tables` multi-schema) | **Verified real.** `schemas_to_query = schema_filter or [None]`; each schema queried with the *same* `limit`/`offset`, concatenated, then `all_tables[:limit]`. Multi-schema + `offset>0` ⇒ offset applied per-schema (wrong global skip); sort honored only within each schema; `has_more` can mislead after truncation. Single-schema/`None` path correct. Contract-sensitive (FR-014). | logged → TD-08 |
| SRC-04 | warning | `mcp_server/schema_tools.py:58-67,388` (`_build_table_entry` detailed) | N+1: detailed-mode listing calls `get_columns` (→ 3 reflection round-trips) per table inside the comprehension. ~300 serial reflections for 100 tables. No batch metadata path exists (Constitution V). | logged → TD-05 |
| SRC-05 | warning | `db/query.py:764-778` (`_build_count_query`) | `_get_total_row_count` wraps the original query in `SELECT COUNT(*) FROM (<orig>) AS …`; a top-level `ORDER BY` makes that invalid T-SQL → COUNT silently returns `None`, so `total_rows_available` is absent on exactly the ordered queries users run most. Best-effort by design, but the ORDER BY interaction is frequent. | logged → TD-08 |
| SRC-06 | warning | `analysis/column_stats.py:664-707` (`get_columns_info` cross-catalog) | Per-column `DESCRIBE TABLE` (via `get_column_data_type`→`_reflect_catalog_columns`, uncached) **and** a second `DESCRIBE EXTENDED` per column. ~1 + N×2 round-trips cross-catalog; the reflected column list is identical every call and should be cached on the collector (Constitution V). | logged → TD-05 |
| SRC-07 | warning | `analysis/fk_candidates.py:505-577,693` (`compute_overlap`) | Source-side `COUNT(DISTINCT)` is identical for every candidate yet recomputed once per target column (full source-table scan each time). Should be computed once before the loop; only the INTERSECT varies per target. | logged → TD-05 |
| SRC-08 | warning | `analysis/pk_discovery.py:432-453` (`_column_is_unique`) | One `COUNT(DISTINCT)/COUNT(*)` per structural-candidate column inside the loop — K full-table scans for K type-matching columns. Combinable into one multi-aggregate scan; dominant cost of PK discovery on wide tables. | logged → TD-05 |
| SRC-09 | warning | `db/metadata.py:580-595` (generic `list_tables`) | Generic path opens a fresh `engine.connect()` + `SELECT COUNT(*)` **per table** in the listing loop (MSSQL avoids this via one DMV CTE). Generic has no cheap batch row-count, but per-table connect is avoidable — reuse one connection across the loop. | logged → TD-05 |
| SRC-10 | warning | `analysis/pk_discovery.py:235-323` + `fk_candidates.py:437-476` | Rule-of-Three crossed: the `information_schema.table_constraints JOIN key_column_usage` PK/UNIQUE query against a backtick-quoted `{catalog}.information_schema` is written 3× (PK, UNIQUE, FK-constraints). A `reflect_constraints()` on `CatalogAwareReflector` would centralize the catalog-quoting + bound-param contract. | logged → TD-06 |
| SRC-11 | info | `db/dialects/{databricks,generic,mssql}.py` (modulo sample) | The MODULO sampling SQL body (`ROW_NUMBER() OVER … % CASE …`) is duplicated near-verbatim across all three dialects; deltas are only LIMIT/TOP + ORDER BY tiebreaker. Rule of Three crossed. | logged → TD-06 |
| SRC-12 | info | `db/validation.py:150-178,225-249` | `_check_execute` and `_check_stored_procedure` restate the same allowlist + `sp_executesql` policy + denial structure; differ only in AST name extraction. Policy could drift across the two copies. | logged → TD-06 |
| SRC-13 | info | `analysis/fk_candidates.py:552,570`; `pk_discovery.py:448-451` | Dead `x = row[0] if row else 0` scalar guards survive — the same class WR-02 removed in `column_stats.py`; now inconsistent across the package (a no-GROUP-BY aggregate always returns one row). | logged → TD-09 |
| SRC-14 | info | `mcp_server/{query_tools,schema_tools}.py` (5 sites) | 5 tool handlers hand-roll the `SQLAlchemyError → _classify_db_error` vs fallback split instead of reusing `_errors.format_unexpected_error`; only the per-tool prefix (shipped contract) differs. | logged → TD-09 |
| SRC-15 | info | `config.py:32-35,48-51,217-259` | Defaults duplicated between `DefaultsConfig` field defaults and `_DEFAULTS_BOUNDS`; per-dialect `known_fields` literals restate dataclass fields 3×. Out-of-range vs absent values can resolve to *different* defaults if the two drift. | logged → TD-06 |
| SRC-16 | info | `type_registry.py:30-43,104-107` | `_handle_bool/_handle_int/_handle_float` are byte-identical pass-throughs; one shared `_handle_identity` reused for the 3 chain entries removes the triplication without touching ordering. | logged → TD-09 |
| SRC-17 | info | `logging_config.py:50` | `_migrate_legacy_log` TODO says "remove after v2.1"; v2.1 shipped 2026-05-31. Dead-code-on-a-timer still stats `_LEGACY_LOG_FILE` every `setup_logging`. | logged → TD-09 |
| SRC-18 | info | `logging_config.py:135-140` | Success branch recomputes `_compute_default_log_path(...)` (blake2b + `cwd().resolve()`) only to log the path already in `log_path`. Reuse the local. | logged → TD-09 |
| SRC-19 | info | `logging_config.py:157-179` (`CredentialFilter`) | **Filter IS wired** (server.py:26 — reviewer claim corrected). Real gap: redacts `record.msg` only, not `record.args`, so a secret passed as a `%s` arg slips through. Narrow but worth a note. | logged → TD-09 |
| SRC-20 | info | `models/relationship.py:78` | `import hashlib` is function-local with no benefit (stdlib, not optional/heavy); least-surprise wants it module-level. | logged → TD-09 |
| SRC-21 | info | `db/azure_auth.py:1-9` | Backward-compat shim re-exporting from `db/dialects/azure_auth.py`; only importer is `tests/unit/test_azure_auth.py`. Not a logic dup (9-line re-export) — candidate deletion + repoint the one test. | logged → TD-09 |
| SRC-22 | info | `db/dialects/protocol.py` | `DatabricksDialect.list_catalogs` is consumed by `connection.py` but not declared on the `DialectStrategy` Protocol; call sites are `isinstance`-guarded so contract-clarity only. | logged → TD-09 |
| SRC-23 | info | `db/dialects/databricks.py:62-69` | Comment "Set to None to allow import" is inverted vs code (sets `_databricks_import_error = e` on failure, `None` on success). Logic correct; comment misleads. | logged → TD-09 |
| SRC-24 | info | `db/dialects/mssql.py:138-261` | `create_engine` ~123 lines + 14-kwarg unpack (>50-line / readable-arity clarity budget). Already partly decomposed; residual is the kwargs unpack + branch. | logged → TD-09 |
| SRC-25 | info | `db/metadata.py:849-943` | `get_table_schema` ~95 lines (>50-line budget); cohesive but the column/index/FK dict-comprehensions could each be a small builder. | logged → TD-09 |
| SRC-26 | info | `db/query.py:475-520` (`_inject_top_in_cte`) | Hand-rolled char-by-char paren-depth scan to find the final top-level SELECT, when sqlglot (already used in `parse_query_type`) is on hand. Correct for common cases, brittle vs string-literal/bracket parens. | logged → TD-09 |
| SRC-27 | info | `db/query.py:300-329` (`_get_validated_columns`) | Error-message context hardcodes MSSQL `[{schema}].[{table}]` brackets for all dialects, and `schema_name` can be `None` → `"[None].[t]"`. Message-only, no functional impact. | logged → TD-09 |
| SRC-28 | info | `models/analysis.py` (every `to_dict`) | Hand-written `to_dict`s restate field names as string literals + repeat "omit when None" across `ColumnStatistics`/`PKCandidate`/`FKCandidateData` — duplicated against the dataclass fields. (Partly deliberate: controls omission + isoformat timing.) | logged → TD-09 |
| SRC-29 | info | `db/validation.py:46-68` | `validate_query` docstring omits the real `safe_operational_commands` parameter from Args. Doc drift. | logged → TD-09 |
| SRC-30 | info | `mcp_server/schema_tools.py:58-67` + `metadata.py:731` | Cross-catalog correctness edge: detailed-mode `get_columns` has no `catalog` param, so with an explicit Databricks `catalog` the summary rows resolve cross-catalog but `columns` come from the connection's **default** catalog. Wrong/empty columns if a same-named table differs across catalogs. Ties to SRC-04. | logged → TD-08 |

**Counts:** 0 critical, 10 warning, 20 info = 30 total; dispositions 0 fixed / 0 verified / 30 logged.
**Suite unchanged by US2** (no `src/` edit) → baseline 1150 passed / 166 skipped / 91.92% holds.

---

## tests/ findings (TST-NN)

US3 sweep — all 70 `tests/` files reviewed (4 parallel reviewers across analysis / db-core /
dialects+mcp / integration+support, T022-T023). **Result: 0 critical, 6 warning, 16 info = 22.**
Unlike US2, US3's scope *is* to apply test fixes (consolidate / deepen / refactor-to-intent),
so the safe, coverage-neutral wins are **fixed** here; larger parametrize/consolidation refactors
(where proving branch-equivalence risks a silent coverage drop) are **logged** to `TD-10`.

> **Reviewer claims verified before acting** (debugging directive): TST-D01's `assert result is
> not 1` does raise a real `SyntaxWarning` (confirmed via `-W error::SyntaxWarning`); TST-A02's
> `test_mssql_uses_sys_indexes` drives a bare `MagicMock` `side_effect` so it never exercises the
> real `sys.indexes` SQL — it is a strict subset of `test_collects_pk_constraint`, confirmed;
> TST-C01's MSSQL `]`→`]]` escape (`mssql.py:110`) was genuinely untested while the Databricks
> backtick equivalent (CR-01) was covered.

| ID | Sev | Location | Finding | Disposition |
|----|-----|----------|---------|-------------|
| TST-D01 | warning | `test_type_registry.py:57` | `assert result is not 1` — real `SyntaxWarning` ("is" with literal) + semantically wrong identity check (only "works" via small-int caching). The next line `type(result) is bool` is the actual coverage. | **fixed** — removed the line (commit below). Suite re-run under `-W error::SyntaxWarning` clean. |
| TST-A02 | warning | `test_fk_candidates.py:823-846` | `test_mssql_uses_sys_indexes` = strict subset of `test_collects_pk_constraint` (:238); identical `MagicMock` `side_effect` means the real sys.indexes path is never hit → 0 added coverage. | **fixed** — deleted with a provenance comment; superset test retained. |
| TST-D03 | warning | `test_nfr_compliance.py:379-394` | `test_nfr_compliance_summary` is `print(...); assert True` — a pure doc-only tautology. | **fixed** — replaced with a module comment carrying the NFR→test map. |
| TST-B02 | warning | `test_connect_tool.py:160` | `test_databricks_connection_name_routes_through_connect_with_config` docstring said "routes to connect_with_url" but body asserts `connect_with_config`. Also ~95% dup of `test_connection_name_valid_calls_connect_with_config` (:65) — but the two pin different config types, so kept distinct. | **fixed** (docstring) — corrected the contradiction; consolidation logged → TD-10. |
| TST-C01 | warning | `test_mssql_dialect.py:54` (`TestQuoteIdentifier`) | Security-coverage asymmetry: MSSQL `quote_identifier` escapes `]`→`]]` (break-out defense) but only simple/spaces/dotted cases were tested; the Databricks backtick equivalent (CR-01) *was* covered. | **fixed** — added `test_embedded_closing_bracket_is_escaped` (`ev]il` → `[ev]]il]`). Coverage gain. |
| TST-D02 | warning | `test_discovery.py:88-151` | The three `list_tables` filter tests pre-filter `SAMPLE_TABLE_ROWS` in the test then feed only matching rows to the mock, so the assert passes even if the tool ignored the filter. Tautological. Ties to the already-logged SRC-03/SRC-30 contract gaps. | **logged → TD-08** (same multi-schema/detailed `list_tables` contract cluster; deepening needs the contract decision TD-08 already gates). |
| TST-C02 | info | `test_validation.py:361` | Docstring said "22 elements"; assert (and source) is 21. | **fixed** — docstring corrected to 21. |
| TST-D13 | info | `test_config.py:616` | `test_init_config_idempotent` docstring claimed "reloads (not cached)" but asserts only value-equality (`first == second`) — proves neither. (Also a minor dup of `TestValidateDefaults`.) | **fixed** (docstring → "equal config for equal inputs"); the duplicate-assert consolidation logged → TD-10. |
| TST-A01 | info | `test_pk_discovery.py:25,737`; `test_fk_candidates.py:27` | Three dead helpers (`_mock_scalar` ×2, `_make_databricks_dialect`) — zero call sites (grep-confirmed). | **fixed** — deleted all three. |
| TST-A03 | info | `test_pk_discovery.py:431` | `test_uses_provided_schema` reads back the constructor arg; discards `find_candidates()` result. | logged → TD-10 (deepen). |
| TST-A04 | info | `test_fk_candidates.py:613,657` | `>= 1` asserts where the mock yields exactly one candidate (`== 1` would catch a dup-regression). | logged → TD-10 (deepen). |
| TST-A05 | info | `test_fk_candidates.py:970` | `test_overlap_transpiled_for_non_mssql` asserts the overlap result, not that transpilation occurred; name over-promises. | logged → TD-10 (refactor-to-intent / rename). |
| TST-A08 | info | `test_column_stats.py:1045` | `.split("DESCRIBE EXTENDED ")[1].split(" ")[0]` string-surgery couples to SQL spacing; the positive 3-part membership assert already suffices. | logged → TD-10 (refactor-to-intent). |
| TST-B01 | info | `test_connection.py:23` + `test_query_timeout.py:16` | `_make_mock_engine()` duplicated verbatim across two files (+ a third `_make_mock_dialect` variant). | logged → TD-10 (consolidate to shared helper). |
| TST-B03 | info | `test_connect_tool.py` (6 tests) | ~20-line 5-collaborator `patch(...)` stack repeated per test — design signal: `connect_database` couples to module-level singletons + Path cache. | logged → TD-10 (extract fixture; design signal is new, test-ergonomic only). |
| TST-B05 | info | `test_metadata.py:196-252` | A few tests build a dict/dataclass by hand and assert the fields they just set (real behavior is "tested in integration" per their own docstrings). | logged → TD-10 (deepen or drop). |
| TST-B09 | info | `test_connection.py:787` | `test_connect_propagates_token_provider_error` dual-patches to force an error the real flow raises only via `creator()`; weak disjunction assert. The adjacent `TestTokenFailureAutoDisconnect` drives it properly. | logged → TD-10 (refactor-to-intent). |
| TST-B10 | info | `test_metadata.py:967-1142` | `TestDescribeExtended` — 11 single-field DTE-extraction tests are near-identical bodies; `test_full_dte_output_parsing` already covers all fields together. Parametrize candidate. | logged → TD-10 (consolidate/parametrize). |
| TST-C05 | info | `test_async_tools.py` | The 9 hand-rolled `*_uses_to_thread` tests overlap the parametrized `_TOOL_PARAMS` safety-net suite (same 9-tool matrix). | logged → TD-10 (consolidate to one parametrized test). |
| TST-C06 | info | `test_databricks_dialect.py` (~15 sites) | `create_engine` import-error save/restore try/finally repeated ~15×; `TestDatabricksCaBundle` already solved it with a fixture. | logged → TD-10 (hoist fixture). |
| TST-C07 | info | `test_validation_edge_cases.py:124` | Several "parse failure = denied" cases assert only `is_safe is False`, not the denial *category* (the load-bearing reason). | logged → TD-10 (deepen). |
| TST-D07/08 | info | `test_nfr_compliance.py` vs `test_nfr00{1,2}.py`; NFR-004 vs `test_validation.py` | Compliance suite re-implements NFR-001/002 timing + NFR-004 read-only checks already covered by the performance + validation suites (generous SQLite thresholds). | logged → TD-10 (consolidate — compliance references rather than re-implements). |
| TST-D09/10 | info | `test_pyproject_extras.py:27`; `test_serialization.py:42` | 6 near-identical `test_core_deps_include_*` (parametrize); `TestConvertForSerialization` re-tests `convert()` already owned by `test_type_registry.py`. | logged → TD-10 (consolidate). |

**Verified-OK (looked suspicious, confirmed deliberate — no action):** the engine-kwarg/ODBC-string
spy tests (TST-B08) and `ca_bundle` regression tests pin the externally observable contract (load-bearing,
not incidental coupling); the IDENT-01/02 "no SHOW CATALOGS fallback" trio (TST-B06) are three
*distinct* contracts; the layered Plan-03 vs Phase-14 catalog-required tests (TST-B07) are deliberate
mocked-helper-vs-real-probe depth; the two `sample_schemas` fixture families (root vs integration
conftest) are intentionally different shapes; `to_thread` delegation asserts (TST-C04) are genuine.

**Dead skip-stubs noted (TST-D05/D06):** `test_analysis_perf.py` (4 empty `pass` placeholders deferred
to phases that never landed) and `TestNFR003DocumentationSize` (2 skips for the 007-removed doc-size
feature). Logged → TD-10 for deletion; left in place this pass (no coverage impact, removal is cleanup).

**Counts:** 0 critical, 6 warning, 16 info = 22 total; dispositions **8 fixed** (TST-D01, A02, D03,
B02-docstring, C01, C02, D13-docstring, A01) / 1 logged-to-TD-08 (D02) / 13 logged-to-TD-10.

**SC-007 before/after (measured 2026-06-01):**

| Metric | Before US3 (US2 close) | After US3 | Δ |
|--------|------------------------|-----------|---|
| Tests passing | 1150 | 1149 | −1 (−2 redundant deleted: A02, D03; +1 added: C01) |
| Tests skipped | 166 | 166 | 0 |
| Coverage (total) | 91.92% | 91.92% | 0.00 (≥85% floor held; removed tests were redundant, added test net-positive) |

All four gates green after US3: `pytest` 1149p/166s; `--cov` 91.92% (Required 85.0% reached); `ruff
check src/` clean; `check_complexity.py` max=15. No `SyntaxWarning` under `-W error::SyntaxWarning`.
US3 touched only `tests/` — no `src/` change, so the WR-05 contract convergence remains the phase's
sole shipped-contract change.
