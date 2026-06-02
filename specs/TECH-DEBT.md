# Tech Debt Registry

Open, actionable work that is **not yet in the codebase** — carried forward from the GSD
era (milestones v1.0–v2.1) so it survives the migration back to spec-kit. None of these
are blocking; all shipped milestones are stable, tested to the 85% coverage floor, and
verified. This file is the spec-kit-native replacement for GSD's `todos/pending/`.

Full historical detail for every item lives in the frozen archive at
[`docs/archive/gsd-planning/`](../docs/archive/gsd-planning/). When an item is actioned,
move it to a feature spec (or fold it into a hardening pass) and strike it here.

## Summary

| ID | Item | Area | Priority | Effort | Source |
|----|------|------|----------|--------|--------|
| TD-04 | Unify the two "table not found" message templates in `analysis_tools.py` | analysis | low | ~5 LOC + 2 tests | feature 012 (IN-04 residue) |
| TD-05 | Query-in-loop / N+1 inefficiency across analysis + listing paths (SRC-04/06/07/08/09) | analysis, db, mcp_server | medium | refactor + cache, ~per-site | feature 012 (US2 sweep) |
| TD-06 | Rule-of-Three knowledge duplication (cross-catalog constraint SQL, modulo sampling, proc allowlist, config defaults) (SRC-10/11/12/15) | analysis, db | low | refactor + tests | feature 012 (US2 sweep) |
| TD-07 | `connection.py` robustness: undisposed engine on probe failure + `connect()` `dialect_name` mislabel (SRC-01/02) | db | medium | ~10 LOC + tests, 3 sites | feature 012 (US2 sweep) |
| TD-08 | Contract-sensitive correctness edges: `list_tables` multi-schema pagination, cross-catalog detailed columns, count-query ORDER BY (SRC-03/05/30) | mcp_server, db | medium | needs contract decision | feature 012 (US2 sweep) |
| TD-09 | Clarity/cleanup grab-bag: dead scalar guards, error-tail dedup, identity handlers, stale legacy-log migration, doc drift, etc. (SRC-13/14/16-29) | all | low | many small | feature 012 (US2 sweep) |
| TD-10 | `tests/` consolidation & deepening backlog: parametrize near-duplicate suites, shared mock-engine helper, deepen a few shallow asserts, delete dead skip-stubs (TST-A03/A04/A05/A08, B01/B03/B05/B09/B10, C05/C06/C07, D05/D06/D07/D08/D09/D10, D13-dup) | tests | low | many small refactors | feature 012 (US3 sweep) |
| TD-11 | `get_column_info` Databricks fast path reports misleading stats: `total_rows=0`, `null_percentage=0.0` (contradicts a populated `null_count`), and `null` mean/stddev on all numeric columns | analysis | **high** | ~15 LOC + tests | feature 012 (live adversarial validation) |
| TD-12 | Inconsistent error envelopes on bad catalog: `list_tables`/`list_schemas` leak the raw driver exception; resolver-path tools drop the catalog qualifier from the message | mcp_server, analysis, db | low | ~10 LOC + tests | feature 012 (live adversarial validation) |

> ~~TD-01, TD-02, TD-03~~ — **all resolved in feature 012 (Hardening & Cleanup Pass,
> 2026-06-01)**; struck below in *Closed / superseded*.
>
> **TD-05…TD-09** were surfaced by feature 012's full-`src/` review sweep (US2, all 34 modules).
> The sweep found **zero reachable correctness bugs**; every actionable item fell outside the
> US1-touched code, so per the triage bar (simplifications fixed only when local to TD-touched
> code) all 30 findings (`SRC-01`…`SRC-30`) were *logged here*, not fixed in 012. Full per-finding
> detail with locations lives in [`specs/012-hardening-cleanup/findings.md`](./012-hardening-cleanup/findings.md).
>
> **TD-10** was surfaced by feature 012's full-`tests/` review sweep (US3, all 70 files). The sweep
> found 22 findings; the 8 safe, coverage-neutral wins (a real `SyntaxWarning`, a subset/duplicate
> test, an `assert True`, three misleading docstrings, three dead helpers, **plus** a new MSSQL
> bracket-escape security test) were **fixed in 012**, and the larger parametrize/consolidation
> refactors — where proving branch-equivalence risks a silent coverage drop — were logged here.
> Per-`TST-NN` detail lives in the same findings.md.
>
> Cross-dialect `ca_bundle` promotion is **future feature scope**, not active debt — it
> lives in [`BACKLOG.md`](./BACKLOG.md). The "unify-3-part identifier" todo was verified
> **resolved** and is recorded as closed at the bottom of this file.

