---
phase: 15-unified-identifier-resolver-cross-dialect
plan: 05
subsystem: mcp-tools
tags: [identifier-resolver, catalog, databricks, get_sample_data, get_column_info]
requires:
  - "src.db.identifiers.resolve_identifier (Plan 03)"
  - "MetadataService.table_exists catalog gate (Phase 14 / metadata.py)"
provides:
  - "get_sample_data with catalog param + resolver routing (IDENT-05)"
  - "get_column_info with catalog param + resolver routing (IDENT-06)"
  - "QueryService.get_sample_data 3-part Databricks table reference"
affects:
  - "src/mcp_server/analysis_tools.py (find_pk/fk_candidates still pending Plan 06)"
tech-stack:
  added: []
  patterns:
    - "resolve_identifier at @mcp.tool boundary in _sync_work"
    - "quote_identifier per-segment for 3-part Databricks SQL (injection defense)"
    - "MetadataService.table_exists(catalog=) for Databricks cross-catalog existence"
key-files:
  created: []
  modified:
    - "src/db/query.py"
    - "src/mcp_server/query_tools.py"
    - "src/mcp_server/analysis_tools.py"
    - "tests/unit/test_query.py"
    - "tests/unit/test_async_tools.py"
    - "tests/staleness/tool_invoker.py"
decisions:
  - "get_column_info column stats bind to engine default catalog (IDENT-01); only the existence check is catalog-aware — documented cross-catalog limitation"
metrics:
  tasks-completed: 3
  files-modified: 6
  completed: 2026-05-28
requirements: [IDENT-05, IDENT-06]
---

# Phase 15 Plan 05: Catalog Param on get_sample_data / get_column_info Summary

Added the `catalog` parameter to `get_sample_data` (IDENT-05) and `get_column_info` (IDENT-06) — the last two namespace-aware tools that lacked it — routed both through `resolve_identifier` at their `@mcp.tool` boundaries (D-03), dropped their `schema_name="dbo"` signature defaults, and threaded the resolved catalog into the SQL/inspector paths so a Databricks 3-part `table_name` works end-to-end without `USE CATALOG` (SC3). The D-07 catalog gate is enforced by the resolver: MSSQL/generic callers passing `catalog` get a `status=error` response.

## What Was Built

### Task 1 — query.py 3-part Databricks SQL (commit 81866a6)
- Added `catalog: str | None = None` to `QueryService.get_sample_data` (after `columns`).
- When `catalog` is truthy AND `self._dialect.name == "databricks"`, builds `full_table_name` as a 3-part `` `cat`.`sch`.`tbl` `` reference; every segment quoted via `quote_identifier` (T-15-10 injection defense — no raw concatenation).
- 2-part (`schema.table`) and no-dialect (unqualified) paths unchanged.
- RED+GREEN tests in `TestGetSampleDataCatalogThreading` (test_query.py) assert the executed SQL contains the 3-part / 2-part / unqualified reference per case.

### Task 2 — catalog + resolver routing on both tools (commit 78d91f8)
- `get_sample_data` (query_tools.py): added `catalog: str | None = None`; changed `schema_name: str = "dbo"` → `str | None = None`; `_sync_work` now calls `resolve_identifier(table_name, schema_name, catalog, dialect)` and passes `resolved.table/schema/catalog` into `QueryService.get_sample_data`.
- `get_column_info` (analysis_tools.py): same param/default changes; `_sync_work` resolves the identifier and uses `resolved.schema/table` for the inspector + `ColumnStatsCollector`. For Databricks cross-catalog access, the existence check routes through `MetadataService.table_exists(..., catalog=resolved.catalog)` (mirrors `metadata.py:table_exists` `SHOW TABLES IN catalog.schema`).
- Imported `resolve_identifier` from `src.db.identifiers` in both tool files.
- `find_pk_candidates` / `find_fk_candidates` left untouched (see "Pending for Plan 06").

