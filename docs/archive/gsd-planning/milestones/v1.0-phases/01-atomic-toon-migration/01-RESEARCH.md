# Phase 1: Atomic TOON Migration - Research

**Researched:** 2026-03-04
**Domain:** Serialization format migration (JSON to TOON) across MCP tool layer
**Confidence:** HIGH

## Summary

Phase 1 replaces all `json.dumps` calls in the 3 tool modules (schema_tools, query_tools, analysis_tools) with a thin wrapper around `toon_format.encode()`, updates all 64 `json.loads` calls across 6 integration test files to use a new `parse_tool_response()` helper, and rewrites 9 tool docstrings to document TOON output format. The response structure (field names, types, nesting) remains identical -- only the serialization format changes.

The `toon-format` library (v0.9.0-beta.1) is available only from GitHub, not PyPI (the PyPI package is a namespace reservation with no implementation). It provides `encode()` and `decode()` functions. Critically, its normalizer silently converts unrecognized types (including Enum subclasses) to `null` with only a log warning -- this directly conflicts with SRLZ-04's "no silent null coercion" requirement, making the pre-serialization step mandatory rather than optional.

**Primary recommendation:** Build a `src/serialization.py` wrapper with a recursive pre-serializer that converts datetime/StrEnum and raises TypeError on unknowns, then calls `toon_format.encode()`. All tool modules call this wrapper exclusively.

<user_constraints>

## User Constraints (from CONTEXT.md)

### Locked Decisions
- New `src/serialization.py` module encapsulates `toon_format.encode()` (satisfies SRLZ-02)
- Single `encode_response(data: dict) -> str` function -- no separate error helper
- All responses (success and error) go through TOON encoding -- consistent format, no format-sniffing needed
- Pre-serialization of non-primitives happens inside the wrapper (not at tool layer or in `to_dict()` methods)
- Recursive walker in `src/serialization.py` handles nested dicts and lists
- `datetime` -> `.isoformat()` string
- `StrEnum` -> `str(value)` (returns the string value, e.g., "sql", "table" -- matches current json.dumps behavior)
- Unknown/unrecognized types -> raise `TypeError` (fail loudly per SRLZ-04: no silent null coercion)
- Docstrings name TOON explicitly: "TOON-encoded string with..."
- Structural outline only -- field names, types, and conditional annotations (no full sample data)
- Same structure as current JSON examples, just different syntax -- pure format swap, no doc cleanup
- Standalone `tests/helpers.py` module with `parse_tool_response()` function (not a fixture)
- TOON-only from day one -- no dual-format support, no auto-detection
- Just decode -- returns dict, no assertion helpers
- Use helper everywhere (both unit and integration tests) for consistency

### Claude's Discretion
- TOON nesting representation in docstrings (pick what aligns with actual TOON syntax)
- Exact `_pre_serialize()` implementation details (type dispatch, edge cases)
- Order of migration across the 3 tool files (schema_tools, query_tools, analysis_tools)
- How to handle the `default=str` currently used in `analysis_tools.py` line 137 (replace with explicit pre-serialization)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope

</user_constraints>

<phase_requirements>

## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| SRLZ-01 | `toon-format` added as project dependency, pinned `>=0.9.0b1,<1.0.0` | Library available from GitHub only; pip install from git URL; pyproject.toml needs git dependency |
| SRLZ-02 | Wrapper module encapsulates `toon_format.encode()` calls | `src/serialization.py` with `encode_response()` -- confirmed encode() accepts dict, returns str |
| SRLZ-03 | All 9 MCP tools return TOON-encoded string content | 41 json.dumps calls across 3 files (16 in schema_tools, 12 in query_tools, 13 in analysis_tools) |
| SRLZ-04 | Non-primitive types pre-serialized before TOON encoding | TOON normalizer silently nullifies unknown types; pre-serializer must convert datetime, StrEnum, and raise on unknowns |
| TEST-01 | `parse_tool_response()` test helper abstracts deserialization | `tests/helpers.py` with `toon_format.decode()` wrapper; replaces 64 json.loads calls + 2 utility functions |
| TEST-02 | All existing test assertions updated to use test helper | 6 integration test files, plus `tests/utils.py` (assert_json_contains, assert_json_has_keys) |
| TEST-03 | Integration tests verify TOON output decodes correctly | Existing integration tests become TOON tests once helper is swapped in |
| DOCS-01 | All 9 tool docstrings updated to document TOON response format | 9 docstrings currently say "JSON string with..."; TOON uses indentation-based syntax |

