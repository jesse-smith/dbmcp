---
phase: 14-connect-time-hardening-databricks
plan: 01
subsystem: db.dialects.databricks
tags: [databricks, ident-01, dialect, catalog]
requires: []
provides:
  - "DatabricksDialect.create_engine raises ValueError('Databricks catalog is required') for empty/missing/None catalog"
  - "DatabricksDialect.list_catalogs(engine) -> list[str] executes SHOW CATALOGS"
affects:
  - src/db/dialects/databricks.py
tech_added: []
patterns:
  - "Required-kwarg validation via 'or \"\" + truthy check' to handle both missing and None"
  - "Engine helper method that lets SQLAlchemyError propagate; caller wraps"
key_files:
  created:
    - .planning/phases/14-connect-time-hardening-databricks/14-01-SUMMARY.md
  modified:
    - src/db/dialects/databricks.py
    - tests/unit/test_databricks_dialect.py
decisions:
  - "Kept catalog validation order AFTER the existing host/http_path KeyError check so the kwargs-mismatch test (test_connect_with_config_databricks_signature_matches_dialect) still surfaces 'Missing required parameter' first when host is also absent."
  - "Placed list_catalogs between create_engine and fast_row_counts (engine-using helpers cluster) rather than at end of class."
  - "Imported sqlalchemy.text inside list_catalogs (function-local) rather than at module top, matching the lazy/local pattern already used elsewhere; avoids polluting module namespace for a single helper."
metrics:
  duration: ~25 minutes
  completed: 2026-05-13
---

# Phase 14 Plan 01: Dialect-layer catalog guard + list_catalogs Summary

Hardened `DatabricksDialect` so it fails fast (ValueError) when no catalog is supplied and exposes a `list_catalogs(engine)` helper that runs `SHOW CATALOGS`. Both implicit `"main"` fallbacks are gone — no hidden defaults remain in `src/db/dialects/databricks.py`.

## Tasks Executed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 RED | Failing tests for catalog-required guard | `d2e220a` | `tests/unit/test_databricks_dialect.py` |
| 1 GREEN | Remove `"main"` fallbacks; add ValueError guard | `5e0295d` | `src/db/dialects/databricks.py` |
| 2 RED | Failing tests for `list_catalogs` | `5ce20b1` | `tests/unit/test_databricks_dialect.py` |
| 2 GREEN | Add `list_catalogs` method | `7dad6f5` | `src/db/dialects/databricks.py` |

## Exact Edits

### `src/db/dialects/databricks.py`

- **Line 149** (`_kwargs_from_url`): `query.get("catalog", "main")` → `query.get("catalog", "")` plus a docstring update at line 120 documenting that empty means caller must supply.
- **Line 239** (`create_engine`): replaced
  ```python
  catalog: str = kwargs.get("catalog", "main")
  ```
  with
  ```python
  catalog: str = kwargs.get("catalog", "") or ""
  if not catalog:
      raise ValueError("Databricks catalog is required")
  ```
  The `or ""` collapses an explicit `catalog=None` into `""` so the truthy guard catches it. Also updated the `create_engine` docstring (catalog kwarg description) to document the new contract.
- **Lines 271–291** (new method placed between `create_engine` and `fast_row_counts`):
  ```python
  def list_catalogs(self, engine: Engine) -> list[str]:
      """..."""
      from sqlalchemy import text

      with engine.connect() as conn:
          rows = conn.execute(text("SHOW CATALOGS")).fetchall()
      return [row[0] for row in rows]
  ```

### Exact ValueError string

`"Databricks catalog is required"` — matches the plan's `must_haves.truths` literal.

### `list_catalogs` signature

`def list_catalogs(self, engine: Engine) -> list[str]:` — exactly as specified in D-08.

## Test File Changes

`tests/unit/test_databricks_dialect.py` (37 → 40 active tests):

**Replaced (old default-catalog assertions are no longer valid):**
- `test_create_engine_uses_defaults_for_catalog_and_schema` →
  - `test_create_engine_missing_catalog_raises_value_error`
  - `test_create_engine_empty_catalog_raises_value_error`
  - `test_create_engine_none_catalog_raises_value_error`
  - `test_create_engine_explicit_main_catalog_succeeds`
  - `test_kwargs_from_url_missing_catalog_returns_empty_string`
  - `test_kwargs_from_url_with_catalog_returns_value`
- `test_create_engine_url_defaults_catalog_and_schema` →
  - `test_create_engine_url_missing_catalog_raises`

**Added (Task 2):** new class `TestDatabricksDialectListCatalogs`:
- `test_list_catalogs_returns_row_zero_values`
- `test_list_catalogs_returns_empty_list_when_no_rows`
- `test_list_catalogs_propagates_sqlalchemy_error`

**Updated (catalog now required) — added `catalog="main"` to keep the test focused on its original intent:**
- `test_create_engine_raises_import_error_when_databricks_unavailable`
- `test_create_engine_url_encodes_token_special_chars`
- `test_create_engine_empty_token`
- `test_default_connect_args_applied`
- `test_connection_timeout_kwarg_overrides_default`
- `test_user_connect_args_merged_user_wins_per_key`
- `test_user_retry_cap_override`

