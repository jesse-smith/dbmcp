---
phase: 15-unified-identifier-resolver-cross-dialect
plan: 04
subsystem: mcp-server-schema-tools
tags: [identifier-resolution, cross-dialect, catalog-gate, backward-incompatible, D-07, D-03]
requires:
  - "15-03: src.db.identifiers.resolve_identifier + _assert_catalog_allowed (import-only)"
provides:
  - "list_schemas / list_tables: D-07 catalog gate via shared _assert_catalog_allowed"
  - "get_table_schema: catalog/schema/table routed through resolve_identifier at the @mcp.tool boundary"
  - "No schema_name='dbo' signature defaults in schema_tools.py"
  - "Catalog docstrings on all 3 schema tools say 'Rejected on non-Databricks dialects'"
affects:
  - "MCP clients calling list_schemas/list_tables/get_table_schema with catalog on MSSQL/generic (now status=error, was silent-ignore)"
tech-stack:
  added: []
  patterns:
    - "Resolver/gate calls placed inside _sync_work so ValueError hits the existing except ValueError -> error_message boundary (D-03)"
    - "table_name-less tools (list_schemas, list_tables) use the shared _assert_catalog_allowed instead of an inline gate message"
key-files:
  created: []
  modified:
    - "src/mcp_server/schema_tools.py"
    - "tests/unit/test_async_tools.py"
    - "tests/staleness/tool_invoker.py"
decisions:
  - "list_tables enforces only the bare catalog gate (it has schema_filter, no per-table table_name) — confirmed no resolve_identifier needed there"
  - "Staleness fixture for get_table_schema upgraded to a concrete resolver dialect because resolve_identifier now drives sqlglot.to_table at the success path"
metrics:
  duration: "~6 min"
  completed: "2026-05-28"
  tasks: 2
  files: 3
requirements: [IDENT-03, IDENT-04, IDENT-07]
---

# Phase 15 Plan 04: Wire Resolver into Schema Tools Summary

Wired the Plan-03 identifier resolver into `get_table_schema` and the shared catalog gate into `list_schemas` + `list_tables`, finished the SC4 dbo sweep, and flipped all three catalog docstrings from "Ignored" to "Rejected" (D-07, backward-incompatible) — MSSQL/generic callers passing `catalog` now get a `status=error` response instead of silent-ignore.

## What Was Built

**Task 1 (`ce9f624`):**
- Imported `resolve_identifier` and `_assert_catalog_allowed` from `src.db.identifiers`.
- `get_table_schema`: changed signature `schema_name: str = "dbo"` → `schema_name: str | None = None`; inside `_sync_work`, fetch the dialect and call `resolved = resolve_identifier(table_name, schema_name, catalog, dialect)`, then pass `resolved.table / resolved.schema / resolved.catalog` into `table_exists` and `get_table_schema`. Docstring catalog line flipped to "Rejected".
- `list_tables`: enforces the D-07 catalog gate inside `_sync_work` via `_assert_catalog_allowed(catalog, dialect)` (shared helper — no inline message); existing `schema_filter`/`catalog` passthrough unchanged. Docstring flipped to "Rejected". (No `dbo` default existed — it uses `schema_filter`.)

**Task 2 (`500f37d`):**
- `list_schemas`: gates catalog inside `_sync_work` via `_assert_catalog_allowed(catalog, dialect)`; docstring flipped to "Rejected".
- Added `TestCatalogGateD07` to `test_async_tools.py`: parametrized assertion that all 3 schema tools return `status=error` ("catalog is not supported") when `catalog` is passed on a mocked shallow (MSSQL-like, depth=2) dialect, plus a `get_table_schema` schema-conflict test (`table_name="a.b"` vs `schema_name="c"` → "Conflicting schema").

## Verification Results

- `uv run pytest tests/unit/test_async_tools.py` — 35 passed.
- Full suite `uv run pytest tests/` — 1050 passed, 78 skipped.
- `grep 'schema_name: str = "dbo"' src/mcp_server/schema_tools.py` — none.
- `grep -c 'Ignored for non-Databricks'` — 0.
- `grep -c 'resolve_identifier'` — 2 (import + get_table_schema).
- `grep -c '_assert_catalog_allowed'` — 3 (import + list_schemas + list_tables).
- `grep -c 'Rejected on non-Databricks dialects'` — 3.
- `uv run ruff check src/mcp_server/schema_tools.py` — clean (no new warnings).

## Deviations from Plan

### Auto-fixed Issues

**1. [Rule 1 - Test fixture bug] Staleness mock dialect insufficient after resolver wiring**
- **Found during:** Task 2 (full-suite regression check).
- **Issue:** `tests/unit/test_staleness.py::test_success_path_fields_match_docstring[get_table_schema]` failed with "missing from response: ['table']". Root cause: `tests/staleness/tool_invoker.py::_get_table_schema_success_mocks` patched `get_dialect` to a bare `MagicMock()`. `get_table_schema` now calls `resolve_identifier`, which invokes `sqlglot.to_table(table_name, dialect=dialect.sqlglot_dialect)`. A bare MagicMock raises `ValueError("Invalid dialect type...")`, so the tool returned an error response (no `table` key) instead of the success shape. Production code is correct; the fixture's mock was simply too thin for the new resolver path.
- **Fix:** Added `_mock_resolver_dialect()` (name="mssql", sqlglot_dialect="tsql", max_identifier_depth=2, default_schema="dbo") and wired it into both `_get_table_schema_success_mocks` and `_get_table_schema_error_mocks`.
- **Files modified:** `tests/staleness/tool_invoker.py`
- **Commit:** `500f37d`
- **Verified:** staleness suite now 21 passed; full suite 1050 passed.

`list_schemas` / `list_tables` staleness mocks were left as bare MagicMocks: their success-path invocations pass no `catalog`, so `_assert_catalog_allowed(None, dialect)` short-circuits on the falsy catalog and never touches the mock's attributes.

## Out-of-Scope / Pre-existing

- Pre-existing ruff lint in test files, NOT introduced by this plan (confirmed identical at HEAD~1):
  - `tests/unit/test_async_tools.py`: 2x E402 + 1x I001 (mid-file `import pytest` / `from sqlalchemy.exc import SQLAlchemyError` at lines 272-273).
  - `tests/staleness/tool_invoker.py`: 1x I001 + 2x F841 (unused `mock_engine` in `_get_column_info`/`_find_*` mocks, lines 122/288).
- These are out of scope (not caused by the current tasks) and were not modified.

## Threat Model Compliance

- **T-15-08 (catalog silent-ignore):** mitigated — D-07 shared gate now rejects `catalog` on `max_identifier_depth < 3`; tested via `TestCatalogGateD07` for all 3 tools.
- **T-15-09 (resolver ValueError crashing tool):** mitigated — resolver/gate calls placed inside `_sync_work`, caught by the existing `except ValueError -> error_message` wrapper on all 3 tools; verified by the new error-response tests.
- **T-15-07 (crafted table_name):** unchanged — resolver decomposes only; downstream `quote_identifier` remains the injection defense. `src/db/identifiers.py` was NOT edited (import-only dependency).

No new threat surface introduced.

## Known Stubs

None.

## Self-Check: PASSED

- FOUND: src/mcp_server/schema_tools.py (modified)
- FOUND: tests/unit/test_async_tools.py (modified)
- FOUND: tests/staleness/tool_invoker.py (modified)
- FOUND commit: ce9f624 (Task 1)
- FOUND commit: 500f37d (Task 2)
