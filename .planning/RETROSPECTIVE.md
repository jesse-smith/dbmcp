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

## Milestone: v1.1 — Concern Handling

**Shipped:** 2026-03-10
**Phases:** 5 | **Plans:** 11 | **Sessions:** ~8

### What Was Built
- Dead code removal (metrics.py), 15 broad exceptions narrowed to specific SQLAlchemy types, type: ignore eliminated
- 70% coverage floor enforced via pyproject.toml fail_under and codecov.yml, with 9 new error-path tests
- Auth-aware pool_recycle=2700 for Azure AD connections, atexit/SIGTERM lifecycle cleanup with SQLSTATE-based error classification
- 28 parametrized sqlglot edge case tests, metadata-based column validation replacing regex-only sanitization
- Unified type handler registry (13 Python types) replacing duplicate _pre_serialize/_truncate_value pipelines
- TOML config file with named connections, ${VAR} credential resolution, SP allowlist extensions
- Config-driven text truncation and _classify_db_error wired into all 9 MCP tool safety nets

### What Worked
- Audit-first approach: v1.0 audit identified 10 concerns, milestone addressed all 10 systematically
- Phase ordering (cleanup → tests → features) meant each phase built on a cleaner foundation
- Phases 4/5/6 were independent of each other (only depended on Phase 3), enabling clean sequential execution
- TDD continued from v1.0 — every plan followed red-green-refactor with zero regressions
- Gap closure phase (Phase 7) caught two real integration gaps that would have shipped as dead code
- Nyquist validation caught all phases, bringing compliance from partial to full

### What Was Inefficient
- ROADMAP.md phase checkboxes stayed unchecked even after phases completed (same cosmetic issue as v1.0)
- STATE.md performance table was missing Phase 03 P01/P02 entries (tracking gap)
- Summary-extract tool couldn't find one_liner fields (summaries used bold text format instead)

### Patterns Established
- `_classify_db_error()` pattern for user-facing error messages from database exceptions
- Type handler registry pattern (ordered chain, subclass-first isinstance dispatch)
- TOML config pattern with env var resolution and tool arg precedence (explicit > config > defaults)
- Metadata-based validation with fail-open regex fallback when metadata unavailable

### Key Lessons
1. Audit → milestone pipeline works: structured concern gathering produces well-scoped milestones
2. Gap closure phases are worth it — Phase 7 found real integration issues that other phases missed
3. Module-level functions (not methods) enable cross-module reuse without class coupling
4. Env var resolution at connection time (not load time) is critical for credential security

### Cost Observations
- Model mix: primarily opus for execution, sonnet for research/planning agents
- Sessions: ~8 (context gathering, research, planning, 5 phase executions)
- Notable: 11 plans across 5 phases in 5 days — sustained velocity from v1.0

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~3 | 2 | First milestone — established TDD + atomic swap patterns |
| v1.1 | ~8 | 5 | Audit-driven milestone — systematic concern resolution with gap closure |

### Cumulative Quality

| Milestone | Tests | Coverage | New Modules |
|-----------|-------|----------|-------------|
| v1.0 | 441 | 99% (staleness) | serialization.py, helpers.py, staleness/ |
| v1.1 | 682 | 70%+ (all modules) | config.py, type_handlers.py, error classification |

### Top Lessons (Verified Across Milestones)

1. TDD with red-green-refactor prevents regressions — zero regressions across both milestones (16 plans)
2. Structured audit → milestone pipeline produces well-scoped, completable work
3. ROADMAP.md checkbox tracking consistently drifts from actual completion — needs automation or workflow fix
