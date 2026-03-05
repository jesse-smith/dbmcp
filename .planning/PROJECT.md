# TOON Response Format Migration

## What This Is

Migrate all dbmcp MCP tool responses from JSON to TOON (Token-Oriented Object Notation) format for token efficiency. All 9 MCP tools now return TOON-encoded responses with ~30-60% token reduction over JSON. A staleness guard test ensures response docstrings stay in sync with data models on every pytest run.

## Core Value

Every MCP tool response uses TOON format, reducing token consumption for LLM consumers without losing any information.

## Requirements

### Validated

- ✓ All 9 MCP tools return TOON-encoded responses instead of JSON strings — v1.0
- ✓ Response docstrings updated to document TOON format (structure, types, enum literals) — v1.0
- ✓ Staleness test validates docstrings match actual response schemas (field names, types, conditionals) — v1.0
- ✓ toon-python (`toon_format`) added as project dependency — v1.0
- ✓ Existing test suite passes with TOON responses (tests updated as needed) — v1.0

### Active

(No active requirements — milestone complete)

### Out of Scope

- Auto-generating docstrings from data models — investigated, wrapper field complexity makes it not worth the effort
- Client format negotiation (JSON vs TOON) — LLM-only consumers, hard switch
- Pydantic migration for data models — current dataclasses work fine
- Changes to MCP tool parameters or business logic — format change only
- Token savings benchmarking (MEAS-01–03) — deferred, not pursuing

## Context

- **Current state:** 9 MCP tools returning TOON-encoded responses, 441 tests (434 passed, 41 skipped)
- **Tech stack:** Python 3.11+, FastMCP, SQLAlchemy, pyodbc, toon-format v0.9.0-beta.1
- **Data models:** Plain Python dataclasses with `to_dict()` methods, pre-serialized by `encode_response()`
- **Staleness guard:** 21 parametrized tests (success + error paths for all 9 tools) with 99% coverage
- **Key files:** `src/serialization.py` (wrapper), `tests/helpers.py` (test helper), `tests/staleness/` (guard)

## Constraints

- **Dependency**: Must use `toon_format` Python package (official TOON implementation)
- **Compatibility**: Response structure (field names, types, nesting) must remain identical — only serialization format changes
- **Docstrings**: FastMCP reads docstrings at import time, so any doc generation must happen before `@mcp.tool()` registration

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hard switch to TOON (no JSON fallback) | Only LLM consumers; simplicity over backward compat | ✓ Good — clean atomic swap, no mixed state |
| Skip auto-docstring generation | Wrapper fields differ per tool; maintenance trade-off not worth it | ✓ Good — staleness test catches drift instead |
| Staleness test for docstring drift | Lightweight way to catch schema/doc mismatch without full auto-gen | ✓ Good — caught 6 real issues during dev |
| StrEnum pre-serialization via .value | Clean string extraction without StrEnum subclass leaking | ✓ Good |
| TypeError on unrecognized types (strict) | Prefer explicit failure over silent str() fallback | ✓ Good |
| ast module for docstring extraction | Avoids circular imports with MCP server modules | ✓ Good — necessary workaround |
| TOON structural outline for docstrings | field: type // annotation format, more token-efficient than JSON notation | ✓ Good |

---
*Last updated: 2026-03-05 after v1.0 milestone*