---

## TD-04 — Unify the two "table not found" message templates (IN-04 residue)

**Priority:** low · **Effort:** ~5 LOC + 2 test updates · Surfaced by feature 012 (IN-04).

`_check_table_exists` (`src/mcp_server/analysis_tools.py`) emits two different
"table not found" `error_message` strings depending on the branch:

- cross-catalog: `Table 'schema.table' not found`
- default: `Table 'table' not found in schema 'schema'`

Downstream `error_message` parsers see the drift. Feature 012's IN-02/03/04 verification
(D-04) confirmed the *dedup* is complete (one shared helper, one hoisted import) — this is
the residual divergence. It was **not** unified in 012 because it is not a one-line local
change: both templates are pinned by tests in `tests/unit/test_analysis_tools_helpers.py`,
it touches two production branches, and it nudges an externally observable `error_message`
(FR-014 territory). The divergence is also partly justified — the default path has no
catalog, while the cross-catalog path carries the dotted `schema.table` because catalog
context matters. **Action:** pick one template (or a catalog-aware single template), update
the two pinned tests, and confirm no downstream parser depends on the old wording.

---

## TD-05 — Query-in-loop / N+1 inefficiency across analysis + listing paths

**Priority:** medium · **Effort:** per-site refactor + caching · Surfaced by feature 012 US2 sweep
(SRC-04, SRC-06, SRC-07, SRC-08, SRC-09). Constitution V ("no I/O in loops where a batch exists").

Five independent spots issue one query (often one connection) per item inside a loop:

- **SRC-04** `schema_tools.py:58-67,388` — detailed-mode `list_tables` calls `get_columns`
  (3 reflection round-trips) per table; ~300 serial reflections for 100 tables. No batch
  metadata path exists on `MetadataService`.
- **SRC-06** `column_stats.py:664-707` — cross-catalog `get_columns_info` issues a per-column
  `DESCRIBE TABLE` (uncached `_reflect_catalog_columns`) **and** a second per-column
  `DESCRIBE EXTENDED`. The reflected column list is identical every call — cache it on the collector.
- **SRC-07** `fk_candidates.py:505-577,693` — source-side `COUNT(DISTINCT)` recomputed once per
  target column though it's invariant for the search; compute once before the loop.
- **SRC-08** `pk_discovery.py:432-453` — one `COUNT(DISTINCT)/COUNT(*)` per structural candidate
  column; combinable into a single multi-aggregate table scan. Dominant cost on wide tables.
- **SRC-09** `metadata.py:580-595` — generic `list_tables` opens a fresh `engine.connect()` +
  `COUNT(*)` per table; reuse one connection across the loop (MSSQL already uses one DMV CTE).

**Action:** address opportunistically per module; SRC-06 (collector-level column cache) and
SRC-08 (multi-aggregate) are the highest value. Each needs a regression/round-trip-count test.

---

## TD-06 — Rule-of-Three knowledge duplication

**Priority:** low · **Effort:** refactor + tests · Surfaced by feature 012 US2 sweep
(SRC-10, SRC-11, SRC-12, SRC-15).

Four spots where the *same knowledge* is restated ≥3× (not mere code-shape similarity):

- **SRC-10** the `information_schema.table_constraints JOIN key_column_usage` PK/UNIQUE query
  against a backtick-quoted `{catalog}.information_schema` is written 3× across
  `pk_discovery._get_constraint_candidates_cross_catalog` (PK + UNIQUE) and
  `fk_candidates._get_constraints_cross_catalog`. Centralize as
  `CatalogAwareReflector.reflect_constraints(catalog, schema, table)`.