</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| toon-format | >=0.9.0b1,<1.0.0 | TOON encoding/decoding | Official Python implementation of TOON format |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| (none new) | - | - | All other deps already in project |

### Alternatives Considered
None -- TOON library is a locked decision. No alternatives to evaluate.

**Installation:**
```bash
# In pyproject.toml dependencies:
"toon-format @ git+https://github.com/toon-format/toon-python.git"

# Then:
uv sync
```

**IMPORTANT: PyPI vs GitHub**
The `toon-format` package on PyPI (v0.1.0, Nov 2025) is a **namespace reservation** with no implementation. The real library (v0.9.0-beta.1) lives at `github.com/toon-format/toon-python` and must be installed from the git URL. The pinned version range `>=0.9.0b1,<1.0.0` in REQUIREMENTS.md applies to the GitHub package. Use a PEP 440 git dependency in pyproject.toml.

## Architecture Patterns

### Recommended Project Structure
```
src/
  serialization.py          # NEW: encode_response() wrapper
  mcp_server/
    schema_tools.py          # MODIFIED: json.dumps -> encode_response
    query_tools.py           # MODIFIED: json.dumps -> encode_response
    analysis_tools.py        # MODIFIED: json.dumps -> encode_response
tests/
  helpers.py                 # NEW: parse_tool_response() test helper
  utils.py                   # MODIFIED: assert_json_* updated to use helpers
```

### Pattern 1: Serialization Wrapper
**What:** Single-function module that pre-serializes non-primitives then calls `toon_format.encode()`
**When to use:** Every tool response path (success and error)
**Example:**
```python
# src/serialization.py
from datetime import datetime, date
from enum import StrEnum
from toon_format import encode

def encode_response(data: dict) -> str:
    """Encode a tool response dict as a TOON string."""
    return encode(_pre_serialize(data))

def _pre_serialize(value):
    """Recursively convert non-primitive types to TOON-safe values."""
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, dict):
        return {k: _pre_serialize(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_pre_serialize(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, StrEnum):
        return str(value)
    raise TypeError(f"Cannot serialize type {type(value).__name__}: {value!r}")
```

### Pattern 2: Test Helper
**What:** Thin decode wrapper returning dict
**When to use:** Every test that receives a tool response string
**Example:**
```python
# tests/helpers.py
from toon_format import decode

def parse_tool_response(response: str) -> dict:
    """Decode a TOON-encoded tool response to a Python dict."""
    result = decode(response)
    if not isinstance(result, dict):
        raise ValueError(f"Expected dict, got {type(result).__name__}")
    return result
```

### Pattern 3: Tool Migration (replacement pattern)
**What:** Replace `json.dumps(...)` with `encode_response(...)` in each tool
**Example:**
```python
# Before:
import json
return json.dumps({"status": "success", "schemas": [...]})

# After:
from src.serialization import encode_response
return encode_response({"status": "success", "schemas": [...]})
```

### Anti-Patterns to Avoid
- **Calling toon_format.encode() directly from tool modules:** Bypasses pre-serialization; any StrEnum or datetime would be silently nullified by TOON's normalizer
- **Keeping json.dumps for error responses:** Creates mixed-format responses; every response must be TOON
- **Adding toon_format.decode() directly in test files:** Scatters deserialization logic; all tests must go through helpers.py
- **Using default=str fallback:** analysis_tools.py currently uses `json.dumps(response, default=str)` -- this pattern has no equivalent in TOON and must be replaced with explicit pre-serialization

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| TOON encoding | Custom serializer | `toon_format.encode()` | Format spec has edge cases (tabular detection, escaping, indentation) |
| TOON decoding | Custom parser | `toon_format.decode()` | Roundtrip correctness requires matching encoder/decoder |
| Type normalization | Rely on TOON's built-in normalizer | Custom `_pre_serialize()` | TOON normalizer silently nullifies unknowns; we need TypeError |

**Key insight:** The TOON library does have built-in type normalization (datetime -> ISO, Decimal -> float), but it also silently converts unknowns to null. Since SRLZ-04 requires fail-loud behavior, we must pre-serialize ourselves and feed only JSON-primitive data to `encode()`.

## Common Pitfalls

