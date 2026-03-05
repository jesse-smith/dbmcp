# Architecture Research

**Domain:** TOON serialization integration into existing MCP server
**Researched:** 2026-03-04
**Confidence:** HIGH

## System Overview

```
┌──────────────────────────────────────────────────────────────────┐
│                      MCP Tool Layer                              │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────┐    │
│  │ schema_tools │ │ query_tools  │ │ analysis_tools        │    │
│  │ (4 tools)    │ │ (2 tools)    │ │ (3 tools)             │    │
│  └──────┬───────┘ └──────┬───────┘ └───────────┬───────────┘    │
│         │                │                     │                │
│         └────────────────┼─────────────────────┘                │
│                          │                                      │
│                          ▼                                      │
│  ┌───────────────────────────────────────────────────────────┐  │
│  │              Serialization Layer (NEW)                     │  │
│  │  json.dumps(response_dict) --> toon_format.encode(dict)   │  │
│  └───────────────────────────────┬───────────────────────────┘  │
│                                  │                              │
│                                  ▼                              │
│                          TOON string returned                   │
│                          to FastMCP framework                   │
├──────────────────────────────────────────────────────────────────┤
│                      Service Layer                               │
│  ┌──────────────┐ ┌──────────────┐ ┌───────────────────────┐    │
│  │ MetadataService│ │ QueryService │ │ Analysis collectors  │    │
│  └──────────────┘ └──────────────┘ └───────────────────────┘    │
├──────────────────────────────────────────────────────────────────┤
│                      Data Models                                 │
│  ┌──────────────┐ ┌──────────────┐                              │
│  │ schema.py    │ │ analysis.py  │  (dataclasses w/ to_dict())  │
│  └──────────────┘ └──────────────┘                              │
├──────────────────────────────────────────────────────────────────┤
│                      Database Layer                               │
│  ┌──────────────────┐ ┌──────────────┐                          │
│  │ ConnectionManager │ │ SQLAlchemy   │                          │
│  └──────────────────┘ └──────────────┘                          │
└──────────────────────────────────────────────────────────────────┘
```

### Component Responsibilities

| Component | Responsibility | Affected by TOON Migration |
|-----------|----------------|---------------------------|
| Tool functions (schema_tools, query_tools, analysis_tools) | Orchestrate business logic, build response dicts, serialize to string | YES -- swap `json.dumps()` for `toon_format.encode()` |
| Response dict construction | Each tool builds a Python dict with status, data, metadata | NO -- dict structure stays identical |
| Data models (schema.py, analysis.py) | Dataclasses with `to_dict()` methods | NO -- untouched |
| Service layer (MetadataService, QueryService, etc.) | Database queries, business logic | NO -- untouched |
| Docstrings | FastMCP reads these as tool descriptions for LLM clients | YES -- must document TOON format instead of JSON |
| Staleness tests (NEW) | Validate docstrings match actual response schemas | YES -- new component |

## Current Serialization Flow (What Changes)

### Before (JSON)

```
Tool function
    │
    ├── Business logic produces data (models, dicts)
    │
    ├── Build response_dict = {"status": "success", ...data...}
    │
    └── return json.dumps(response_dict)
              ▲
              │
              This is the ONLY line that changes per tool
```

### After (TOON)

```
Tool function
    │
    ├── Business logic produces data (models, dicts)  [unchanged]
    │
    ├── Build response_dict = {"status": "success", ...data...}  [unchanged]
    │
    └── return toon_format.encode(response_dict)
              ▲
              │
              Mechanical substitution: json.dumps → toon_format.encode
```

### Key Architectural Insight

The migration is a leaf-node change. Every tool already constructs a plain Python dict, then calls `json.dumps()` as the final step. The dict construction, data models, service layer, and database layer are all untouched. This means:

1. **No new abstraction layer needed.** A serialization helper module would be over-engineering for a one-liner substitution (`json.dumps(d)` to `toon_format.encode(d)`).
2. **No interface changes.** Tools still return `str`. FastMCP doesn't care what the string contains.
3. **The real work is in docstrings and tests**, not in the serialization swap itself.

## Component Boundaries

### Boundary 1: Tool Function -> Serialization

**Current:** Each tool has 1-5 `json.dumps()` call sites (success path + error paths).

