---
phase: 15-unified-identifier-resolver-cross-dialect
plan: 06
subsystem: mcp-tools
tags: [identifier-resolver, databricks, catalog, analysis-tools, D-14]
requires: ["15-02", "15-03", "15-05"]
provides:
  - "find_pk_candidates routes table_name/schema_name/catalog through resolve_identifier (D-14)"
  - "find_fk_candidates routes table_name/schema_name/catalog through resolve_identifier (D-14)"
  - "Databricks-only catalog param on both tools (gated on non-Databricks)"
  - "Zero schema_name='dbo' signature defaults across src/mcp_server/ (categorical SC4)"
  - "D-12 boundary matrix spans all 7 resolver-routed tools"
affects:
  - src/mcp_server/analysis_tools.py
  - tests/unit/test_async_tools.py
  - tests/staleness/tool_invoker.py
tech-stack:
  added: []
  patterns:
    - "resolve_identifier at the @mcp.tool boundary inside _sync_work (mirrors get_column_info, Plan 05)"
    - "schema_name: str | None = None (dialect default_schema fills) instead of hardcoded 'dbo'"
    - "catalog: str | None = None at end of signature; gated by resolver on shallow dialects"
key-files:
  created: []
  modified:
    - src/mcp_server/analysis_tools.py
    - tests/unit/test_async_tools.py
    - tests/staleness/tool_invoker.py
decisions:
  - "find_pk/fk use the Inspector path bound to the connection's default catalog (KISS, same as get_column_info); resolver GATES catalog rather than threading it cross-catalog through the Inspector"
  - "Boundary tests extended via parallel class methods (the existing in-file pattern) rather than a separate parametrization, keeping the D-12 matrix consistent with Plans 04/05"
metrics:
  duration: ~25m
  completed: 2026-05-28
  tasks: 2
  files_changed: 3
  commits: 3
---

# Phase 15 Plan 06: Full namespace-awareness for find_pk_candidates and find_fk_candidates (D-14) Summary

Made `find_pk_candidates` and `find_fk_candidates` full resolver-routed tools — dropping their `schema_name="dbo"` defaults, adding a Databricks-only `catalog` param, and threading `table_name`/`schema_name`/`catalog` through `resolve_identifier` — bringing the total from 5 to 7 resolver-routed tools and closing the categorical SC4 gap (zero `dbo` defaults anywhere in `src/mcp_server/`).

## What Was Built

**Task 1 — Sweep dbo + add catalog + resolver routing (commit 99191dd):**
- `find_pk_candidates`: `schema_name: str = "dbo"` → `schema_name: str | None = None`; added `catalog: str | None = None`. `_sync_work` now calls `resolve_identifier(table_name, schema_name, catalog, dialect)` before the Inspector calls and uses `resolved.schema`/`resolved.table` for `get_table_names`, `PKDiscovery`, the success payload, and the not-found error message.
- `find_fk_candidates`: same signature sweep + `catalog` param. `_sync_work` resolves the identifier and uses `resolved.schema`/`resolved.table` for `get_table_names`, `get_columns`, `FKCandidateSearch`, the `source` block, and the not-found / column-not-found error messages.
- Docstrings updated to document dotted `table_name`, the dialect-default schema, and the gated `catalog` param (copied from `get_table_schema` / `get_column_info`).
- The shared `resolve_identifier` import already added by Plan 05 was reused (no duplicate import).

**Task 2 — Extend the D-12 boundary matrix to all 7 tools (commit 6ba1c46):**
- `TestCatalogGateBoundary`: added catalog-on-MSSQL error tests for both tools.
- `TestResolverConflictBoundary`: added `table_name="sales.orders"` + `schema_name="hr"` conflict tests for both tools.
- `TestDatabricksThreePartHappyPath`: added Databricks 3-part (`cat.sch.tbl`) tests asserting the resolved `schema="sch"`/`table="tbl"` reach `PKDiscovery` / `FKCandidateSearch` (via `get_table_names(schema="sch")`, `get_columns("tbl", schema="sch")`, and constructor kwargs).

## Verification

- `uv run pytest tests/unit/test_async_tools.py` — 43 passed.
- `grep -nE 'schema_name: str = "dbo"' src/mcp_server/analysis_tools.py` — no matches.
- `grep -rnE 'schema_name: str = "dbo"' src/mcp_server/` — no matches (categorical SC4 met for all 7 tools).
- `grep -c 'resolve_identifier' src/mcp_server/analysis_tools.py` — 4 (3 calls + 1 import).
- `uv run ruff check src/mcp_server/analysis_tools.py` — All checks passed.
- Full suite: **1065 passed, 78 skipped** in 39.51s.

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Bug] Staleness guard success mocks returned a None dialect, breaking find_pk/fk after resolver routing**
- **Found during:** Task 2 (full-suite regression check after Task 1)
- **Issue:** `tests/staleness/tool_invoker.py` `_find_pk_candidates_success_mocks` and `_find_fk_candidates_success_mocks` patched `get_dialect` to return `None`. Once `_sync_work` began calling `resolve_identifier(..., dialect)`, the None dialect produced an AttributeError → error response → `test_success_path_fields_match_docstring` drift for both tools. This is the same class of fix Plan 05 applied for `get_column_info`.
- **Fix:** Both success mocks now return `_mock_resolver_dialect()` (the resolver-compatible MagicMock already defined in the helper for `get_table_schema`/`get_sample_data`/`get_column_info`).
- **Files modified:** tests/staleness/tool_invoker.py
- **Commit:** 8d63cdd

## Cross-Catalog Inspector Limitation

Consistent with `get_column_info` (Plan 05): on Databricks the resolver GATES `catalog` (rejecting it on non-Databricks dialects), satisfying the D-14 gate requirement, but the SQLAlchemy Inspector used by `find_pk_candidates` / `find_fk_candidates` binds to the connection's **default catalog** (IDENT-01, set at connect time). Unlike `get_column_info`'s existence check, these two tools do **not** route catalog through `MetadataService` — their entire PK/FK discovery runs against the Inspector. Therefore a non-default `catalog` is validated and accepted on Databricks but does **not** redirect discovery to another catalog; cross-catalog PK/FK discovery requires connecting with that catalog as the default. This is the deliberate KISS posture for these inspector-direct tools.

## Deferred Issues

Pre-existing ruff warnings (present at base commit 08d712f, in code not touched by this plan; logged to `deferred-items.md`):
- `tests/unit/test_async_tools.py:281-282` — E402 module-level import not at top (mid-file import block introduced by Plans 04/05).
- `tests/staleness/tool_invoker.py` — I001 (import block, line 8), F841 (unused `mock_engine`, line 122), datetime.UTC alias (line 288).

## Threat Model Compliance

- T-15-14 (Tampering, resolved schema/table → Inspector): mitigated — Inspector parameterizes names; no string concatenation into SQL by these tools.
- T-15-15 (Spoofing/Elevation, new catalog param): mitigated — `catalog` gated by `resolve_identifier` (tested for both tools in `TestCatalogGateBoundary`).
- T-15-16 (DoS, resolver ValueError): mitigated — resolver call sits inside `_sync_work`; existing `except ValueError -> error_message` boundary catches it (tested in `TestResolverConflictBoundary`).

No new security surface introduced beyond the planned `catalog` param.

## Self-Check: PASSED

All modified files exist; all three task commits (99191dd, 6ba1c46, 8d63cdd) present in git history.