### Pitfall 1: TOON Normalizer Silently Eats Types
**What goes wrong:** StrEnum values pass through to `encode()` and get silently converted to `null`
**Why it happens:** TOON's normalize.py converts unrecognized types to `null` with only a log warning, not an exception
**How to avoid:** Pre-serialize ALL non-primitive types before calling `encode()`. The wrapper's `_pre_serialize()` must handle datetime, date, StrEnum, and raise TypeError on anything else.
**Warning signs:** Response fields showing `null` where strings were expected

### Pitfall 2: analysis_tools.py default=str Fallback
**What goes wrong:** `json.dumps(response, default=str)` silently stringifies any type; removing it without pre-serialization causes TypeError at the wrong layer
**Why it happens:** `default=str` was a lazy catch-all for Decimal/datetime in column stats
**How to avoid:** The wrapper's pre-serializer handles all types that `default=str` was catching. The `to_dict()` methods on analysis models already convert datetime to isoformat, so the main risk is Decimal values from SQL Server numeric stats.
**Warning signs:** `get_column_info` tests failing with type errors

### Pitfall 3: Incomplete json.loads Replacement in Tests
**What goes wrong:** Some tests still use `json.loads` directly, creating mixed-format test failures
**Why it happens:** 64 occurrences across 6 files plus 2 utility functions in `tests/utils.py` -- easy to miss some
**How to avoid:** Grep for `json.loads` in tests after migration; the success criterion is ZERO direct json.loads calls on tool responses. Also update `assert_json_contains()` and `assert_json_has_keys()` in `tests/utils.py`.
**Warning signs:** Import of `json` in test files (should no longer be needed for response parsing)

### Pitfall 4: Tuple Values from to_dict() Methods
**What goes wrong:** `StringStats.to_dict()` returns `sample_values` as `list[tuple[str, int]]`; tuples need handling
**Why it happens:** TOON normalizer converts tuples to sorted lists, which changes the order of (value, count) pairs
**How to avoid:** `_pre_serialize()` handles tuples by converting to lists while preserving order (not sorted)
**Warning signs:** `sample_values` data in get_column_info responses showing reordered pairs

### Pitfall 5: TOON decode() Returns Different Numeric Types
**What goes wrong:** JSON always returns `int` for `42` and `float` for `42.0`; TOON decode may return different types
**Why it happens:** Format difference in how numbers are represented/parsed
**How to avoid:** Test assertions should use appropriate comparison (avoid strict type checks on numeric values where format conversion might differ)
**Warning signs:** Assertion failures comparing `42` vs `42.0` in test assertions

### Pitfall 6: Docstring TOON Syntax
**What goes wrong:** Docstrings show JSON-style curly braces; FastMCP sends docstrings verbatim to LLM clients
**Why it happens:** Current docstrings use `{...}` JSON examples; TOON uses indentation-based format
**How to avoid:** Use TOON's actual syntax in docstrings: indented key-value pairs, no braces
**Warning signs:** LLM clients seeing JSON examples but receiving TOON responses

## Code Examples

### Current json.dumps Sites (Replacement Targets)

**schema_tools.py** -- 16 calls across 4 tools:
```python
# connect_database: 4 return paths (success, auth error, connection error, validation error, unexpected)
# list_schemas: 3 return paths (success, ValueError, Exception)
# list_tables: 3 return paths (validation error, success, ValueError, Exception)
# get_table_schema: 4 return paths (not found, success, ValueError, Exception)
```

**query_tools.py** -- 12 calls across 2 tools:
```python
# get_sample_data: 5 return paths (size error, method error, method parse error, success, ValueError, Exception)
# execute_query: 5 return paths (limit low, limit high, empty query, success, ValueError, Exception)
```

**analysis_tools.py** -- 13 calls across 3 tools:
```python
# get_column_info: 4 return paths (table not found, success with default=str, ValueError, Exception)
# find_pk_candidates: 4 return paths (table not found, success, ValueError, Exception)
# find_fk_candidates: 5 return paths (table not found, col not found, success, ValueError, Exception)
```

### TOON Output Format Example
For a tool response like `{"status": "success", "total_schemas": 3, "schemas": [{"schema_name": "dbo", "table_count": 10}]}`, TOON encodes as:
```
status: success
total_schemas: 3
schemas:
  [1,]{schema_name,table_count}:
    dbo,10
```

