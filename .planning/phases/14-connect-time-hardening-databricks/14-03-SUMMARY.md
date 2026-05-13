---
phase: 14-connect-time-hardening-databricks
plan: 03
subsystem: db.connection
tags: [databricks, ident-01, connection-layer, catalog]
requires:
  - "14-01: DatabricksDialect.create_engine ValueError + list_catalogs"
provides:
  - "ConnectionManager._require_databricks_catalog enrichment helper"
  - "connect_with_url and _connect_databricks_from_config both raise enriched ConnectionError listing accessible catalogs when catalog absent"
  - "D-18: line-499 'main' fallback removed from _connect_databricks_from_config"
affects:
  - src/db/connection.py
tech_added: []
patterns:
  - "ValueError catch alongside SQLAlchemyError catch in connect-layer try-blocks"
  - "Helper as private method on ConnectionManager (matches _test_connection / _register_engine placement)"
  - "Probe engine with placeholder catalog='system'; engine.dispose() in finally"
key_files:
  created:
    - .planning/phases/14-connect-time-hardening-databricks/14-03-SUMMARY.md
  modified:
    - src/db/connection.py
    - tests/unit/test_connect_with_config_databricks.py
decisions:
  - "Helper placed as private method on ConnectionManager (not standalone, not on dialect) — keeps IO-handling code with the rest of the connect layer."
  - "Probe placeholder catalog is exactly 'system' per plan recommendation. If 'system' is not present on a given workspace, the SQLAlchemyError branch yields the both-problems message — user still gets actionable feedback."
  - "URL path re-parses the URL via dialect._kwargs_from_url(sqlalchemy_url, {}) to surface host/http_path/token/schema for the helper. This avoids restructuring connect_with_url's existing dispatch."
  - "isinstance(dialect, DatabricksDialect) gate ensures non-Databricks ValueErrors propagate untouched (mssql etc. don't have list_catalogs)."
metrics:
  duration: ~30 minutes
  completed: 2026-05-13
---

# Phase 14 Plan 03: Connect-layer catalog enrichment Summary

Added `ConnectionManager._require_databricks_catalog` and wired it into both Databricks connect paths (`connect_with_url`, `_connect_databricks_from_config`). When the dialect-level `ValueError("Databricks catalog is required")` (introduced by Plan 01) fires, the helper builds a probe engine with `catalog="system"`, runs `SHOW CATALOGS` via `dialect.list_catalogs`, and raises `ConnectionError` whose message lists accessible catalogs (with truncation past 20). The original `ValueError` is chained via `__cause__`. D-18 line-499 `"main"` fallback is removed so named-config flows through the same enrichment.

## Tasks Executed

| # | Task | Commit | Files |
|---|------|--------|-------|
| 1 RED | Failing tests for config-path enrichment + D-18 | `b6fe3b3` | `tests/unit/test_connect_with_config_databricks.py` |
| 1 GREEN | Add helper, wire into config path, drop "main" line 499 | `0fd64a6` | `src/db/connection.py` |
| 2 RED | Failing tests for URL-path enrichment + non-Databricks pass-through | `53692b0` | `tests/unit/test_connect_with_config_databricks.py` |
| 2 GREEN | Wire helper into connect_with_url with isinstance gate | `4aea1a0` | `src/db/connection.py` |

## Exact Edits

### `src/db/connection.py`

- **Line 499** (`_connect_databricks_from_config`): `else "main"` → `else ""` (D-18). Empty string flows into `dialect.create_engine(catalog="")`, which raises the Plan 01 ValueError, which the new ValueError-catch routes to the helper.
- **Lines 487–545 (new method)**: `_require_databricks_catalog` placed immediately above `_connect_databricks_from_config`, between `_connect_generic_from_config` and the Databricks branch. Method body:
  ```python
  def _require_databricks_catalog(
      self,
      dialect,
      *,
      host, http_path, token, schema,
      orig_value_error: ValueError,
  ) -> None:
      hint = "Pass one via ?catalog= in the URL or catalog= in the config."
      probe_engine = None
      try:
          probe_engine = dialect.create_engine(
              host=host, http_path=http_path, token=token,
              catalog="system", schema=schema or "default",
          )
          catalogs = dialect.list_catalogs(probe_engine)
      except SQLAlchemyError as probe_exc:
          raise ConnectionError(
              f"Databricks connection requires a catalog, and SHOW CATALOGS "
              f"failed ({type(probe_exc).__name__}: {probe_exc}). {hint}"
          ) from orig_value_error
      except Exception as probe_exc:
          raise ConnectionError(
              f"Databricks connection requires a catalog, and probing "
              f"SHOW CATALOGS failed ({type(probe_exc).__name__}: {probe_exc}). "
              f"{hint}"
          ) from orig_value_error
      finally:
          if probe_engine is not None:
              try:
                  probe_engine.dispose()
              except Exception:
                  pass

      truncated = catalogs[:20]
      suffix = f" (and {len(catalogs) - 20} more)" if len(catalogs) > 20 else ""
      listing = ", ".join(truncated) if truncated else "(none)"
      raise ConnectionError(
          f"Databricks connection requires a catalog. "
          f"Accessible catalogs: {listing}{suffix}. {hint}"
      ) from orig_value_error
  ```
