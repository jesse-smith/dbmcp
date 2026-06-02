---
description: "Task list for 012 Hardening & Cleanup Pass"
---

# Tasks: Hardening & Cleanup Pass

**Input**: Design documents from `/specs/012-hardening-cleanup/`

**Prerequisites**: plan.md, spec.md, research.md (D-01…D-07), data-model.md, quickstart.md

**Tests**: Tests ARE in scope. FR-018 mandates red-green-refactor TDD where code changes; TD-01
(FR-001/002) is test-only. Test tasks are therefore first-class here, not optional.

## Format: `[ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependency on incomplete tasks)
- **[Story]**: US1 (known TD fixes, P1), US2 (`src/` sweep, P2), US3 (`tests/` sweep, P3)
- All paths are repo-root-relative. All Python tooling runs via `uv run`.

## The four gates (run before EVERY commit — quickstart.md)

```bash
uv run pytest tests/                               # full suite green
uv run pytest --cov=src --cov-report=term-missing  # coverage ≥85% (SC-003)
uv run ruff check src/                             # lint src/ only, zero warnings
uv run python scripts/check_complexity.py          # cognitive complexity ≤15 (SC-004)
```

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Establish the review ledger and a measured baseline so SC-002/SC-003/SC-007 are
verifiable as deltas.

- [X] T001 Create `specs/012-hardening-cleanup/findings.md` from the data-model.md ledger schema: YAML frontmatter (`phase`, `reviewed`, `src_modules_total`, `src_modules_reviewed`, `findings{}`, `dispositions{}`), a `## src/ module coverage checklist` seeded with all 34 modules from `find src -name '*.py'` (all unchecked), an empty `## src/ findings (SRC-NN)` section, and an empty `## tests/ findings (TST-NN)` section.
- [X] T002 [P] Record the baseline in the findings.md frontmatter / a "Baseline" note: current passing/skipped test counts (`uv run pytest tests/ -q` → 1119/146 expected) and current coverage % (`uv run pytest --cov=src`), so SC-003/SC-007 deltas are measurable at close. **Measured: 1138 passed / 146 skipped / 91.33% cover.**
- [X] T003 [P] Confirm `dbmcp-test` MCP server reachability for live validation (StemSoftClinicTest + Databricks warehouse) and note any auth steps (Cloudflare re-auth / `kinit`) needed. If unreachable this session, flag it — live gates (SC-006/SC-008) will need a session where it is. **Both reachable; no auth steps needed.**

**Checkpoint**: Ledger exists with full module checklist; baseline captured.

---

## Phase 2: Foundational

**Purpose**: None required. The known fixes (US1) are mutually independent and each is its own
red-green-refactor unit; there is no shared scaffold to build first. US1 begins immediately
after Setup.

---

## Phase 3: User Story 1 — Close the three open tech-debt items (Priority: P1) 🎯 MVP

**Goal**: TD-01/02/03 resolved, tested, and struck from `TECH-DEBT.md`. Highest-confidence,
lowest-risk slice — every item has a precise location and prescribed fix.

**Independent Test**: New/changed unit tests for TD-01/02/TD-03 pass; full suite green at ≥85%;
`TECH-DEBT.md` no longer lists TD-01/02/03 as open.

> Sequencing within US1 follows quickstart.md: TD-02 (operator-facing) → TD-01 (test-only) →
> WR-01/WR-02 → IN-01 → IN-02/03/04 (verify) → WR-05 (behavioral, live-validated) → closure.
> Each numbered fix is one logical commit (FR-018). Reconnect `dbmcp-test` after merging any
> `src/` change before live-probing (memory: MCP server runs session-start code).

### TD-02 — URL-mode probe `ca_bundle` (D-02, FR-003)