- **SRC-11** the MODULO sampling SQL body is duplicated near-verbatim across `databricks.py`,
  `generic.py`, `mssql.py`; deltas are only LIMIT/TOP + ORDER BY tiebreaker.
- **SRC-12** `validation._check_execute` and `_check_stored_procedure` restate the same
  allowlist + `sp_executesql` policy + denial structure; risk of policy drift.
- **SRC-15** `config.py` duplicates dialect defaults between `DefaultsConfig` field defaults and
  `_DEFAULTS_BOUNDS`, and restates dataclass fields in 3 per-dialect `known_fields` literals.

**Action:** extract the shared knowledge per item. SRC-12 (security policy) is the most
drift-dangerous despite low effort.

---

## TD-07 — `connection.py` robustness gaps

**Priority:** medium · **Effort:** ~10 LOC + tests, 3 call sites · Surfaced by feature 012 US2
sweep (SRC-01, SRC-02).

- **SRC-01** When `_register_engine`'s `_test_connection` raises `SQLAlchemyError`, the engine
  created just above (`connect_with_url` ~358, `_connect_databricks_from_config` ~612, and the
  MSSQL `connect()` ~206) is orphaned — never stored in `self._engines`, never `dispose()`d —
  leaking a connection pool until GC. Dispose in the failure path.
- **SRC-02** `connect()` builds `Connection(...)` without `dialect_name`, relying on the model
  default `"mssql"`, although it accepts a `dialect` param. Latent mislabel if a non-MSSQL
  dialect is ever routed through `connect()` (only MSSQL reaches it today). `_register_engine`
  already sets `dialect_name=dialect.name` correctly — mirror that.

**Action:** both are small, well-localized fixes with clear regression tests; do them together.

---

## TD-08 — Contract-sensitive correctness edges (need a contract decision first)

**Priority:** medium · **Effort:** fix gated on a contract decision · Surfaced by feature 012
US2 sweep (SRC-03, SRC-05, SRC-30). These are genuine wrong-result paths, but fixing them
changes externally observable tool behavior (FR-014), so they were **not** patched silently.

- **SRC-03** `schema_tools.py:358-399` — `list_tables` with a **multi-schema** `schema_filter`
  applies `limit`/`offset` per-schema then concatenates + `[:limit]`: global offset spanning
  schema boundaries is wrong, sort order holds only within each schema, and `has_more` can
  mislead after truncation. Single-schema / `None` path is correct.
- **SRC-30** `schema_tools.py:58-67` + `metadata.py:731` — detailed-mode `get_columns` has no
  `catalog` param, so with an explicit Databricks `catalog` the summary rows resolve
  cross-catalog but `columns` are fetched from the connection's **default** catalog (wrong/empty
  if a same-named table differs across catalogs). Ties into the SRC-04 N+1 (TD-05).
- **SRC-05** `query.py:764-778` — `_get_total_row_count` wraps the original query in
  `SELECT COUNT(*) FROM (<orig>) AS …`; a top-level `ORDER BY` makes that invalid T-SQL → COUNT
  silently returns `None`, so `total_rows_available` is absent on exactly the ordered queries
  users run most. Strip a trailing top-level ORDER BY before wrapping, or accept best-effort.

**Action:** decide the intended pagination/ordering contract for multi-schema `list_tables` and
the cross-catalog detailed-columns semantics, *then* fix + update the pinned tests.

---

## TD-09 — Clarity / cleanup grab-bag

**Priority:** low · **Effort:** many small independent edits · Surfaced by feature 012 US2 sweep
(SRC-13, SRC-14, SRC-16 … SRC-29). None are correctness bugs; all are clarity-budget, dead-code,
doc-drift, or minor-dedup items safe to pick off opportunistically. Highlights:

- **SRC-13** dead `x = row[0] if row else 0` scalar guards survive in `fk_candidates.py` /
  `pk_discovery.py` — the same class WR-02 removed in `column_stats.py`; now inconsistent.
- **SRC-14** 5 tool handlers hand-roll the `SQLAlchemyError`→classify-vs-fallback split instead
  of reusing `_errors.format_unexpected_error` (only the per-tool prefix differs).