- **`_connect_databricks_from_config` try-block (~line 549–580 post-insert)**: New `except ValueError as ve:` branch added between `try` and the existing `except SQLAlchemyError as e:`. Calls helper, then `raise` (defensive — helper is NoReturn).
- **`connect_with_url` try-block (lines 354–384 area)**: New `except ValueError as ve:` branch added between the `except ConnectionError: raise` and the existing `except SQLAlchemyError as e:`. Imports `DatabricksDialect` lazily, gates on `isinstance(dialect, DatabricksDialect)`, calls `dialect._kwargs_from_url(sqlalchemy_url, {})` to surface the per-field kwargs, then invokes the helper. Non-Databricks `ValueError` re-raises naturally.

### `tests/unit/test_connect_with_config_databricks.py`

Added 7 tests (file grew from 2 to 9 active tests):
- `test_connect_with_config_empty_catalog_raises_enriched_connection_error`
- `test_connect_with_config_none_catalog_raises_enriched_connection_error`
- `test_connect_with_config_probe_failure_message_names_both`
- `test_connect_with_config_valid_catalog_does_not_invoke_helper`
- `test_connect_with_url_databricks_missing_catalog_raises_enriched`
- `test_connect_with_url_databricks_with_catalog_succeeds`
- `test_connect_with_url_non_databricks_value_error_not_routed_to_helper`

Plus a small helper `_patch_no_test_connection` to share `_test_connection` neutralization across tests.

## Discretionary Decisions

1. **Helper placement** — private method on `ConnectionManager`, immediately above `_connect_databricks_from_config`. Reads naturally with the surrounding connect-from-config code; no awkward forward references.
2. **URL path uses `_kwargs_from_url(sqlalchemy_url, {})`** — empty `original_kwargs` because the helper only needs the URL-derived values. Adds an extra parse on the failure path; cheap, and avoids restructuring `connect_with_url` to expose locals before the create_engine call.
3. **Defensive `raise` after helper** — helper is logically NoReturn but typed as `-> None` (simpler than importing `typing.NoReturn`). Trailing `raise` keeps type-checkers and human readers honest.
4. **Probe `engine.dispose()` wrapped in try/except** — best-effort cleanup; if a malformed mock or partially-constructed engine doesn't support dispose, we don't shadow the more important error. `pragma: no cover` since the happy path always disposes cleanly.
5. **`isinstance(dialect, DatabricksDialect)` import is lazy** — keeps the existing `connect_with_url` import surface intact (only `DialectStrategy`, `MssqlDialect` at module top). Inline import has near-zero cost on the failure path.

## Verification Results

- `uv run pytest tests/unit/test_connect_with_config_databricks.py -x` → **9 passed**
- `uv run pytest tests/ -q -m "not integration"` → **974 passed, 78 skipped, 7 deselected** (no regressions; +7 net new tests vs. pre-Plan-03 974−7=967 baseline from Plan 01)
- `uv run ruff check src/db/connection.py tests/unit/test_connect_with_config_databricks.py` → **All checks passed**

### Acceptance-criteria greps

- `grep -n 'else "main"' src/db/connection.py` → **0 matches** (D-18 confirmed)
- `grep -n "def _require_databricks_catalog" src/db/connection.py` → 1 match (line 487)
- `grep -c "_require_databricks_catalog" src/db/connection.py` → **3** (definition + config-path call + url-path call)
- `grep -n "isinstance(dialect, DatabricksDialect)" src/db/connection.py` → 1 match in `connect_with_url`
- `grep -n "safe_url = parsed_url.render_as_string" src/db/connection.py` → 2 matches (both unchanged from Plan 02 baseline)
- `grep -n 'Could not connect to {safe_url}' src/db/connection.py` → 2 matches (both unchanged)

## Deviations from Plan

None — plan executed exactly as written. The plan called out that Task 2 might require restructuring `connect_with_url` to surface kwargs; I chose the lighter-weight `_kwargs_from_url(sqlalchemy_url, {})` re-parse on the failure path, which the plan explicitly permitted ("If the current code … does not destructure … restructure so host/http_path/token/schema are available — keep the change minimal").

## Authentication Gates

None.

## Known Stubs

None — all changes are concrete implementations exercised by tests.

## TDD Gate Compliance

Plan-level type was `execute` with both tasks marked `tdd="true"`. RED→GREEN cycle observed for both:

1. `test(14-03)` — `b6fe3b3` (Task 1 RED) → `feat(14-03)` — `0fd64a6` (Task 1 GREEN)
2. `test(14-03)` — `53692b0` (Task 2 RED) → `feat(14-03)` — `4aea1a0` (Task 2 GREEN)

No REFACTOR commits — implementations were minimal.

## Self-Check

### Files claimed to be created/modified

- `src/db/connection.py` — **FOUND** (modified)
- `tests/unit/test_connect_with_config_databricks.py` — **FOUND** (modified)
- `.planning/phases/14-connect-time-hardening-databricks/14-03-SUMMARY.md` — **FOUND** (this file)

### Commits claimed

- `b6fe3b3` test(14-03): add failing tests for catalog-required enrichment in config path — **FOUND**
- `0fd64a6` feat(14-03): add _require_databricks_catalog helper and wire into config path — **FOUND**
- `53692b0` test(14-03): add failing tests for catalog-required enrichment in URL path — **FOUND**
- `4aea1a0` feat(14-03): wire _require_databricks_catalog into connect_with_url — **FOUND**

## Self-Check: PASSED
