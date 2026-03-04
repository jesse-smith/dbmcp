# TOON Response Format Migration

## What This Is

Migrate all dbmcp MCP tool responses from JSON to TOON (Token-Oriented Object Notation) format for token efficiency. TOON achieves 30-60% token reduction over JSON, especially for tabular data like database query results. Since the only consumers are LLMs, this is a pure win with no backward compatibility concerns. Also adds a staleness test to ensure response docstrings stay in sync with data models.

## Core Value

Every MCP tool response uses TOON format, reducing token consumption for LLM consumers without losing any information.

## Requirements

### Validated

(None yet — ship to validate)

### Active

- [ ] All 9 MCP tools return TOON-encoded responses instead of JSON strings
- [ ] Response docstrings updated to document TOON format (structure, types, enum literals)
- [ ] Staleness test validates docstrings match actual response schemas (field names, types, conditionals)
- [ ] toon-python (`toon_format`) added as project dependency
- [ ] Existing test suite passes with TOON responses (tests updated as needed)

### Out of Scope

- Auto-generating docstrings from data models — investigated, wrapper field complexity makes it not worth the effort
- Client format negotiation (JSON vs TOON) — LLM-only consumers, hard switch
- Pydantic migration for data models — current dataclasses work fine
- Changes to MCP tool parameters or business logic — format change only

## Context

- **Current state:** 6 active + 3 analysis tools, all return `json.dumps(dict)` strings
- **Data models:** Plain Python dataclasses in `src/models/schema.py` and `src/models/analysis.py` with `to_dict()` methods
- **Envelope pattern:** Each tool wraps model data in a response dict adding `status`, `error_message`, and tool-specific metadata (pagination, computed fields)
- **FastMCP:** Uses function docstrings verbatim as tool descriptions sent to LLM clients
- **TOON library:** `toon-format/toon-python` provides `encode()` function accepting any JSON-serializable Python value
- **Token savings:** TOON benchmarks show ~49% reduction vs JSON overall; tabular tools (list_tables, execute_query, get_sample_data) will see the biggest gains

## Constraints

- **Dependency**: Must use `toon_format` Python package (official TOON implementation)
- **Compatibility**: Response structure (field names, types, nesting) must remain identical — only serialization format changes
- **Docstrings**: FastMCP reads docstrings at import time, so any doc generation must happen before `@mcp.tool()` registration

## Key Decisions

| Decision | Rationale | Outcome |
|----------|-----------|---------|
| Hard switch to TOON (no JSON fallback) | Only LLM consumers; simplicity over backward compat | — Pending |
| Skip auto-docstring generation | Wrapper fields differ per tool; maintenance trade-off not worth it | — Pending |
| Staleness test for docstring drift | Lightweight way to catch schema/doc mismatch without full auto-gen | — Pending |

---
*Last updated: 2026-03-04 after initialization*
