# Project Research Summary

**Project:** dbmcp v2.0 Multi-Dialect Support
**Domain:** Multi-dialect database MCP server (SQL Server + Databricks + generic SQLAlchemy)
**Researched:** 2026-04-13
**Confidence:** HIGH

## Executive Summary

dbmcp can be extended to support Databricks and arbitrary SQLAlchemy databases with a dialect strategy pattern that keeps per-dialect code small (~150-200 lines each). The key enablers are already in the stack: databricks-sqlalchemy 2.0.9 implements all 6 Inspector methods dbmcp uses, sqlglot 30.4.2 already supports the `databricks` dialect for parsing/validation/transpilation, and the existing MetadataService already has a dual-path pattern (`is_mssql`/generic) that maps cleanly to the strategy interface.

The recommended approach is a three-tier query strategy: Tier 1 (SQLAlchemy Inspector) for universal metadata, Tier 2 (standard SQL via sqlglot transpilation) for analysis queries, and Tier 3 (dialect-specific) for optimized paths like DMV row counts (MSSQL) and DESCRIBE EXTENDED stats (Databricks). The DialectStrategy protocol with MssqlDialect, DatabricksDialect, and GenericDialect implementations keeps dialect knowledge out of the tool layer.

The highest-risk areas are: (1) analysis modules containing 15+ SQL Server-only constructs that need rewriting/transpiling, (2) the breaking `connect_database` interface change (mitigatable by supporting both old and new params), and (3) databricks-sqlalchemy Inspector raising non-SQLAlchemy exceptions that current handlers miss. Build order should extract MSSQL behind the protocol first (pure refactor, all tests pass), then add config discrimination, then GenericDialect, then Databricks, then analysis adaptation, then interface simplification.

## Key Findings

### Recommended Stack

Two new dependencies for Databricks; zero for generic dialect support. Users bring their own SQLAlchemy driver.

**New dependencies:**

- `databricks-sqlalchemy>=2.0.0`: SQLAlchemy dialect implementing all Inspector methods (get_schema_names, get_table_names, get_columns, get_pk_constraint, get_foreign_keys, get_indexes stub). Requires SQLAlchemy >=2.0.21 (safe bump).
- `databricks-sql-connector>=4.0.0`: Thrift-based DBAPI driver. Heavy transitive deps (pandas mandatory ~40MB). Only affects `databricks` extra users.

**Stack changes:**

- SQLAlchemy floor bump to >=2.0.21 (from >=2.0.0) -- required by databricks-sqlalchemy
- pyodbc and azure-identity move to `mssql` optional extra
- Databricks packages go in `databricks` optional extra
- Core deps become dialect-agnostic (SQLAlchemy + sqlglot + mcp + toon-format)

### Expected Features

**Must have (table stakes):**

- Schema/table/column listing across all dialects (Inspector-based)
- Query execution with dialect-aware sqlglot validation
- Sample data retrieval with dialect-appropriate LIMIT/TOP syntax
- TOML config for Databricks connections (host, http_path, catalog, token)
- Identifier quoting per dialect (brackets/backticks/double-quotes)
- Three-level namespace support for Databricks (catalog.schema.table)
- Backward-compatible MSSQL config (existing TOML works unchanged)

**Should have (differentiators):**

- Databricks column stats from DESCRIBE EXTENDED (precomputed, fast)
- Databricks table metadata (owner, format, managed/external, creation time)
- PK/FK discovery with informational-constraint awareness (Databricks PKs are not enforced)
- Partition-aware metadata for Databricks tables
- Dialect-agnostic analysis fallbacks (Tier 2 standard SQL when Tier 3 unavailable)

**Defer:**

- Unity Catalog tag metadata (nice enrichment, not core)
- Cross-catalog queries (scope to one catalog per connection)
- Auto-triggering ANALYZE TABLE (violates read-only; read existing stats only)
- Histogram data from ANALYZE TABLE (optimizer artifact, not useful for LLMs)

### Architecture Approach

Single DialectStrategy protocol with a registry, three implementations, and a tier fallback chain (Tier 3 -> Tier 2 -> Tier 1). MetadataService delegates to dialect for optimized queries, falls back to Inspector. ConnectionManager stores dialect alongside engine. All dialect-specific code lives in `src/db/dialects/`. MCP tools remain dialect-agnostic.

**Major components:**

1. `src/db/dialect.py` -- DialectStrategy protocol + registry
2. `src/db/dialects/{mssql,databricks,generic}.py` -- Per-dialect implementations
3. `src/db/connection.py` (modified) -- Stores (Engine, DialectStrategy) tuples, delegates engine creation
4. `src/db/metadata.py` (modified) -- Tier 3/Tier 1 fallback via dialect delegation
5. `src/db/validation.py` (modified) -- Accepts dialect parameter for sqlglot parsing
6. `src/analysis/` (modified) -- Dialect-aware quoting and SQL generation

### Critical Pitfalls

