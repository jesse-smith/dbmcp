# dbmcp

## What This Is

A Model Context Protocol (MCP) server that gives LLM agents safe, read-only access to SQL Server, Databricks, and other SQLAlchemy-supported databases. MCP tools for schema exploration, query execution, and data analysis — all returning token-efficient TOON-encoded responses. Hardened with metadata-based query validation, unified type serialization, and external TOML configuration. Dialect-aware architecture minimizes per-database code via a three-tier query strategy.

## Core Value

LLM agents can explore and query databases safely, with validated read-only access, dialect-aware metadata, and clear error reporting.

## Current State

**Shipped:** v2.1 Databricks identifier fixes (2026-05-31)

dbmcp supports three dialects — SQL Server (MSSQL), Databricks, and any SQLAlchemy URL (Generic) — via a `DialectStrategy` protocol, with all seven namespace-aware MCP tools routing identifier resolution through one shared resolver (`src/db/identifiers.py`). Databricks connections require an explicit catalog at connect time (fail-fast with an accessible-catalog list); dotted `table_name` is parsed at dialect-aware depth (3/2/1) with strict conflict detection against explicit params; per-dialect default schema replaces every hardcoded `"dbo"`. On Databricks, an explicit non-default `catalog` now actually targets that catalog's metadata via stateless raw 3-part SQL (shared `CatalogAwareReflector`, no `USE CATALOG`), closing the CR-02 silent mis-targeting bug — verified live (bmtct → cerner_src, 7/7 UAT).

**Next milestone:** Not yet defined. Run `/gsd:new-milestone`. Candidate sources: the 5 deferred items in STATE.md, the DISC-01 catalog-enumeration backlog item, and the cross-catalog-FK-targets deferral.

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
- ✓ Multi-dialect support via DialectStrategy protocol — v2.0
- ✓ Databricks dialect with optimized stats/reflections — v2.0
- ✓ Generic dialect fallback for arbitrary SQLAlchemy databases — v2.0
- ✓ Simplified connect_database tool interface (connection_name / sqlalchemy_url) — v2.0
- ✓ Discriminated TOML config with required dialect field — v2.0 (adjusted from default-to-mssql to required per D-02)
- ✓ SQLAlchemy Inspector-based metadata (Tier 1) — v2.0
- ✓ Standard SQL analysis queries with sqlglot transpilation (Tier 2) — v2.0
- ✓ Dialect-specific optimizations (Tier 3) — v2.0
- ✓ Optional dependency groups (mssql, databricks extras) with lazy imports — v2.0
- ✓ Dialect-aware query validation (sqlglot parse + safe-procedure list per dialect) — v2.0
- ✓ Databricks three-level namespace (catalog.schema.table) + DESCRIBE EXTENDED table properties — v2.0
- ✓ Dialect-parameterized test fixtures; coverage floor raised to 85% — v2.0
- ✓ `connect_database` rejects catalog-less Databricks connections, listing accessible catalogs in the error (IDENT-01) — v2.1
- ✓ `list_schemas` no longer silently returns catalog names when schema lookup fails; fallback removed (IDENT-02) — v2.1
- ✓ All seven namespace-aware tools parse dotted `table_name` per dialect depth and error on extra parts (IDENT-03) — v2.1
- ✓ Conflicting explicit `schema_name`/`catalog` vs `table_name` segments produce a named-conflict error, no silent overrides (IDENT-04) — v2.1
- ✓ `get_sample_data` accepts a `catalog` param on Databricks; errors on MSSQL/generic (IDENT-05) — v2.1
- ✓ `get_column_info` accepts a `catalog` param on Databricks; errors on MSSQL/generic (IDENT-06) — v2.1
- ✓ Per-dialect default schema on `DialectStrategy`; no tool signature hardcodes `"dbo"` (IDENT-07) — v2.1
- ✓ `find_pk_candidates`/`find_fk_candidates`/column-stats target the resolved non-default Databricks catalog via stateless 3-part SQL; CR-02 mis-targeting eliminated (IDENT-08) — v2.1 (Phase 15.1)
- ✓ Regression test for env-var substitution on `catalog`/`schema_name` in Databricks `connect_with_config` (TEST-01) — v2.1
- ✓ Regression test for `SQLAlchemyError` → `ConnectionError` wrapping on Databricks connect path (TEST-02) — v2.1

### Active

(None — v2.1 shipped. Next milestone requirements defined via `/gsd:new-milestone`.)

Candidate inputs for the next milestone:
- DISC-01 — cross-dialect `list_catalogs`/`list_databases` enumeration tool (backlog)
- Cross-catalog FK targets in a *different* catalog than the source (deferred from Phase 15.1)
- 5 deferred items at v2.1 close (see STATE.md Deferred Items): residual Databricks integration tests, cross-dialect `ca_bundle` support, URL-mode probe `ca_bundle` inheritance, Phase 15.1 code-review follow-ups

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

