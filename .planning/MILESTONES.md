# Milestones

## v2.0 Multi-Dialect Support (Shipped: 2026-05-06)

**Phases completed:** 7 phases (6 + 13.1 inserted), 20 plans
**Timeline:** 23 days (2026-04-13 → 2026-05-06)
**Commits:** 235 | **LOC:** ~27,000 Python (src + tests)
**Archive:** [milestones/v2.0-ROADMAP.md](milestones/v2.0-ROADMAP.md) · [milestones/v2.0-REQUIREMENTS.md](milestones/v2.0-REQUIREMENTS.md) · [milestones/v2.0-MILESTONE-AUDIT.md](milestones/v2.0-MILESTONE-AUDIT.md)

**Delivered:** Extended dbmcp from SQL Server-only to a three-dialect MCP server (MSSQL, Databricks, Generic SQLAlchemy) via a DialectStrategy protocol, with optimized Databricks paths (catalog awareness, DESCRIBE EXTENDED, Tier-3 precomputed stats), dialect-aware query validation, and parameterized fixtures that exercise every dialect path.

**Key accomplishments:**
- DialectStrategy protocol with MssqlDialect, DatabricksDialect, GenericDialect; registry-backed dispatch; all existing MSSQL behavior preserved through Phase 8 extraction
- Three-level namespace (catalog.schema.table) for Databricks with DESCRIBE EXTENDED property parsing and partition metadata
- Sqlglot-based query validation accepts a dialect parameter; safe-procedure list dialect-aware (MSSQL sp_ / empty for others); denylist unchanged across all dialects
- connect_database tool simplified to (connection_name | sqlalchemy_url); pyodbc + azure-identity relocated to `mssql` extra; databricks packages to `databricks` extra; lazy imports with clear error messages
- Cross-dialect analysis tools (column stats, PK/FK discovery) via TSQL-base + sqlglot transpilation; Tier-3 Databricks fast path reads precomputed stats from DESCRIBE EXTENDED when available
- Dialect-parameterized test fixtures (generic + Databricks mock-based); coverage floor ratcheted 70% → 85% with baseline 90.64%; 872 tests across all three dialect paths
- Phase 13.1 integration closure: WIRING-01/02/03 resolved — connect_database, get_sample_data, and ConnectionManager.connect all thread the registered dialect; quick 260506-n8s moved sample-query SQL generation into `DialectStrategy.build_sample_query`

**Known deferred items at close:** Phase 999.1 (API consistency pass — `catalog` kwarg gap, hardcoded `dbo` default, row-limit naming drift, sample_size typing drift); Databricks integration test todo (env-var substitution + error wrapping).

---

## v1.1 Concern Handling (Shipped: 2026-03-10)

**Phases completed:** 5 phases, 11 plans, 22 tasks
**Timeline:** 5 days (2026-03-06 → 2026-03-10)
**Commits:** 88 | **LOC:** 5,891 Python | **Changes:** 93 files, +11,441/-1,315

**Delivered:** Cleared all 10 concern items from the v1.0 audit — code quality, test coverage, connection lifecycle, security hardening, serialization, and configuration.

**Key accomplishments:**
- Deleted dead metrics module, narrowed 15 broad exception blocks to specific SQLAlchemy types, eliminated all type: ignore suppressions
- Enforced 70%+ test coverage floor across all modules with CI-enforceable baseline (pyproject.toml fail_under + codecov)
- Azure AD token-aware pool_recycle with auto-disconnect on failure, atexit/SIGTERM lifecycle cleanup for session end
- Metadata-based column validation replacing regex-only sanitization, sqlglot pinned with 28 parametrized edge case tests
- Unified type handler registry replacing duplicate _pre_serialize/_truncate_value pipelines, covering 13 Python types
- TOML config file support with named connections, configurable defaults, SP allowlist extensions, and ${VAR} credential resolution
- Config-driven text truncation limits and _classify_db_error wired into all 9 MCP tool safety nets

---

## v1.0 TOON Response Format Migration (Shipped: 2026-03-05)

**Phases completed:** 2 phases, 5 plans, 8 tasks
**Timeline:** 2 days (2026-03-04 → 2026-03-05)
**Commits:** 35 | **LOC:** 17,101 Python

**Delivered:** Every MCP tool response uses TOON format, reducing token consumption for LLM consumers without losing any information.

**Key accomplishments:**
- TOON serialization wrapper with recursive pre-serialization for datetime/StrEnum/Decimal
- Atomic swap of all 9 MCP tools from JSON to TOON (40 json.dumps → encode_response)
- All 9 tool docstrings updated to TOON structural outline format
- Docstring parser and bidirectional field comparison utilities for drift detection
- Parametrized staleness guard test covering all 9 tools (21 tests, 99% coverage)
- Staleness guard caught 6 real docstring-schema drift issues during development

---