**Count by module:**
- `schema_tools.py`: ~12 `json.dumps()` calls across 4 tools
- `query_tools.py`: ~8 `json.dumps()` calls across 2 tools
- `analysis_tools.py`: ~9 `json.dumps()` calls across 3 tools

**Approach:** Direct substitution at each call site. No wrapper function needed because `toon_format.encode()` accepts the same input type (any JSON-serializable Python value) and returns `str`.

**One caveat:** Some tools use `json.dumps(response, default=str)` (e.g., `get_column_info`). Need to verify `toon_format.encode()` handles datetime objects and other non-JSON-native types. If not, pre-convert with `to_dict()` / `.isoformat()` before encoding (which most tools already do).

### Boundary 2: Tool Docstrings -> FastMCP Registration

**Current:** Each tool's docstring contains a `Returns:` section with JSON examples using `::` literal blocks. FastMCP reads these at import time and sends them verbatim to LLM clients.

**After:** Docstrings must show TOON format examples instead of JSON. The LLM client needs to understand the response it will receive.

**This is the highest-effort component** because each tool has a bespoke response shape with conditionals (e.g., "on error only", "detailed mode only", "only when include_overlap=True"). Each docstring must be manually updated to reflect TOON encoding of that specific response shape.

### Boundary 3: Staleness Tests -> Data Models + Docstrings

**New component.** A test that:
1. Imports each tool function
2. Extracts field names and types from the docstring (parsing the TOON format documentation)
3. Compares against actual response schema (either from dataclass fields or by calling the tool with mocked data)
4. Fails if they diverge

This is the most architecturally interesting new piece. Two viable approaches:

**Approach A: Schema-from-mock-response.** Call each tool with test fixtures, decode the TOON response, compare field names against docstring. Pros: Tests the real output path. Cons: Requires test fixtures for every tool.

**Approach B: Schema-from-dict-construction.** Inspect the response dict keys built in each tool's success/error paths. Compare against docstring. Pros: No fixtures needed. Cons: Requires AST analysis or manual schema declarations.

**Recommendation: Approach A.** The project already has 385 tests with fixtures for every tool. Reuse existing fixtures, capture the response dict (before serialization), and diff field names against docstring declarations. This tests the full path and is the more honest verification.

## Recommended Project Structure Changes

```
src/
├── mcp_server/
│   ├── server.py              # Unchanged
│   ├── schema_tools.py        # json.dumps → toon_format.encode + docstring updates
│   ├── query_tools.py         # json.dumps → toon_format.encode + docstring updates
│   └── analysis_tools.py      # json.dumps → toon_format.encode + docstring updates
├── models/
│   ├── schema.py              # Unchanged
│   └── analysis.py            # Unchanged
tests/
├── compliance/
│   └── test_docstring_staleness.py   # NEW: docstring-schema sync validation
├── unit/
│   └── (existing tool tests)         # Updated: assertions change from json.loads to
│                                     #   toon_format.decode (or string matching)
```

**No new src/ modules needed.** The migration adds one dependency (`toon_format`), modifies three existing modules, and adds one new test file.

## Architectural Patterns

### Pattern 1: Direct Serialization Substitution

**What:** Replace `json.dumps(dict)` with `toon_format.encode(dict)` at each call site. No intermediate abstraction.

**When to use:** When the new serializer has the same interface as the old one (accepts dict, returns str) and there is no need for format negotiation.

**Trade-offs:**
- Pro: Zero abstraction overhead, easy to grep, easy to review
- Pro: Each call site is self-documenting
- Con: If we ever need dual-format support, we'd need to revisit (but PROJECT.md explicitly rules this out)

**Example:**
```python
# Before
return json.dumps({
    "status": "success",
    "schemas": [{"schema_name": s.schema_name, ...} for s in schemas],
    "total_schemas": len(schemas),
})

# After
return toon_format.encode({
    "status": "success",
    "schemas": [{"schema_name": s.schema_name, ...} for s in schemas],
    "total_schemas": len(schemas),
})
```

### Pattern 2: Docstring-as-Contract

**What:** FastMCP uses docstrings as the LLM-facing tool description. The docstring IS the API contract for consumers. If the docstring says "returns JSON", the LLM will try to parse JSON. If it says "returns TOON", the LLM needs to understand TOON.

**When to use:** Always in FastMCP tools -- this is how the framework works.

