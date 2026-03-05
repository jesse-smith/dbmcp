# Milestones

## v1.0 TOON Response Format Migration (Shipped: 2026-03-05)

**Phases completed:** 2 phases, 5 plans, 8 tasks
**Timeline:** 2 days (2026-03-04 → 2026-03-05)
**Commits:** 35 | **LOC:** 17,101 Python

**Delivered:** Every MCP tool response uses TOON format, reducing token consumption for LLM consumers without losing any information.

**Key accomplishments:**
- TOON serialization wrapper with recursive pre-serialization for datetime/StrEnum/Decimal
- Atomic swap of all 9 MCP tools from JSON to TOON (40 json.dumps → encode_response)
- All 9 tool docstrings updated to TOON structural outline format
- Docstring parser and bidirectional field comparison utilities for drift detection
- Parametrized staleness guard test covering all 9 tools (21 tests, 99% coverage)
- Staleness guard caught 6 real docstring-schema drift issues during development

---