- [X] T004 [US1] **RED**: add a unit test to `tests/unit/` (alongside the existing connection/probe tests — locate the URL-mode `_require_databricks_catalog` probe test or add to `tests/unit/test_connect_with_url*.py`) asserting that when a Databricks URL carries `?ca_bundle=/path/ca.pem` and triggers the "catalog required" enrichment, the probe engine built by `_require_databricks_catalog` receives `ca_bundle`. Test must FAIL against current `src/db/connection.py:364-378` (ca_bundle dropped). **Done: `test_connect_with_url_databricks_probe_inherits_ca_bundle` — RED confirmed (probe got `''`).**
- [X] T005 [US1] **GREEN**: in `connect_with_url` (`src/db/connection.py`, Databricks catalog-required branch ~364-378), extract `ca_bundle` from the parsed URL kwargs (`dialect._kwargs_from_url(...)` already returns it) and forward it into the `_require_databricks_catalog(...)` call, mirroring the config path (~618-625). ~3 LOC. Note in findings.md that FR-003's `_tls_trusted_ca_file` is *derived inside* `create_engine` from `ca_bundle` (databricks.py:328-332), so forwarding `ca_bundle` alone is sufficient (D-02 scope clarification). Live check is **deferred** to corp-MITM UAT (FR-017) — record the deferral. **Done: commit `76d48c0`, GREEN, four gates pass, deferral recorded.**

### TD-01 — regression tests only (D-03, FR-001/002)

- [X] T006 [P] [US1] Add to `tests/unit/test_connect_with_config_databricks.py` (reuse `_make_engine_spy`, line 27): a test asserting `catalog="${DBX_CATALOG}"` / `schema_name="${DBX_SCHEMA}"` resolve from the environment into the captured engine kwargs (exercises `resolve_env_vars`, `connection.py:579-580`). Verify it would FAIL if the resolve call were removed. **ALREADY EXISTS** (`test_env_var_substitution_for_catalog_and_schema`, commit `48a2c5b`/v2.1) — mutation-checked genuine, no new test needed.
- [X] T007 [P] [US1] Add to the same file: a test asserting a `SQLAlchemyError` raised by `dialect.create_engine` is wrapped in `ConnectionError` with the host string present in the message (`connection.py:629-636`). Verify it would FAIL if the wrap were removed. **ALREADY EXISTS** (`test_sqlalchemy_error_wrapped_as_connection_error`, commit `48a2c5b`/v2.1) — mutation-checked genuine, no new test needed.

### TD-03 robustness — WR-01, WR-02 (D-06, FR-004/005)

- [X] T008 [US1] **WR-01** (`src/analysis/column_stats.py`, `_try_describe_extended_stats` ~437): RED — add a test asserting a non-DESCRIBE infra error (e.g. an `OperationalError`/auth error) propagates rather than being swallowed to `None`; and a test confirming an "unsupported syntax" `ProgrammingError` (subclass of `SQLAlchemyError`) still degrades to `None` → Tier-2. GREEN — narrow `except Exception` to `except SQLAlchemyError`. Verify against the live Databricks warehouse that "DESCRIBE EXTENDED unsupported" still raises a catchable `SQLAlchemyError` (so graceful degradation is preserved) — SC-006. **Done: commit `280a874`. NOTE: the task's `OperationalError` example is imprecise — it IS a SQLAlchemyError, so it'd still be caught; the propagation test uses a genuine non-SQLAlchemy `PermissionError`. Live SC-006 check pending after reconnect.**
- [X] T009 [US1] **WR-02** (`column_stats.py` `get_basic_stats` ~275-277, `get_numeric_stats` ~305, siblings): RED — add/adjust a test proving correct stats are returned for a normal aggregate row without the spurious guard. GREEN — drop the misleading `row[1] if row else 0` guards (a no-GROUP-BY aggregate always returns exactly one full-width row); remove the dead `if not row` guard in `get_numeric_stats`. Trust the aggregate contract per D-06. **Done: commit `280a874`. Also simplified get_string_stats + get_datetime_stats (kept its load-bearing `row[0] is None`).**

### TD-03 consistency — IN-01, IN-02/03/04 (D-04, D-05, FR-006/008)

