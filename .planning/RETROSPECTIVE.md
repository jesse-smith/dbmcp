# Project Retrospective

*A living document updated after each milestone. Lessons feed forward into future planning.*

## Milestone: v1.0 — TOON Response Format Migration

**Shipped:** 2026-03-05
**Phases:** 2 | **Plans:** 5 | **Sessions:** ~3

### What Was Built
- TOON serialization wrapper (`encode_response`) with recursive pre-serialization for datetime, StrEnum, Decimal
- Atomic swap of all 9 MCP tools from JSON to TOON (40 json.dumps calls replaced)
- Test helper (`parse_tool_response`) replacing 64+ json.loads calls across integration tests
- All 9 tool docstrings rewritten in TOON structural outline format
- Docstring parser and bidirectional field comparison utilities
- Parametrized staleness guard test (21 tests, 99% coverage) covering all 9 tools

### What Worked
- Two-phase structure (migration then guard) kept each phase focused and fast
- TDD throughout — every plan followed red-green-refactor, zero regressions
- Atomic swap approach avoided mixed JSON/TOON state (research identified this as Pitfall 5)
- Coarse granularity kept plans at 3-6 min each — fast feedback loops
- Staleness guard immediately proved its value by catching 6 real docstring-schema mismatches during development

### What Was Inefficient
- Nothing notable — this was a clean, well-scoped milestone with minimal friction
- Phase 1 checkbox in ROADMAP.md wasn't marked as complete (cosmetic, caught by audit)

### Patterns Established
- `encode_response()` wrapper pattern for all future tool serialization
- `parse_tool_response()` test helper for all future test assertions on tool output
- TOON structural outline format for docstrings (field: type // annotation)
- Staleness guard as ongoing regression protection for docstring-schema sync

### Key Lessons
1. Atomic swaps work well for format migrations — do everything in one coordinated phase rather than tool-by-tool
2. Staleness tests that run during development catch real issues before they ship, not just hypothetical drift
3. ast module is the right approach for extracting Python docstrings when direct imports cause circular dependencies

### Cost Observations
- Model mix: primarily opus for execution, haiku for research agents
- Sessions: ~3 (research+plan, Phase 1 execution, Phase 2 execution)
- Notable: 5 plans in 19 total minutes — extremely efficient for a 9-tool migration

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~3 | 2 | First milestone — established TDD + atomic swap patterns |

### Cumulative Quality

| Milestone | Tests | Coverage | New Modules |
|-----------|-------|----------|-------------|
| v1.0 | 441 | 99% (staleness) | serialization.py, helpers.py, staleness/ |

### Top Lessons (Verified Across Milestones)

1. (Awaiting second milestone for cross-validation)
