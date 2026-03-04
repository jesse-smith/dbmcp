# Phase 2: Staleness Guard - Context

**Gathered:** 2026-03-04
**Status:** Ready for planning

<domain>
## Phase Boundary

An automated test that catches docstring-schema drift on every commit. When a tool's response fields change without a corresponding docstring update (or vice versa), the test fails. Lives in the standard test suite — no special invocation required.

</domain>

<decisions>
## Implementation Decisions

### Detection strategy
- Call each of the 9 tools with mocked DB connections to get real response dicts
- Extract declared fields from docstring Returns sections and compare against actual response keys
- Cover all 9 tools including the 3 currently-hidden analysis tools (get_column_info, find_pk_candidates, find_fk_candidates) — catches drift if they're re-enabled

### Tool coverage
- All 9 tools: connect_database, list_schemas, list_tables, get_table_schema, get_sample_data, execute_query, get_column_info, find_pk_candidates, find_fk_candidates

### Claude's Discretion
- Docstring parsing approach (regex vs structured parser vs hybrid) — pick what's most maintainable
- Auto-discover tool functions vs explicit registry — balance coverage with reliability
- Drift scope depth: field names only vs field names + types — based on effort vs value tradeoff
- Whether to validate conditional annotations (// on error only) or treat them as documentation-only
- Bidirectional checking (missing + extra fields) vs docstring-is-superset only
- Nesting depth for field validation (top-level only, one level deep, or recursive)
- Test structure: parametrized over all tools vs one test per tool
- Failure message verbosity: diff-style output vs simple assertion
- Test location: unit tests (fast, mocked) vs integration tests — guided by "runs on every commit" requirement
- Whether to also check Args section matches function signature (beyond DOCS-02 scope)
- Runtime introspection vs checked-in snapshot for baseline
- Snapshot generation/update mechanism (if snapshot approach chosen)
- Meta-tests for the parser/comparison logic — guided by 90%+ coverage requirement

</decisions>

<specifics>
## Specific Ideas

No specific requirements — open to standard approaches

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/helpers.py`: `parse_tool_response()` — TOON decoder, returns dict from tool response string
- Existing mock patterns in `tests/unit/` for SQLAlchemy engine, connection, and result mocking
- `tests/conftest.py`: shared fixtures for mock engines and sample data

### Established Patterns
- Tool response pattern: all 9 tools return `encode_response({"status": "success"|"error", ...})` — uniform structure
- Docstring format: TOON structural outline with `field: type // annotation` per Phase 1 decisions
- Test organization: `tests/unit/test_<module>.py` with test classes per feature
- Parametrized tests used throughout (e.g., `test_validation.py`)
- pytest-asyncio with `asyncio_mode = "auto"` for async tool testing

### Integration Points
- `src/mcp_server/schema_tools.py`: 4 tools (connect_database, list_schemas, list_tables, get_table_schema)
- `src/mcp_server/query_tools.py`: 2 tools (get_sample_data, execute_query)
- `src/mcp_server/analysis_tools.py`: 3 tools (get_column_info, find_pk_candidates, find_fk_candidates)
- Tool docstrings accessed via `tool_function.__doc__`

</code_context>

<deferred>
## Deferred Ideas

None — discussion stayed within phase scope

</deferred>

---

*Phase: 02-staleness-guard*
*Context gathered: 2026-03-04*
