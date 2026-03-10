# Phase 7: Wire Orphaned Exports - Context

**Gathered:** 2026-03-10
**Status:** Ready for planning

<domain>
## Phase Boundary

All cross-phase exports are wired into production code — no config fields are silently ignored and no utility functions are dead code. Specifically: `text_truncation_limit` config flows into query.py truncation, and `_classify_db_error` is called in production error paths.

</domain>

<decisions>
## Implementation Decisions

### _classify_db_error wiring
- Wire into all 9 MCP tool safety nets (schema_tools, query_tools, analysis_tools)
- Safety nets remain `except Exception:` — classification makes them smarter, not narrower
- When caught exception IS a SQLAlchemyError: pass through `_classify_db_error` for actionable guidance
- Non-SQLAlchemy errors: keep generic `str(e)` fallback as before
- Error format: guidance first + raw exception detail in parens — e.g., "Authentication failure: Check your credentials and verify the account has access. (Login failed for user 'bob')"
- Import `_classify_db_error` from `src.db.connection` into each tool module

### text_truncation_limit plumbing
- Read config inline at each call site: `get_config().defaults.text_truncation_limit`
- Replace hardcoded `1000` at query.py lines ~333 and ~667
- Same pattern already used in query_tools.py for sample_size and row_limit
- No API changes to QueryService — internal-only change

### Truncation test approach
- Unit test with mocked `get_config`: patch to return limit=500, run query with 700-char string, assert truncation occurs
- Verify the inverse: patch with limit=1000, assert same string is NOT truncated
- No integration test with real TOML file needed — unit coverage sufficient

### Claude's Discretion
- Exact `isinstance` check pattern for SQLAlchemyError detection in safety nets
- Whether to extract a shared helper for the classify-and-format pattern or inline it in each tool
- Test structure for _classify_db_error wiring (per-tool tests vs parametrized)

</decisions>

<specifics>
## Specific Ideas

- Phase 3 narrowed db-layer exceptions to specific types; Phase 4 created `_classify_db_error` for reuse. This phase completes the circuit by wiring classification into the MCP tool safety nets.
- Error classification improves UX without changing the exception handling architecture — safety nets stay broad, messages get specific.

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `_classify_db_error` (connection.py:60-108): Maps SQLSTATE 28xxx→auth_failure, 08xxx→connection_lost, token+expired→token_expired, fallback→unknown. Already has 9 tests.
- `get_config()` (config.py:280): Singleton accessor, returns `AppConfig` with `defaults.text_truncation_limit`. Already used in query_tools.py and validation.py.
- `convert()` from type_handlers registry: Called at query.py:333 and :667 with hardcoded `1000` — second arg is the truncation limit to replace.

### Established Patterns
- query_tools.py already reads config inline: `get_config().defaults.sample_size` and `get_config().defaults.row_limit`
- Tool safety nets follow identical pattern: `except Exception as e: return encode_response({"status": "error", "error_message": str(e)})`
- Phase 4 decision: `_classify_db_error` is module-level function (not method) specifically for cross-module reuse

### Integration Points
- `src/mcp_server/schema_tools.py` — 4 tool safety nets to enhance
- `src/mcp_server/query_tools.py` — 3 tool safety nets to enhance
- `src/mcp_server/analysis_tools.py` — 2 tool safety nets to enhance
- `src/db/query.py:333` — `convert(value, 1000)` → `convert(value, get_config().defaults.text_truncation_limit)`
- `src/db/query.py:667` — same replacement

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 07-wire-orphaned-exports*
*Context gathered: 2026-03-10*
