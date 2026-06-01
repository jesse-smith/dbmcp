# Phase 6: Serialization & Configuration - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

Type conversion is centralized into a single registry replacing the separate `_truncate_value()` and `_pre_serialize()` pipelines. The server supports an optional TOML config file for named connections, default parameters, and SP allowlist extensions. Missing or malformed config degrades gracefully.

</domain>

<decisions>
## Implementation Decisions

### Unified type pipeline
- Single registry mapping Python types to handler functions — each handler does BOTH conversion and truncation in one pass
- Every handler returns `(converted_value, was_truncated)` tuple — callers that don't need truncation tracking ignore the flag
- TypeError raised on unknown types (strict) — matches existing project decision from Phase 3; no silent str() fallback
- Registry is internal-only (Python code) — not extensible via config file. New types require code changes + tests
- Replaces both `_truncate_value()` in query.py and `_pre_serialize()` in serialization.py with a single pipeline
- Fallback logging for unknown types is not needed since TypeError is raised (strict mode)

### Config file discovery
- Check project-local `dbmcp.toml` first, then `~/.dbmcp/config.toml` — local overrides global
- Use Python 3.11+ stdlib `tomllib` — no new dependency
- Missing config file is normal — no warning, just no config loaded
- Malformed config file (invalid TOML or invalid values): log a warning with the parse error, skip entire config, continue with defaults

### Named connections
- New optional `connection_name` parameter on `connect_database` MCP tool
- If provided, loads connection settings from config file's `[connections.<name>]` section
- Other explicitly provided params override config values (tool args > config > hardcoded defaults)
- Existing interface unchanged when no connection_name given — fully backward compatible

### Credentials in config
- Credentials (password, tenant_id) support environment variable references
- Env var syntax: Claude's discretion (pick between `$VAR_NAME` prefix or `${VAR_NAME}` expansion based on simplicity and TOML conventions)
- Unresolved env vars produce a clear error at connection time, not at config load time

### Config defaults section
- A `[defaults]` section sets fallback values for all connections and tool behavior
- Named connections inherit from defaults and can override per-connection
- Configurable defaults (query-facing only):
  - `query_timeout` — default query execution timeout
  - `text_truncation_limit` — max chars before truncation (currently 1000)
  - `sample_size` — default sample rows (currently 5)
  - `row_limit` — default row limit for execute_query (currently 1000, capped at 10000 per tool contract)
- Pool settings (pool_size, max_overflow, pool_timeout) stay hardcoded — internal implementation detail
- All configurable values validated with min/max bounds — out-of-range values warn and fall back to hardcoded defaults
- No config inspection tool — config effects are visible through tool behavior

### Precedence rules
- Explicit MCP tool args > config file values > hardcoded defaults
- Project-local `dbmcp.toml` > user-global `~/.dbmcp/config.toml`

### SP allowlist extension
- Config can ADD stored procedures to the allowlist — additive only, cannot remove hardcoded system SPs
- Merged allowlist = union of hardcoded system SPs + config-provided SPs
- SP names validated with syntax check (identifier pattern) — no SQL injection via SP names in config
- Schema-qualified names supported: `dbo.my_custom_report` or just `my_proc` (unqualified matches any schema)
- No limit on number of user-added SPs — set lookup, negligible performance impact
- Hardcoded system SPs (sp_tables, sp_columns, etc.) remain non-overridable regardless of config content

### Claude's Discretion
- Env var reference syntax choice ($VAR vs ${VAR})
- Exact min/max bounds for each configurable default
- Type handler registry internal structure (dict, class, or module-level functions)
- Config loading architecture (module-level singleton vs passed-through parameter)
- TOML section naming conventions for connections and defaults

</decisions>

<specifics>
## Specific Ideas

- User wants env var references for credentials rather than plaintext or no-credentials — balance of convenience and security
- Validation bounds should prevent foot-guns (e.g., query_timeout=0) but not be overly restrictive
- Named connections are a shortcut, not a replacement — existing connect_database interface must remain fully functional without config
- Row limit is configurable as a default but still hard-capped at 10000 per the MCP tool contract

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_pre_serialize()` (serialization.py): Handles datetime, date, Decimal, StrEnum, dict/list/tuple recursion. 70 lines. Will be absorbed into unified registry.
- `_truncate_value()` (query.py:340-379): Handles bytes, datetime, date, time, Decimal, large text. Will be absorbed into unified registry.
- `PoolConfig` dataclass (connection.py:27-44): Already parameterizes pool settings — pattern for config-driven defaults.
- `tomllib` in Python 3.11+ stdlib — no dependency needed for TOML parsing.

### Established Patterns
- Strict TypeError on unknown types (serialization.py:54) — unified registry preserves this
- `ConnectionManager` constructor takes optional `PoolConfig` — config values flow through similar injection pattern
- `AuthenticationMethod` enum distinguishes auth types — config connections specify auth_method the same way
- DEBUG logging pattern via `src/logging_config.py` — config warnings use same pattern

### Integration Points
- `serialization.py:encode_response()` — entry point for TOON encoding, will call unified registry instead of `_pre_serialize`
- `query.py:QueryService._truncate_value()` — will be replaced by registry calls
- `query.py:QueryService._process_rows()` — calls `_truncate_value`, will call registry instead
- `connection.py:ConnectionManager.connect()` — where config-loaded connection params would be applied
- `server.py` — config loading at startup, before `mcp.run()`
- `validation.py:ALLOWED_STORED_PROCEDURES` — where config SP allowlist merges in

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 06-serialization-configuration*
*Context gathered: 2026-03-10*
