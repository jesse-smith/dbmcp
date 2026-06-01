# Phase 4: Connection Management - Research

**Researched:** 2026-03-09
**Domain:** SQLAlchemy connection pooling, Azure AD token lifecycle, process shutdown cleanup
**Confidence:** HIGH

## Summary

Phase 4 has two focused requirements: (1) Azure AD token refresh via pool_recycle/pool_pre_ping so connections survive 60+ minute sessions, and (2) cleanup of all connections on MCP server exit via atexit/SIGTERM. The existing codebase already has most of the infrastructure -- `PoolConfig` with `pool_recycle` and `pool_pre_ping`, `AzureTokenProvider.get_token()` that can be called repeatedly, `disconnect_all()` that disposes all engines, and a `creator` callable pattern that acquires a fresh token on every new connection.

The changes are surgical: (a) make `_create_engine` set `pool_recycle=2700` for Azure AD auth methods instead of the default 3600, (b) register `atexit.register(connection_manager.disconnect_all)` in server.py, (c) add SIGTERM-to-sys.exit handler, and (d) improve error messages with cause-specific guidance for connection vs auth failures. No new dependencies are needed.

**Primary recommendation:** This phase is low-risk incremental work on well-understood SQLAlchemy APIs. The creator callable pattern already handles token refresh on new connections; pool_recycle just needs a shorter value for Azure AD. Focus implementation time on error classification and test coverage rather than the pool mechanics.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Auth-aware pool_recycle: Azure AD connections get pool_recycle=2700 (45 min), SQL auth and Windows auth connections keep pool_recycle=3600 (1 hour)
- Hook into SQLAlchemy pool events to silently re-acquire a fresh Azure AD token when pool_pre_ping detects a stale connection -- non-Azure connections are not affected
- Token re-acquisition is silent -- log at DEBUG level only, never surface to user in tool responses
- The 2700s Azure AD recycle value is the hardcoded default but overridable via PoolConfig for power users with non-standard token lifetimes
- If token re-acquisition itself fails (credential source revoked): fail the current query with a clear error AND auto-disconnect the stale connection to keep things clean
- Register `atexit.register(connection_manager.disconnect_all)` in server.py for normal exits
- Add a one-liner SIGTERM handler that converts SIGTERM to sys.exit(0) so atexit fires on process manager termination
- Cleanup logs at DEBUG level -- invisible in normal use, available for troubleshooting
- Best-effort cleanup: if engine.dispose() throws, swallow the error (log at DEBUG), continue to next connection
- No automatic retry on connection failure -- pool_pre_ping already handles stale connections before execution
- Include cause-specific actionable guidance in error messages, but ONLY suggest actions that are always valid for that error type
- Distinguish between error types: OperationalError (connection lost) gets different guidance than auth failures (credential expired)
- Keep current defaults: pool_size=5, max_overflow=10, pool_timeout=30s, query_timeout=30s -- no changes to pool sizing

### Claude's Discretion
- Exact SQLAlchemy pool event hook implementation for token re-acquisition (e.g., pool_checkout, pool_connect, or custom pre_ping handler)
- Which specific SQLAlchemy/pyodbc error types map to "connection lost" vs "auth expired" -- use what's reliably detectable
- Exact error message wording for each failure category
- Whether to add tests for the atexit/SIGTERM cleanup path (may require mocking process signals)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONN-01 | Azure AD token refresh handled via `pool_recycle` (< token lifetime) and `pool_pre_ping` so pooled connections with expired tokens are discarded before use | Auth-aware pool_recycle in `_create_engine`, existing creator callable pattern handles token refresh on new connection creation, pool_pre_ping already enabled |
| CONN-02 | Database connections cleaned up when MCP session ends via `atexit` handler (or FastMCP lifecycle hook if available) | atexit.register + SIGTERM handler in server.py, disconnect_all() already implements full cleanup, best-effort error swallowing in shutdown path |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlalchemy | 2.0.47 | Connection pooling, pool events, engine lifecycle | Already in use; pool_recycle and pool_pre_ping are native features |
| azure-identity | >=1.14.0 | DefaultAzureCredential for token acquisition/refresh | Already in use; get_token() handles token caching/refresh internally |
| pyodbc | >=5.0.0 | DBAPI connection to SQL Server | Already in use; SQL_COPT_SS_ACCESS_TOKEN for token-based auth |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| atexit | stdlib | Register shutdown cleanup handlers | Process exit cleanup |
| signal | stdlib | SIGTERM handler to trigger clean exit | Process manager termination |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| atexit + SIGTERM | FastMCP lifecycle hooks | FastMCP has no session-level lifecycle hooks (confirmed in STATE.md); atexit is the only option |
| pool_recycle for token expiry | Custom pool event to check token expiry time | Unnecessary complexity; pool_recycle at 2700s (< 3600s default Azure AD token lifetime) is sufficient |

