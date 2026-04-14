# Roadmap: dbmcp

## Milestones

- ✅ **v1.0 TOON Response Format Migration** — Phases 1-2 (shipped 2026-03-05)
- ✅ **v1.1 Concern Handling** — Phases 3-7 (shipped 2026-03-10)
- 🚧 **v2.0 Multi-Dialect Support** — Phases 8-13 (in progress)

## Phases

<details>
<summary>✅ v1.0 TOON Response Format Migration (Phases 1-2) — SHIPPED 2026-03-05</summary>

- [x] Phase 1: Atomic TOON Migration (3/3 plans) — completed 2026-03-04
- [x] Phase 2: Staleness Guard (2/2 plans) — completed 2026-03-05

</details>

<details>
<summary>✅ v1.1 Concern Handling (Phases 3-7) — SHIPPED 2026-03-10</summary>

- [x] Phase 3: Code Quality & Test Coverage (3/3 plans) — completed 2026-03-09
- [x] Phase 4: Connection Management (2/2 plans) — completed 2026-03-09
- [x] Phase 5: Security Hardening (2/2 plans) — completed 2026-03-09
- [x] Phase 6: Serialization & Configuration (2/2 plans) — completed 2026-03-10
- [x] Phase 7: Wire Orphaned Exports (2/2 plans) — completed 2026-03-10

</details>

### 🚧 v2.0 Multi-Dialect Support (In Progress)

**Milestone Goal:** Extend dbmcp from SQL Server-only to support Databricks and arbitrary SQLAlchemy databases via a dialect strategy pattern, with minimal per-dialect code.

- [ ] **Phase 8: Dialect Protocol & MSSQL Extraction** - Define DialectStrategy protocol and extract all MSSQL-specific code behind it
- [ ] **Phase 9: Config Discrimination & Validation Dialect** - Discriminated TOML config and dialect-aware query validation
- [ ] **Phase 10: GenericDialect & Tool Interface** - Generic dialect fallback, simplified connect_database, optional dependency groups
- [ ] **Phase 11: DatabricksDialect** - Databricks dialect with catalog awareness, token auth, and optimized metadata
- [ ] **Phase 12: Analysis Module Adaptation** - Dialect-aware analysis tools across all three dialects
- [ ] **Phase 13: Test Infrastructure & Coverage** - Parameterized dialect test fixtures and coverage enforcement

## Phase Details

### Phase 8: Dialect Protocol & MSSQL Extraction
**Goal**: All existing SQL Server-specific behavior is encapsulated behind an abstract DialectStrategy protocol, with zero behavior change for current users
**Depends on**: Phase 7 (v1.1 complete)
**Requirements**: DIAL-01, DIAL-02, DIAL-05, META-05, TEST-01
**Success Criteria** (what must be TRUE):
  1. DialectStrategy protocol exists with name, sqlglot_dialect, create_engine, fast_row_counts, quote_identifier, and capability flags
  2. MssqlDialect implements the protocol with all existing MSSQL-specific code (ODBC strings, Azure AD, DMV queries, bracket quoting)
  3. Dialect registry resolves dialect names to strategy implementations with fail-fast error on unknown names (GenericDialect fallback deferred to Phase 10)
  4. All existing tests pass unchanged (zero behavior regression)
**Plans:** 3 plans
Plans:
- [x] 08-01-PLAN.md — Define DialectStrategy protocol and dialect registry
- [x] 08-02-PLAN.md — Implement MssqlDialect and relocate azure_auth
- [x] 08-03-PLAN.md — Wire dialect into ConnectionManager, MetadataService, QueryService

### Phase 9: Config Discrimination & Validation Dialect
**Goal**: Users can configure non-MSSQL connections via TOML and execute validated queries against any supported dialect
**Depends on**: Phase 8
**Requirements**: CONF-01, CONF-02, VALID-01, VALID-02, VALID-03
**Success Criteria** (what must be TRUE):
  1. TOML config with `dialect` field correctly routes to dialect-specific config models; omitting `dialect` defaults to "mssql" (backward compatible)
  2. Typed config models validate dialect-specific fields and reject invalid combinations
  3. Query validation accepts a dialect parameter and parses with the correct sqlglot dialect
  4. Safe procedure list returns MSSQL sp_ procedures for MSSQL and empty list for other dialects
  5. Denylist validation (INSERT/UPDATE/DELETE/CREATE/DROP) works identically across all sqlglot dialects
**Plans:** 2 plans
Plans:
- [ ] 09-01-PLAN.md — Per-dialect config dataclasses and dispatch parser
- [ ] 09-02-PLAN.md — Dialect-aware validate_query and test call site updates

