---
id: 260507-e8m
title: "Fix all 8 complexity violations flagged by CI complexipy gate"
status: complete
mode: quick
created: 2026-05-07
completed: 2026-05-07
---

# 260507-e8m: Fix all 8 complexity violations — SUMMARY

## Result

CI complexipy gate is green. All 8 functions now score ≤ 15 cognitive
complexity. `MAX_COMPLEXITY = 15` in `scripts/check_complexity.py` was not
changed. No public APIs were modified; all refactors are behavior-preserving
extract-method splits.

## Per-function results

| # | File::Function | Before | After | Commit |
|---|----------------|--------|-------|--------|
| 1 | `src/db/metadata.py::MetadataService::_parse_databricks_table_properties` | 26 | ≤15 | `f026ca0` |
| 2 | `src/db/connection.py::ConnectionManager::connect_with_config` | 23 | ≤15 | `2e7b1b9` |
| 3 | `src/mcp_server/schema_tools.py::connect_database` | 22 | ≤15 | `a3117be` |
| 4 | `src/analysis/column_stats.py::ColumnStatsCollector::get_columns_info` | 18 | ≤15 | `7fc0531` |
| 5 | `src/analysis/pk_discovery.py::PKDiscovery::get_structural_candidates` | 16 | ≤15 | `2e1559e` |
| 6 | `src/db/dialects/mssql.py::MssqlDialect::create_engine` | 16 | ≤15 | `de8e433` |
| 7 | `src/db/metadata.py::MetadataService::_collect_objects_from_schema` | 16 | ≤15 | `be992eb` |
| 8 | `src/db/query.py::QueryService::_run_query` | 16 | ≤15 | `6bbc680` |

Plus one follow-up style commit: `76bc6c1` — ruff UP037 cleanup on the
`_build_pool_kwargs` annotation introduced in Task 6.

## Extraction strategy used per task

1. **_parse_databricks_table_properties** — Extracted `_process_dte_row`
   (per-row dispatcher that mutates accumulators), `_classify_dte_row` (pure
   section classifier), and `_apply_dte_detail_row` (pure key-map applier).
   Needed one extra extraction beyond the plan (`_process_dte_row`) because
   the plan's two-helper split still scored 16; pulling the full loop body
   into `_process_dte_row` brought the main function well under.
2. **connect_with_config** — Extracted three per-config-type dispatchers as
   planned (`_connect_mssql_from_config`, `_connect_generic_from_config`,
   `_connect_databricks_from_config`). Main is now a small isinstance
   dispatcher with `ValueError` fallthrough.
3. **connect_database** — Extracted `_connect_by_name`, `_connect_by_url`,
   and `_connect_error_response` as planned. Named-connection path can
   short-circuit with an error dict (config parse failure / missing name);
   outer `_sync_connect` handles the sentinel.
4. **get_columns_info** — Extracted `_resolve_columns_to_analyze` as
   planned.
5. **get_structural_candidates** — Extracted both helpers (`_list_all_columns`,
   `_column_is_unique`) as the plan anticipated might be needed; main loop
   is now filter + delegate + build PKCandidate.
6. **MssqlDialect.create_engine** — Extracted both `_build_pool_kwargs` and
   `_build_azure_ad_creator` (plan said second was optional; it wasn't
   strictly required to get under 15, but the resulting main method is
   clearer and is safely under).
7. **_collect_objects_from_schema** — Extracted `_build_table_entry` as
   planned; returns `None` for filtered entries so the caller can skip.
8. **_run_query** — Extracted `_dispatch_result` (SELECT / safe-op / DDL
   routing) as planned.

## Final validation trio

```
uv run python scripts/check_complexity.py
  → Complexity check passed (max=15)

uv run ruff check src/
  → All checks passed!

uv run pytest -m "not integration and not slow" -q
  → 955 passed, 78 skipped, 9 deselected in 3.70s
```

Pre-existing ruff warning about `Generator` import in `src/metrics.py`
(noted in project memory) is still present and was not touched — it is not
on the list.

## Deviations from plan

- **Task 1 needed a 3rd helper.** The plan specified
  `_classify_dte_row` + `_apply_dte_detail_row`. That combination left the
  main function at 16 (just over). I added `_process_dte_row` — a per-row
  dispatcher that wraps both classifier + applier and mutates the caller's
  accumulators — which brings the main function well under. This is
  still behavior-preserving; no signature or return shape changed.
- **Ruff UP037 fixup commit.** The `_build_pool_kwargs` helper I added in
  Task 6 had a quoted forward-reference annotation (`"AuthenticationMethod"`)
  that ruff UP037 flagged, because that enum is already imported at module
  top. Fixed in a separate `style(260507-e8m)` commit (`76bc6c1`) rather
  than amending the Task 6 commit (per protocol: never amend).
- **Worktree base reset.** The worktree started at `ef4122b`, one commit
  behind main's `90273e7` (the pre-dispatch plan commit), so PLAN.md was
  not present. Because HEAD was on a per-agent branch (verified via the
  `worktree_branch_check`), `git reset --hard 90273e7` is the documented
  safe-recovery path. No protected-ref `update-ref` was used.

## Commits (chronological)

```
f026ca0  refactor(260507-e8m-01): reduce complexity of _parse_databricks_table_properties (26 → ≤15)
2e7b1b9  refactor(260507-e8m-02): reduce complexity of connect_with_config (23 → ≤15)
a3117be  refactor(260507-e8m-03): reduce complexity of connect_database (22 → ≤15)
7fc0531  refactor(260507-e8m-04): reduce complexity of get_columns_info (18 → ≤15)
2e1559e  refactor(260507-e8m-05): reduce complexity of get_structural_candidates (16 → ≤15)
de8e433  refactor(260507-e8m-06): reduce complexity of MssqlDialect.create_engine (16 → ≤15)
be992eb  refactor(260507-e8m-07): reduce complexity of _collect_objects_from_schema (16 → ≤15)
6bbc680  refactor(260507-e8m-08): reduce complexity of _run_query (16 → ≤15)
76bc6c1  style(260507-e8m): unquote AuthenticationMethod annotation in _build_pool_kwargs
```

## Self-Check

- [x] `src/db/metadata.py` modified (Tasks 1, 7) — verified via `git log`
- [x] `src/db/connection.py` modified (Task 2) — verified via `git log`
- [x] `src/mcp_server/schema_tools.py` modified (Task 3) — verified via `git log`
- [x] `src/analysis/column_stats.py` modified (Task 4) — verified via `git log`
- [x] `src/analysis/pk_discovery.py` modified (Task 5) — verified via `git log`
- [x] `src/db/dialects/mssql.py` modified (Task 6 + fixup) — verified via `git log`
- [x] `src/db/query.py` modified (Task 8) — verified via `git log`
- [x] All 9 commit hashes exist in `git log`
- [x] `uv run python scripts/check_complexity.py` exits 0
- [x] `uv run ruff check src/` exits 0
- [x] `uv run pytest -m "not integration and not slow"` passes (955 / 78 skip)

## Self-Check: PASSED
