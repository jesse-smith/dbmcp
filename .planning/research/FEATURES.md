# Feature Landscape

**Domain:** Concern handling for Python MCP database server (SQLAlchemy + pyodbc + SQL Server)
**Researched:** 2026-03-06

## Table Stakes

Features users expect. Missing = product feels incomplete or fragile.

| Feature | Why Expected | Complexity | Dependencies | Notes |
|---------|--------------|------------|--------------|-------|
| Specific exception handling | Bare `except Exception` hides bugs, makes debugging impossible; 25 instances across codebase | Medium | None (existing exception types from sqlalchemy, pyodbc, azure.identity) | SQLAlchemy raises `OperationalError`, `ProgrammingError`, `InterfaceError`; pyodbc raises `pyodbc.Error` subtypes; azure-identity raises `CredentialUnavailableError`, `ClientAuthenticationError`. The MCP tool layer should catch known types and only use bare Exception as a true last-resort sentinel. |
| Dead code removal (metrics.py) | Unused module creates confusion about codebase intent; no imports reference it | Low | None | `src/metrics.py` is imported by nothing. Zero references outside its own docstring. Safe to delete. |
| Type ignore cleanup | `# type: ignore` on Query._columns/_rows/_total_rows_available hides a design smell (ad-hoc attribute injection on a dataclass) | Low-Medium | None | Fix is either: (a) add those fields to the Query dataclass with defaults, or (b) return a separate result container alongside Query. Option (b) is cleaner -- a `QueryResult` dataclass holding columns/rows/total_rows_available, returned as a tuple from `execute_query`. |
| Test coverage to 70% per module | Below 70% signals untested code paths, especially in metadata.py (heavy exception handling) and MCP tool layer | Medium-High | pytest-cov (already installed) | The MCP tool layer uses `asyncio.to_thread` wrapping sync functions -- test the sync inner functions directly, not through the async wrapper. metadata.py has ~13 bare except blocks that need exercising. |
| MCP session cleanup | Connections leak if LLM client disconnects without calling disconnect; `ConnectionManager` has no session lifecycle hook | Medium | FastMCP session/lifecycle events | FastMCP supports server lifecycle context managers. Wire `disconnect_all()` to session/server shutdown. |

## Differentiators

Features that set the product apart. Not expected, but valuable.

| Feature | Value Proposition | Complexity | Dependencies | Notes |
|---------|-------------------|------------|--------------|-------|
| Azure AD token refresh in connection pool | Current code acquires a token once at connection creation via the `creator` callable. Azure AD tokens expire after ~60-75 minutes. Long-running sessions silently break when pool returns a stale connection. | Medium | azure-identity (already installed) | The `creator` function in `_create_engine` already calls `provider.get_token()` per physical connection, which is good. But SQLAlchemy's pool reuses physical connections -- `pool_pre_ping` only tests connectivity (SELECT 1), not token validity. Solution: set `pool_recycle` to ~3000s (under 60-min expiry), so pooled connections are recycled before tokens expire. Optionally cache `AccessToken.expires_on` and force reconnect when approaching expiry. |
| Type handler registry for serialization | Current `_truncate_value` in query.py handles types inline with if/elif chains (datetime, Decimal, bytes, etc.). `_pre_serialize` in serialization.py has a parallel chain. Adding a new type requires editing two places. | Medium | None | Pattern: a registry dict mapping `type -> callable` that both query result processing and TOON serialization consult. Register handlers at module load. Enables extending for `uuid.UUID`, `memoryview`, `bytearray`, custom SQL types without touching core logic. |
| SQL identifier validation against metadata | Current `_sanitize_identifier` uses regex `[a-zA-Z0-9_\s]+` -- rejects valid SQL Server identifiers (e.g., names with hyphens, unicode chars) and cannot verify the column actually exists | Medium | MetadataService (already exists) | Pattern: accept identifier if it matches a known column/table from metadata cache, OR is bracket-quoted. This prevents injection AND handles weird-but-valid names. Requires threading metadata context into QueryService. |
| Configuration file for connections and defaults | Currently all config is passed via MCP tool parameters at call time; no way to set defaults, connection presets, or customize SP allowlist without code changes | Medium | tomllib (stdlib in 3.11+) | TOML is the Python standard (PEP 680). Pattern: `dbmcp.toml` in project root or `~/.config/dbmcp/config.toml`. Sections: `[defaults]` (query_timeout, row_limit, pool_recycle), `[connections.name]` (server, database, auth), `[validation]` (additional safe_procedures). Config is optional -- all current behavior works without a file. |
| sqlglot version pinning with edge case fixtures | sqlglot API changes between major versions (e.g., Execute vs Command for EXEC between v25 and v29); current range `>=26,<30` is wide | Low-Medium | None | Pin more tightly to the currently-installed minor version. Add test fixtures for known parsing edge cases: DBCC commands, multi-statement batches, EXEC with output params, nested CTEs. These act as regression canaries when bumping sqlglot. |

