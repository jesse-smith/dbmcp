---
quick_id: 260528-fks
description: Fix Defect A — Databricks catalog defaults bypass IDENT-01
date: 2026-05-28
branch: gsd/v2.1-databricks-identifier-fixes
status: ready_for_execution
must_haves:
  truths:
    - Defect A root cause is the `"main"` defaults at `src/config.py:77` (`DatabricksConnectionConfig.catalog: str = "main"`) and `src/config.py:243` (`params.get("catalog", "main")` in `_parse_databricks_connection`). Together they make a toml entry with `catalog` omitted produce a config carrying `catalog="main"`, bypassing the dialect's `if not catalog: raise ValueError("Databricks catalog is required")` guard at `src/db/dialects/databricks.py:241-243` — the user then sees a misleading "Catalog 'main' was not found" instead of the IDENT-01 enrichment.
    - The IDENT-01 enrichment path in `ConnectionManager.connect_with_config` is already correct and tested — `tests/unit/test_connect_with_config_databricks.py:173-216` verifies that an empty-string `cfg.catalog` triggers the enriched `Databricks connection requires a catalog ... Accessible catalogs: ...` ConnectionError. The fix simply has to make catalog-omitted toml routes through this same code path.
    - `src/db/metadata.py:928` `dte_catalog = catalog or "main"` is a separate IDENT-01 hygiene leftover. The correct fallback mirrors `src/db/metadata.py:105` `effective_catalog = catalog or self._engine_catalog()` — the engine's URL query is the post-IDENT-01 invariant source of truth.
    - Existing test `tests/unit/test_config.py:178` (`assert c.catalog == "main"`) must be updated since it locks in the very default we're removing.
  artifacts:
    - src/config.py:77 — `catalog: str = "main"` → `catalog: str = ""`
    - src/config.py:243 — `params.get("catalog", "main")` → `params.get("catalog", "")`
    - src/db/metadata.py:928 — `dte_catalog = catalog or "main"` → `dte_catalog = catalog or self._engine_catalog()`
    - tests/unit/test_config.py — update `test_databricks_fields` catalog assertion to `""`; add `test_parse_databricks_connection_omitted_catalog_defaults_to_empty` for the parser default
    - tests/unit/test_config.py — add `test_parse_databricks_connection_explicit_catalog_preserved` (regression — explicit catalog must still flow through)
  key_links:
    - src/config.py:69-79 (`DatabricksConnectionConfig` dataclass)
    - src/config.py:236-246 (`_parse_databricks_connection`)
    - src/db/dialects/databricks.py:240-243 (catalog-required guard)
    - src/db/connection.py — IDENT-01 enrichment in `connect_with_config` (`_require_databricks_catalog`)
    - src/db/metadata.py:155-162 (`_engine_catalog`) and :928 (`dte_catalog` leftover)
    - tests/unit/test_connect_with_config_databricks.py:173-248 (existing IDENT-01 enrichment tests — no change needed)
---

# Quick Task 260528-fks: Fix Defect A — Databricks catalog defaults bypass IDENT-01

## Goal

Stop `DatabricksConnectionConfig.catalog` and `_parse_databricks_connection` from silently defaulting to `"main"`. After the fix, a toml entry with `catalog` omitted carries `catalog=""` end-to-end, the dialect's `if not catalog: raise ValueError` fires, and `ConnectionManager.connect_with_config` enriches the failure with the IDENT-01 message ("Databricks connection requires a catalog. Accessible catalogs: ..."). Also clean up the parallel `or "main"` leftover in `metadata.py:928`.

Defects B/C/D are unrelated to this fix:
- **B** is fixed (commit `6cfe60c`).
- **C/D** are fixed (commit `bc2244f`, prior quick task `260515-m30`).

## Approach

**TDD red → green → refactor.** Update the dataclass-default test to assert `""` (currently asserts `"main"` — a green test locking in the bug), add a parser-default test, then change the two `"main"` defaults plus the `metadata.py` leftover. The IDENT-01 enrichment path is already tested at `tests/unit/test_connect_with_config_databricks.py:173-216`; that test currently passes only because callers explicitly pass `catalog=""`. After this fix, the same enrichment fires for callers that simply omit `catalog` from their toml — no new integration test required because the existing test already exercises the empty-string codepath.

Considered but rejected:
- **Raising at parse time** when toml omits catalog. Cleaner in theory, but it skips the IDENT-01 enrichment (which lists accessible catalogs by probing the connection). Letting the empty default flow through to `connect_with_config` is what gives users the actionable error.
- **Keeping `"main"` as the default and special-casing it in the dialect.** Magic-string special-cases are exactly what KISS rejects. Empty string is the correct sentinel: "user did not specify."

## Tasks

### Task 1 — Update + add tests in `tests/unit/test_config.py`