1. **Inspector returns different shapes per dialect** -- databricks-sqlalchemy may raise TypeError/NotImplementedError (not SQLAlchemyError). Add capability flags to DialectStrategy; widen exception handling.
2. **Three-level namespace (catalog.schema.table)** -- Entire codebase assumes two-level. Scope to one catalog per connection in v2.0; add catalog to data model for future.
3. **15+ SQL Server-only constructs in analysis modules** -- Bracket quoting, `sys.*` DMVs, `DATEDIFF`, `LEN`, `STRING_SPLIT`, `TOP N`. Use sqlglot transpilation for Tier 2; dialect-specific Tier 3 for the rest.
4. **Hardcoded `dialect="tsql"` in validation** -- Blocks all non-MSSQL query execution. Must parameterize early.
5. **Breaking connect_database interface** -- Support both old and new params; old SQL Server params internally construct MSSQL URL. Deprecate old params, don't remove.

## Implications for Roadmap

### Phase 1: Dialect Protocol + MSSQL Extraction

**Rationale:** Establish the abstraction without changing behavior. All 607+ tests pass unchanged.
**Delivers:** DialectStrategy protocol, MssqlDialect, dialect registry, ConnectionManager/MetadataService refactored to accept dialect
**Addresses:** Foundation for everything; identifier quoting abstraction
**Avoids:** Pitfall 1 (Inspector shapes), Pitfall 9 (quoting)

### Phase 2: Config Discrimination + Validation Dialect

**Rationale:** Users need to configure connections before anything works. Validation blocks query execution.
**Delivers:** Discriminated TOML config (dialect field), typed config models, validation accepts dialect param
**Addresses:** Config table stakes, query execution unblocking
**Avoids:** Pitfall 4 (validation mismatch), Pitfall 10 (SQL Server-shaped config)

### Phase 3: GenericDialect + Tool Interface

**Rationale:** Proves the abstraction with zero new dependencies. SQLite test coverage validates the generic path.
**Delivers:** GenericDialect implementation, sqlalchemy_url support in connect_database, optional dependency groups
**Addresses:** Generic dialect table stakes, package restructuring
**Avoids:** Pitfall 5 (breaking interface -- additive change), Pitfall 12 (import crashes -- lazy imports)

### Phase 4: DatabricksDialect

**Rationale:** Priority second dialect. Built on stable foundation from phases 1-3.
**Delivers:** DatabricksDialect with engine construction, token auth, catalog awareness, Tier 3 optimizations
**Addresses:** Databricks connection, metadata, query execution
**Avoids:** Pitfall 2 (namespace), Pitfall 6 (non-SQLAlchemy exceptions), Pitfall 7 (connection lifecycle)

### Phase 5: Analysis Module Adaptation

**Rationale:** Highest MSSQL-specific SQL density. Deferred until dialect infrastructure is stable.
**Delivers:** Dialect-aware column stats, PK discovery, FK candidates across all dialects
**Addresses:** Databricks-optimized stats/reflections differentiator
**Avoids:** Pitfall 3 (hardcoded syntax), Pitfall 11 (empty results), Pitfall 13 (transpilation gaps)

### Phase Ordering Rationale

- Extract-then-extend: MSSQL extraction first preserves test safety net
- Config before code: TOML discrimination enables new dialects without code changes
- Generic before Databricks: Proves abstraction with zero external deps
- Analysis last: Depends on all other layers being stable; highest-effort change

### Research Flags

Phases likely needing deeper research during planning:

- **Phase 4 (Databricks):** OAuth M2M auth via connect_args needs integration testing; Inspector behavior with MAP/STRUCT/ARRAY columns unknown
- **Phase 5 (Analysis):** sqlglot transpilation coverage for specific analysis query patterns needs empirical validation

Phases with standard patterns (skip research-phase):

- **Phase 1 (Protocol):** Well-understood Protocol pattern; direct code extraction
- **Phase 2 (Config):** Standard discriminated union; backward-compatible defaults
- **Phase 3 (Generic):** Inspector-only path; minimal new code

## Confidence Assessment

| Area | Confidence | Notes |
|------|------------|-------|
| Stack | HIGH | Versions verified on PyPI; sqlglot dialect tested locally |
| Features | HIGH | Based on direct codebase analysis + official Databricks docs |
| Architecture | HIGH | Follows existing dual-path pattern; direct codebase inspection |
| Pitfalls | HIGH (MSSQL), MEDIUM (Databricks) | MSSQL risks from code review; Databricks risks from docs + GitHub issues |

**Overall confidence:** HIGH

### Gaps to Address

- databricks-sqlalchemy Inspector behavior with complex types (MAP, STRUCT, ARRAY, VARIANT) -- test at implementation time
- OAuth M2M auth via connect_args with Databricks -- mechanism is standard SQLAlchemy but not directly tested
- sqlglot transpilation for specific analysis query patterns (INTERSECT, STDEV, DATEDIFF equivalents) -- validate empirically in Phase 5
- Warehouse cold-start latency handling -- configure longer timeouts, document expected behavior

## Sources

### Primary (HIGH confidence)

- PyPI: databricks-sqlalchemy 2.0.9, databricks-sql-connector 4.2.5
- GitHub: databricks-sqlalchemy source (Inspector method implementations)
- Local: sqlglot 30.4.2 Databricks dialect parsing/transpilation verification
- Databricks docs: information_schema, DESCRIBE TABLE, ANALYZE TABLE, constraints
- Direct codebase: all src/ modules inspected for MSSQL-specific patterns

### Secondary (MEDIUM confidence)

- databricks-sqlalchemy GitHub issues (50+ open -- UUID, INTERVAL, cross-catalog)
- databricks-sql-connector GitHub issues (pandas dependency, rate limiting)

---
*Research completed: 2026-04-13*
*Ready for roadmap: yes*
