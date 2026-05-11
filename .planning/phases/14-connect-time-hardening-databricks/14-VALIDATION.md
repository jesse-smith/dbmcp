---
phase: 14
slug: connect-time-hardening-databricks
status: draft
nyquist_compliant: false
wave_0_complete: false
created: 2026-05-11
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
| IDENT-01 | Catalog-less Databricks config raises `ConnectionError` with SHOW CATALOGS list, chained `ValueError`, host in msg | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_databricks_catalog_required_lists_accessible_catalogs -x` | ✅ (extend) |
| IDENT-01 | When SHOW CATALOGS itself fails, outer error names both problems | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_databricks_catalog_required_surfaces_show_catalogs_failure -x` | ✅ (new case) |
| IDENT-01 | URL mode (sqlalchemy_url without `?catalog=`) also rejected with same rich error | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_connect_with_url_databricks_requires_catalog -x` | ✅ (new case) |
| IDENT-02 | `list_schemas` on Databricks never issues `SHOW CATALOGS` | unit | `uv run pytest tests/unit/test_metadata.py::test_list_schemas_databricks_does_not_fall_back_to_show_catalogs -x` | ❌ W0 |
| TEST-01 | Env-var placeholders in `catalog`/`schema_name` resolve before dialect receives kwargs | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_env_var_substitution_for_catalog_and_schema -x` | ✅ (extend) |
| TEST-02 | `SQLAlchemyError` from `create_engine` surfaces as `ConnectionError` with host in msg | unit | `uv run pytest tests/unit/test_connect_with_config_databricks.py::test_sqlalchemy_error_wrapped_as_connection_error -x` | ✅ (extend) |

*Status: ⬜ pending · ✅ green · ❌ red · ⚠️ flaky*

---

## Wave 0 Requirements

- [ ] Confirm `tests/unit/test_metadata.py` exists and has Databricks `list_schemas` coverage scaffolding. If the Databricks branch is thin, add a fixture for a Databricks-bound `MetadataService` (inject a `DatabricksDialect` plus an engine-spy whose `url.query = {"catalog": "my_cat"}`).
- [ ] Shared `_make_engine_spy_with_catalogs(catalog_names)` factory — co-located in `test_connect_with_config_databricks.py` next to the existing `_make_engine_spy`, or promoted to `tests/unit/conftest.py` if a second test module will consume it.
- [ ] No framework install needed — pytest + monkeypatch already in use.

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

- [ ] All tasks have `<automated>` verify or Wave 0 dependencies
- [ ] Sampling continuity: no 3 consecutive tasks without automated verify
- [ ] Wave 0 covers all MISSING references
- [ ] No watch-mode flags
- [ ] Feedback latency < 30s
- [ ] `nyquist_compliant: true` set in frontmatter

**Approval:** pending