**Files:** `tests/unit/test_config.py`

**Action:**

1. In `test_databricks_fields` (line 173-180), change `assert c.catalog == "main"` to `assert c.catalog == ""`. Add a one-line comment: `# Empty default — required so IDENT-01 enrichment fires for catalog-omitted toml (Defect A)`.

2. After `test_databricks_dialect_produces_databricks_config` (line 214-225), add a new test class `TestParseDatabricksDefaults` containing:

```python
class TestParseDatabricksDefaults:
    """Defect A: catalog must default to "" so IDENT-01 enrichment fires for
    catalog-omitted toml entries instead of "main" silently bypassing the guard."""

    def test_parse_databricks_connection_omitted_catalog_defaults_to_empty(self):
        raw = {"warehouse": {
            "dialect": "databricks",
            "host": "h",
            "http_path": "/p",
            # catalog intentionally omitted
        }}
        result = _parse_connections(raw)
        assert result["warehouse"].catalog == ""

    def test_parse_databricks_connection_explicit_catalog_preserved(self):
        raw = {"warehouse": {
            "dialect": "databricks",
            "host": "h",
            "http_path": "/p",
            "catalog": "analytics",
        }}
        result = _parse_connections(raw)
        assert result["warehouse"].catalog == "analytics"
```

**Verify:** `uv run pytest tests/unit/test_config.py::TestConnectionConfigDataclasses::test_databricks_fields tests/unit/test_config.py::TestParseDatabricksDefaults -x` — `test_databricks_fields` and `test_parse_databricks_connection_omitted_catalog_defaults_to_empty` fail against current code; `test_parse_databricks_connection_explicit_catalog_preserved` passes immediately.

**Done:** 2 of 3 tests fail on current code; 1 passes as a regression guard.

### Task 2 — Apply the three-line fix

**Files:** `src/config.py`, `src/db/metadata.py`

**Action:**

1. `src/config.py:77`: `catalog: str = "main"` → `catalog: str = ""`
2. `src/config.py:243`: `catalog=params.get("catalog", "main"),` → `catalog=params.get("catalog", ""),`
3. `src/db/metadata.py:928`: `dte_catalog = catalog or "main"  # Fall back to default catalog` → `dte_catalog = catalog or self._engine_catalog()  # IDENT-01: engine-bound catalog`

**Verify:**
- `uv run pytest tests/unit/test_config.py::TestConnectionConfigDataclasses::test_databricks_fields tests/unit/test_config.py::TestParseDatabricksDefaults -x` → all green.
- `uv run pytest tests/unit/test_connect_with_config_databricks.py -x` → green (existing IDENT-01 enrichment tests still pass — they pass `catalog=""` explicitly, so behavior is unchanged for them).
- `uv run pytest tests/` → full suite green; no regressions.
- `uv run ruff check src/config.py src/db/metadata.py tests/unit/test_config.py` → clean.

**Done:** Atomic commit: `fix(config): drop "main" catalog defaults so IDENT-01 fires for omitted toml (Phase 14 A)`.

### Task 3 — UAT against `dbmcp-test`

**Files:** none (manual verification, recorded in SUMMARY.md).

**Action:** With `dbmcp.toml` `catalog` line **commented out**, reconnect `dbmcp-test` and call `connect_database(connection_name="stem-databricks")`. Expect the enriched ConnectionError ("Databricks connection requires a catalog. Accessible catalogs: ...") — NOT a raw "Catalog 'main' was not found" or a silent connect-to-main success.

Then uncomment the toml `catalog` line, reconnect, and verify connect succeeds (regression guard for the explicit-catalog path).

**Done:** SUMMARY.md UAT section captures both the negative and positive observations.

## Out of Scope

- Defects B, C, D — already fixed (B in `6cfe60c`, C/D in `bc2244f`).
- URL-mode env-var resolution gap (Probe 3 from quick task `260515-m30`) — separate quick task.
- `execute_query` cross-dialect LIMIT/TOP leak — separate `/gsd:debug` session.
- Any rename of `catalog="main"` test fixtures elsewhere — these explicitly exercise the success path with a real catalog name, not the bug-defaulting path. They stay as-is.

## Risks

- **Tests elsewhere relying on the implicit `"main"` default.** Low — the only test that asserts the default is `test_databricks_fields`. Other tests (e.g. `test_connect_with_config_databricks.py`) construct `DatabricksConnectionConfig` with explicit `catalog=...`, so they're insulated from the default change. The full pytest run in Task 2 catches anything missed.
- **`_engine_catalog()` raising KeyError** if a Databricks engine were ever built without `?catalog=` in its URL. In practice the dialect's `create_engine` guard prevents this — there's no path that builds a Databricks engine with empty catalog. If somehow violated, we'd see an explicit KeyError at the metadata path instead of a silent fallback to "main", which is the right failure mode.
