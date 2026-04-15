# Requirements: dbmcp

**Defined:** 2026-04-13
**Core Value:** LLM agents can explore and query databases safely, with validated read-only access, dialect-aware metadata, and clear error reporting.

## v2.0 Requirements

Requirements for multi-dialect support milestone. Each maps to roadmap phases.

### Dialect Infrastructure

- [ ] **DIAL-01**: Server supports DialectStrategy protocol with name, sqlglot_dialect, create_engine, fast_row_counts, quote_identifier, and capability flags
- [ ] **DIAL-02**: MssqlDialect extracts all existing SQL Server-specific code (ODBC strings, Azure AD, DMV queries) behind the protocol
- [ ] **DIAL-03**: DatabricksDialect builds databricks:// engines with token auth, catalog/schema awareness, and Databricks-optimized paths
- [ ] **DIAL-04**: GenericDialect accepts any SQLAlchemy URL and uses Inspector-only metadata with COUNT(*) fallback for row counts
- [ ] **DIAL-05**: Dialect registry maps dialect names to strategy implementations with GenericDialect as fallback

### Connection & Config

- [ ] **CONF-01**: TOML config supports `dialect` discriminator field, defaulting to "mssql" when absent (backward compatible)
- [ ] **CONF-02**: Typed config models validate dialect-specific fields (MssqlConnectionConfig, DatabricksConnectionConfig, GenericConnectionConfig)
- [ ] **CONF-03**: connect_database tool accepts connection_name or sqlalchemy_url (clean break -- old SQL Server-specific params removed)
- [ ] **CONF-04**: pyodbc and azure-identity move to `mssql` optional extra; databricks packages to `databricks` extra
- [ ] **CONF-05**: Dialect-specific dependencies use lazy imports with clear error messages when missing

### Query Validation

- [ ] **VALID-01**: validate_query accepts dialect parameter and passes it to sqlglot.parse()
- [ ] **VALID-02**: Safe procedure list is dialect-aware (MSSQL sp_ list; empty for Databricks/generic)
- [ ] **VALID-03**: Denylist validation (INSERT/UPDATE/DELETE/CREATE/DROP) works unchanged across all sqlglot dialects

### Metadata

- [ ] **META-01**: list_schemas, list_tables, get_table_schema work for all three dialects via Inspector with MSSQL optimized overrides preserved
- [ ] **META-02**: Databricks three-level namespace (catalog.schema.table) scoped per connection with catalog in data model
- [ ] **META-03**: Databricks table properties surfaced (owner, storage format, managed/external, creation time) via DESCRIBE EXTENDED
- [ ] **META-04**: get_table_schema omits index section for dialects where supports_indexes is false (Databricks)
- [ ] **META-05**: Dialect-appropriate identifier quoting in all generated SQL (brackets/backticks/double-quotes)

### Analysis Tools

- [x] **ANLYS-01**: get_column_info works across all dialects using standard SQL aggregates (Tier 2) with sqlglot transpilation
- [x] **ANLYS-02**: Databricks get_column_info reads precomputed stats from DESCRIBE EXTENDED when available (Tier 3)
- [x] **ANLYS-03**: find_pk_candidates works across all dialects using uniqueness/null checks (Tier 2), with informational-constraint awareness for Databricks
- [x] **ANLYS-04**: find_fk_candidates works across all dialects using Inspector-based index checks and value overlap via INTERSECT (Tier 2)
- [x] **ANLYS-05**: Databricks partition metadata surfaced in table schema responses

### Testing

- [ ] **TEST-01**: All existing MSSQL tests pass unchanged after dialect extraction (zero behavior change)
- [ ] **TEST-02**: Dialect-parameterized test fixtures for generic and Databricks paths (mock-based, no live connection required)
- [ ] **TEST-03**: 70%+ test coverage maintained across all modules

## Future Requirements

### Deferred Enrichment

- **ENRICH-01**: Unity Catalog tag metadata (PII classification, data domain, ownership) surfaced in schema responses
- **ENRICH-02**: Cross-catalog schema discovery and switching within a single Databricks connection
- **ENRICH-03**: Auto-triggering ANALYZE TABLE for Databricks tables missing precomputed stats

### Deferred Analysis

- **ANLYS-06**: Histogram data from Databricks ANALYZE TABLE stats
- **ANLYS-07**: Cross-dialect type normalization (STRING->VARCHAR, TIMESTAMP_NTZ->DATETIME2 display mapping)

## Out of Scope

| Feature | Reason |
|---------|--------|
| Write operations for any dialect | Violates core read-only security model |
| Auto-triggering ANALYZE TABLE | Runs compute on user's cluster, costs money, violates read-only |
| Full cross-catalog queries | Massive complexity; scope to one catalog per connection |
| Databricks-specific SQL in generic tools | Leaks dialect knowledge; keep in DialectStrategy implementations |
| Index metadata for Databricks | Databricks has no traditional indexes; Delta uses data skipping/Z-ordering |
| Enforced constraint semantics for Databricks PK/FK | Misleading -- Databricks constraints are informational only |
| Pydantic migration for data models | Current dataclasses work fine |
| Query result caching / audit logging | Future milestone |

## Traceability

| Requirement | Phase | Status |
|-------------|-------|--------|
| DIAL-01 | Phase 8 | Pending |
| DIAL-02 | Phase 8 | Pending |
| DIAL-03 | Phase 11 | Pending |
| DIAL-04 | Phase 10 | Pending |
| DIAL-05 | Phase 8 | Pending |
| CONF-01 | Phase 9 | Pending |
| CONF-02 | Phase 9 | Pending |
| CONF-03 | Phase 10 | Pending |
| CONF-04 | Phase 10 | Pending |
| CONF-05 | Phase 10 | Pending |
| VALID-01 | Phase 9 | Pending |
| VALID-02 | Phase 9 | Pending |
| VALID-03 | Phase 9 | Pending |
| META-01 | Phase 11 | Pending |
| META-02 | Phase 11 | Pending |
| META-03 | Phase 11 | Pending |
| META-04 | Phase 11 | Pending |
| META-05 | Phase 8 | Pending |
| ANLYS-01 | Phase 12 | Complete |
| ANLYS-02 | Phase 12 | Complete |
| ANLYS-03 | Phase 12 | Complete |
| ANLYS-04 | Phase 12 | Complete |
| ANLYS-05 | Phase 12 | Complete |
| TEST-01 | Phase 8 | Pending |
| TEST-02 | Phase 13 | Pending |
| TEST-03 | Phase 13 | Pending |

**Coverage:**

- v2.0 requirements: 26 total
- Mapped to phases: 26
- Unmapped: 0

---
*Requirements defined: 2026-04-13*
*Last updated: 2026-04-13 after roadmap creation*
