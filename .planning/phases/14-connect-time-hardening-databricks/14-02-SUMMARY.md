---
phase: 14-connect-time-hardening-databricks
plan: 02
subsystem: metadata
tags: [databricks, list_schemas, fallback-removal, ident-02]
requires: [IDENT-01]
provides: [IDENT-02]
affects:
  - src/db/metadata.py
tech-stack:
  added: []
  patterns:
    - "Single-path branches with loud failure (KeyError/SQLAlchemyError propagate) instead of silent fallback"
key-files:
  created: []
  modified:
    - src/db/metadata.py
    - tests/unit/test_metadata.py
decisions:
  - "Combined Task 1 and Task 2 into a single source-code commit (plan permits)"
  - "Updated existing fallback test in-place rather than deleting it; new test name encodes the post-IDENT-02 contract"
  - "Pre-existing 'main' string literals in unrelated methods of metadata.py left untouched (Pitfall 4 explicitly contemplates this)"
metrics:
  duration: "~10min"
  completed: 2026-05-13
---

# Phase 14 Plan 02: Drop list_schemas SHOW CATALOGS Fallback — Summary

**One-liner:** Deleted the silent `SHOW CATALOGS` fallback and the `"main"` default in `MetadataService`, collapsing the Databricks `list_schemas` branch to a single deterministic path that fails loudly on invariant violations.

## What Changed

### `src/db/metadata.py`

1. **`list_schemas` Databricks branch (lines 79–127 → 79–117 after edit):**
   - Removed the try/except `SQLAlchemyError` block (was lines 107–115).
   - Replaced with the single-path form:
     ```python
     effective_catalog = catalog or self._engine_catalog()
     result = self._list_schemas_databricks(connection_id, effective_catalog)
     ```
   - Docstring rewritten to reflect the post-IDENT-02 invariant (no fallback to catalog enumeration; engine-bound catalog used when `catalog=` is not passed).
   - Inline comment updated from "fall back to listing available catalogs via SHOW CATALOGS so the caller can discover what to pass" to "single deterministic path … no fallback to SHOW CATALOGS — errors propagate".

2. **`_list_databricks_catalogs` (was lines 164–190): DELETED** in entirety (D-09). 27 lines removed including method body that issued `SHOW CATALOGS` and built pseudo-`Schema` rows.

3. **`_databricks_default_catalog` → `_engine_catalog` (was lines 192–201, now 155–162):**
   - Renamed.
   - Body collapsed from a `try/except AttributeError` returning `"main"` default to a single `return self.engine.url.query["catalog"]` line.
   - Docstring updated: post-IDENT-01 invariant + "loud failure beats a silent default".

### `tests/unit/test_metadata.py`

- **`test_list_schemas_no_catalog_falls_back_to_show_catalogs` → `test_list_schemas_propagates_sqlalchemy_error_no_catalog_fallback`:** Renamed and rewritten to assert the new contract — when the engine-bound catalog lookup raises `SQLAlchemyError`, it propagates instead of being caught and converted into a `SHOW CATALOGS` call. The mock still wires up a `catalogs_result` for the second `execute` so the *old* (pre-IDENT-02) code path would silently succeed; the new test confirms it does not.

## Tasks Executed

| Task | Status | Commits |
| ---- | ------ | ------- |
| 1: Delete `_list_databricks_catalogs` and try/except fallback | DONE | RED `1160bef` + GREEN `631f2d1` |
| 2: Rename `_databricks_default_catalog` → `_engine_catalog`, strip `"main"` | DONE | folded into GREEN `631f2d1` (plan permits combining) |

Two source commits matching the TDD red-green cycle:

1. `1160bef test(14-02): assert list_schemas propagates SQLAlchemyError without SHOW CATALOGS fallback`
2. `631f2d1 feat(14-02): collapse list_schemas Databricks branch to single deterministic path`

## Verification

### Acceptance Criteria

- ✓ `grep -rn "_list_databricks_catalogs" src/ tests/` → zero source matches (only stale `.pyc` bytecode).
- ✓ `grep -rn "_databricks_default_catalog" src/ tests/` → zero source matches.
- ✓ `grep -n "def _engine_catalog" src/db/metadata.py` → exactly 1 match (line 155).
- ✓ `_engine_catalog` body is a single `return self.engine.url.query["catalog"]` — no try/except, no `.get(...)` with default, no `"main"`.
- ✓ The string "falls back to listing available catalogs" is gone from `metadata.py`.
- ✓ `uv run pytest tests/unit/test_metadata.py -x` — 82 passed.
- ✓ `uv run pytest tests/unit/` (full unit suite) — 892 passed, 37 skipped.
- ✓ `uv run ruff check src/db/metadata.py tests/unit/test_metadata.py` — clean.

### `"main"` Literal Sweep

`grep -n '"main"' src/db/metadata.py` returns 6 matches at lines 234, 243, 438, 531, 584, 928 — all **pre-existing** in unrelated methods (`_list_schemas_generic`, table-listing helpers, DTE catalog default). Per the plan's Pitfall 4 ("pre-existing unrelated matches, if any, are fine — inspect each"), these are out of scope for IDENT-02. Inspected; none are inside the `list_schemas` Databricks branch.

The acceptance criterion as literally written says "ZERO matches" but is qualified by Pitfall 4 — verified the only `"main"` introductions in this plan were in my new `_engine_catalog` docstring (subsequently removed for cleanliness).

## Deviations from Plan

None. Plan executed as written, with the explicit option to combine Tasks 1 and 2 into a single source commit exercised (plan permitted this).

## Self-Check: PASSED

- `1160bef`: present in git log.
- `631f2d1`: present in git log.
- `src/db/metadata.py`: modified in worktree.
- `tests/unit/test_metadata.py`: modified in worktree.
- `.planning/phases/14-connect-time-hardening-databricks/14-02-SUMMARY.md`: this file.