## Anti-Features

Features to explicitly NOT build.

| Anti-Feature | Why Avoid | What to Do Instead |
|--------------|-----------|-------------------|
| Pydantic migration | PROJECT.md explicitly marks this out of scope; dataclasses work fine for this scale. Pydantic adds import overhead and dependency weight for no benefit here. | Keep dataclasses. Fix type issues by adding proper fields or companion types. |
| Custom exception middleware/framework | Over-engineering for a tool with 9 endpoints. Exception handling should be specific but simple -- not an abstract framework. | Map specific exceptions to error responses at the tool boundary. A simple helper function per error category is sufficient. |
| Configuration GUI/TUI | This is a headless MCP server consumed by LLMs. No human interacts with it directly at runtime. | TOML config file with clear defaults and comments. |
| Retry logic for Azure AD tokens | Token refresh on expiry is correct; automatic retry with backoff adds complexity and can mask auth misconfiguration. | Fail fast on auth errors with actionable messages (already done well in azure_auth.py). Use pool_recycle for preemptive refresh. |
| Query result caching | Explicitly out of scope per PROJECT.md; adds stale data risk and memory pressure for unclear benefit. | Keep stateless: every query hits the database. |
| Audit logging | Explicitly out of scope per PROJECT.md; future milestone. | Defer entirely. |

## Feature Dependencies

```
Dead code removal -------> (none, independent)
Exception specificity ---> (none, but benefits from test coverage to verify no regressions)
Type ignore cleanup -----> (none, independent; creates QueryResult type)
Test coverage -----------> Exception specificity (tests validate correct exceptions caught)
                       --> Type ignore cleanup (tests validate new QueryResult type)
                       --> MCP session cleanup (tests validate cleanup behavior)
Azure AD token refresh --> (none, independent change to pool_recycle + token caching)
MCP session cleanup -----> (none, but test coverage should cover it)
Identifier validation ---> MetadataService (already exists, need to thread context)
Type handler registry ---> Type ignore cleanup (registry replaces inline chains)
                       --> Serialization module (refactor _pre_serialize)
Config file -------------> (none, but influences defaults for pool_recycle, query_timeout, SP allowlist)
sqlglot pinning ---------> (none, independent; add test fixtures)
```

Key ordering constraint: do refactoring (exception specificity, type cleanup) BEFORE writing tests. Writing tests against code you plan to refactor wastes effort.

## MVP Recommendation

Prioritize (Phase 1 -- cleanup and safety):
1. **Dead code removal** -- 15 minutes, zero risk, cleans up codebase
2. **Exception specificity** -- highest impact on debuggability; the 25 bare-except blocks in metadata.py and MCP tools mask real errors
3. **Type ignore cleanup** -- small scope, introduces QueryResult container type
4. **MCP session cleanup** -- prevents connection leaks in production

Prioritize (Phase 2 -- hardening):
5. **Test coverage to 70%** -- validates Phase 1 changes and catches regressions; do after refactoring so tests cover final code
6. **Azure AD token refresh** -- prevents silent auth failures in long sessions
7. **sqlglot pinning + edge case fixtures** -- prevents surprise breakage on dependency updates