- **SRC-16** `type_registry._handle_bool/int/float` are byte-identical pass-throughs →
  one `_handle_identity`.
- **SRC-17** `logging_config._migrate_legacy_log` TODO "remove after v2.1" — v2.1 shipped
  2026-05-31; the migration still stats the legacy path every `setup_logging`. Confirm no
  environment still carries a stale `./dbmcp.log`, then remove.
- **SRC-18** `logging_config.py:135-140` recomputes `_compute_default_log_path` only to log a
  path already in `log_path`.
- **SRC-19** `CredentialFilter` (correctly wired at `server.py:26`) redacts `record.msg` only,
  not `record.args` — a secret passed as a `%s` arg is not redacted. Narrow but real.
- **SRC-20** `models/relationship.py:78` function-local `import hashlib` with no benefit.
- **SRC-21** `src/db/azure_auth.py` is a re-export shim with a single test-only importer →
  delete + repoint the test.
- **SRC-22** `DatabricksDialect.list_catalogs` not declared on the `DialectStrategy` Protocol.
- **SRC-23** `databricks.py:62-69` comment inverted vs code.
- **SRC-24/25** `mssql.create_engine` (~123 lines) and `metadata.get_table_schema` (~95 lines)
  exceed the >50-line clarity budget.
- **SRC-26** `query._inject_top_in_cte` hand-rolls paren-depth parsing where sqlglot is on hand.
- **SRC-27** `query._get_validated_columns` hardcodes MSSQL `[{schema}].[{table}]` brackets in an
  error message for all dialects; `schema_name` can be `None` → `"[None].[t]"`.
- **SRC-28** `models/analysis.py` `to_dict`s restate field names + repeat "omit when None".
- **SRC-29** `validate_query` docstring omits the `safe_operational_commands` parameter.

**Action:** opportunistic — fold individual items into any future edit that touches the file.

---

## ~~TD-01~~ — Residual Databricks `connect_with_config` regression tests · ✅ RESOLVED (feature 012, 2026-06-01)

> **Resolved:** the two regression tests already existed (commit `48a2c5b`, tag v2.1,
> predating feature 012) — verified genuine by mutation-checking each against its target
> production line. No production change needed. See `specs/012-hardening-cleanup/findings.md`.
> Detail retained below for provenance.

**Priority:** low · **Effort:** ~35 LOC · **No production code changes.**

Two coverage gaps remain in the Databricks connect path. The code under test is correct;
these are hardening additions, not fixes (verdict from quick-task `260505-mr3` audit).

1. **Env-var substitution for `catalog`/`schema_name`** (`src/db/connection.py:466-467`).
   Existing tests pass literal strings, so `resolve_env_vars` on those lines is never
   exercised — removing it would fail no test. Add a test asserting that
   `catalog="${DBX_CATALOG}"` / `schema_name="${DBX_SCHEMA}"` resolve to env values in the
   captured engine kwargs.
2. **`SQLAlchemyError` → `ConnectionError` wrapping** (`src/db/connection.py:494-502`).
   The Databricks branch wraps `SQLAlchemyError` from `dialect.create_engine` into
   `ConnectionError` with the host in the message; no test covers it. Add a test asserting
   the wrap fires and the host string appears in the message.

Both go in `tests/unit/test_connect_with_config_databricks.py` (reuse `_make_engine_spy`).

---

## ~~TD-02~~ — URL-mode probe engine should inherit `ca_bundle` for IDENT-01 enrichment · ✅ RESOLVED (feature 012, 2026-06-01)

> **Resolved:** commit `76d48c0` — `connect_with_url` now forwards `ca_bundle` from the parsed
> URL kwargs into `_require_databricks_catalog`, mirroring the config path. D-02 clarified that
> `_tls_trusted_ca_file` is derived from `ca_bundle` inside `create_engine`, so forwarding
> `ca_bundle` alone suffices (FR-003 over-spec corrected). Live corp-MITM probe deferred to UAT
> (FR-017). Detail retained below for provenance.

**Priority:** medium · **Effort:** ~10 LOC, surgical · Matches the v2.1 audit WARNING.

