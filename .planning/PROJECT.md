# dbmcp

## What This Is

A Model Context Protocol (MCP) server that gives LLM agents safe, read-only access to SQL Server databases. 9 MCP tools for schema exploration, query execution, and data analysis — all returning token-efficient TOON-encoded responses. Hardened with metadata-based query validation, unified type serialization, and external TOML configuration.

## Core Value

LLM agents can explore and query SQL Server databases safely, with validated read-only access and clear error reporting.

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

(None — next milestone not yet defined)

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

- **Current state:** 9 MCP tools, 682 tests, 5,891 LOC Python, TOON serialization, 70%+ test coverage
- **Tech stack:** Python 3.11+, FastMCP, SQLAlchemy, pyodbc, toon-format, sqlglot, azure-identity
- **Configuration:** Optional TOML config file (`~/.dbmcp/config.toml` or `dbmcp.toml`)
- **Key modules:** `src/db/` (connection, query, validation, metadata, config), `src/mcp_server/` (tools), `src/analysis/` (column stats, FK candidates), `src/serialization/` (type handlers, TOON)
- **Milestones shipped:** v1.0 (TOON migration), v1.1 (concern handling)

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

---
*Last updated: 2026-03-10 after v1.1 milestone*