- **Current state:** 9 MCP tools (7 namespace-aware, all routing through the shared identifier resolver), 1072 tests, 85% coverage floor, TOON serialization, 3 dialects (MSSQL, Databricks, Generic) via DialectStrategy protocol, dialect-aware analysis tools with Databricks Tier-3 fast path and cross-catalog metadata targeting
- **Tech stack:** Python 3.11+, FastMCP, SQLAlchemy, pyodbc (mssql extra), databricks-sqlalchemy (databricks extra), toon-format, sqlglot, azure-identity (mssql extra)
- **Configuration:** Optional TOML config file (`~/.dbmcp/config.toml` or `dbmcp.toml`) with required `dialect` discriminator and per-dialect typed config models; Databricks config requires an explicit catalog
- **Key modules:** `src/db/dialects/` (protocol, mssql, databricks, generic, registry), `src/db/` (connection, query, validation, metadata, config, **identifiers**), `src/mcp_server/` (tools), `src/analysis/` (column stats, FK candidates, **_sql CatalogAwareReflector**), `src/serialization/` (type handlers, TOON)
- **Milestones shipped:** v1.0 (TOON migration), v1.1 (concern handling), v2.0 (multi-dialect support), v2.1 (Databricks identifier fixes)
- **Known follow-ups (5 deferred at v2.1 close — see STATE.md):** residual Databricks integration tests; cross-dialect `ca_bundle` support; URL-mode probe `ca_bundle` inheritance (audit WARNING); Phase 15.1 code-review follow-ups (7 non-blocking); plus DISC-01 (catalog enumeration tool) and cross-catalog FK targets in the backlog

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
| DialectStrategy protocol over inheritance (v2.0) | Strategy pattern, least coupling, easy to add dialects | ✓ Good |
| Dialect required in TOML config, no "mssql" default (v2.0, D-02) | Explicit failure over silent cross-dialect misconfiguration | ✓ Good |
| Write base SQL in TSQL + transpile via sqlglot per-dialect (v2.0) | Single canonical query form instead of N hand-written variants | ✓ Good |
| Probe-first-column heuristic for Databricks DESCRIBE EXTENDED Tier-3 fast path (v2.0) | Avoids unnecessary compute when precomputed stats missing | ✓ Good |
| Inspector-first with MSSQL INFORMATION_SCHEMA fallback (v2.0) | SQLAlchemy Inspector as canonical metadata path | ✓ Good |
| `supports_indexes` capability flag gating (v2.0) | Databricks has no traditional indexes; clean schema response | ✓ Good |
| Coverage floor ratchet 70 → 85 (v2.0, Phase 13) | Single global knob, ~5pt headroom over 90.64% baseline | ✓ Good |
| `build_sample_query` method on DialectStrategy (v2.0 quick 260506-n8s) | Moved dialect-specific SQL out of QueryService — no more TSQL-as-default | ✓ Good |
| Breaking change: require catalog at Databricks connect time, no silent default (v2.1, IDENT-01) | Clear fail-fast error over mysterious downstream wrong-catalog failures | ✓ Good |
| Single shared identifier resolver across all 7 namespace-aware tools (v2.1, IDENT-03) | DRY; depth measured via `len(Table.parts)`, never `Table.name/db/catalog` (sqlglot pitfall) | ✓ Good |
| Disagreement-only conflict detection, not most-specific-wins (v2.1, IDENT-04) | Explicit-over-implicit; redundant-but-consistent params allowed, contradictions error | ✓ Good |
| Per-dialect `default_schema` property replaces hardcoded `"dbo"` (v2.1, IDENT-07) | Correctness across dialects; MSSQL→dbo, Databricks→session default, generic→none | ✓ Good |
| Catalog gate runs BEFORE depth check in resolver (v2.1) | A catalog on a shallow dialect reports the gate message, not a confusing depth error | ✓ Good |
| Cross-catalog targeting via stateless raw 3-part SQL, no `USE CATALOG` (v2.1, IDENT-08) | Bypasses catalog-blind Inspector; no per-connection session state, safe on pooled conns | ✓ Good |
| Shared `CatalogAwareReflector` helper for cross-catalog reads (v2.1, Phase 15.1) | Rule of Three: reused by PK/FK/column-stats; one place for 3-part reflection | ✓ Good |
| FK target enumeration scoped to resolved catalog only (v2.1, Phase 15.1) | KISS; cross-catalog FK targets (different catalog than source) deferred | — Pending |
| `quote_tsql_identifier()` shared helper + backtick escaping (v2.1, CR-01/WR-04) | Closes injection break-out in FK candidate generation; defense at the quoting boundary | ✓ Good |

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
*Last updated: 2026-05-31 after v2.1 milestone — Databricks identifier fixes (IDENT-01..08, TEST-01/02) shipped; unified cross-dialect resolver, catalog-required connect, cross-catalog metadata targeting.*
