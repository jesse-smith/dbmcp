# Requirements: dbmcp v2.1 — Databricks identifier fixes

**Defined:** 2026-05-08
**Core Value:** LLM agents can explore and query databases safely, with validated read-only access, dialect-aware metadata, and clear error reporting.

**Scope:** Fix Databricks catalog handling and unify 3-part identifier resolution across the five namespace-aware MCP tools. Surfaced by the 2026-05-08 stress test against `dbmcp-test`; design discussed and agreed same day. API is changing — existing Databricks connections without a catalog in the URL will break by design.

## v2.1 Requirements

### Identifier Resolution

- [x] **IDENT-01**: `connect_database` rejects Databricks connections without a catalog in the SQLAlchemy URL (or the named-connection config equivalent). The error lists accessible catalogs from `SHOW CATALOGS` and explains that a catalog is required.
- [x] **IDENT-02**: `list_schemas` no longer silently falls through to returning catalog names when schema lookup fails against the configured default catalog. With IDENT-01 in place, this path is unreachable for valid connections; the fallback code is removed.
- [x] **IDENT-03**: A shared identifier resolver parses `table_name` into 1, 2, or 3 parts per dialect depth (Databricks=3, MSSQL=2, generic/SQLite=1). Supplying more parts than the dialect allows produces a clear error naming the expected depth.
- [x] **IDENT-04**: When `table_name` carries a leading segment (catalog or schema) AND the matching explicit parameter (`catalog` or `schema_name`) is also provided AND the two values disagree, the tool returns an error naming the specific conflict. No silent overrides.
- [x] **IDENT-05**: `get_sample_data` accepts an optional `catalog` parameter on Databricks and routes through the shared resolver. Passing `catalog` on MSSQL or generic dialects produces a dialect-inappropriate-parameter error.
- [x] **IDENT-06**: `get_column_info` accepts an optional `catalog` parameter on Databricks and routes through the shared resolver. Same dialect gate as IDENT-05.
- [x] **IDENT-07**: Each dialect advertises its own default schema (if any) on `DialectStrategy`. Tool signatures no longer hardcode `schema_name='dbo'`; the default resolves per connected dialect (MSSQL → `dbo`, Databricks → session default, generic → no default).
- [x] **IDENT-08**: `find_pk_candidates`, `find_fk_candidates`, and the `get_column_info` column-statistics path actually TARGET the resolved Databricks catalog (not the connection default) when a non-default `catalog` is supplied. When the requested catalog differs from the connection default, results (columns / constraints / statistics) come from the requested catalog — the silent mis-targeting documented as CR-02 (Phase 15) is eliminated. Mechanism: stateless raw 3-part SQL (no `USE CATALOG`), bypassing the catalog-blind SQLAlchemy Inspector. The default-catalog path and the MSSQL/generic catalog gate (IDENT-05/06) remain unchanged. _(Added Phase 15.1 — closes CR-02; partially overlaps the deferred DISC-01 cross-catalog goal.)_

### Regression Tests (residual from v2.0 audit)

- [x] **TEST-01**: `tests/unit/test_connect_with_config_databricks.py::test_env_var_substitution_for_catalog_and_schema` — given `catalog="${DBX_CATALOG}"` and `schema_name="${DBX_SCHEMA}"` with env vars set, the kwargs captured by the engine spy contain resolved values, not `${…}` literals.
- [x] **TEST-02**: `tests/unit/test_connect_with_config_databricks.py::test_sqlalchemy_error_wrapped_as_connection_error` — when a patched `DatabricksDialect.create_engine` raises `SQLAlchemyError`, `connect_with_config` raises `ConnectionError` whose message contains the host string.

## Future Requirements

Deferred to later milestones; tracked but not in v2.1 roadmap.

### Cross-Dialect Discovery

- **DISC-01**: New `list_catalogs` / `list_databases` tool that enumerates server-visible databases (MSSQL: `sys.databases`) or catalogs (Databricks: `SHOW CATALOGS`). Informational only on MSSQL — listed entries may not be queryable from the current connection due to login scope.

## Out of Scope

Explicitly excluded from v2.1. Documented to prevent scope creep.

| Feature | Reason |
|---------|--------|
| Cross-dialect `list_databases`/`list_catalogs` tool | Pure additive feature; independent of the resolver refactor. Filed as DISC-01 for later. |
| Backwards-compatible silent defaulting for catalog-less Databricks URLs | User explicitly chose the breaking-change path; existing connections will get a clear error instead of mysterious downstream failures. |
| Most-specific-wins conflict resolution on `table_name` vs params | Rejected during discussion. Strict-conflict-error was chosen to match the explicit-over-implicit engineering norm. |
| Auto-detecting default catalog by probing (`SHOW CATALOGS` → pick first) | Fragile; arbitrary ordering. Requiring the user to pick at connect time is clearer. |
| Hardcoded `hive_metastore` fallback on Databricks | Not universal across Unity Catalog workspaces; silent wrong-catalog is exactly the class of bug v2.1 removes. |

## Traceability

Populated by the roadmap step.

| Requirement | Phase | Status |
|-------------|-------|--------|
| IDENT-01 | Phase 14 | Complete |
| IDENT-02 | Phase 14 | Complete |
| TEST-01 | Phase 14 | Complete |
| TEST-02 | Phase 14 | Complete |
| IDENT-03 | Phase 15 | Complete |
| IDENT-04 | Phase 15 | Complete |
| IDENT-05 | Phase 15 | Complete |
| IDENT-06 | Phase 15 | Complete |
| IDENT-07 | Phase 15 | Complete |
| IDENT-08 | Phase 15.1 | Complete |

**Coverage:**
- v2.1 requirements: 9 total
- Mapped to phases: 9
- Unmapped: 0 ✓

---
*Requirements defined: 2026-05-08*
*Last updated: 2026-05-08 after initial definition*