When `connect_with_url` raises "Databricks catalog is required", the IDENT-01 enrichment
helper builds a **probe engine** and runs `SHOW CATALOGS` to populate the
"Accessible catalogs: …" list in the surfaced error. That probe engine is built fresh from
the URL but does **not** inherit `ca_bundle` from the URL query string. On corp-MITM TLS
networks the probe `SHOW CATALOGS` fails with `SSLCertVerificationError`, and enrichment
degrades to the generic D-06 fallback — the user never sees the actionable catalog list,
even though the **named-config** route (which carries `ca_bundle`) returns 22 catalogs on
the same workspace. Asymmetry confirmed in Phase 14 UAT (2026-05-28, post-`260528-gsk`).

**Fix:** in the enrichment helper (`src/db/connection.py`, near where the probe engine is
constructed), parse the inbound URL and forward `ca_bundle` (and `_tls_trusted_ca_file`)
into the probe engine's `connect_args`, exactly as the real engine would receive them. Add
a unit test asserting the probe engine receives `ca_bundle` when the URL carries one (live
UAT needs the corp-MITM environment).

---

## ~~TD-03~~ — Phase 15.1 code-review follow-ups (WR-01/02/05, IN-01–04) · ✅ RESOLVED (feature 012, 2026-06-01)

> **Resolved** across feature 012:
> - **WR-01** narrowed `except Exception`→`SQLAlchemyError` (commit `280a874`).
> - **WR-02** dropped dead/misleading row guards (commit `280a874`).
> - **WR-05** (Option B) DESCRIBE EXTENDED fast path now fires cross-catalog (commit `1dedd71`);
>   live SC-008 "after" capture pending a `dbmcp-test` server restart (unit-proven).
> - **IN-01** fail-fast on SHOW TABLES row shape (commit `21d738d`).
> - **IN-02/03/04** verified already-refactored (D-04); IN-04 message-template residue moved to
>   **TD-04** above (not a one-line local change).
>
> See `specs/012-hardening-cleanup/findings.md` for the full audit trail. Detail retained below.

**Priority:** low · 7 non-blocking robustness/clarity/dedup findings from the Phase 15.1
code review (`15.1-REVIEW.md`: 1 critical + 5 warnings + 4 info; 5 files reviewed). The
phase goal (IDENT-08 cross-catalog targeting) is verified, secured (16/16 threats), and
live-UAT'd — these are quality debt, not correctness gaps.

**Already fixed during/after the phase (NOT part of this item):** CR-01 backtick escaping
(commit `537680c`), WR-04 TSQL bracket escaping (`b49d525`), WR-03 cross-catalog
nullability (quick-task `260529-jwa`, `67245ba`/`0bcb466`).

**Action trigger:** pick these up when a hardening pass is scheduled, or opportunistically
the next time you edit `src/analysis/column_stats.py`, `src/analysis/_sql.py`, or
`src/mcp_server/analysis_tools.py`. Promote **WR-01 to urgent** if it ever masks a real incident.

### Robustness — `src/analysis/column_stats.py`

- **WR-01 — bare `except Exception: return None` masks real failures.**
  `_try_describe_extended_stats` (`column_stats.py:425-429`) treats auth failures, network
  errors, injection-induced syntax errors, and "stats genuinely unavailable" identically,
  then silently falls through to the Tier-2 path. **Fix:** narrow to
  `sqlalchemy.exc.SQLAlchemyError` and ideally distinguish "DESCRIBE EXTENDED unsupported"
  from infra errors that should propagate. *Most worth promoting to urgent of the seven.*
- **WR-02 — `row[1]`/`row[2]` dereferenced after only guarding `row` truthiness.**
  `get_basic_stats`/`get_numeric_stats`/etc. (`column_stats.py:265-269, 293-308, 375-380`)
  use `row[1] if row else 0`; the `else` guards `None`, not a short row, so an unexpected
  aggregate shape raises `IndexError` instead of falling back. **Fix:** drop the misleading
  guards (trust the aggregate contract) or guard width: `row[1] if row and len(row) > 1 else 0`.

### Clarity / dead code — `src/analysis/column_stats.py`

