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

## Milestone: v2.0 — Multi-Dialect Support

**Shipped:** 2026-05-06
**Phases:** 7 (6 + 13.1 inserted) | **Plans:** 20 | **Sessions:** many (live Databricks verification surfaced 12 quick-tasks)
**Duration:** 23 days (2026-04-13 → 2026-05-06)

### What Was Built
- DialectStrategy protocol (`src/db/dialects/protocol.py`) with MssqlDialect, DatabricksDialect, GenericDialect implementations and registry-backed dispatch
- Discriminated TOML config with required `dialect` field and per-dialect typed config models
- Simplified connect_database tool signature (connection_name | sqlalchemy_url) with pyodbc/azure-identity moved to `mssql` extra, databricks packages to `databricks` extra, lazy imports with clear error messages
- Databricks three-level namespace (catalog.schema.table), DESCRIBE EXTENDED property parsing, partition metadata in schema responses, Tier-3 precomputed-stats fast path
- Dialect-aware query validation (sqlglot parse + safe-procedure list), denylist unchanged across dialects
- Cross-dialect analysis tools via TSQL-base + sqlglot transpilation (column stats, PK/FK discovery) with Inspector-based metadata and `supports_indexes` capability gating
- Dialect-parameterized test fixtures (mock-based, no live connections required), coverage floor ratcheted 70% → 85% (baseline 90.64%)
- Phase 13.1 integration closure + quick 260506-n8s: WIRING-01/02/03 resolved; sample-query SQL generation moved out of QueryService into `DialectStrategy.build_sample_query`

### What Worked
- Strategy-over-inheritance for dialects: zero coupling between MSSQL and Databricks code, each dialect self-contained
- TSQL-as-base + sqlglot transpile: write queries once, dispatch per-dialect — avoided N-way hand-written variants
- Capability-flag gating (`supports_indexes`): clean way to omit features that don't apply per-dialect without cluttering consumer code with isinstance checks
- D-02 choice to require dialect in config: one integration test would have failed silently in prod with a default; explicit failure caught it immediately
- Inserting Phase 13.1 instead of opening v3.0: audit surfaced three wiring gaps and four tech-debt items; decimal phase kept milestone intact without dragging on
- Live Databricks verification after Phase 13.1 surfaced the dialect-blind sample-query bug — live integration is a faster truth-finder than unit tests for cross-dialect SQL generation

### What Was Inefficient
- 12 quick-tasks piled up during live Databricks verification (2026-04-28 through 2026-05-06) — suggests Phase 11 missed integration dimensions that only show up against a real warehouse (env-var substitution, error wrapping, cross-catalog column fetch, URL parsing, connect_timeout + retry, driver override). Consider a "live smoke test" gate between Phase 11 and Phase 12 in future milestones that ship a new dialect.
- REQUIREMENTS.md traceability checkboxes stayed `[ ]` throughout the milestone despite VERIFICATION tables marking SATISFIED — same pattern as v1.0 and v1.1, still unfixed. Needs automation (auto-tick from VERIFICATION) or workflow change.
- SUMMARY `requirements-completed` frontmatter was inconsistently populated across plans; Phase 13.1 TD-03 mechanically reconciled 16 SUMMARY files. Would be better to enforce at write time.
- Milestone audit first ran 2026-05-05 and reported `gaps_found` (WIRING-01/02/03 + tech debt) — audit-first catches real issues; in retrospect, it should have been run before marking Phase 13 complete rather than as a separate pass.

### Patterns Established
- DialectStrategy protocol as the extension point for new databases — adding a dialect = one file in `src/db/dialects/` + registry entry + optional pyproject extra
- Capability flags (`supports_indexes`, `supports_catalog`) instead of type checks in consumer code
- `build_sample_query`-style delegation pattern: any SQL that diverges per-dialect belongs on the strategy, not in the service layer
- Lazy imports guarded with try/except ImportError in dialect module-level code → clear actionable error messages when extras are missing
- Audit-driven decimal-phase insertion (13.1) as the standard way to close milestone gaps without extending scope

### Key Lessons
1. **Live integration catches what unit tests miss for cross-dialect work.** 12 quick-tasks and one deferred integration test (sample_data) all surfaced against a real Databricks warehouse — unit mocks couldn't model Unity Catalog three-part naming, env-var substitution quirks, or SQL syntax divergence.
2. **Require config fields instead of defaulting when the default is wrong for N-1 of N cases.** Defaulting `dialect` to `mssql` would have been silently wrong for every Databricks user. Explicit failure beats implicit coercion.
3. **Dispatch SQL generation, don't branch on `_dialect is None`.** The `_dialect is None` SQLite proxy in QueryService persisted for weeks as latent breakage for every non-MSSQL path — fixed only when live Databricks made it visible. Any "if dialect X then A else B" in service code should migrate to the strategy.
4. **Milestone audits are best run before marking the last phase complete, not after.** The 2026-05-05 audit report is exactly the kind of artifact that should gate phase completion, not follow it.

### Cost Observations
- Model mix: predominantly opus for execution/planning, sonnet for research and integration-checker subagent
- Sessions: many (one per phase discuss/plan/execute + 12 quick-tasks + milestone audit + close)
- Notable: 20 plans + 12 quick-tasks over 23 days; velocity slower than v1.1 due to the dialect-per-phase expansion pattern and live Databricks feedback loop

---

## Cross-Milestone Trends

### Process Evolution

| Milestone | Sessions | Phases | Key Change |
|-----------|----------|--------|------------|
| v1.0 | ~3 | 2 | First milestone — established TDD + atomic swap patterns |
| v1.1 | ~8 | 5 | Audit-driven milestone — systematic concern resolution with gap closure |
| v2.0 | many | 7 | Architecture milestone — DialectStrategy protocol + live-integration feedback loop; audit-inserted decimal phase (13.1) to close wiring gaps |

### Cumulative Quality

| Milestone | Tests | Coverage | New Modules |
|-----------|-------|----------|-------------|
| v1.0 | 441 | 99% (staleness) | serialization.py, helpers.py, staleness/ |
| v1.1 | 682 | 70%+ (all modules) | config.py, type_handlers.py, error classification |
| v2.0 | 872 | 90.64% (85% floor) | `src/db/dialects/` (protocol, mssql, databricks, generic, registry), sqlite_schema fixture, dialect-parameterized conftest |

### Top Lessons (Verified Across Milestones)

1. TDD with red-green-refactor prevents regressions — zero regressions across both milestones (16 plans)
2. Structured audit → milestone pipeline produces well-scoped, completable work
3. ROADMAP.md checkbox tracking consistently drifts from actual completion — needs automation or workflow fix