Defer (Phase 3 -- infrastructure):
8. **Identifier validation against metadata** -- requires threading metadata context; moderate scope
9. **Type handler registry** -- nice-to-have extensibility; current inline approach works
10. **Configuration file** -- lowest urgency; current parameter-passing works; most impactful for the SP allowlist customization

**Rationale:** Clean up first (dead code, exceptions, types), then prove it with tests, then add infrastructure. Config file is last because it only improves developer experience, not correctness or safety.

## Complexity Estimates

| Feature | Lines Changed (est.) | Test Effort | Risk |
|---------|---------------------|-------------|------|
| Dead code removal | ~5 (delete file, remove any stale refs) | None needed | Negligible |
| Exception specificity | ~100-150 (25 blocks to refine) | Medium (verify each exception path) | Low -- narrowing catches is safe |
| Type ignore cleanup | ~30-50 (new dataclass + refactor execute_query return) | Low-Medium | Low -- internal refactor |
| MCP session cleanup | ~15-25 (lifecycle hook + test) | Low | Low |
| Test coverage to 70% | ~300-500 (new test cases) | High (this IS the test effort) | Negligible |
| Azure AD token refresh | ~20-30 (pool_recycle tuning + token expiry check) | Medium (mock token expiry) | Low |
| sqlglot pinning | ~5 (pyproject.toml) + ~100 (edge case fixtures) | Medium | Low |
| Identifier validation | ~50-80 (metadata-aware validation) | Medium | Medium -- behavior change |
| Type handler registry | ~80-120 (registry + migration of inline handlers) | Medium | Low-Medium |
| Config file | ~150-200 (TOML loader + schema + integration) | Medium | Low |

## Exception Specificity Detail

Breakdown of the 25 `except Exception` blocks by module and what they should catch:

**metadata.py (13 blocks):** Most are around SQL Server DMV queries that can fail with permission errors or connectivity issues. Replace with `sqlalchemy.exc.OperationalError` (connection lost), `sqlalchemy.exc.ProgrammingError` (permission denied / invalid query), `pyodbc.Error` (driver-level failures).

**MCP tool layer (9 blocks across schema_tools, query_tools, analysis_tools):** These are the outermost boundary. Pattern: catch `ValueError` (validation), `ConnectionError` (auth/connect), `sqlalchemy.exc.SQLAlchemyError` (any DB operation), then bare `Exception` only as final sentinel with `logger.exception()`. Already partially done in some tools (connect_database catches ConnectionError and ValueError specifically).

**query.py (3 blocks):** `_run_query` catches Exception for query execution errors -- should catch `sqlalchemy.exc.OperationalError` (timeout, connection lost), `sqlalchemy.exc.ProgrammingError` (syntax error), `sqlalchemy.exc.ResourceClosedError` (result set issues). The `_get_total_row_count` swallows Exception silently -- acceptable for best-effort count, but should at minimum catch `sqlalchemy.exc.SQLAlchemyError`.

**connection.py (1 block):** Already specific (`ConnectionError` re-raise + generic Exception -> ConnectionError wrapping). Good pattern, no change needed.

## Sources

- Codebase analysis: all `src/` modules read directly (connection.py, query.py, validation.py, metadata.py, azure_auth.py, serialization.py, metrics.py, server.py, schema_tools.py, query_tools.py, analysis_tools.py)
- PROJECT.md: active requirements, out-of-scope items, constraints
- SQLAlchemy exception hierarchy: `sqlalchemy.exc` module -- OperationalError, ProgrammingError, InterfaceError, DisconnectionError, InvalidRequestError, ResourceClosedError
- pyodbc exception hierarchy: PEP 249 DB-API 2.0 -- DatabaseError > DataError, OperationalError, IntegrityError, InternalError, ProgrammingError, NotSupportedError
- azure-identity exceptions: `CredentialUnavailableError`, `ClientAuthenticationError` from `azure.core.exceptions`
- Azure AD token lifetime: default 60-75 minutes for access tokens (Microsoft identity platform documentation)
- Python 3.11 tomllib: PEP 680, stdlib read-only TOML parser
- FastMCP lifecycle: server context managers for startup/shutdown hooks
