# Phase 1: Atomic TOON Migration - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

Replace JSON serialization with TOON across all 9 MCP tools, all tests, and all docstrings in a single coordinated swap. Response structure (field names, types, nesting) remains identical — only serialization format changes. No new tools, no business logic changes, no data model changes.

</domain>

<decisions>
## Implementation Decisions

### Wrapper module design
- New `src/serialization.py` module encapsulates `toon_format.encode()` (satisfies SRLZ-02)
- Single `encode_response(data: dict) -> str` function — no separate error helper
- All responses (success and error) go through TOON encoding — consistent format, no format-sniffing needed
- Pre-serialization of non-primitives happens inside the wrapper (not at tool layer or in `to_dict()` methods)

### Non-primitive pre-serialization
- Recursive walker in `src/serialization.py` handles nested dicts and lists
- `datetime` → `.isoformat()` string
- `StrEnum` → `str(value)` (returns the string value, e.g., "sql", "table" — matches current json.dumps behavior)
- Unknown/unrecognized types → raise `TypeError` (fail loudly per SRLZ-04: no silent null coercion)

### Docstring format examples
- Name TOON explicitly: "TOON-encoded string with..."
- Structural outline only — field names, types, and conditional annotations (no full sample data)
- Same structure as current JSON examples, just different syntax — pure format swap, no doc cleanup
- Claude's Discretion: nesting representation (indented sub-fields vs actual TOON syntax)

### Test helper strategy
- Standalone `tests/helpers.py` module with `parse_tool_response()` function (not a fixture)
- TOON-only from day one — no dual-format support, no auto-detection
- Just decode — returns dict, no assertion helpers
- Use helper everywhere (both unit and integration tests) for consistency

### Claude's Discretion
- TOON nesting representation in docstrings (pick what aligns with actual TOON syntax)
- Exact `_pre_serialize()` implementation details (type dispatch, edge cases)
- Order of migration across the 3 tool files (schema_tools, query_tools, analysis_tools)
- How to handle the `default=str` currently used in `analysis_tools.py` line 137 (replace with explicit pre-serialization)

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `to_dict()` methods on 3 model files (analysis.py, schema.py, metrics.py) — already convert models to dicts, but don't handle datetime/enum pre-serialization
- Existing `json.dumps` pattern in all 3 tool files provides clear replacement targets

### Established Patterns
- Tool response pattern: `return json.dumps({"status": "success"|"error", ...})` — uniform across all 9 tools
- Error responses always include `"status": "error"` and `"error_message"` — this shape stays the same
- `analysis_tools.py` uses `json.dumps(response, default=str)` — the only tool using `default=str` fallback
- Models use Python dataclasses with `to_dict()`, not Pydantic

### Integration Points
- `src/mcp_server/schema_tools.py`: 4 tools (connect_database, list_schemas, list_tables, get_table_schema) — ~16 json.dumps calls
- `src/mcp_server/query_tools.py`: 2 tools (get_sample_data, execute_query) — ~11 json.dumps calls
- `src/mcp_server/analysis_tools.py`: 3 tools (get_column_info, find_pk_candidates, find_fk_candidates) — ~6 json.dumps calls
- `tests/integration/`: 64 json.loads calls across 6 test files
- `tests/unit/`: 0 json.loads calls (but should adopt helper for consistency)

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 01-atomic-toon-migration*
*Context gathered: 2026-03-04*