**Installation:**
No new dependencies needed. All libraries already installed.

## Architecture Patterns

### Recommended Change Map
```
src/
  db/
    connection.py     # Auth-aware pool_recycle, best-effort disconnect_all, error classification
  mcp_server/
    server.py         # atexit registration, SIGTERM handler
tests/
  unit/
    test_connection.py  # New tests for pool_recycle, error classification, shutdown cleanup
```

### Pattern 1: Auth-Aware Pool Recycle
**What:** Set `pool_recycle=2700` for Azure AD auth methods, keep 3600 for others
**When to use:** In `_create_engine` when building pool_kwargs
**Example:**
```python
# In _create_engine, before creating the engine:
pool_recycle = self._pool_config.pool_recycle
if authentication_method in (
    AuthenticationMethod.AZURE_AD,
    AuthenticationMethod.AZURE_AD_INTEGRATED,
):
    # Azure AD tokens expire at ~3600s; recycle at 2700s (45 min) to stay ahead
    # Use PoolConfig value only if user explicitly overrode it; otherwise use 2700
    if self._pool_config.pool_recycle == PoolConfig.pool_recycle:  # default unchanged
        pool_recycle = 2700

pool_kwargs["pool_recycle"] = pool_recycle
```

**Design note:** The `PoolConfig.pool_recycle` default is 3600. To detect whether the user explicitly set it (power user override), compare against the dataclass field default. If it matches 3600, apply the Azure AD override of 2700. If the user set it to something else, respect their choice. An alternative approach is to add an `azure_ad_pool_recycle` field to PoolConfig -- simpler and more explicit.

### Pattern 2: Token Refresh via Creator + pool_pre_ping
**What:** The existing `creator` callable in `_create_engine` already calls `provider.get_token()` on every invocation. When `pool_pre_ping=True` detects a stale/dead connection, SQLAlchemy invalidates it and creates a new one via `creator`, which automatically gets a fresh token.
**When to use:** Already in place -- no code changes needed for the core token refresh mechanism
**How it works:**
1. `pool_pre_ping=True` causes SQLAlchemy to issue `SELECT 1` before returning a pooled connection
2. If the ping fails (expired token = closed connection), the connection is invalidated
3. SQLAlchemy creates a new connection via `creator()`
4. `creator()` calls `provider.get_token()` which acquires a fresh token via DefaultAzureCredential
5. DefaultAzureCredential handles token caching internally -- it returns cached tokens when valid, refreshes when expired

**Key insight:** No pool event hooks are needed for the core refresh mechanism. The creator callable pattern already solves this. Pool events would only be needed if we wanted to do something extra (like logging) during token refresh, which we don't (DEBUG logging of the token re-acquisition happens naturally inside DefaultAzureCredential).

### Pattern 3: Best-Effort Shutdown Cleanup
**What:** atexit handler + SIGTERM -> sys.exit(0) one-liner
**Example:**
```python
# In server.py, after creating _connection_manager:
import atexit
import signal
import sys

atexit.register(_connection_manager.disconnect_all)

def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    logger.info("Starting dbmcp MCP server")
    mcp.run(transport="stdio")
```

### Pattern 4: Error Classification for Connection Failures
**What:** Distinguish connection-lost vs auth-expired errors for actionable messages
**When to use:** In query execution error handling and potentially in connect()
**Example:**
```python
from sqlalchemy.exc import OperationalError, DBAPIError

# OperationalError with specific pyodbc codes indicates connection issues
# pyodbc.Error subtypes carry SQLSTATE codes:
#   08S01 = Communication link failure
#   08001 = Unable to connect
#   HYT00 = Timeout expired
#   28000 = Invalid authorization (login failed)

def classify_connection_error(exc: SQLAlchemyError) -> str:
    """Classify a connection error for user-facing messages."""
    orig = getattr(exc, 'orig', None)
    if orig and hasattr(orig, 'args') and len(orig.args) >= 1:
        sqlstate = orig.args[0] if isinstance(orig.args[0], str) else ''
        if sqlstate.startswith('08'):
            return "connection_lost"
        if sqlstate == '28000':
            return "auth_failed"
    # Fallback: check message content
    msg = str(exc).lower()
    if 'login failed' in msg or 'credential' in msg or 'token' in msg:
        return "auth_failed"
    if 'communication' in msg or 'connection' in msg or 'network' in msg:
        return "connection_lost"
    return "unknown"
```

