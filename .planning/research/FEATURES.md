# Feature Research

**Domain:** TOON format migration for MCP server responses
**Researched:** 2026-03-04
**Confidence:** HIGH

## Feature Landscape

### Table Stakes (Users Expect These)

Features that must work correctly or the migration is broken/regressive.

| Feature | Why Expected | Complexity | Notes |
|---------|--------------|------------|-------|
| Replace `json.dumps()` with `toon_format.encode()` in all 9 tool return paths | The entire point of the migration; partial conversion means two formats in flight | LOW | 41 `json.dumps` call sites across 3 tool modules (schema_tools, query_tools, analysis_tools). Mechanical replacement: build the same dict, call `encode()` instead of `json.dumps()`. |
| Preserve response structure (field names, types, nesting) | PROJECT.md constraint: "Response structure must remain identical -- only serialization format changes" | LOW | `encode()` accepts any JSON-serializable Python value, so existing dict-building code stays unchanged. |
| Handle error responses correctly | Every tool has `{"status": "error", "error_message": ...}` paths; these must encode cleanly | LOW | Simple flat dicts. TOON encodes these trivially as `status: error` / `error_message: ...`. No quoting issues expected. |
| Update all test assertions from `json.loads()` to `toon_format.decode()` | 65 `json.loads`/`json.dumps` occurrences across 7 test files; tests break immediately without this | MEDIUM | Bulk find-and-replace with some care around test helpers. The decode function exists and is stable. Most integration tests parse the tool return string and check dict fields. |
| Update tool docstrings to document TOON format | FastMCP reads docstrings verbatim as tool descriptions sent to LLM clients. If docstrings still say "JSON string with..." the LLM consumer gets wrong format info. | MEDIUM | 9 tools, each with a `Returns:` docstring block showing JSON examples. Must rewrite to show TOON structure, types, and enum literals. This is the most labor-intensive table-stakes item because each tool has a unique response shape. |
| Add `toon-format` (`toon_format`) as project dependency | Nothing works without the library installed | LOW | Single `uv add` of the package. Python 3.8+ supported, project uses 3.11+. |

### Differentiators (Competitive Advantage)

Features that go beyond "it works" to make the migration robust and maintainable.

| Feature | Value Proposition | Complexity | Notes |
|---------|-------------------|------------|-------|
| Docstring-schema staleness test | Catches drift between response data models and docstrings automatically. Without it, docstrings rot silently and LLM consumers get stale format descriptions. PROJECT.md lists this as a core requirement. | MEDIUM | Approach: for each tool, invoke it with mock/fixture data, inspect the returned dict's keys and value types, compare against parsed docstring claims. Does not require auto-generation -- just validation. Key challenge is defining "what to check" (field names, types, conditional presence) without being so brittle the test breaks on every refactor. |
| Tabular encoding for list-heavy responses | TOON's biggest token savings come from tabular arrays (uniform objects become CSV-like rows). Tools like `list_tables`, `execute_query`, `get_sample_data`, `list_schemas`, and `find_fk_candidates` return arrays of uniform objects -- these should encode as tables automatically. | LOW | `toon_format.encode()` auto-detects tabular arrays when all elements are objects with identical keys and primitive values. No special code needed **unless** response objects have optional/conditional fields (see Pitfall below). |
| Conditional field handling for analysis tools | `get_column_info` includes `numeric_stats`, `datetime_stats`, or `string_stats` conditionally per column. `find_fk_candidates` conditionally includes `overlap_count`/`overlap_percentage`. These non-uniform objects break TOON tabular encoding and fall back to expanded list format (more tokens). | MEDIUM | Options: (1) Accept the fallback -- expanded list is still more compact than JSON. (2) Restructure responses to always include all fields as null -- enables tabular but adds null noise. Recommendation: Accept fallback for analysis tools (they return fewer rows, so savings difference is small). Keep tabular optimization for high-volume tools (list_tables, execute_query, get_sample_data). |
| Token savings measurement | Quantify actual savings per tool using `toon_format.estimate_savings()` or `compare_formats()`. Validates the 30-60% claim against real response data. | LOW | The library ships with built-in benchmarking utilities. Run against fixture data from existing tests. Useful for the PR description and for prioritizing future optimization. |
| `default=str` handling for datetime serialization | Several tools use `json.dumps(response, default=str)` to handle datetime objects. `toon_format.encode()` normalizes datetime to ISO 8601 automatically per spec, so the `default=str` pattern can be dropped. | LOW | Verify that `encode()` handles `datetime` objects directly. The spec says "datetime -> ISO 8601". If `encode()` does not handle raw datetimes (only JSON-serializable values), pre-convert with `.isoformat()` as currently done in `to_dict()` methods. Test with real datetime values. |