### Task 3 — boundary tests (commit 202f837)
- New test classes in test_async_tools.py: `TestCatalogGateBoundary`, `TestResolverConflictBoundary`, `TestDatabricksThreePartHappyPath` — covering both tools:
  - D-07 catalog gate: `catalog="x"` on MSSQL → `status=error`, message mentions catalog.
  - D-04 conflict: `table_name="sales.orders"` + `schema_name="hr"` → conflict error.
  - SC3 happy path: Databricks 3-part `table_name="cat.sch.tbl"` splits to catalog/schema/table and reaches `QueryService.get_sample_data` (kwargs) / `MetadataService.table_exists("tbl","sch",catalog="cat")` + `ColumnStatsCollector(schema_name="sch", table_name="tbl")`.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 3 - Blocking] Staleness mock harness broke on the new resolver call**
- **Found during:** Task 3 (full-suite regression check)
- **Issue:** `tests/staleness/tool_invoker.py` `_get_sample_data_success_mocks` / `_get_column_info_success_mocks` patched `get_dialect` to return a bare `MagicMock()`. With the new `resolve_identifier` call in `_sync_work`, `sqlglot.to_table(..., dialect=<MagicMock>)` failed, so both tools returned an error response — failing `test_staleness.py::test_success_path_fields_match_docstring[get_sample_data|get_column_info]`.
- **Fix:** Pointed both success mocks at the existing `_mock_resolver_dialect()` helper (created in Plan 04 for get_table_schema), which supplies concrete `sqlglot_dialect`/`max_identifier_depth`/`default_schema`/`name`.
- **Files modified:** `tests/staleness/tool_invoker.py`
- **Commit:** 202f837

**2. [Rule 3 - Blocking] Existing dialect-threading test fixture lacked resolver attributes**
- **Found during:** Task 2
- **Issue:** `test_get_sample_data_threads_dialect_into_metadata_and_query_services` used a `MagicMock` dialect that broke the new resolver parse, so `MetadataService` was never reached.
- **Fix:** Added resolver-compatible facts (`sqlglot_dialect="databricks"`, `max_identifier_depth=3`, `default_schema=None`) to the fixture.
- **Files modified:** `tests/unit/test_async_tools.py`
- **Commit:** 78d91f8

## Cross-Catalog Limitation (get_column_info)

`get_column_info` GATES catalog via the resolver (rejected on non-Databricks) and routes the **table-existence check** through the catalog-aware `MetadataService.table_exists`. However, the **column statistics** themselves are still computed via the SQLAlchemy Inspector + `ColumnStatsCollector`, which bind to the engine's **default catalog** (set at connect time, Phase 14 IDENT-01). Cross-catalog column profiling therefore requires connecting with the target catalog as the connection default. This satisfies IDENT-06's gate requirement; full cross-catalog stats are out of scope for this plan (KISS — no catalog-qualified inspector path is cleanly available).

## Pending for Plan 06 (analysis_tools.py state)

`find_pk_candidates` (analysis_tools.py:186) and `find_fk_candidates` (analysis_tools.py:290) are **unchanged** by this plan — both still carry `schema_name: str = "dbo"` defaults and do NOT route through the resolver or accept a `catalog` param. Plan 06 (D-14, depends_on 15-05) sweeps their dbo defaults and adds resolver routing + catalog. The `resolve_identifier` import is already present in analysis_tools.py for Plan 06 to reuse.

## Verification

- `uv run pytest tests/unit/test_async_tools.py tests/unit/test_query.py` — 120 passed.
- Full suite: `uv run pytest tests/` — 1059 passed, 78 skipped, 0 failures.
- `grep schema_name: str = "dbo" query_tools.py` — none; in analysis_tools.py only find_pk/fk_candidates remain (get_column_info clear).
- `grep -c catalog` — query_tools.py 5, analysis_tools.py 16.
- `grep -c resolve_identifier` — query_tools.py 2, analysis_tools.py 2.
- `ruff check` on the three src files — all checks passed; no new test-file warnings (pre-existing E402/I001/F841 in test harness files unchanged, out of scope).

## Threat Surface

All threats in the plan's register (T-15-10..13, T-15-SC) are mitigated as planned. No new security-relevant surface beyond the plan's `<threat_model>` was introduced. No threat flags.