### Anti-Patterns to Avoid
- **Custom pool_pre_ping implementation:** SQLAlchemy's built-in `pool_pre_ping=True` handles this correctly. Do not implement a custom "do_ping" event -- just use the flag.
- **Token caching in application code:** DefaultAzureCredential already caches tokens internally. Do not add a second caching layer.
- **Retry loops on connection failure:** The CONTEXT.md explicitly says no automatic retry. pool_pre_ping handles stale connections; mid-execution failures are real failures.
- **Catching broad Exception in shutdown:** While the shutdown path should swallow errors, catch specific exception types (SQLAlchemyError, OSError) rather than bare Exception.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Token refresh timing | Timer thread to refresh tokens proactively | pool_recycle + creator callable | SQLAlchemy handles connection lifecycle; creator gets fresh token on each new connection |
| Connection health check | Custom ping/heartbeat loop | pool_pre_ping=True | SQLAlchemy's built-in pre-ping is battle-tested and integrates with the pool lifecycle |
| Token caching | Manual token cache with expiry tracking | DefaultAzureCredential internal caching | azure-identity handles token cache, refresh tokens, and credential chain internally |
| Graceful shutdown | Custom signal handling framework | atexit + signal.signal one-liner | stdlib provides everything needed; over-engineering shutdown adds complexity |

**Key insight:** The existing creator callable pattern + pool_pre_ping + pool_recycle already provides 90% of what CONN-01 needs. The main new code is the auth-aware pool_recycle value and error classification.

## Common Pitfalls

### Pitfall 1: pool_recycle Too Close to Token Lifetime
**What goes wrong:** If pool_recycle equals the token lifetime (3600s), connections may still be returned with an expired token in the window between recycle check and actual use.
**Why it happens:** pool_recycle is checked at checkout time against the connection's creation timestamp. Network latency or processing time can push actual use past the token expiry.
**How to avoid:** Set pool_recycle well below token lifetime. 2700s (45 min) provides a 15-minute buffer.
**Warning signs:** Intermittent auth failures after ~60 minutes of idle time.

### Pitfall 2: atexit Not Firing on SIGKILL
**What goes wrong:** If the process is killed with SIGKILL (kill -9), atexit handlers never run and connections leak.
**Why it happens:** SIGKILL cannot be caught by any handler. This is an OS-level constraint.
**How to avoid:** Accept this as a known limitation. Database connection timeouts will eventually clean up server-side. Document that SIGTERM is the proper way to stop the server.
**Warning signs:** "Ghost" connections visible in SQL Server's sys.dm_exec_sessions after server stop.

### Pitfall 3: Swallowing Errors Masking Real Problems
**What goes wrong:** Best-effort shutdown cleanup swallows all errors, hiding bugs in disconnect logic.
**Why it happens:** The CONTEXT.md says to swallow errors during shutdown, which is correct for production, but tests should verify the cleanup logic works.
**How to avoid:** Log swallowed errors at DEBUG level so they're available for troubleshooting. Unit tests should verify disconnect_all works correctly in the normal case.

### Pitfall 4: SIGTERM Handler and asyncio Event Loop
**What goes wrong:** Calling sys.exit(0) from a signal handler inside an asyncio event loop can cause warnings or incomplete cleanup.
**Why it happens:** FastMCP runs an asyncio event loop. Signal handlers run in the main thread, and sys.exit() raises SystemExit which may interrupt the event loop.
**How to avoid:** The simple `lambda *_: sys.exit(0)` approach should work because (a) sys.exit raises SystemExit which Python handles gracefully, and (b) atexit handlers run after the event loop is stopped. If issues arise during testing, an alternative is `loop.call_soon_threadsafe(loop.stop)` but this adds unnecessary complexity.
**Warning signs:** "RuntimeWarning: coroutine was never awaited" messages on shutdown.

