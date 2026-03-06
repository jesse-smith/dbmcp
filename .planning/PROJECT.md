# dbmcp

## What This Is

A Model Context Protocol (MCP) server that gives LLM agents safe, read-only access to SQL Server databases. 9 MCP tools for schema exploration, query execution, and data analysis — all returning token-efficient TOON-encoded responses.

## Core Value

LLM agents can explore and query SQL Server databases safely, with validated read-only access and clear error reporting.

## Current Milestone: v1.1 Concern Handling

**Goal:** Clear all important codebase concerns from the v1.0 audit — tech debt, code quality, test coverage, connection management, security hardening, and infrastructure improvements.

**Target features:**
- Remove dead code and fix code quality issues (broad exceptions, type ignores)
- Increase test coverage to 70% minimum across all modules
- Fix connection lifecycle (Azure AD token refresh, session cleanup)
- Harden query validation (identifier sanitization, sqlglot edge cases)
- Add type handler registry and configuration file support

## Requirements

### Validated

- All 9 MCP tools return TOON-encoded responses instead of JSON strings — v1.0
- Response docstrings updated to document TOON format — v1.0
- Staleness test validates docstrings match actual response schemas — v1.0
- toon-python (`toon_format`) added as project dependency — v1.0
- Existing test suite passes with TOON responses — v1.0

### Active

- [ ] Remove unused metrics module (dead code)
- [ ] Replace 25 broad `except Exception:` blocks with specific types
- [ ] Fix type ignore suppressions in query module
- [ ] Increase test coverage to 70% minimum for all modules
- [ ] Handle Azure AD token refresh in connection pool
- [ ] Close database connections when MCP session ends
- [ ] Fix identifier sanitization to validate against metadata
- [ ] Pin sqlglot version and add edge case test fixtures
- [ ] Add type handler registry for query result serialization
- [ ] Add config file for connections, defaults, and SP allowlist

### Out of Scope

- Auto-generating docstrings from data models — investigated, not worth the effort
- Client format negotiation (JSON vs TOON) — LLM-only consumers, hard switch
- Pydantic migration for data models — current dataclasses work fine
- Token savings benchmarking — deferred, not pursuing
- Query result caching / result set versioning — future milestone
- Audit logging of query execution — future milestone
- Parameterized queries from MCP clients — future milestone

## Context

- **Current state:** 9 MCP tools, 441 tests (434 passed, 41 skipped), TOON serialization
- **Tech stack:** Python 3.11+, FastMCP, SQLAlchemy, pyodbc, toon-format v0.9.0-beta.1
- **Concerns audit:** 2026-03-03, captured as 10 pending todos on 2026-03-06
- **Key modules:** `src/db/` (connection, query, validation, metadata), `src/mcp_server/` (tools), `src/analysis/` (column stats, FK candidates)

## Constraints

- **Compatibility**: Must maintain all 9 existing MCP tool interfaces unchanged
- **Read-only**: No write operations to user databases; query validation must remain strict
- **Dependencies**: Minimize new dependencies; prefer stdlib solutions
- **Testing**: All changes must maintain or improve test coverage

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hard switch to TOON (no JSON fallback) | Only LLM consumers; simplicity over backward compat | Good |
| Staleness test for docstring drift | Lightweight way to catch schema/doc mismatch | Good |
| TypeError on unrecognized types (strict) | Prefer explicit failure over silent str() fallback | Good |
| ast module for docstring extraction | Avoids circular imports with MCP server modules | Good |

---
*Last updated: 2026-03-06 after v1.1 milestone start*