### Anti-Features (Commonly Requested, Often Problematic)

| Feature | Why Requested | Why Problematic | Alternative |
|---------|---------------|-----------------|-------------|
| Format negotiation (JSON vs TOON toggle) | "What if some client needs JSON?" | Only consumers are LLMs. Adding negotiation means two code paths, two test suites, content-type header complexity, and defeats the simplicity goal. PROJECT.md explicitly scopes this out. | Hard switch. If a non-LLM consumer appears later, add a JSON endpoint then. YAGNI. |
| Auto-generate docstrings from data models | Eliminates manual docstring maintenance | Investigated and rejected in PROJECT.md. Wrapper fields differ per tool (pagination metadata, computed fields, conditional sections). Auto-gen would need per-tool templates, which is just a different kind of manual maintenance with more indirection. | Staleness test catches drift without the complexity of generation. Manual docstrings with automated validation. |
| Pydantic migration for response models | "Dataclasses are legacy, Pydantic validates" | Current dataclasses work. Pydantic adds a dependency, changes serialization patterns, and is orthogonal to the format migration. Coupling two migrations increases risk. | Keep dataclasses. Migrate to Pydantic (if ever) as a separate effort. |
| Custom TOON encoder for domain-specific optimization | "We could hand-tune the encoding for our specific schemas" | The library handles encoding correctly. Custom encoding means maintaining a fork, losing upstream improvements, and introducing bugs. The auto-tabular detection already handles the main optimization opportunity. | Use `encode()` as-is. Accept the library's formatting decisions. |
| Streaming/chunked TOON responses | "Large query results should stream" | TOON is a document format, not a streaming protocol. MCP tool responses are single strings. Chunked encoding would require protocol-level changes outside this migration's scope. | Keep existing row_limit parameters (max 10000). If responses are too large, the limit is the control mechanism, not streaming. |

## Feature Dependencies

```
[Add toon-format dependency]
    |
    v
[Replace json.dumps with encode() in tool modules] ---requires---> [Add toon-format dependency]
    |
    v
[Update test assertions from json.loads to decode()] ---requires---> [Replace json.dumps]
    |
    v
[Update tool docstrings for TOON format] ---requires---> [Replace json.dumps]
    |                                                      (need to see actual output first)
    v
[Docstring staleness test] ---requires---> [Updated docstrings]
                                           [Updated test infrastructure]

[Token savings measurement] ---independent---> (can run anytime after encode() is wired up)

[Conditional field handling analysis] ---informs---> [Replace json.dumps]
                                                     (decides whether to restructure before encoding)
```

### Dependency Notes

- **Replace json.dumps requires toon-format dependency:** Cannot call `encode()` without the package installed.
- **Test updates require json.dumps replacement:** Tests call tools and parse output. Must update parsing to match new format.
- **Docstring updates require seeing actual TOON output:** Best written after encoding is working so examples are accurate, not guessed.
- **Staleness test requires updated docstrings:** The test validates docstrings against schemas. If docstrings still describe JSON, the test would flag everything as stale immediately.
- **Token savings measurement is independent:** Can be done as a side task once encoding works, or even before as a motivating benchmark.

## MVP Definition

### Launch With (v1)

Minimum to ship the format migration and call it done.

