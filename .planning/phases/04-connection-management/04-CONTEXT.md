# Phase 4: Connection Management - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Database connections survive long-running sessions and are cleaned up when sessions end. Azure AD token refresh is handled transparently so pooled connections don't fail after 60+ minutes of idle time. All connections are properly disposed when the MCP server process exits.

</domain>

<decisions>
## Implementation Decisions

### Token refresh strategy
- Auth-aware pool_recycle: Azure AD connections get pool_recycle=2700 (45 min), SQL auth and Windows auth connections keep pool_recycle=3600 (1 hour)
- Hook into SQLAlchemy pool events to silently re-acquire a fresh Azure AD token when pool_pre_ping detects a stale connection — non-Azure connections are not affected
- Token re-acquisition is silent — log at DEBUG level only, never surface to user in tool responses
- The 2700s Azure AD recycle value is the hardcoded default but overridable via PoolConfig for power users with non-standard token lifetimes
- If token re-acquisition itself fails (credential source revoked): fail the current query with a clear error AND auto-disconnect the stale connection to keep things clean

### Session cleanup
- Register `atexit.register(connection_manager.disconnect_all)` in server.py for normal exits
- Add a one-liner SIGTERM handler that converts SIGTERM to sys.exit(0) so atexit fires on process manager termination
- Cleanup logs at DEBUG level — invisible in normal use, available for troubleshooting
- Best-effort cleanup: if engine.dispose() throws, swallow the error (log at DEBUG), continue to next connection. Crashing during shutdown is worse than leaking a connection.

### Connection failure UX
- No automatic retry on connection failure — pool_pre_ping already handles stale connections before execution. If a query fails mid-execution, it's a real failure.
- Include cause-specific actionable guidance in error messages, but ONLY suggest actions that are always valid for that error type. Incorrect guidance is worse than none.
- Distinguish between error types: OperationalError (connection lost) gets different guidance than auth failures (credential expired). Each message must be accurate for its cause.

### Pool tuning
- Keep current defaults: pool_size=5, max_overflow=10, pool_timeout=30s, query_timeout=30s
- These are fine for MCP single-agent usage — idle connections are cheap and the overhead is minimal
- No changes to pool sizing in this phase

### Claude's Discretion
- Exact SQLAlchemy pool event hook implementation for token re-acquisition (e.g., pool_checkout, pool_connect, or custom pre_ping handler)
- Which specific SQLAlchemy/pyodbc error types map to "connection lost" vs "auth expired" — use what's reliably detectable
- Exact error message wording for each failure category
- Whether to add tests for the atexit/SIGTERM cleanup path (may require mocking process signals)

</decisions>

<specifics>
## Specific Ideas

- Token re-acquisition should be invisible — the user asked about whether it requires re-authentication and was satisfied that DefaultAzureCredential handles this silently via cached refresh tokens
- Error guidance must be conservative: "only suggest actions that are always valid for that error type — incorrect guidance is worse than none"
- The SIGTERM handler is literally a one-liner: `signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))`

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `ConnectionManager.disconnect_all()` (connection.py:416-428): Already implements full cleanup — dispose all engines, clear dicts. Just needs to be called on shutdown.
- `ConnectionManager.disconnect()` (connection.py:398-414): Per-connection cleanup for the auto-disconnect-on-auth-failure case.
- `AzureTokenProvider` (azure_auth.py): Already acquires tokens via DefaultAzureCredential. `get_token()` can be called again for refresh — no code changes needed for re-acquisition itself.
- `PoolConfig` dataclass (connection.py:27-44): Already has pool_recycle and pool_pre_ping fields. Auth-aware defaults just change how pool_recycle is set per engine.

### Established Patterns
- Each `connect_database()` call creates its own SQLAlchemy engine with its own pool — auth-aware recycle can be set per-engine at creation time
- `AuthenticationMethod` enum (schema.py) distinguishes sql/windows/azure_ad/azure_ad_integrated — already available for conditional logic
- Exception handling in db layer uses SQLAlchemyError (narrowed in Phase 3) — connection failure detection builds on this
- DEBUG logging pattern established across the codebase via `src/logging_config.py`

### Integration Points
- `server.py:26` — Global `_connection_manager = ConnectionManager()` is where atexit registration happens
- `server.py:58-61` — `main()` is where SIGTERM handler registration happens (before `mcp.run()`)
- `connection.py:_create_engine()` — Where auth-aware pool_recycle gets applied based on auth method
- `connection.py:connect()` — Where Azure AD token provider is created; pool event hooks attach here

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 04-connection-management*
*Context gathered: 2026-03-09*