### Pitfall 5: Detecting User-Overridden PoolConfig Values
**What goes wrong:** Using `self._pool_config.pool_recycle == 3600` to detect "default" is fragile -- a user could explicitly set 3600 and we'd override it.
**Why it happens:** Python dataclass defaults don't distinguish "explicitly set to default" from "never set."
**How to avoid:** Either (a) add an `azure_ad_pool_recycle: int | None = None` field to PoolConfig where None means "use default 2700 for Azure AD," or (b) just always apply 2700 for Azure AD unless `azure_ad_pool_recycle` is set. Option (b) is simpler and matches the CONTEXT.md: "hardcoded default but overridable via PoolConfig."

## Code Examples

### Auth-Aware pool_recycle in _create_engine
```python
# Source: Existing connection.py pattern + CONTEXT.md decision
def _create_engine(
    self,
    odbc_conn_str: str,
    authentication_method: AuthenticationMethod,
    tenant_id: str | None,
    query_timeout: int = 30,
) -> Engine:
    # Determine pool_recycle based on auth method
    pool_recycle = self._pool_config.pool_recycle
    is_azure = authentication_method in (
        AuthenticationMethod.AZURE_AD,
        AuthenticationMethod.AZURE_AD_INTEGRATED,
    )
    if is_azure:
        pool_recycle = self._pool_config.azure_ad_pool_recycle or 2700
        logger.debug(f"Azure AD auth: pool_recycle set to {pool_recycle}s")

    pool_kwargs = {
        "poolclass": QueuePool,
        "pool_size": self._pool_config.pool_size,
        "max_overflow": self._pool_config.max_overflow,
        "pool_timeout": self._pool_config.pool_timeout,
        "pool_pre_ping": self._pool_config.pool_pre_ping,
        "pool_recycle": pool_recycle,
        "echo": False,
    }
    # ... rest unchanged
```

### PoolConfig with Azure AD Override Field
```python
@dataclass
class PoolConfig:
    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True
    query_timeout: int = 30
    azure_ad_pool_recycle: int = 2700  # Separate field for Azure AD token-aware recycle
```

### Best-Effort disconnect_all
```python
def disconnect_all(self) -> int:
    """Close all database connections (best-effort for shutdown)."""
    count = len(self._engines)
    for conn_id, engine in list(self._engines.items()):
        try:
            engine.dispose()
        except Exception:
            logger.debug(f"Error disposing engine {conn_id} during shutdown", exc_info=True)
    self._engines.clear()
    self._connections.clear()
    logger.debug(f"Shutdown cleanup: disposed {count} connections")
    return count
```

### SIGTERM + atexit Registration in server.py
```python
import atexit
import signal
import sys

# ... after _connection_manager creation ...
atexit.register(_connection_manager.disconnect_all)

def main():
    signal.signal(signal.SIGTERM, lambda *_: sys.exit(0))
    logger.info("Starting dbmcp MCP server")
    mcp.run(transport="stdio")
```