- [ ] `toon-format` added as dependency -- gate for everything else
- [ ] All 9 tools return `encode(response_dict)` instead of `json.dumps(response_dict)` -- the core deliverable
- [ ] All existing tests pass with `decode()` instead of `json.loads()` -- proves nothing broke
- [ ] Tool docstrings rewritten for TOON format -- LLM consumers need accurate format descriptions

### Add After Validation (v1.x)

Features to add once the core migration is verified working.

- [ ] Docstring staleness test -- prevents future drift; not needed for initial migration correctness
- [ ] Token savings measurement -- validates the business case; nice for documentation but not blocking

### Future Consideration (v2+)

- [ ] Response restructuring for better tabular encoding (e.g., flattening conditional fields) -- only if measurement shows significant savings opportunity
- [ ] TOON encode options tuning (delimiter, indent, length markers) -- only if LLM consumers show preference

## Feature Prioritization Matrix

| Feature | User Value | Implementation Cost | Priority |
|---------|------------|---------------------|----------|
| Add toon-format dependency | HIGH (blocker) | LOW | P1 |
| Replace json.dumps with encode() | HIGH (core goal) | LOW | P1 |
| Update test assertions | HIGH (prevents regression) | MEDIUM | P1 |
| Update tool docstrings | HIGH (LLM consumers need this) | MEDIUM | P1 |
| Docstring staleness test | MEDIUM (prevents future drift) | MEDIUM | P2 |
| Token savings measurement | LOW (informational) | LOW | P2 |
| Conditional field analysis | LOW (marginal gains) | LOW | P3 |
| TOON encode options tuning | LOW (defaults are fine) | LOW | P3 |

**Priority key:**
- P1: Must have for launch
- P2: Should have, add when possible
- P3: Nice to have, future consideration

## Response Shape Analysis

Mapping each tool's response to expected TOON encoding behavior.

| Tool | Response Shape | Tabular Candidate? | Expected Savings | Notes |
|------|---------------|---------------------|------------------|-------|
| `connect_database` | Flat dict (5-6 fields) | N/A (single object) | Low (~20%) | Small response, minimal key overhead |
| `list_schemas` | Flat dict + array of uniform objects | YES (schemas array) | High (~50%) | `schemas` array has identical keys per row |
| `list_tables` | Flat dict + array of uniform objects | YES (tables array) | High (~50%) | Large arrays, repeated keys. `columns` sub-array in detailed mode breaks tabular for that field. |
| `get_table_schema` | Nested dict (table > columns[], indexes[], foreign_keys[]) | PARTIAL | Medium (~35%) | `columns` array is tabular; `indexes` has list fields (`columns`, `included_columns`) that break tabular; top-level is nested |
| `get_sample_data` | Flat dict + array of row objects | YES (rows array) | High (~50%) | Rows are uniform dicts. Biggest volume tool. |
| `execute_query` | Flat dict + columns array + rows array | YES (rows array) | High (~50%) | Same as sample_data -- high-volume, uniform rows |
| `get_column_info` | Flat dict + array of non-uniform objects | NO (conditional stats fields) | Medium (~30%) | Falls back to expanded list due to numeric_stats/datetime_stats/string_stats being conditional |
| `find_pk_candidates` | Flat dict + array of uniform objects | YES (candidates array) | Medium (~40%) | Small result sets typically |
| `find_fk_candidates` | Flat dict + array of conditionally-uniform objects | MAYBE | Medium (~35%) | Uniform when `include_overlap=False`; non-uniform when True (adds 2 optional fields) |

## Sources

- TOON specification v3.0 (Working Draft): https://github.com/toon-format/spec
- toon-python library (v0.9.x beta): https://github.com/toon-format/toon-python
- PROJECT.md: Local project requirements and constraints
- Codebase analysis: 41 `json.dumps` call sites, 65 `json.loads` test assertions, 9 MCP tools

---
*Feature research for: TOON format migration for MCP server responses*
*Researched: 2026-03-04*