**Trade-offs:**
- Pro: Single source of truth for LLM consumers
- Con: Docstrings are free-form text, easy to drift from actual behavior
- Mitigation: Staleness test (Pattern 3)

**Docstring format after migration:**
```python
"""
Returns:
    TOON-encoded string. Structure:

    status: <"success" | "error">
    schemas[N,]{schema_name,table_count,view_count}:
      <string>,<int>,<int>
      ...
    total_schemas: <int>
    error_message: <string>     // on error only
"""
```

### Pattern 3: Staleness Test Guard

**What:** A test that programmatically verifies docstring field declarations match the actual response schema produced by each tool.

**When to use:** When docstrings serve as API contracts and drift would confuse consumers.

**Implementation sketch:**
```python
# tests/compliance/test_docstring_staleness.py

TOOL_SCHEMAS = {
    "list_schemas": {
        "success_fields": {"status", "schemas", "total_schemas"},
        "error_fields": {"status", "error_message"},
        "nested": {
            "schemas[]": {"schema_name", "table_count", "view_count"},
        },
    },
    # ... per tool
}

def test_docstring_declares_all_fields():
    """Every field in the actual response must appear in the docstring."""
    for tool_name, schema in TOOL_SCHEMAS.items():
        docstring = get_tool_docstring(tool_name)
        for field in schema["success_fields"]:
            assert field in docstring, f"{tool_name}: missing '{field}' in docstring"
```

**Trade-off:** Requires maintaining a parallel schema declaration. But this is intentional -- it's a lightweight cross-check that catches when someone adds a field to the response dict but forgets to update the docstring (or vice versa). The schema declaration is 5-10 lines per tool, not burdensome.

## Data Flow

### Request Flow (Unchanged)

```
LLM Client
    │ (MCP protocol, stdio transport)
    ▼
FastMCP framework
    │ (dispatches to @mcp.tool() function)
    ▼
Tool function (e.g., list_schemas)
    │
    ├── Validate inputs
    ├── Call service layer
    ├── Build response dict
    ├── Serialize to TOON string  ◀── ONLY CHANGE
    │
    ▼
FastMCP framework
    │ (wraps in MCP response envelope)
    ▼
LLM Client (reads TOON-encoded content)
```

### Serialization Detail

```
Python dict                    TOON string
─────────────                  ───────────
{"status": "success",    →     status: success
 "schemas": [            →     schemas[1,]{schema_name,table_count,view_count}:
   {"schema_name": "dbo",→       dbo,42,5
    "table_count": 42,
    "view_count": 5}
 ],
 "total_schemas": 1}     →     total_schemas: 1
```

The tabular encoding is where TOON delivers the biggest token savings. Tools returning arrays of uniform objects (list_tables, execute_query, get_sample_data, get_column_info, find_fk_candidates) will see the largest reduction because repeated key names are eliminated.

## Build Order (Dependencies Between Components)

```
Phase 1: Add dependency + serialization swap
    │     (toon_format added to pyproject.toml,
    │      json.dumps → toon_format.encode in all tools)
    │
    ▼
Phase 2: Update docstrings
    │     (rewrite Returns: sections to document TOON format)
    │     Depends on Phase 1: need to see actual TOON output
    │     to write accurate docstrings
    │
    ▼
Phase 3: Staleness tests
    │     (validate docstrings match schemas)
    │     Depends on Phase 2: docstrings must exist to test
    │
    ▼
Phase 4: Update existing tests
          (assertions that parse json.loads need updating)
          Can partially overlap with Phase 1, but cleanest after
```

**Rationale for ordering:**
- Phase 1 before Phase 2: You need to see the actual TOON output of each tool to write accurate docstrings. Encoding a sample response and inspecting the output is the only reliable way to document the format.
- Phase 2 before Phase 3: Staleness tests compare docstrings against schemas. Docstrings must be written first.
- Phase 4 (test updates) is the largest effort by line count but mechanically straightforward. It can start during Phase 1 (updating test assertions as each tool is migrated) or be done as a batch after all tools are migrated. Batch is cleaner because it avoids a mixed state where some tests expect JSON and others expect TOON.

**Alternative ordering considered:** Updating tests alongside each tool migration (interleaved). Rejected because it creates a longer period of mixed JSON/TOON expectations in the test suite and makes it harder to review.