### Error Classification
```python
from sqlalchemy.exc import OperationalError

def _classify_db_error(exc: SQLAlchemyError) -> tuple[str, str]:
    """Classify a database error and return (category, guidance).

    Returns:
        Tuple of (error_category, user_guidance_message)
    """
    orig = getattr(exc, 'orig', None)
    sqlstate = ''
    if orig and hasattr(orig, 'args') and orig.args:
        sqlstate = str(orig.args[0]) if orig.args else ''

    # SQLSTATE 28xxx = auth/login failures
    if sqlstate.startswith('28'):
        return ("auth_failure",
                "Login failed. Verify your credentials are correct.")

    # SQLSTATE 08xxx = connection failures
    if sqlstate.startswith('08'):
        return ("connection_lost",
                "Connection to the database was lost. The server may be unreachable.")

    # Check for Azure AD specific errors in the message
    msg_lower = str(exc).lower()
    if 'token' in msg_lower and ('expired' in msg_lower or 'invalid' in msg_lower):
        return ("token_expired",
                "Azure AD token has expired. Re-authenticate with 'az login'.")

    return ("unknown", "An unexpected database error occurred.")
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual connection health checks | pool_pre_ping=True (SA 1.2+) | SQLAlchemy 1.2 (2018) | Built-in, no custom code needed |
| Fixed pool_recycle for all auth | Auth-aware pool_recycle | This phase | Azure AD connections recycled before token expiry |
| No shutdown cleanup | atexit + SIGTERM handler | This phase | Clean connection disposal on process exit |

**Deprecated/outdated:**
- `pool_listeners` (pre-SQLAlchemy 0.7): Use `event.listens_for` instead (already done in codebase)
- `engine.pool.dispose()`: Use `engine.dispose()` which handles pool recreation

## Open Questions

1. **Azure AD token lifetime variability**
   - What we know: Default Azure AD token lifetime is ~3600s (1 hour). 2700s pool_recycle provides 15-minute buffer.
   - What's unclear: Some Azure AD configurations allow custom token lifetimes (Configurable Token Lifetimes policy). Could be shorter than 2700s.
   - Recommendation: 2700s default is safe for standard configurations. The `azure_ad_pool_recycle` PoolConfig field handles non-standard lifetimes.

2. **Azure AD password auth (AZURE_AD method) token handling**
   - What we know: AZURE_AD method uses `Authentication=ActiveDirectoryPassword` in ODBC string -- the ODBC driver handles token acquisition internally, not our creator callable.
   - What's unclear: Whether pool_recycle is sufficient for AZURE_AD (driver-managed tokens) or only applies to AZURE_AD_INTEGRATED (our creator callable).
   - Recommendation: Apply the 2700s pool_recycle to both Azure AD methods. For AZURE_AD, the ODBC driver handles token refresh when creating new connections; pool_recycle ensures stale connections are discarded.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 9.0.2 + pytest-asyncio 1.3.0 |
| Config file | pyproject.toml [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/test_connection.py -x` |
| Full suite command | `uv run pytest tests/ -m "not integration and not performance" -x` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| CONN-01a | Azure AD pool_recycle set to 2700 | unit | `uv run pytest tests/unit/test_connection.py -x -k "pool_recycle and azure"` | Partially (T020 exists but tests 3600, needs update) |
| CONN-01b | SQL/Windows auth keeps pool_recycle=3600 | unit | `uv run pytest tests/unit/test_connection.py -x -k "pool_recycle and not azure"` | No (Wave 0) |
| CONN-01c | Creator callable gets fresh token on pool reconnect | unit | `uv run pytest tests/unit/test_connection.py -x -k "creator_calls_get_token"` | Yes (T019 exists) |
| CONN-01d | Token re-acquisition failure disconnects stale connection | unit | `uv run pytest tests/unit/test_connection.py -x -k "token_failure_disconnect"` | No (Wave 0) |
| CONN-02a | atexit.register called with disconnect_all | unit | `uv run pytest tests/unit/test_connection.py -x -k "atexit"` | No (Wave 0) |
| CONN-02b | SIGTERM handler converts to sys.exit(0) | unit | `uv run pytest tests/unit/test_connection.py -x -k "sigterm"` | No (Wave 0) |
| CONN-02c | disconnect_all swallows errors best-effort | unit | `uv run pytest tests/unit/test_connection.py -x -k "disconnect_all_best_effort"` | No (Wave 0) |
| CONN-02d | Error classification returns correct category | unit | `uv run pytest tests/unit/test_connection.py -x -k "classify_error"` | No (Wave 0) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_connection.py -x`
- **Per wave merge:** `uv run pytest tests/ -m "not integration and not performance" -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Tests for auth-aware pool_recycle (2700 for Azure AD, 3600 for SQL/Windows)
- [ ] Tests for best-effort disconnect_all error swallowing
- [ ] Tests for atexit registration in server.py
- [ ] Tests for SIGTERM handler (may use signal mocking)
- [ ] Tests for error classification function
- [ ] Tests for token re-acquisition failure triggering auto-disconnect

## Sources

### Primary (HIGH confidence)
- SQLAlchemy 2.0.47 installed locally -- pool events, pool_recycle, pool_pre_ping behavior verified via introspection
- Existing codebase: `src/db/connection.py`, `src/db/azure_auth.py`, `src/mcp_server/server.py` -- current implementation patterns
- Python stdlib docs: `atexit`, `signal` modules -- standard behavior

### Secondary (MEDIUM confidence)
- Azure AD token lifetime defaults (3600s) -- based on Microsoft documentation for Configurable Token Lifetimes

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- all libraries already in use, no new dependencies
- Architecture: HIGH -- patterns directly from existing code + SQLAlchemy documented APIs
- Pitfalls: HIGH -- based on well-understood SQLAlchemy pool mechanics and stdlib signal handling

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable domain, no fast-moving dependencies)
