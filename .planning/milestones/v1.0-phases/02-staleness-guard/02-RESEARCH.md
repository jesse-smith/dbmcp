# Phase 2: Staleness Guard - Research

**Researched:** 2026-03-04
**Domain:** Python docstring parsing, schema introspection, test automation
**Confidence:** HIGH

## Summary

This phase requires building an automated test that detects drift between tool docstring field declarations and actual response schemas. The codebase has 9 MCP tools across 3 modules, all following a uniform pattern: `encode_response({...})` returns a TOON-encoded string, and each tool's docstring documents the response fields in a consistent `field: type // annotation` structural outline format.

The core problem decomposes into three parts: (1) parsing the Returns section of each tool's docstring to extract declared field names, (2) invoking each tool with mocked dependencies to capture actual response keys, and (3) comparing the two sets and failing when they diverge. All infrastructure needed (mock patterns, async test fixtures, TOON decoder, parametrized test patterns) already exists in the test suite.

**Primary recommendation:** Build a pure-Python docstring parser for the TOON structural outline format, auto-discover tools via `@mcp.tool()` decorator inspection, use parametrized tests over all 9 tools, and compare field sets bidirectionally (extra + missing). Keep it as a fast unit test (no DB, no network).

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- Call each of the 9 tools with mocked DB connections to get real response dicts
- Extract declared fields from docstring Returns sections and compare against actual response keys
- Cover all 9 active tools (all have @mcp.tool() decorators)