- **WR-05 (Phase 15.1) — Databricks DESCRIBE EXTENDED "fast path" is dead code cross-catalog.**
  `get_columns_info` (`column_stats.py:600-623`) probes only `columns_to_analyze[0]` for
  `use_fast_path`. On the cross-catalog branch `get_column_data_type` returns a *string*
  (`column_stats.py:194-198`), so `isinstance(type_info, sa_types.TypeEngine)` is always
  False and the fast path never fires — every cross-catalog column silently takes the
  Tier-2 path, contradicting the docstrings that advertise a Databricks fast path.
  **Fix:** gate the probe on `not self._is_cross_catalog_databricks` and document the fast
  path as default-catalog-only, OR make the cross-catalog reflector return a `TypeEngine`.
  *(Disambiguation: this WR-05 is NOT the FK `target_schema` WR-05 closed by quick-task `260528-v61`.)*

### Dedup / consistency — `src/mcp_server/analysis_tools.py` (IN-02/03/04 share ONE fix)

- **IN-03 — identical cross-catalog scaffolding duplicated across all three tools.**
  The `cross_catalog` predicate plus the `if cross_catalog: MetadataService.table_exists(…)
  else: inspector.get_table_names/get_view_names` existence block is copy-pasted at
  `analysis_tools.py:112-147, 262-295, 429-462` (and recomputed inside
  `PKDiscovery`/`FKCandidateSearch`/`ColumnStatsCollector`). Rule of Three crossed.
  **Fix:** extract a shared `resolve_and_check_table_exists(...)` helper. **It naturally
  subsumes IN-02 and IN-04 — do all three together.**
- **IN-02 — lazy `from src.db.metadata import MetadataService` duplicated in 3 tool fns**
  (`analysis_tools.py:126-128, 275-277, 442-444`). Hoist to module top-level if no cycle,
  else add a one-line comment naming the cycle. Folds into the IN-03 helper.
- **IN-04 — inconsistent "table not found" message between cross-catalog and default paths.**
  Cross-catalog emits `Table 'schema.table' not found`; default emits
  `Table 'table' not found in schema 'schema'` (`analysis_tools.py:135 vs 146, 284/294, 451/461`).
  Downstream `error_message` parsers see drift. Use one template for both branches; folds
  into the IN-03 helper.

### Consistency — `src/analysis/_sql.py`

- **IN-01 — `list_tables` row-shape fallback contradicts its documented contract.**
  `_sql.py:119` (≈140 after the WR-03 fix): `return [row[1] if len(row) > 1 else row[0]
  for row in rows]`. The docstring says SHOW TABLES returns `(database, tableName,
  isTemporary)` with `row[1]` the table name; the `len(row) > 1` fallback to `row[0]` would
  silently return a database name as a table name for a shape the docstring says never
  occurs. **Fix:** assert the expected shape (fail fast) or document why the fallback exists.

**Out of scope for TD-03:** re-litigating CR-01/WR-03/WR-04 (fixed); the pre-existing
`src/metrics.py` `Generator` import-location ruff warning (tracked separately); behavioral
changes to the default-catalog / MSSQL / Inspector paths.

---

## TD-11 — `get_column_info` Databricks fast path reports misleading stats

**Priority:** high · **Effort:** ~15 LOC + test updates · Surfaced by feature 012 live
adversarial validation (2026-06-02), grounded in source.

On Databricks, `get_column_statistics` (`src/analysis/column_stats.py:583-588`) takes the
`DESCRIBE EXTENDED` fast path for **every** table where precomputed column stats exist —
both default-catalog and cross-catalog. `_build_stats_from_describe_extended`
(`column_stats.py:543-553`) then hardcodes three fields the DESCRIBE output cannot supply:

- `total_rows=0` (line 548) — factually wrong; e.g. `cerner_dm.demographics` has 190,782 rows.
- `null_percentage=0.0` (line 551) — **self-contradictory** with the populated `null_count`
  it returns alongside (observed `null_count: 7722` next to `null_percentage: 0.0`). A
  consumer reasonably reads this as "no nulls." This is actively misleading, not merely
  incomplete.
- `mean_value=None`, `std_dev=None` (lines 539-540) — silently dropped on all numeric
  columns; the MSSQL / Tier-2 path populates both.

