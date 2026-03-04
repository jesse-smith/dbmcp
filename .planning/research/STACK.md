# Stack Research

**Domain:** TOON format serialization for Python MCP server
**Researched:** 2026-03-04
**Confidence:** MEDIUM (library is pre-1.0 beta; core API is simple and stable but version pinning needs care)

## Recommended Stack

### Core Technologies

| Technology | Version | Purpose | Why Recommended |
|------------|---------|---------|-----------------|
| toon-format | >=0.9.0b1 | TOON serialization via `toon_format.encode()` | Only official Python implementation of TOON spec. Single function API (`encode(value)`) accepting any JSON-serializable Python value -- directly replaces `json.dumps(dict)` calls. Pre-release but functional; 0.1.0 is a namespace stub with no implementation. |
| Python | >=3.11 (existing) | Runtime | Already pinned in project. toon-format supports >=3.10, so no conflict. |

### Supporting Libraries

| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| tiktoken | (optional) | Token counting for TOON savings measurement | Only if you want to use `toon_format.estimate_savings()` or `compare_formats()` for benchmarking. Not needed at runtime -- useful during development/testing to validate actual token reduction. |

### Development Tools

| Tool | Purpose | Notes |
|------|---------|-------|
| pytest (existing) | Test TOON output correctness | Tests will need updating: assertions currently parse JSON strings via `json.loads()`. Replace with TOON-aware assertions or test against the dict before serialization. |
| ruff (existing) | Linting | No changes needed. |

## Installation

```bash
# Core -- use pre-release flag since 0.9.0b1 is a beta
uv add "toon-format>=0.9.0b1"

# Optional: token counting for benchmarking during development
uv add --group dev tiktoken
```

**Important:** `uv add toon-format` without the version specifier will install 0.1.0 (the namespace stub), which has no implementation. You must explicitly request `>=0.9.0b1` or use `--prerelease allow` to get the working beta.

## Alternatives Considered

| Recommended | Alternative | When to Use Alternative |
|-------------|-------------|-------------------------|
| toon-format (official) | Hand-rolled TOON encoder | Never. The format spec has edge cases (type coercion, nested arrays, delimiter escaping) that the official library handles. Rolling your own invites subtle bugs. |
| toon-format (official) | YAML serialization | Never for this use case. YAML is more readable than JSON but not token-optimized. TOON's tabular layout for uniform arrays is specifically what gives 30-60% savings on database results. |
| toon-format (official) | CSV for tabular data only | Partial overlap. CSV handles flat tabular data well but cannot represent the mixed response envelopes (status, metadata, plus nested table data) that MCP tools return. TOON handles both flat and structured data in one format. |

## What NOT to Use

| Avoid | Why | Use Instead |
|-------|-----|-------------|
| toon-format==0.1.0 (stable) | Namespace reservation only -- no actual `encode()` implementation. Will import successfully but fail at runtime. | toon-format>=0.9.0b1 |
| msgpack / protobuf / other binary formats | MCP tool responses must be human-readable strings that LLMs consume directly as text. Binary formats require decoding and defeat the purpose. | toon-format |
| Custom "compact JSON" (stripping whitespace, shortening keys) | Marginal savings (~5-10%), loses readability, and the keys still consume tokens. TOON's structural approach (indentation + tabular arrays) achieves 30-60%. | toon-format |
| pydantic for data models | PROJECT.md explicitly scopes this out. Current dataclasses with `to_dict()` methods work fine and feed directly into `toon_format.encode()`. | Keep existing dataclasses |

## Integration Pattern

The migration is a serialization-layer swap. The critical pattern:

**Current (JSON):**
```python
return json.dumps({"status": "success", "tables": [...]})
```

**Target (TOON):**
```python
from toon_format import encode
return encode({"status": "success", "tables": [...]})
```

`encode()` accepts any value that `json.dumps()` would accept (dicts, lists, strings, numbers, booleans, None). The `default=str` pattern used in one analysis tool (`json.dumps(response, default=str)`) has no equivalent in `toon_format.encode()` -- those datetime/Decimal values must be pre-serialized to strings before passing to `encode()`.

### encode() Options

| Option | Default | When to Change |
|--------|---------|----------------|
| `delimiter` | `","` | Leave default. Comma delimiter is most token-efficient for tabular data. |
| `indent` | `2` | Leave default. Matches typical LLM prompt formatting. |
| `lengthMarker` | `""` | Leave default. Length markers add tokens without helping LLM comprehension. |

**Recommendation:** Use `encode(value)` with no options. The defaults are optimized for the LLM consumption case.

## Version Compatibility

| Package | Compatible With | Notes |
|---------|-----------------|-------|
| toon-format >=0.9.0b1 | Python >=3.10 | Project requires >=3.11, so no conflict. |
| toon-format >=0.9.0b1 | mcp[cli] >=1.0.0 | No interaction -- toon-format is pure serialization, no MCP protocol awareness needed. |
| toon-format >=0.9.0b1 | sqlalchemy, pyodbc | No interaction -- operates on Python dicts, not DB objects. |

### Pre-release Stability Risk

toon-format is at 0.9.0b1 (Nov 2025) with no subsequent releases in 4 months. The API surface is tiny (one function), so breakage risk is low, but:

- **Pin conservatively:** `toon-format>=0.9.0b1,<1.0.0` to avoid surprise breaking changes if 1.0.0 changes the API.
- **Vendoring option:** If the library stalls, the core `encode()` for flat/tabular data could be vendored (~200 lines). Only consider this if the package becomes unmaintained AND you hit a bug.
- **Confidence:** MEDIUM. The library works for its stated purpose, but the 4-month gap between beta and now with no 1.0 release suggests slow development cadence.

## Testing Strategy Implications

Current tests do `json.loads(result)` to verify response structure. Two options:

1. **Test the dict, not the serialization:** Refactor tools to build the response dict, then serialize. Test the dict-building logic. One integration test per tool verifies TOON serialization. This is cleaner.
2. **Parse TOON in tests:** Would require a TOON decoder, which toon-format does not provide (encode-only library -- TOON is write-only by design since LLMs consume it, not machines). This confirms option 1 is the right approach.

**Recommendation:** Option 1. Separate response construction from serialization. This also makes the staleness test (docstring vs schema validation) simpler since it can inspect the dict structure.

## Sources

- https://pypi.org/project/toon-format/ -- Version history, Python compatibility (MEDIUM confidence, verified)
- https://pypi.org/simple/toon-format/ -- Confirmed only 0.1.0 and 0.9.0b1 exist (HIGH confidence)
- https://github.com/toon-format/toon-python -- README with API docs, encode() signature and options (MEDIUM confidence)
- https://github.com/toon-format/toon -- TOON spec: tabular format for uniform arrays, indentation for nesting (MEDIUM confidence)
- https://github.com/toon-format/toon-python/releases -- Only one release (v0.9.0-beta.1, Nov 2025) (HIGH confidence)
- PROJECT.md -- Project constraints and decisions (HIGH confidence, primary source)

---
*Stack research for: TOON format migration in dbmcp*
*Researched: 2026-03-04*