### Phase 10: GenericDialect & Tool Interface
**Goal**: Users can connect to any SQLAlchemy-supported database via URL, with clean dependency separation
**Depends on**: Phase 9
**Requirements**: DIAL-04, CONF-03, CONF-04, CONF-05
**Success Criteria** (what must be TRUE):
  1. GenericDialect accepts any SQLAlchemy URL and provides Inspector-only metadata with COUNT(*) row count fallback
  2. connect_database tool accepts connection_name or sqlalchemy_url (old SQL Server-specific params removed)
  3. pyodbc and azure-identity are in `mssql` optional extra; databricks packages in `databricks` extra; core install has neither
  4. Missing dialect-specific dependencies produce clear error messages at import time (not cryptic ImportErrors)
**Plans**: TBD

### Phase 11: DatabricksDialect
**Goal**: Users can connect to Databricks with full metadata support including catalog awareness, table properties, and partition info
**Depends on**: Phase 10
**Requirements**: DIAL-03, META-01, META-02, META-03, META-04
**Success Criteria** (what must be TRUE):
  1. DatabricksDialect builds databricks:// engines with token auth and catalog/schema scoping
  2. list_schemas, list_tables, get_table_schema work for all three dialects (MSSQL optimized overrides preserved, Databricks and generic via Inspector)
  3. Databricks connections expose three-level namespace (catalog.schema.table) with catalog stored in the data model
  4. Databricks table properties (owner, storage format, managed/external, creation time) are surfaced via DESCRIBE EXTENDED
  5. get_table_schema omits index section when the dialect's supports_indexes capability is false
**Plans**: TBD
**UI hint**: no

### Phase 12: Analysis Module Adaptation
**Goal**: All analysis tools (column stats, PK/FK discovery) work across all three dialects with optimized Databricks paths
**Depends on**: Phase 11
**Requirements**: ANLYS-01, ANLYS-02, ANLYS-03, ANLYS-04, ANLYS-05
**Success Criteria** (what must be TRUE):
  1. get_column_info returns correct stats for MSSQL, Databricks, and generic databases using Tier 2 standard SQL with sqlglot transpilation
  2. Databricks get_column_info reads precomputed stats from DESCRIBE EXTENDED when available (Tier 3 fast path)
  3. find_pk_candidates works across all dialects using uniqueness/null checks, with informational-constraint awareness for Databricks
  4. find_fk_candidates works across all dialects using Inspector-based index checks and value overlap via INTERSECT
  5. Databricks partition metadata is surfaced in table schema responses
**Plans**: TBD

### Phase 13: Test Infrastructure & Coverage
**Goal**: Dialect-parameterized test fixtures enable comprehensive testing of all dialect paths without live connections
**Depends on**: Phase 12
**Requirements**: TEST-02, TEST-03
**Success Criteria** (what must be TRUE):
  1. Dialect-parameterized test fixtures exist for generic and Databricks paths (mock-based, no live connection required)
  2. 70%+ test coverage maintained across all modules including new dialect code
  3. Test suite exercises all three dialect paths (MSSQL, Databricks, generic) through parameterized fixtures
**Plans**: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 8 → 9 → 10 → 11 → 12 → 13

| Phase | Milestone | Plans Complete | Status | Completed |
|-------|-----------|----------------|--------|-----------|
| 1. Atomic TOON Migration | v1.0 | 3/3 | Complete | 2026-03-04 |
| 2. Staleness Guard | v1.0 | 2/2 | Complete | 2026-03-05 |
| 3. Code Quality & Test Coverage | v1.1 | 3/3 | Complete | 2026-03-09 |
| 4. Connection Management | v1.1 | 2/2 | Complete | 2026-03-09 |
| 5. Security Hardening | v1.1 | 2/2 | Complete | 2026-03-09 |
| 6. Serialization & Configuration | v1.1 | 2/2 | Complete | 2026-03-10 |
| 7. Wire Orphaned Exports | v1.1 | 2/2 | Complete | 2026-03-10 |
| 8. Dialect Protocol & MSSQL Extraction | v2.0 | 3/3 | Complete | 2026-04-14 |
| 9. Config Discrimination & Validation Dialect | v2.0 | 0/2 | Planning | - |
| 10. GenericDialect & Tool Interface | v2.0 | 0/0 | Not started | - |
| 11. DatabricksDialect | v2.0 | 0/0 | Not started | - |
| 12. Analysis Module Adaptation | v2.0 | 0/0 | Not started | - |
| 13. Test Infrastructure & Coverage | v2.0 | 0/0 | Not started | - |