Reproduced on both the default-catalog (`cerner_dm.demographics`) and cross-catalog
(`samples.tpch.customer`) branches, so it is **all-Databricks**, not a cross-catalog
artifact. MSSQL is unaffected (its Tier-2 aggregate path returns correct values throughout).

**Lineage (important):** this is a *new side-effect of the feature-012 WR-05 fix*, not a
re-log of the old WR-05. Pre-012, the fast path was dead code cross-catalog (it never fired
because the type resolved to a string). The 012 WR-05 fix made the fast path *fire*; the
hardcoded `0`/`0.0`/`None` placeholders inside it then became externally observable.

**Coverage gap:** `test_build_stats_from_describe_extended_numeric`
(`tests/unit/test_column_stats.py`) asserts `null_count` but **never** `total_rows` or
`null_percentage` — so the contradiction is both shipped and test-blind.

**Fix options (pick one — externally observable, so it's a contract decision):**
1. Have the fast path issue one `COUNT(*)` to populate `total_rows` and derive
   `null_percentage` honestly (sacrifices the "zero extra queries" property; cheapest correct).
2. If the fast path must stay query-free, emit `total_rows=null` and `null_percentage=null`
   so the response reads as "unknown" rather than "zero." Lower-effort, preserves intent.
   For mean/stddev, `null` is already defensible (DESCRIBE genuinely lacks them) but should
   be documented in the tool contract rather than left implicit.

Either way, add fast-path assertions on `total_rows` and `null_percentage` to close the gap.

---

## TD-12 — Inconsistent error envelopes on a nonexistent catalog (Databricks)

**Priority:** low · **Effort:** ~10 LOC + tests · Surfaced by feature 012 live adversarial
validation (2026-06-02). Message-quality only — no functional break.

Two related envelope-hygiene defects on the Databricks bad-catalog path:

- **Raw driver leak (SHOW-path tools).** `list_tables` and `list_schemas` issue
  `SHOW … IN <catalog>` directly; a nonexistent catalog surfaces the **raw
  `databricks.sql.exc.ServerOperationError`** including the internal SQL
  (`SHOW TABLES IN \`x\`.\`tpch\``) and the `sqlalche.me/e/20/4xp6` URL, instead of the
  clean `error_message` envelope the rest of the tools produce.
- **Dropped catalog qualifier (resolver-path tools).** `get_table_schema` and
  `get_column_info` go through `resolve_and_check_table_exists`, which returns a clean
  envelope — but it says `Table 'tpch.customer' not found` when the *catalog* is what's
  missing, hiding the real cause.

The same raw-leak pattern (`sqlalche.me` URL + pyodbc/driver text) also appears on
wrong-dialect *execution* errors (e.g. `LIMIT` on MSSQL via `execute_query`) — arguably more
acceptable there since it's an execution-time error, but worth folding into the same wrap.

**Action:** wrap the `SHOW`-path driver exception in the standard `status: error` envelope
with a `Catalog '<x>' not found` message; and have the resolver-path message name the
catalog when one was supplied. One shared "catalog not found" template across both paths.

---

## Closed / superseded

- **`unify-3-part-identifier-handling` (GSD todo, 2026-05-08) — RESOLVED, no action.**
  All five reported Databricks bugs were fixed by milestone v2.1 (Phases 15 + 15.1,
  IDENT-01–08). Verified against live code on migration (2026-06-01):
  - Catalog-required connect + dropped `list_schemas` catalog fallback → IDENT-01/02.
  - Dotted `table_name` parsing, dialect-aware depth, disagreement-only conflict detection
    → `resolve_identifier` in `src/db/identifiers.py:59-127` (IDENT-03/04).
  - `catalog` param on `get_sample_data`/`get_column_info` → `analysis_tools.py:126/247/356`
    (IDENT-05/06).
  - Hardcoded `'dbo'` removed; per-dialect `default_schema` (MSSQL→`dbo`, others own) →
    `src/db/dialects/*.py` (IDENT-07).
  - Cross-catalog metadata targeting via stateless 3-part SQL → IDENT-08 (Phase 15.1).
