# Requirements: TOON Response Format Migration

**Defined:** 2026-03-04
**Core Value:** Every MCP tool response uses TOON format, reducing token consumption for LLM consumers without losing any information.

## v1 Requirements

Requirements for initial release. Each maps to roadmap phases.

### Serialization

- [ ] **SRLZ-01**: `toon-format` added as project dependency, pinned `>=0.9.0b1,<1.0.0`
- [ ] **SRLZ-02**: Wrapper module encapsulates `toon_format.encode()` calls, insulating codebase from library API changes
- [ ] **SRLZ-03**: All 9 MCP tools return TOON-encoded string content (MCP JSON-RPC envelope unchanged)
- [ ] **SRLZ-04**: Non-primitive types (datetime, Decimal, Enum) pre-serialized before TOON encoding (no silent null coercion)

### Testing

- [ ] **TEST-01**: `parse_tool_response()` test helper abstracts deserialization across all test files
- [ ] **TEST-02**: All existing test assertions updated to use test helper (no direct `json.loads` for tool responses in tests)
- [ ] **TEST-03**: Integration tests verify TOON output decodes correctly for each tool's response shapes

### Documentation

- [ ] **DOCS-01**: All 9 tool docstrings updated to document TOON response format (structure, types, enum literals)
- [ ] **DOCS-02**: Staleness test validates docstring field declarations match actual response schemas

## v2 Requirements

### Measurement

- **MEAS-01**: Token savings benchmarked per tool (JSON vs TOON)
- **MEAS-02**: Performance benchmark of `encode()` on large result sets (10K+ rows)
- **MEAS-03**: Token savings documented for users

## Out of Scope

| Feature | Reason |
|---------|--------|
| Format negotiation (JSON vs TOON) | LLM-only consumers; hard switch simplifies implementation |
| Auto-generated docstrings from data models | Investigated; wrapper fields differ per tool, maintenance trade-off not worth it |
| Pydantic migration for data models | Explored as auto-docstring enabler; staleness test achieves the goal without migration cost |

## Traceability

Which phases cover which requirements. Updated during roadmap creation.

| Requirement | Phase | Status |
|-------------|-------|--------|
| SRLZ-01 | — | Pending |
| SRLZ-02 | — | Pending |
| SRLZ-03 | — | Pending |
| SRLZ-04 | — | Pending |
| TEST-01 | — | Pending |
| TEST-02 | — | Pending |
| TEST-03 | — | Pending |
| DOCS-01 | — | Pending |
| DOCS-02 | — | Pending |

**Coverage:**
- v1 requirements: 9 total
- Mapped to phases: 0
- Unmapped: 9 ⚠️

---
*Requirements defined: 2026-03-04*
*Last updated: 2026-03-04 after initial definition*