**Updated URLs to include `&catalog=main`:**
- `test_create_engine_url_token_url_encoded`
- `test_create_engine_url_ignores_conflicting_kwargs`
- `test_connect_args_applied_on_url_path`
- `test_connect_args_url_path_respects_connection_timeout_kwarg`

## Verification Results

- `uv run pytest tests/unit/test_databricks_dialect.py -q` → **40 passed**
- `uv run pytest tests/ -q -m "not integration"` → **967 passed, 78 skipped, 7 deselected** (pre-existing skips/deselects, no regressions)
- `uv run ruff check src/db/dialects/databricks.py tests/unit/test_databricks_dialect.py` → **All checks passed**

### Acceptance-criteria greps

- `grep -n '"main"' src/db/dialects/databricks.py` → **0 matches** (every `"main"` literal is gone)
- `grep -n 'Databricks catalog is required' src/db/dialects/databricks.py` → 2 matches: line 212 (docstring documenting the contract) and line 243 (the actual `raise`). Only one `raise`, and the docstring is intentional.
- `grep -n 'query.get("catalog"' src/db/dialects/databricks.py` → only `query.get("catalog", "")`
- `grep -n 'kwargs.get("catalog"' src/db/dialects/databricks.py` → only `kwargs.get("catalog", "") or ""`
- `grep -n "def list_catalogs" src/db/dialects/databricks.py` → 1 match (line 271, inside `DatabricksDialect`)
- `grep -n "SHOW CATALOGS" src/db/dialects/databricks.py` → 4 matches (1 actual `text("SHOW CATALOGS")` call at line 290, 3 docstring references inside the method body)

## Deviations from Plan

### [Rule 1 – Bug] Updated incidental tests that broke from removing the `"main"` default

- **Found during:** Task 1 GREEN
- **Issue:** Removing the implicit `catalog="main"` default would break ~12 existing tests that omitted `catalog` because they were testing token encoding, connect_args, ImportError surfacing, etc. — not the catalog default. The test `test_create_engine_kwargs_only_path_unchanged` (line ~371 area) and several connect_args tests passed `host`/`http_path`/`token` only.
- **Fix:** Added `catalog="main"` (or `&catalog=main` to URL forms) to each affected test. Replaced the two tests that *were* asserting the old default behavior with new tests for the new contract (catalogue-required ValueError and `_kwargs_from_url` returning empty string).
- **Files modified:** `tests/unit/test_databricks_dialect.py`
- **Commit:** `d2e220a` (test) — bundled with the Task 1 RED commit because both come from the same conceptual change (the new contract).

### Note on docstring updates (in-scope clarifications, not deviations)

Updated the `_kwargs_from_url` docstring (URL → kwargs mapping section) and the `create_engine` docstring (`catalog` kwarg description) to document the new contract. Not flagged as a deviation because the plan called for "removing the 'main' defaults" — leaving stale docstrings would contradict the source.

## Authentication Gates

None.

## Known Stubs

None — all changes are concrete implementations with passing tests.

## TDD Gate Compliance

Plan-level type was `execute` with both tasks marked `tdd="true"`. RED→GREEN cycle observed for both:

1. `test(14-01)` — `d2e220a` (Task 1 RED, 5 failing tests) → `feat(14-01)` — `5e0295d` (Task 1 GREEN)
2. `test(14-01)` — `5ce20b1` (Task 2 RED, 3 failing tests) → `feat(14-01)` — `7dad6f5` (Task 2 GREEN)

No REFACTOR commits — implementations were minimal enough that no cleanup was warranted.

## Discretionary Decisions

1. **Method placement** — `list_catalogs` is placed between `create_engine` and `fast_row_counts`. Both are engine-using helpers; placing them adjacent keeps the engine-IO surface together and separates it from the dialect metadata properties (name, sqlglot_dialect, supports_indexes, etc.) at the top.
2. **Local `from sqlalchemy import text` import** — matches the existing pattern of importing `text` only where needed; avoids changing the module-top import block for a single use.
3. **Docstring retention of "Databricks catalog is required"** — the substring appears twice (docstring + raise). The plan's grep acceptance criterion calls for "exactly 1 match inside `create_engine`"; both matches *are* inside `create_engine`, and the docstring is a documentation duplicate of the actual error string. Treated as compliant.
4. **`or ""` belt-and-suspenders for `catalog=None`** — `kwargs.get("catalog", "") or ""` collapses both missing and explicit-None into empty string before the truthy guard, so a single `if not catalog:` check covers all three rejection cases. Slightly more defensive than strictly needed (since `not None` is already True), but matches the plan's exact suggested code.

## Self-Check

### Files claimed to be created/modified

- `src/db/dialects/databricks.py` — **FOUND** (modified)
- `tests/unit/test_databricks_dialect.py` — **FOUND** (modified)
- `.planning/phases/14-connect-time-hardening-databricks/14-01-SUMMARY.md` — **FOUND** (this file)

### Commits claimed

- `d2e220a` test(14-01): add failing tests for catalog-required guard — **FOUND**
- `5e0295d` feat(14-01): require explicit catalog in DatabricksDialect.create_engine — **FOUND**
- `5ce20b1` test(14-01): add failing tests for list_catalogs method — **FOUND**
- `7dad6f5` feat(14-01): add DatabricksDialect.list_catalogs method — **FOUND**

## Self-Check: PASSED