- [X] T010 [US1] **IN-01** (`src/analysis/_sql.py:178`, `CatalogAwareReflector.list_tables`): RED — add a test asserting an unexpected SHOW TABLES row shape fails fast with a clear error instead of silently returning `row[0]` (a database name) as a table name. GREEN — replace `return [row[1] if len(row) > 1 else row[0] for row in rows]` with a fail-fast on rows lacking the documented `(database, tableName, isTemporary)` width. Separately review the `len(row) > 1` idiom in `reflect_columns` (line 110): disposition in findings.md as `verified` (genuinely defensive at DESCRIBE section markers) or `fixed` — decide per its actual behavior, do not blanket-change. **Done: commit `21d738d`. reflect_columns idiom → `verified` (defensive, defaults to `""`, not wrong data).**
- [X] T011 [US1] **IN-02/03/04** (`src/mcp_server/analysis_tools.py`): VERIFY (D-04 — already refactored). Confirm `_is_cross_catalog` (line ~26) and `_check_table_exists` (line ~41) are the single shared helper called by all three tools (`get_column_info` ~206, `find_pk_candidates` ~314, `find_fk_candidates` ~441), that the lazy `MetadataService` import is hoisted to one site, and that no inline duplication remains in `PKDiscovery`/`FKCandidateSearch`/`ColumnStatsCollector`. Record as `verified` in findings.md. Then disposition IN-04's residue: the two not-found message templates (`'schema.table' not found` vs `'table' not found in schema 'schema'`) — unify ONLY if it is a one-line local change, else `log` to TECH-DEBT.md with provenance. **Done: all dedup verified present. IN-04 residue → logged as TD-04 (not one-line local; both templates test-pinned; FR-014 observable string; divergence contextually justified). TECH-DEBT entry added at T016.**

### TD-03 behavioral — WR-05 Option B (D-01, FR-007 — the one perf/behavior change, own commit)

- [X] T012 [US1] **RED**: in `tests/unit/test_column_stats.py` (`TestDatabricksFastPath` or a cross-catalog sibling), add a test where a cross-catalog `ColumnStatsCollector` (no inspector, `_is_cross_catalog_databricks=True`) has `get_column_data_type` return a `TypeEngine` so the `isinstance` gate in `get_columns_info` (line 626) / `get_column_statistics` (line 513) passes and the DESCRIBE EXTENDED fast path FIRES cross-catalog. Assert: (a) `isinstance(result, sa_types.TypeEngine)`; (b) unknown type token → `NullType()` (still a TypeEngine, takes fast path, lands "other"); (c) the result `ColumnStatistics` keys/shape are unchanged. Test FAILS today (cross-catalog returns a raw string at `column_stats.py:204-205`). **Done: `TestCrossCatalogTypeEngine` (7 tests), RED confirmed.**
- [X] T013 [US1] **GREEN**: change `get_column_data_type`'s cross-catalog branch (`column_stats.py:201-205`) to convert the DESCRIBE-TABLE type string → `TypeEngine`. **Pinned entry point (D-01 resolved)**: reuse the Databricks dialect's own map — `from databricks.sqlalchemy._parse import GET_COLUMNS_TYPE_MAP, parse_numeric_type_precision_and_scale`; lowercase + strip the leading word of the type token (e.g. `"decimal(10,2)"` → `"decimal"`), look it up in the map, special-case `decimal` via `parse_numeric_type_precision_and_scale`, instantiate the mapped class, and fall back to `sa_types.NullType()` for any unmapped token (symmetric with the default-catalog path at line 211). Keep the import local to the method or guard it so non-Databricks paths don't import the databricks package. Update the method docstring (and `get_columns_info`/`get_column_statistics` docstrings) to state the cross-catalog path now returns a TypeEngine and fires the fast path. Keep complexity ≤15 — extract a small `_databricks_type_string_to_engine` helper if needed. **Done: commit `1dedd71`, module-level `_databricks_type_string_to_engine` helper (bare-decimal guarded), docstrings updated.**
- [X] T014 [US1] **CONTRACT CHECK (FR-014/SC-005)**: converting to a TypeEngine changes the `data_type` response field on the cross-catalog path from the raw lowercase DESCRIBE string (`"int"`, `"string"`) to `str(TypeEngine)` (`"INTEGER"`, `"VARCHAR"`). This *converges* cross-catalog onto the format the default-catalog Databricks path already emits (it already does `str(type_obj)` at `_build_stats_from_describe_extended:493` and `get_column_statistics:515`). Confirm this is the intended convergence (not a regression), document the `data_type` format change explicitly in findings.md with the FR-014 rationale, and grep `tests/` for any assertion pinning a cross-catalog `data_type` to a lowercase string — update such tests to the converged format and note them. **Done: documented in commit msg + findings.md. Grep found NO cross-catalog `get_column_data_type` test pinning lowercase — only `_reflect_source_column` FK path (`"bigint"`, separate fn, unchanged) and the new WR-05 test asserting converged `"INTEGER"`. No test edits required.**
- [X] T015 [US1] **LIVE (SC-008)**: against the live Databricks warehouse via `dbmcp-test` (reconnect first), call `get_column_info` on a cross-catalog table for one numeric + one string column. Confirm the response now comes via the precomputed DESCRIBE EXTENDED stats (fast path fired) and the keys/shape match what Tier-2 returned before. Capture before/after output in findings.md as the SC-008 evidence. **DONE after server restart: `samples.tpch.customer` cross-catalog now returns uppercase `str(TypeEngine)` data_type (BIGINT/VARCHAR/NUMERIC(18,2)) + total_rows=0 + null mean/std — fast path fired, shape preserved. Before/after table in findings.md. SC-008 met.**