### Docstring Format Example (TOON)
```python
"""...
Returns:
    TOON-encoded string with connection details:

        status: "success" | "error"
        connection_id: string               // on success only
        message: string                     // on success only
        schema_count: int                   // on success only
        has_cached_docs: bool               // on success only
        error_message: string               // on error only
"""
```

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| JSON string responses | TOON string responses | This migration | 30-60% token reduction for LLM consumers |
| json.dumps + default=str | Explicit pre-serialization + toon_format.encode() | This migration | Fail-loud on unknown types vs silent coercion |
| json.loads in tests | parse_tool_response() helper | This migration | Single point of change for future format changes |

## Open Questions

1. **Decimal handling in _pre_serialize()**
   - What we know: TOON normalizer converts Decimal to float. The pre-serializer runs before encode().
   - What's unclear: Should _pre_serialize convert Decimal to float (matching TOON behavior) or to str (matching json.dumps default=str behavior)?
   - Recommendation: Convert to float -- matches TOON's built-in behavior and preserves numeric semantics. The `to_dict()` methods don't produce Decimals directly (SQL results come through as Python floats from pyodbc), but add Decimal handling defensively.

2. **git dependency syntax in pyproject.toml**
   - What we know: toon-format is GitHub-only; PEP 440 supports git URLs
   - What's unclear: Whether `uv` handles git dependencies with the same syntax as pip
   - Recommendation: Use `"toon-format @ git+https://github.com/toon-format/toon-python.git@v0.9.0-beta.1"` and verify `uv sync` works before proceeding with implementation.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest 7.0+ with pytest-asyncio |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/ -x -q` |
| Full suite command | `uv run pytest tests/ -v` |

### Phase Requirements -> Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| SRLZ-01 | toon-format importable | unit | `uv run pytest tests/unit/test_serialization.py::test_toon_import -x` | No -- Wave 0 |
| SRLZ-02 | encode_response returns TOON string | unit | `uv run pytest tests/unit/test_serialization.py::TestEncodeResponse -x` | No -- Wave 0 |
| SRLZ-03 | All tools return TOON (not JSON) | integration | `uv run pytest tests/integration/ -x` | Yes (existing, needs update) |
| SRLZ-04 | TypeError on unknown types | unit | `uv run pytest tests/unit/test_serialization.py::TestPreSerialize -x` | No -- Wave 0 |
| TEST-01 | parse_tool_response helper works | unit | `uv run pytest tests/unit/test_helpers.py -x` | No -- Wave 0 |
| TEST-02 | No json.loads in test files | compliance | grep-based verification (no json.loads on tool responses) | N/A |
| TEST-03 | Integration tests decode TOON correctly | integration | `uv run pytest tests/integration/ -x` | Yes (existing, needs update) |
| DOCS-01 | Docstrings show TOON format | compliance | grep-based verification (no "JSON string" in docstrings) | N/A |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -v`
- **Phase gate:** Full suite green + `uv run ruff check src/` clean before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `tests/unit/test_serialization.py` -- covers SRLZ-01, SRLZ-02, SRLZ-04 (encode_response, _pre_serialize, TypeError on unknowns)
- [ ] `tests/unit/test_helpers.py` -- covers TEST-01 (parse_tool_response roundtrip)
- [ ] `toon-format` dependency in pyproject.toml -- SRLZ-01 prerequisite

## Sources

### Primary (HIGH confidence)
- GitHub `toon-format/toon-python` README -- encode/decode API, installation, version (v0.9.0-beta.1)
- GitHub `toon-format/toon-python` normalize.py -- type normalization behavior (datetime -> isoformat, Decimal -> float, unknown -> null with warning)
- Project source code -- 3 tool modules, 6 integration test files, model files, conftest files

### Secondary (MEDIUM confidence)
- PyPI `toon-format` page -- confirmed v0.1.0 is namespace reservation only, not the real library

### Tertiary (LOW confidence)
- TOON output format syntax (indentation, tabular arrays) -- inferred from README examples; would benefit from testing actual encode output with project data shapes

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH -- library confirmed on GitHub, API verified from source
- Architecture: HIGH -- wrapper pattern is straightforward; all replacement sites identified and counted
- Pitfalls: HIGH -- TOON normalizer behavior verified from source code; `default=str` usage confirmed in codebase
- TOON output syntax for docstrings: MEDIUM -- inferred from README examples, not tested with actual project data

**Research date:** 2026-03-04
**Valid until:** 2026-04-04 (stable -- library is pre-1.0 but API unlikely to change within beta)
