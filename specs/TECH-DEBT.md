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
| TD-01 | Residual Databricks `connect_with_config` regression tests | testing | low | ~35 LOC | [todo](../docs/archive/gsd-planning/todos/pending/2026-05-05-add-databricks-integration-tests.md) |
| TD-02 | URL-mode probe engine should inherit `ca_bundle` | database | medium | ~10 LOC | [todo](../docs/archive/gsd-planning/todos/pending/2026-05-28-url-mode-probe-engine-inherit-ca-bundle-for-ident-01-enrichm.md) |
| TD-03 | Phase 15.1 code-review follow-ups (WR-01/02/05, IN-01–04) | analysis | low | see below | [todo](../docs/archive/gsd-planning/todos/pending/2026-05-31-phase-15.1-code-review-followups.md) |

> Cross-dialect `ca_bundle` promotion is **future feature scope**, not active debt — it
> lives in [`BACKLOG.md`](./BACKLOG.md). The "unify-3-part identifier" todo was verified
> **resolved** and is recorded as closed at the bottom of this file.

---

## TD-01 — Residual Databricks `connect_with_config` regression tests

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

## TD-02 — URL-mode probe engine should inherit `ca_bundle` for IDENT-01 enrichment

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

## TD-03 — Phase 15.1 code-review follow-ups (WR-01/02/05, IN-01–04)

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