### TD-03 closure

- [X] T016 [US1] Strike TD-01, TD-02, TD-03 from `specs/TECH-DEBT.md` per the file's own convention (move to resolved / mark struck), referencing the commits from T005/T007/T008-T015 (FR-009/SC-001). If IN-04's message-template residue was logged rather than fixed (T011), add that new entry to TECH-DEBT.md in the same edit. **Done: all three struck (strikethrough headers + resolution banners, detail retained for provenance, commit refs cited); IN-04 residue added as new open TD-04.**

**Checkpoint**: All known debt resolved, tested, live-validated where reachable (only TD-02
corp-MITM probe deferred), struck from TECH-DEBT.md. **MVP complete and independently shippable.**

---

## Phase 4: User Story 2 — Full `src/` review + simplification sweep (Priority: P2)

**Goal**: Every one of the 34 `src/` modules reviewed for correctness bugs and
reuse/simplification/efficiency cleanups (prior 15.1 review covered only 5). Every finding
dispositioned per the triage bar.

**Independent Test**: findings.md `src_modules_reviewed == src_modules_total` (34); every
`SRC-NN` finding has a disposition; correctness fixes have regression tests; suite green ≥85%.

> Runs AFTER US1 so the sweep reviews post-fix code (D-07). Triage bar (clarify Q1):
> correctness bugs fixed always (+ regression test); simplifications fixed only when local to
> TD-touched code; larger refactors logged to TECH-DEBT.md/BACKLOG.md with provenance.
>
> **Review criteria for each module (T017-T020)** — flag against these, disposition per the
> triage bar above (most are `logged`, not in-scope to fix): correctness bugs; reuse/DRY and
> simplification opportunities; efficiency (no I/O in loops where batch exists — Constitution
> V); and the Constitution VI clarity budgets the `check_complexity.py` gate does NOT catch —
> **function length >50 lines, >5 parameters, nesting >2-3 levels, names/comments that restate
> rather than explain WHY**. These line/param/clarity budgets are review-surfaced findings
> (logged unless local to TD-touched code), not a blocking gate like complexity ≤15.

