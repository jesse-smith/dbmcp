# dbmcp

## What This Is

A Model Context Protocol (MCP) server that gives LLM agents safe, read-only access to SQL Server, Databricks, and other SQLAlchemy-supported databases. MCP tools for schema exploration, query execution, and data analysis — all returning token-efficient TOON-encoded responses. Hardened with metadata-based query validation, unified type serialization, and external TOML configuration. Dialect-aware architecture minimizes per-database code via a three-tier query strategy.

## Core Value

LLM agents can explore and query databases safely, with validated read-only access, dialect-aware metadata, and clear error reporting.

## Current Milestone: v2.0 Multi-Dialect Support

**Goal:** Extend dbmcp from SQL Server-only to support Databricks (priority) and arbitrary SQLAlchemy+sqlglot databases via a dialect strategy pattern, with minimal per-dialect code.

**Target features:**

- DialectStrategy protocol with MssqlDialect, DatabricksDialect, GenericDialect implementations
- Discriminated connection config (TOML `dialect` field, typed config models per dialect)
- Simplified connect_database tool interface (connection_name / sqlalchemy_url)
- Tier 1 metadata via SQLAlchemy Inspector (with MSSQL optimized overrides preserved)
- Tier 2 standard SQL analysis queries (transpiled via sqlglot where needed)
- Tier 3 dialect-specific optimizations (fast row counts, engine construction)
- Databricks-optimized stats and reflections (column info, PK/FK analysis)
- Explicit sqlglot dialect passing for query validation
- Optional dependency groups (mssql, databricks extras)

## Requirements

### Validated

- ✓ All 9 MCP tools return TOON-encoded responses instead of JSON strings — v1.0
- ✓ Response docstrings updated to document TOON format — v1.0
- ✓ Staleness test validates docstrings match actual response schemas — v1.0
- ✓ toon-python (`toon_format`) added as project dependency — v1.0
- ✓ Existing test suite passes with TOON responses — v1.0
- ✓ Dead metrics module removed from codebase — v1.1
- ✓ All broad `except Exception:` blocks replaced with specific types — v1.1
- ✓ Type ignore suppressions in query module eliminated — v1.1
- ✓ All source modules at 70%+ test coverage with CI enforcement — v1.1
- ✓ Azure AD token refresh handled via pool_recycle and pool_pre_ping — v1.1
- ✓ Database connections cleaned up on session end via atexit — v1.1
- ✓ Identifier sanitization validates against database metadata — v1.1
- ✓ sqlglot pinned with 28 edge case test fixtures — v1.1
- ✓ Unified type handler registry for serialization pipeline — v1.1
- ✓ TOML config file support for named connections and defaults — v1.1

### Active

- [ ] Multi-dialect support via DialectStrategy protocol
- [ ] Databricks dialect with optimized stats/reflections
- [ ] Generic dialect fallback for arbitrary SQLAlchemy databases
- [ ] Simplified connect_database tool interface
- [ ] Discriminated TOML config with dialect field
- [ ] SQLAlchemy Inspector-based metadata (Tier 1)
- [ ] Standard SQL analysis queries with sqlglot transpilation (Tier 2)
- [ ] Dialect-specific optimizations (Tier 3)
- [ ] Optional dependency groups (mssql, databricks extras)

### Out of Scope

- Auto-generating docstrings from data models — investigated, not worth the effort
- Client format negotiation (JSON vs TOON) — LLM-only consumers, hard switch
- Pydantic migration for data models — current dataclasses work fine
- Token savings benchmarking — deferred, not pursuing
- Query result caching / result set versioning — future milestone
- Audit logging of query execution — future milestone
- Parameterized queries from MCP clients — future milestone
- Resource warning fix in test fixtures — cosmetic, warnings don't affect test outcomes
- Metadata service N+1 query optimization — performance concern, not correctness
- Column stats caching — performance optimization, not a concern fix

## Context

- **Current state:** 9 MCP tools, 806 tests, TOON serialization, 70%+ test coverage, 3 dialects (MSSQL, Databricks, Generic)
- **Tech stack:** Python 3.11+, FastMCP, SQLAlchemy, pyodbc, toon-format, sqlglot, azure-identity
- **Configuration:** Optional TOML config file (`~/.dbmcp/config.toml` or `dbmcp.toml`)
- **Key modules:** `src/db/` (connection, query, validation, metadata, config), `src/mcp_server/` (tools), `src/analysis/` (column stats, FK candidates), `src/serialization/` (type handlers, TOON)
- **Milestones shipped:** v1.0 (TOON migration), v1.1 (concern handling)
- **Breaking change planned:** connect_database tool signature simplification (v2.0)

## Constraints

- **Compatibility**: Must maintain all 9 existing MCP tool interfaces unchanged
- **Read-only**: No write operations to user databases; query validation must remain strict
- **Dependencies**: Minimize new dependencies; prefer stdlib solutions
- **Testing**: All changes must maintain 70%+ coverage floor
- **Security**: Metadata-based identifier validation; hardcoded system SPs non-overridable

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hard switch to TOON (no JSON fallback) | Only LLM consumers; simplicity over backward compat | ✓ Good |
| Staleness test for docstring drift | Lightweight way to catch schema/doc mismatch | ✓ Good |
| TypeError on unrecognized types (strict) | Prefer explicit failure over silent str() fallback | ✓ Good |
| ast module for docstring extraction | Avoids circular imports with MCP server modules | ✓ Good |
| Delete metrics.py without archiving | Disposable dead code, no value in preserving | ✓ Good |
| SQLAlchemyError only for db-layer catching | SQLAlchemy wraps pyodbc errors; catch at right layer | ✓ Good |
| MCP tool safety nets kept as except Exception | Top-level handlers need broad catching for user safety | ✓ Good |
| 70% coverage floor with fail_under | Enforceable baseline without being unreachable | ✓ Good |
| pool_recycle=2700 for Azure AD | Under 1hr token lifetime; discards stale connections | ✓ Good |
| _classify_db_error as module-level function | Reusable outside ConnectionManager | ✓ Good |
| Metadata as single source of truth for identifiers | More secure than regex-only validation | ✓ Good |
| Ordered handler chain for type registry | Subclass-first isinstance ordering for correct dispatch | ✓ Good |
| Env vars resolved at connection time | Credential security; not cached at load time | ✓ Good |
| Tool arg precedence: explicit > config > defaults | Clear override semantics | ✓ Good |

## Evolution

This document evolves at phase transitions and milestone boundaries.

**After each phase transition** (via `/gsd-transition`):
1. Requirements invalidated? → Move to Out of Scope with reason
2. Requirements validated? → Move to Validated with phase reference
3. New requirements emerged? → Add to Active
4. Decisions to log? → Add to Key Decisions
5. "What This Is" still accurate? → Update if drifted

**After each milestone** (via `/gsd-complete-milestone`):
1. Full review of all sections
2. Core Value check — still the right priority?
3. Audit Out of Scope — reasons still valid?
4. Update Context with current state

---
*Last updated: 2026-04-15 after Phase 11 complete — DatabricksDialect with token-auth engine construction, catalog-aware metadata (three-level namespace), DESCRIBE EXTENDED parsing for table properties, index gating, and optional catalog parameter on all schema tools*
