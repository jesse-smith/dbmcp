---
phase: 14
slug: connect-time-hardening-databricks
status: validated
nyquist_compliant: true
wave_0_complete: true
created: 2026-05-11
last_audited: 2026-05-14
---

# Phase 14 — Validation Strategy

> Per-phase validation contract for feedback sampling during execution.

---

## Test Infrastructure

| Property | Value |
|----------|-------|
| **Framework** | pytest 7.0.0+ (existing) |
| **Config file** | `pyproject.toml` `[tool.pytest.ini_options]` |
| **Quick run command** | `uv run pytest tests/unit/test_connect_with_config_databricks.py tests/unit/test_metadata.py -x` |
| **Full suite command** | `uv run pytest tests/` |
| **Estimated runtime** | ~15 seconds (quick); ~45 seconds (full unit) |

---

## Sampling Rate

- **After every task commit:** `uv run pytest tests/unit/test_connect_with_config_databricks.py tests/unit/test_metadata.py -x`
- **After every plan wave:** `uv run pytest tests/ -m "not integration"`
- **Before `/gsd:verify-work`:** `uv run pytest tests/` full suite green, 85% coverage floor maintained
- **Max feedback latency:** ~15 seconds

---

## Per-Task Verification Map

*Populated by planner from PLAN.md task IDs. Seeded with requirement-level mappings below.*

| Req ID | Behavior | Test Type | Automated Command | File Exists |
|--------|----------|-----------|-------------------|-------------|
| IDENT-01 | Catalog-less Databricks config raises `ConnectionError` with SHOW CATALOGS list, chained `ValueError`, host in msg | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_databricks_catalog_required_lists_accessible_catalogs -x` | ✅ green |
| IDENT-01 | When SHOW CATALOGS itself fails, outer error names both problems | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_databricks_catalog_required_surfaces_show_catalogs_failure -x` | ✅ green |
| IDENT-01 | URL mode (sqlalchemy_url without `?catalog=`) also rejected with same rich error | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_with_url_databricks_requires_catalog -x` | ✅ green |
| IDENT-01 (D-18) | Named-config with empty/None `catalog` enriches and raises (no silent `"main"` fallback) | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_with_config_empty_catalog_raises_enriched_connection_error tests/unit/test_connect_with_config_databricks.py::test_connect_with_config_none_catalog_raises_enriched_connection_error -x` | ✅ green |
| IDENT-02 | `list_schemas` on Databricks never issues `SHOW CATALOGS` | unit | `uv run pytest 'tests/unit/test_metadata.py::TestCatalogListSchemas::test_list_schemas_databricks_does_not_fall_back_to_show_catalogs' -x` | ✅ green |
| TEST-01 | Env-var placeholders in `catalog`/`schema_name` resolve before dialect receives kwargs | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_env_var_substitution_for_catalog_and_schema -x` | ✅ green |
| TEST-01 (dim 4) | Unresolved `${VAR}` raises `ValueError` at resolver boundary | unit | `uv run pytest tests/unit/test_config.py -k 'resolve_env_vars and undefined' -x` | ✅ green |
| TEST-02 | `SQLAlchemyError` from `create_engine` surfaces as `ConnectionError` with host in msg | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_sqlalchemy_error_wrapped_as_connection_error -x` | ✅ green |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [x] `tests/unit/test_metadata.py` Databricks `list_schemas` coverage scaffolding present (`TestCatalogListSchemas` class, line 614).
- [x] Shared `_make_engine_spy*` factories live in `test_connect_with_config_databricks.py`.
- [x] No framework install needed — pytest + monkeypatch already in use.

---

## Validation Dimensions (Nyquist)

1. **Happy path (TEST-01):** Config with env-var refs resolves cleanly; engine receives literal values.
2. **Catalog-missing, SHOW CATALOGS succeeds (IDENT-01 primary):** Rich error with catalog list; chained cause.
3. **Catalog-missing, SHOW CATALOGS fails (IDENT-01 D-06):** Outer error names both failures.
4. **Unresolved env var (adjacent to TEST-01):** `resolve_env_vars` raises `ValueError` — regression check, parametrized case.
5. **SQLAlchemyError at create_engine (TEST-02):** `ConnectionError` with host in message.
6. **IDENT-02 regression lock (D-15):** `list_schemas` produces schema list with zero `SHOW CATALOGS` executions.
7. **URL-mode catalog absence (edge of IDENT-01):** `databricks://...` URL without `?catalog=` → same `ConnectionError` as config path.
8. **Named-config catalog absence (D-18, added 2026-05-11):** Named `DatabricksConnectionConfig` with empty/None `catalog` → same `ConnectionError` as URL path (covers the third `"main"` fallback at `connection.py:499`).

---

## Manual-Only Verifications

| Behavior | Requirement | Why Manual | Test Instructions |
|----------|-------------|------------|-------------------|
| Live Databricks connection end-to-end smoke test against a real workspace | IDENT-01 | Requires Unity Catalog workspace credentials; not in CI | After green unit suite, connect against a real Databricks workspace: (a) omit catalog in URL, confirm rich error with real catalog names; (b) connect with a valid catalog, run `list_schemas`, confirm schemas returned (not catalogs). |

---

## Validation Sign-Off

- [x] All tasks have `<automated>` verify or Wave 0 dependencies
- [x] Sampling continuity: no 3 consecutive tasks without automated verify
- [x] Wave 0 covers all MISSING references
- [x] No watch-mode flags
- [x] Feedback latency < 30s
- [x] `nyquist_compliant: true` set in frontmatter

**Approval:** validated 2026-05-14

---

## Validation Audit 2026-05-14

| Metric | Count |
|--------|-------|
| Dimensions checked | 8 |
| Dimensions COVERED | 8 |
| Dimensions PARTIAL | 0 |
| Dimensions MISSING | 0 |
| Doc fixes applied | 2 (IDENT-02 row class scope; added D-18 + dim-4 rows) |
| Tests run | 6 (all green, 0.04s) |

**Verdict:** Phase 14 is Nyquist-compliant. All 8 validation dimensions have automated coverage; only fix was a stale class path in the IDENT-02 row of the Per-Task Map.