### Claude's Discretion
- Docstring parsing approach (regex vs structured parser vs hybrid) -- pick what's most maintainable
- Auto-discover tool functions vs explicit registry -- balance coverage with reliability
- Drift scope depth: field names only vs field names + types -- based on effort vs value tradeoff
- Whether to validate conditional annotations (// on error only) or treat them as documentation-only
- Bidirectional checking (missing + extra fields) vs docstring-is-superset only
- Nesting depth for field validation (top-level only, one level deep, or recursive)
- Test structure: parametrized over all tools vs one test per tool
- Failure message verbosity: diff-style output vs simple assertion
- Test location: unit tests (fast, mocked) vs integration tests -- guided by "runs on every commit" requirement
- Whether to also check Args section matches function signature (beyond DOCS-02 scope)
- Runtime introspection vs checked-in snapshot for baseline
- Snapshot generation/update mechanism (if snapshot approach chosen)
- Meta-tests for the parser/comparison logic -- guided by 90%+ coverage requirement

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| DOCS-02 | Staleness test validates docstring field declarations match actual response schemas | All research findings below directly support this: docstring parser, tool discovery, mock invocation patterns, comparison logic, and meta-test strategy |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | (existing) | Test framework | Already configured with asyncio_mode=auto |
| pytest-asyncio | (existing) | Async tool invocation | All 9 tools are `async def` |
| unittest.mock | stdlib | Mock DB connections | Established pattern in tests/unit/ and tests/integration/ |
| re | stdlib | Docstring field extraction | Sufficient for the structured `field: type // annotation` format |
| inspect | stdlib | Tool function discovery | `inspect.getmembers()` + checking for `@mcp.tool()` markers |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| textwrap.dedent | stdlib | Clean docstring indentation | When extracting Returns block content |
| toon_format.decode | (existing) | Decode tool responses | Via existing `parse_tool_response()` helper |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| regex parsing | docstring_parser lib | External dependency for a simple, consistent format -- not worth it |
| Runtime introspection | Checked-in snapshot file | Snapshot adds maintenance burden (must update file); runtime is self-healing |
| Auto-discovery | Explicit tool list | Explicit list is fragile when tools are added; auto-discovery catches new tools automatically |

**Installation:**
No new dependencies required. Everything is stdlib or already in the project.

## Architecture Patterns

### Recommended Project Structure
```
tests/
  unit/
    test_staleness.py          # The staleness guard test (parametrized)
  staleness/                   # Parser + comparison utilities
    __init__.py
    docstring_parser.py        # Extract fields from TOON docstring format
    schema_extractor.py        # Get actual response keys from tool invocation
    comparison.py              # Compare declared vs actual fields
```

**Alternative (simpler):** Put all logic in `tests/unit/test_staleness.py` directly. Given the 90%+ coverage requirement means we need meta-tests for the parser logic, a separate module is cleaner -- but that module could live in `tests/` rather than `src/` since it's test infrastructure only.

### Pattern 1: Auto-Discovery via MCP Server Module
**What:** Import all tool functions from `src.mcp_server.server` (which re-exports them), then filter for functions with `@mcp.tool()` decorator marker.
**When to use:** Tool registry for staleness checking.
**Example:**
```python
import inspect
from src.mcp_server import server

def discover_tool_functions():
    """Find all @mcp.tool() decorated functions."""
    tools = []
    for name, obj in inspect.getmembers(server, inspect.isfunction):
        # FastMCP @mcp.tool() wraps functions -- check if they're in mcp's tool registry
        if hasattr(obj, '__wrapped__') or name in _KNOWN_TOOL_NAMES:
            tools.append((name, obj))
    return tools
```

**Important discovery:** FastMCP's `@mcp.tool()` decorator behavior needs verification. The safest approach is to use `server.mcp._tool_manager.tools` or equivalent registry if FastMCP exposes it. Fallback: use an explicit list cross-referenced with auto-discovery for safety.

### Pattern 2: Docstring Returns Section Parsing
**What:** Extract the indented block after "Returns:" and parse `field: type` lines.
**When to use:** Getting declared field names from any tool docstring.

The docstring format is highly consistent across all 9 tools:
```
Returns:
    TOON-encoded string with ...:

        status: "success" | "error"
        field_name: type
        nested_list: list
            nested_field: type
        conditional_field: type    // annotation
```

Key parsing rules:
- The Returns block starts with a line matching `Returns:` (after Args:)
- Skip the first line (description like "TOON-encoded string with...")
- Field lines are indented and match `field_name: type`
- Nesting is indicated by increased indentation
- Annotations after `//` are metadata (not field names)
- The block ends at the next section header or end of docstring

### Pattern 3: Parametrized Test with Per-Tool Mock Fixtures
**What:** A single parametrized test that iterates over all tools with appropriate mocks.
**When to use:** The main staleness guard test.
**Example:**
```python
import pytest

TOOL_CONFIGS = [
    ("connect_database", {"server": "x", "database": "y"}, mock_connect_deps),
    ("list_schemas", {"connection_id": "x"}, mock_schema_deps),
    # ... all 9 tools
]

@pytest.mark.parametrize("tool_name,args,mock_setup", TOOL_CONFIGS)
async def test_docstring_matches_response_schema(tool_name, args, mock_setup):
    """Staleness guard: docstring fields must match actual response keys."""
    tool_fn = get_tool_function(tool_name)
    declared = parse_docstring_fields(tool_fn.__doc__)

    with mock_setup():
        response = await tool_fn(**args)

    actual = set(parse_tool_response(response).keys())
    assert declared == actual, f"Drift detected in {tool_name}: ..."
```

### Anti-Patterns to Avoid
- **Snapshot files that must be manually updated:** Creates a maintenance burden and defeats the "automatic" purpose. Use runtime introspection instead.
- **Testing only top-level keys while docstrings document nested structure:** This creates a false sense of safety. At minimum, validate one level deep for list/object children.
- **Hardcoding tool names without cross-referencing discovery:** If a new tool is added but the test doesn't know about it, drift goes undetected.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Async test execution | Custom async runner | pytest-asyncio (already configured) | asyncio_mode=auto handles all async fixtures/tests |
| TOON response decoding | Custom decoder | `parse_tool_response()` from tests/helpers.py | Already exists, battle-tested across 433 tests |
| DB connection mocking | New mock framework | Existing patterns from tests/integration/ and tests/unit/ | Well-established `patch.object(get_connection_manager(), ...)` pattern |

## Common Pitfalls

### Pitfall 1: Conditional Fields Create False Positives
**What goes wrong:** Fields marked `// on error only` or `// detailed mode only` won't appear in every response. If the test invokes the tool in only one code path (success), the error-only fields will appear as "declared but not present" drift.
**Why it happens:** The docstring is a superset of all possible response shapes, but any single invocation produces a subset.
**How to avoid:** Either (a) invoke each tool in multiple modes (success + error) and union the response keys, or (b) parse the `// on error only` annotations and treat annotated fields as "optional" in comparison, or (c) compare per-branch (success fields vs success docstring fields, error fields vs error docstring fields).
**Recommendation:** Option (c) is most precise. Invoke each tool once for success path and once for error path. Compare each path's fields against its declared subset. The `// on error only` / `// on success only` annotations provide the grouping.

### Pitfall 2: Nested Field Validation Complexity
**What goes wrong:** Docstrings document nested structures (e.g., `columns: list` with sub-fields). Validating only top-level keys misses drift in nested objects; validating recursively is complex.
**Why it happens:** Tools like `get_table_schema` have 3 levels of nesting.
**How to avoid:** Start with top-level keys + one level of nesting for list/object children. This catches the most common drift (adding/removing a field) without parsing deeply nested structures. Document the depth limit explicitly.
**Recommendation:** Top-level + one level deep. Flag deeper nesting as documentation-only (not validated).

### Pitfall 3: FastMCP Decorator Hides Original Function
**What goes wrong:** `@mcp.tool()` may wrap the function, making `__doc__` inaccessible or replacing it.
**Why it happens:** FastMCP might use `functools.wraps` (preserves `__doc__`) or might not.
**How to avoid:** Verify in a quick test that `connect_database.__doc__` returns the expected docstring. If it doesn't, access the unwrapped function via `__wrapped__` or use `inspect.unwrap()`.
**Warning signs:** `tool_fn.__doc__` returns `None` or a generic string.

### Pitfall 4: execute_query Returns Dynamic Keys
**What goes wrong:** `execute_query` calls `query_svc.get_query_results(query)` which returns a dict built elsewhere. The response schema may differ from what's declared.
**Why it happens:** Unlike other tools that build their response dict inline, `execute_query` delegates to `QueryService.get_query_results()`.
**How to avoid:** Mock `QueryService.get_query_results()` to return a known dict matching the expected schema, then verify docstring matches.

### Pitfall 5: Indentation-Sensitive Parsing
**What goes wrong:** Python trims leading whitespace from docstrings inconsistently. The first line after `"""` has no indentation, but subsequent lines do.
**Why it happens:** Python docstring convention + `inspect.getdoc()` vs raw `__doc__`.
**How to avoid:** Use `inspect.cleandoc()` or `textwrap.dedent()` to normalize indentation before parsing. Or parse relative to the indentation of the `Returns:` line.

## Code Examples

### Docstring Field Extraction (verified from codebase inspection)
```python
import re
import inspect

def parse_returns_fields(docstring: str) -> dict[str, set[str]]:
    """Parse TOON structural outline from a tool docstring's Returns section.

    Returns a dict mapping path prefixes to field name sets, e.g.:
    {"": {"status", "connection_id", ...}, "schemas[]": {"schema_name", ...}}
    """
    if not docstring:
        return {}

    lines = inspect.cleandoc(docstring).splitlines()

    # Find the Returns: section
    returns_idx = None
    for i, line in enumerate(lines):
        if line.strip() == "Returns:":
            returns_idx = i
            break

    if returns_idx is None:
        return {}

    # Skip description line(s) until we hit the indented field block
    # Field lines match: "    field_name: type"
    field_pattern = re.compile(r'^(\s+)(\w+):\s+(.+?)(?:\s+//.*)?$')

    fields = {}
    current_path = ""
    base_indent = None

    for line in lines[returns_idx + 1:]:
        # Stop at next section (e.g., "Error conditions:")
        stripped = line.strip()
        if stripped and not stripped.startswith(('status', 'error', 'connection', 'message')) and stripped.endswith(':') and not ':' in stripped[:-1]:
            # Could be a new section header
            if base_indent and len(line) - len(line.lstrip()) <= base_indent:
                break

        match = field_pattern.match(line)
        if match:
            indent = len(match.group(1))
            field_name = match.group(2)
            field_type = match.group(3).strip()

            if base_indent is None:
                base_indent = indent

            # Determine nesting level from indent
            # ... build field tree

    return fields
```

**Note:** The above is illustrative. The actual parser should be simpler since the format is very consistent. A practical approach:

```python
def extract_top_level_fields(docstring: str) -> set[str]:
    """Extract top-level field names from TOON docstring Returns section."""
    lines = inspect.cleandoc(docstring).splitlines()

    # Find Returns: block
    in_returns = False
    field_block_indent = None
    fields = set()
    field_re = re.compile(r'^(\s+)(\w+):\s+')

    for line in lines:
        if line.strip() == "Returns:":
            in_returns = True
            continue

        if not in_returns:
            continue

        # Stop at next section header (unindented or less indented non-field line)
        match = field_re.match(line)
        if match:
            indent = len(match.group(1))
            if field_block_indent is None:
                field_block_indent = indent
            if indent == field_block_indent:
                fields.add(match.group(2))
        elif line.strip() and not line.strip().startswith(("TOON", "-", "//")) and field_block_indent is not None:
            # Non-field, non-empty line at same or less indent = section end
            stripped_indent = len(line) - len(line.lstrip())
            if stripped_indent <= field_block_indent - 4:
                break

    return fields
```

### Tool Invocation with Mocks (from existing codebase patterns)
```python
from unittest.mock import patch, MagicMock

async def invoke_tool_success(tool_fn, tool_name):
    """Invoke a tool with mocks to get a success response."""
    # Pattern from tests/integration/test_discovery.py
    from src.mcp_server.server import get_connection_manager

    with patch.object(get_connection_manager(), "get_engine") as mock_engine:
        mock_engine.return_value = create_mock_engine_for(tool_name)
        # Tool-specific args
        args = get_success_args(tool_name)
        return await tool_fn(**args)
```

### Bidirectional Comparison
```python
def compare_fields(declared: set[str], actual: set[str], tool_name: str):
    """Compare declared docstring fields against actual response keys."""
    missing = declared - actual  # In docstring but not in response
    extra = actual - declared    # In response but not in docstring

    messages = []
    if missing:
        messages.append(f"Declared but missing from response: {sorted(missing)}")
    if extra:
        messages.append(f"In response but undocumented: {sorted(extra)}")

    assert not messages, f"Schema drift in {tool_name}:\n" + "\n".join(messages)
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| Manual docstring review | Automated staleness test | This phase | Prevents drift silently accumulating |
| JSON schema validation (Pydantic) | Docstring-based field validation | Decided during planning | Avoids Pydantic migration cost; staleness test achieves the same goal |

## Open Questions

1. **FastMCP `@mcp.tool()` decorator -- does it preserve `__doc__`?**
   - What we know: FastMCP uses decorators to register tools. Standard practice is `functools.wraps`.
   - What's unclear: Whether `connect_database.__doc__` returns the original docstring after decoration.
   - Recommendation: Verify with a quick assertion in Wave 0. If not preserved, use `inspect.unwrap()`.

2. **Conditional fields: how many are there and what's the annotation pattern?**
   - What we know: Several tools use `// on error only` and `// on success only` and `// detailed mode only` annotations.
   - What's unclear: Whether the annotations are consistent enough to parse reliably.
   - Recommendation: Audit all 9 docstrings (done above -- annotations are consistent). Parse `// on {condition} only` pattern to classify fields as conditional.

3. **execute_query response shape from QueryService.get_query_results()**
   - What we know: This tool delegates response construction to another service.
   - What's unclear: Whether the returned dict always has the exact keys documented.
   - Recommendation: Mock `get_query_results()` to return a dict with the documented keys. The staleness test verifies the docstring matches the mock; separate integration tests verify the mock matches reality.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest + pytest-asyncio (existing) |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/test_staleness.py -x` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| DOCS-02a | Staleness test fails when response schema changes without docstring update | unit | `uv run pytest tests/unit/test_staleness.py -x` | No -- Wave 0 |
| DOCS-02b | Staleness test passes on current codebase (baseline correctness) | unit | `uv run pytest tests/unit/test_staleness.py -x` | No -- Wave 0 |
| DOCS-02c | CI runs staleness test (lives in standard test suite) | unit | `uv run pytest tests/ -x` (already in CI) | No -- Wave 0 |
| DOCS-02d | Staleness test module has 90%+ coverage | unit | `uv run pytest tests/unit/test_staleness.py --cov=tests/unit/test_staleness --cov-report=term-missing` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/test_staleness.py -x`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green + coverage check before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_staleness.py` -- the staleness guard test itself (DOCS-02a/b/c)
- [ ] Parser/comparison utility module(s) -- docstring parsing + field comparison logic
- [ ] Meta-tests for parser logic -- needed for 90%+ coverage (DOCS-02d)
- [ ] pytest-cov may need to be added as dev dependency for coverage measurement

## Discretion Recommendations

Based on research, here are recommendations for Claude's Discretion items:

| Area | Recommendation | Rationale |
|------|---------------|-----------|
| Docstring parsing | Regex-based parser | Format is simple and consistent; a structured parser lib is overkill |
| Tool discovery | Hybrid: auto-discover + validate against known list | Auto-discover catches new tools; known list catches decorator changes |
| Drift scope depth | Field names only (not types) | Types in docstrings use human notation ("ISO 8601 string"); matching against Python types is fragile |
| Conditional annotations | Parse and classify as optional | Prevents false positives; `// on error only` pattern is consistent |
| Bidirectional checking | Yes -- both missing and extra fields | Extra undocumented fields are also drift |
| Nesting depth | Top-level + one level for list/object children | Catches most common drift without excessive complexity |
| Test structure | Parametrized over all tools | Less boilerplate; consistent pattern used elsewhere in codebase |
| Failure messages | Diff-style (missing/extra sets) | Clear, actionable output |
| Test location | Unit tests (fast, mocked) | "Runs on every commit" requirement; no DB needed |
| Args section validation | Out of scope | Not in DOCS-02; could be a future enhancement |
| Runtime vs snapshot | Runtime introspection | Self-healing; no snapshot file to maintain |
| Meta-tests | Yes, for parser + comparison modules | Required by 90%+ coverage criterion |

## Sources

### Primary (HIGH confidence)
- Codebase inspection: `src/mcp_server/schema_tools.py`, `query_tools.py`, `analysis_tools.py` -- all 9 tool docstrings examined
- Codebase inspection: `tests/integration/test_discovery.py` -- established mock pattern for tool invocation
- Codebase inspection: `tests/conftest.py` -- shared fixtures
- Codebase inspection: `tests/helpers.py` -- `parse_tool_response()` helper
- Codebase inspection: `src/mcp_server/server.py` -- tool import/registration pattern
- Codebase inspection: `pyproject.toml` -- pytest configuration with asyncio_mode=auto

### Secondary (MEDIUM confidence)
- FastMCP decorator behavior (functools.wraps preservation) -- based on standard Python library conventions; verify in Wave 0

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all libraries already in project, no new deps needed
- Architecture: HIGH - docstring format is consistent, parsing approach is straightforward
- Pitfalls: HIGH - identified from direct codebase analysis (conditional fields, nested structures, execute_query delegation)

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable domain, no external dependency changes expected)