- [X] T017 [US2] Review `src/analysis/` modules (`column_stats.py`, `_sql.py`, `pk_discovery.py`, `fk_candidates.py`, `__init__.py`) — already partly touched by US1, so review the rest for correctness + local simplifications. Record each finding as `SRC-NN` (location, severity, description, disposition); check the modules off in the coverage checklist. **Done: SRC-06/07/08/10/13 + verifieds. 0 correctness bugs; per-column query-in-loop + cross-catalog constraint dup are the substantive items.**
- [X] T018 [US2] Review `src/db/` modules (`connection.py`, `dialects/*.py`, `identifiers.py`, `metadata.py`, `validation.py`, and the rest). Record `SRC-NN` findings + disposition; check off. **Done: SRC-01/02/05/09/11/12/15/21-27/29. 0 correctness bugs on reachable paths; TD-02 ca_bundle verified consistent across both call sites.**
- [X] T019 [US2] Review `src/mcp_server/` modules (`analysis_tools.py`, `schema_tools.py`, `query_tools.py`, server bootstrap, and the rest). Record `SRC-NN` findings + disposition; check off. **Done: SRC-03/04/14/30. `list_tables` multi-schema pagination (SRC-03) verified a real wrong-result edge but contract-sensitive → logged TD-08. IN-04/TD-04 not re-reported.**
- [X] T020 [US2] Review all remaining `src/` modules not covered by T017-T019 (top-level `src/*.py` incl. `metrics.py` — note the known `Generator` import nit — and any `config`/util modules) until the coverage checklist is 100% checked. Record `SRC-NN` findings + disposition. **Done: SRC-16/17/18/19/20/28. CORRECTION: `src/metrics.py` was deleted (commit `1fda3e7`) — the `Generator` nit is fully resolved, project memory stale. `CredentialFilter` IS wired (server.py:26) — reviewer claim corrected. 34/34 modules checked off.**
- [X] T021 [US2] Apply the in-scope fixes surfaced by T017-T020: every correctness bug gets a fix + regression test (red-green) and a `fixed` disposition citing commit+test; simplifications local to US1-touched code get applied; everything else gets a `logged` disposition citing the TECH-DEBT/BACKLOG ID it was moved to. Re-run all four gates. Live-validate any behavioral fix against StemSoftClinicTest/Databricks where reachable (SC-006); if a fix would change a tool contract, surface the delta explicitly before landing (FR-014/Edge Cases). **Done (no-op with rationale): the sweep found 0 reachable correctness bugs and 0 simplifications local to US1-touched code, so per the triage bar all 30 findings are `logged` (TD-05…TD-09 in TECH-DEBT.md). US2 lands no `src/`/`tests/` change → four gates unaffected; suite state holds at the US1-close 1150/166/91.92%.**

**Checkpoint**: 100% of `src/` reviewed and checked off; every `SRC-NN` finding dispositioned;
gates green.

---

## Phase 5: User Story 3 — Full `tests/` review + simplification sweep (Priority: P3)

**Goal**: `tests/` reviewed for redundancy, shallow coverage, and intent-vs-implementation
drift. Redundant/shallow tests consolidated, implementation-coupled tests refactored to intent,
hard-to-write tests captured as design signals. Coverage never drops below 85%.

**Independent Test**: coverage ≥85% after consolidation; suite passes; before/after counts
recorded (SC-007); every `TST-NN` finding dispositioned.

> Runs LAST (D-07): US1/US2 add and remove tests, so the suite must stabilize first.

- [X] T022 [US3] Review `tests/` for redundancy and shallow coverage: identify tests asserting identical behavior and tests that assert nothing meaningful. Record each as `TST-NN` (location, severity, description) in the findings.md `tests/` section. Do not change code yet. **Done: 4 parallel reviewers over all 70 files. Redundancy/shallow items: TST-A01/A02 (dead helpers, subset dup), B01/B10/C05 (verbatim helper, parametrizable suites), D03/D05/D06 (assert-True, dead skip-stubs), D07/08/09/10 (cross-suite NFR/validation/convert dups).**
- [X] T023 [US3] Review `tests/` for intent-vs-implementation drift (tests coupled to implementation detail rather than observable behavior) and for hard-to-write tests that signal a design problem in the code under test. Record `TST-NN` findings; for each design-signal, note whether the underlying issue is in-scope (fix) or logged (FR-013). **Done: drift items TST-A08 (SQL-spacing string-surgery), B02 (docstring contradicts assert), C01 (security-coverage gap), C02/D13 (doc drift); design signals B03 (5-collaborator patch stack), B09 (dual-patched error), C06 (import-error sentinel) — all test-ergonomic, logged to TD-10 (no new `src/` debt). Verified-OK: load-bearing ODBC/ca_bundle spies, IDENT-02 trio, layered catalog-required tests, dual fixture families.**
- [X] T024 [US3] Apply the `tests/` dispositions: consolidate redundant tests WITHOUT dropping coverage <85% (re-check `--cov` after each consolidation — back out any that would breach the floor, per Edge Cases); refactor implementation-coupled tests to encode intent (or document the coupling as deliberate); fix in-scope design signals, log the rest. Each finding gets `fixed`/`verified`/`logged`. Record before/after passing/skipped counts and coverage in findings.md (SC-007). **Done: 8 fixed (TST-D01 SyntaxWarning removed; A02 subset-dup deleted; D03 assert-True → doc comment; A01 3 dead helpers deleted; C01 MSSQL `]`-escape security test ADDED; B02/C02/D13 docstrings corrected), 1 logged→TD-08 (D02), 13 logged→TD-10 (new entry). Four gates green: 1149p/166s, cov 91.92% (unchanged, floor held), ruff clean, complexity max=15. SC-007 before/after table in findings.md.**