## Anti-Patterns

### Anti-Pattern 1: Serialization Abstraction Layer

**What people do:** Create a `serialize_response(dict, format="toon")` helper function that wraps `toon_format.encode()`, add it to a new `src/mcp_server/serialization.py` module, and have all tools call through it.

**Why it's wrong:** Over-engineering for a one-liner call. The project explicitly rules out format negotiation (JSON vs TOON). An abstraction layer adds indirection with no benefit. If dual-format is ever needed (unlikely per PROJECT.md), it can be added then.

**Do this instead:** Direct `toon_format.encode()` calls at each site. One import, one call.

### Anti-Pattern 2: Auto-Generating Docstrings from Data Models

**What people do:** Build a system that introspects dataclass fields and generates docstring text automatically, then inject it before `@mcp.tool()` registration.

**Why it's wrong:** PROJECT.md already investigated this and rejected it. Each tool wraps model data in a response envelope with tool-specific metadata (pagination fields, computed fields, conditional sections). The envelope differs per tool, so auto-generation would need per-tool configuration that's as complex as just writing the docstrings.

**Do this instead:** Hand-write docstrings, guard with staleness tests.

### Anti-Pattern 3: Changing Response Dict Structure "While We're At It"

**What people do:** Since we're touching every tool anyway, also restructure the response dicts, rename fields, change nesting, etc.

**Why it's wrong:** PROJECT.md constraint: "Response structure (field names, types, nesting) must remain identical -- only serialization format changes." Mixing structural changes with format changes makes it impossible to isolate regressions.

**Do this instead:** Pure format swap. If structural changes are needed, do them in a separate feature.

### Anti-Pattern 4: Testing TOON Output by String Comparison

**What people do:** Assert that `tool_result == "status: success\nschemas[1,]..."` with exact string matching.

**Why it's wrong:** Brittle. TOON encoding may have minor formatting variations (whitespace, field ordering) between library versions. Tests would break on `toon_format` upgrades.

**Do this instead:** Decode the TOON output with `toon_format.decode()` and assert on the resulting Python dict. This tests the round-trip and is resilient to formatting changes.

```python
# Bad
assert result == "status: success\nschemas[1,]..."

# Good
decoded = toon_format.decode(result)
assert decoded["status"] == "success"
assert len(decoded["schemas"]) == 1
```

## Integration Points

### External: toon_format Library

| Aspect | Detail |
|--------|--------|
| Package | `toon-format` (PyPI) / `toon_format` (import) |
| Key functions | `encode(value, options=None) -> str`, `decode(input_str, options=None) -> Any` |
| Input | Any JSON-serializable Python value (dict, list, str, int, float, bool, None) |
| Output | TOON-formatted string |
| Concern | Library maturity -- PyPI shows 0.1.0 as namespace reservation, GitHub README describes 0.9.x beta. Need to verify actual installable version and test coverage before depending on it. |
| Mitigation | Pin version in pyproject.toml. Run full test suite against it before committing. |

### Internal Boundaries

| Boundary | Communication | Notes |
|----------|---------------|-------|
| Tool functions -> toon_format | Direct function call (`encode()`) | Same interface as `json.dumps()` |
| Tool functions -> data models | `model.to_dict()` -> dict -> `encode()` | No change to model layer |
| Staleness tests -> tool docstrings | `inspect.getdoc()` to read docstrings | Standard Python introspection |
| Existing tests -> tool responses | `toon_format.decode(result)` to get dict | Replaces `json.loads(result)` |

## Confidence Notes

| Claim | Confidence | Basis |
|-------|------------|-------|
| toon_format.encode() accepts Python dicts and returns str | MEDIUM | GitHub README shows this API; PyPI page shows 0.1.0 placeholder. Actual installable version needs verification. |
| Direct substitution works (no wrapper needed) | HIGH | Verified: all 9 tools follow identical pattern of `json.dumps(dict)` as final step |
| Docstring updates are highest-effort component | HIGH | Verified: each tool has bespoke response shapes with conditionals |
| Existing test suite needs assertion updates | HIGH | Verified: tests use `json.loads()` to parse tool responses |
| No changes needed to data models or service layer | HIGH | Verified: serialization is leaf-node concern in tool functions only |

---
*Architecture research for: TOON format migration in dbmcp*
*Researched: 2026-03-04*