**Checkpoint**: `tests/` measurably leaner/clearer where drift was found; no net coverage loss;
every `TST-NN` finding dispositioned.

---

## Phase 6: Polish & Cross-Cutting Concerns (phase closure)

**Purpose**: Verify all success criteria and close the ledger.

- [X] T025 Close findings.md: set `src_modules_reviewed = src_modules_total = 34`; ensure `dispositions.fixed + verified + logged == findings.total` (no open finding); confirm every `fixed` row cites a commit+test and every `logged` row cites a TECH-DEBT/BACKLOG ID (data-model.md close-time invariants → SC-002). **Done: frontmatter reconciles 8 fixed + 0 verified + 44 logged = 52 total (30 SRC + 14 TST logged). Added commit `28cbd68` to the TST-D01 row and a close-time invariant note to the US3 counts line citing the commit for all 8 fixes; modules already 34/34. SC-002 invariants hold.**
- [X] T026 [P] Run the full quickstart.md "Definition of done" checklist and the live-validation cheatsheet end-to-end: all four gates pass; SC-008 fast-path evidence captured; the 9 tool contracts confirmed stable (FR-014/SC-005) except the documented WR-05 `data_type` convergence; only the TD-02 corp-MITM probe deferred (SC-006). **Done: all four gates re-run green at HEAD `28cbd68` (1149p/166s, cov 91.92%, ruff src/ clean, complexity max=15). SC-008 cross-catalog fast-path before/after captured in findings.md live-evidence log; MSSQL default-path regression confirmed (`dbo.PerformedActs`); 9 contracts stable except the documented WR-05 `data_type` convergence; only TD-02 corp-MITM probe deferred (FR-017).**
- [X] T027 [P] Update project memory/registries as needed: confirm `specs/TECH-DEBT.md` no longer lists TD-01/02/03; note the test-count/coverage delta vs the T002 baseline for the next session's reference. **Done: TECH-DEBT.md lists TD-01/02/03 only as struck/resolved (verified). Project memory updated: test count 1119→1149 / 91.92% recorded; corrected the stale `src/metrics.py` Generator-nit point (file deleted in `1fda3e7`, verified absent). Baseline delta: T002 baseline 1138p/146s/91.33% → close 1149p/166s/91.92% (+11 net pass after US1 add/US3 trim, +20 skipped from dialect markers, +0.59pp cover).**

---

## Phase 7: Post-close validation follow-ups (TD-11/TD-12)

**Purpose**: Resolve the two Databricks defects surfaced by the live *adversarial* MCP
validation run on 2026-06-02 (after Phase 6 closed). Logged first as TD-11/TD-12 (commit
`4491326`), then fixed here — they are follow-on findings from 012's own validation, kept in
012's ledger rather than opening a new feature. This reconciles the close-time caveat that the
"9 tool contracts stable" line (T026) had not caught TD-11.

- [X] T028 TD-11 (high): Databricks `get_column_info` fast path shipped `total_rows=0` +
  `null_percentage=0.0` next to a populated `null_count` (self-contradictory), a regression
  exposed by WR-05 (T012–T015) making the fast path fire. Red→green→refactor: fast path now
  issues one `COUNT(*)` (metadata-cheap on Delta, confirmed live read-only) for `total_rows`
  and derives `null_percentage`; mean/stddev stay `None` by design (intrinsically absent from
  columnar metadata) and are now documented in the contract. Closed the coverage gap
  (`total_rows`/`null_percentage` now asserted on the fast path). `src/analysis/column_stats.py`
  + `tests/unit/test_column_stats.py`. **Done: commit `824b6eb`; struck from TECH-DEBT.md.**
- [X] T029 TD-12 (low): clean bad-catalog error envelopes. Shared `_raise_if_missing_catalog`
  helper keys on the `NO_SUCH_CATALOG_EXCEPTION` marker (SQLSTATE 42704, confirmed live) →
  clean `ValueError("Catalog 'X' not found")` across both SHOW-path methods + `table_exists`;
  resolver-path message now names the catalog. Other `SQLAlchemyError`s propagate unchanged.
  `src/db/metadata.py`, `src/mcp_server/analysis_tools.py` + `test_metadata.py`,
  `test_analysis_tools_helpers.py`. **Done: commit `663b03d`; struck from TECH-DEBT.md.**
- [ ] T030 Four gates re-run green (1155p/168s, cov 91.94%, ruff `src/` clean, complexity
  max=15 — **done**); live re-probe of `dbmcp-test` against the warehouse after `/mcp` reload
  to confirm real `total_rows`/consistent `null_percentage`/null mean+stddev (TD-11) and clean
  `Catalog 'X' not found` envelopes (TD-12); MSSQL Tier-2 path unaffected. **Gates done;
  live probe pending `/mcp` reload.**

---

## Dependencies & Execution Order

### Phase dependencies

- **Setup (Phase 1)**: no dependencies — start immediately.
- **Foundational (Phase 2)**: none (empty).
- **US1 (Phase 3)**: after Setup. The MVP — independently shippable.
- **US2 (Phase 4)**: after US1 (reviews post-fix code — D-07).
- **US3 (Phase 5)**: after US2 (suite must stabilize — D-07).
- **Polish (Phase 6)**: after US3.

### Within US1 (ordered, mostly sequential — same files)

- TD-02 (T004→T005) and TD-01 (T006, T007) are independent of each other.
- WR-01 (T008), WR-02 (T009), IN-01 (T010) all touch `column_stats.py`/`_sql.py` — sequential to avoid same-file churn.
- IN-02/03/04 (T011) is verify-mostly, independent.
- WR-05 (T012→T013→T014→T015) is a strict chain (red→green→contract→live) and lands as its own commit AFTER the robustness fixes.
- Closure (T016) last in US1.

### Parallel opportunities

- **Setup**: T002 ‖ T003 (after T001 creates the ledger).
- **TD-01**: T006 ‖ T007 (same file, independent test functions — can be written together).
- **US2 review**: T017 ‖ T018 ‖ T019 ‖ T020 are different module groups — review can fan out; T021 (the fixes) is the join point.
- **Polish**: T026 ‖ T027 after T025.

### Parallel example — US2 review fan-out

```text
Task: "Review src/analysis/ modules"          # T017
Task: "Review src/db/ modules"                 # T018
Task: "Review src/mcp_server/ modules"         # T019
Task: "Review remaining src/ modules"          # T020
# join → T021 applies the triaged fixes
```

---

## Implementation Strategy

### MVP first (US1 only)

1. Phase 1 Setup (ledger + baseline).
2. Phase 3 US1 — close TD-01/02/03, live-validate WR-05, strike from TECH-DEBT.md.
3. **STOP and VALIDATE**: suite green ≥85%, gates pass, SC-001/SC-008 met. Shippable here.

### Incremental delivery

- US1 delivers the known debt resolution (value even if sweeps find nothing).
- US2 adds `src/`-wide correctness/cleanup on top.
- US3 leaves the test suite leaner. Each story is independently testable and adds value without
  breaking the prior.

---

## Notes

- `[P]` = different files, no incomplete dependency.
- Every code change is red-green-refactor with the four gates green before commit (FR-018).
- The complexity gate is `scripts/check_complexity.py` (≤15), NOT bare `complexipy`; CI lints
  `src/` only. A fix that would cross the gate is refactored under it, never bypassed.
- Reconnect `dbmcp-test` after merging any `src/` change before live-probing.
- The single behavioral/contract change in the whole phase is WR-05's `data_type` convergence
  (T013/T014) — it is documented, not silent (FR-014/SC-005).
