# Phase 13: Test Infrastructure & Coverage - Context

**Gathered:** 2026-04-24
**Status:** Ready for planning

<domain>
## Phase Boundary

Build dialect-parameterized test infrastructure that exercises MSSQL, Databricks, and Generic code paths without live connections, and raise the coverage floor to prevent regression. Deliver: (1) a `dialect` pytest fixture parametrized over all three dialects with opt-out via marker, (2) a hybrid mocking strategy (in-memory SQLite for Inspector-driven generic tests, MagicMock + canned Row objects for SQL-execution and MSSQL/Databricks tests), (3) parameterization applied to shared-behavior tests in analysis + metadata modules (not Query/validation, not dialect-implementation tests), (4) coverage floor raised from 70% to 85% as a regression ratchet.

CI integration, histogram stats, and test fold-ins of existing dialect-specific files are out of scope.

</domain>

<decisions>
## Implementation Decisions

### Fixture Architecture
- **D-01:** A single pytest fixture `dialect` parametrized over `['mssql','databricks','generic']`. Tests that accept it run 3x; failures surface the dialect in the pytest node ID (e.g., `test_foo[mssql]`). Minimal boilerplate, clear failure attribution.
- **D-02:** Default behavior is all three dialects; tests narrow via a marker (e.g., `@pytest.mark.dialects('mssql')`) when a behavior genuinely only applies to one dialect. Matches the intent "shared behavior should work everywhere"; opt-out is rare and intentional.
- **D-03:** The fixture yields a bundle (DialectStrategy instance + matching mock/real Engine + Inspector + helper connection) so tests can request `dialect.engine`, `dialect.inspector`, etc. without per-test plumbing.

### Mocking Strategy
- **D-04:** Generic dialect uses a **hybrid backing**: real SQLAlchemy + in-memory SQLite when the test drives Inspector/metadata (get_columns, get_pk_constraint, get_unique_constraints); MagicMock + canned Row objects when the test asserts specific SQL execution results (Tier 2 aggregates, INFORMATION_SCHEMA responses). The Phase 10/12 Inspector + `isinstance(TypeEngine)` code paths get real SQLAlchemy behavior; SQL-parsing assertions stay deterministic.
- **D-05:** MSSQL and Databricks use MagicMock Engine + Inspector with pre-built Row-like objects for `connection.execute()` responses. Covers DESCRIBE EXTENDED, sys.indexes DMV, INFORMATION_SCHEMA.TABLE_CONSTRAINTS (ENFORCED='NO'), and other dialect-specific SQL surfaces.
- **D-06:** Canned Row objects are constructed inline per test or via small helpers — not stored as JSON/YAML fixture files. Keeps response shape next to the assertion that depends on it. If large response blocks start repeating, planner can introduce a fixture file at that point.
- **D-07:** SQLite backing for generic requires a sqlite-adapted variant of `tests/fixtures/test_db_schema.sql` (or a new minimal schema). Planner decides whether to adapt the existing SQL or write a Python-driven schema builder using SQLAlchemy Core.

### Parameterization Scope
- **D-08:** Parameterize shared-behavior tests in: `test_column_stats.py`, `test_pk_discovery.py`, `test_fk_candidates.py`, and the shared-behavior subset of `test_metadata.py` (list_schemas, list_tables, get_table_schema). These are the modules Phases 11–12 made dialect-aware.
- **D-09:** Do NOT parameterize `test_query.py` or validation tests. Query validation is already dialect-aware via sqlglot and existing parametrization; 3x runs would mostly re-cover the same code with no new signal.
- **D-10:** Keep existing dialect-specific test files (`test_mssql_dialect.py`, `test_databricks_dialect.py`, `test_generic_dialect.py`) as-is. They cover the dialect implementations themselves (protocol methods, quoting, capability flags, DESCRIBE EXTENDED parsing) — a distinct surface from shared-behavior tests. No fold-in.

### Coverage Enforcement
- **D-11:** Raise `[tool.coverage.report]` `fail_under` from 70 to 85. Ratchets current 89% quality without being fragile at the exact measured value. Protects against silent regression; leaves ~4 points of headroom for normal churn.
- **D-12:** No per-module coverage floors. Single global knob keeps `pyproject.toml` simple; dialect-module regressions will show up in the global number and in parametrized-test failures regardless.
- **D-13:** CI/GitHub Actions integration is deferred — out of scope for Phase 13. Local `pytest --cov` continues to enforce via `fail_under`. CI is its own future concern.

### Claude's Discretion
- **D-14:** Fixture file organization (new `tests/fixtures/dialects/` directory vs. extending `tests/conftest.py` vs. `tests/fixtures/dialect_fixtures.py`) — planner picks based on existing conftest patterns.
- **D-15:** Internal shape of the `dialect` fixture bundle (dataclass, namedtuple, dict, or a small `DialectTestContext` helper) — planner picks based on readability at call sites.
- **D-16:** How the SQLite-vs-MagicMock selection for the generic path is expressed (two fixtures, a marker, or a parameter) — planner picks the cleanest opt-in surface.
- **D-17:** Whether to migrate existing MSSQL-only tests in `test_column_stats.py` / `test_metadata.py` in-place to the parametrized fixture, or add parallel parametrized tests alongside and retire the old ones after verification — planner picks based on risk tolerance and diff noise.

</decisions>

<canonical_refs>
## Canonical References

**Downstream agents MUST read these before planning or implementing.**

### Requirements
- `.planning/REQUIREMENTS.md` — TEST-02 (dialect-parameterized fixtures), TEST-03 (70%+ coverage — superseded upward by D-11)

### Existing Code (modification targets)
- `tests/conftest.py` — Global fixtures (mock_engine, mock_connection, mock_inspector, sample_columns/indexes); new `dialect` fixture added here or alongside
- `tests/fixtures/test_db_schema.sql` — MSSQL DDL; reference for sqlite-adapted variant if needed
- `tests/unit/test_column_stats.py` — Parameterization target (analysis)
- `tests/unit/test_pk_discovery.py` — Parameterization target (analysis)
- `tests/unit/test_fk_candidates.py` — Parameterization target (analysis)
- `tests/unit/test_metadata.py` — Parameterization target (shared-behavior subset only)
- `tests/unit/test_mssql_dialect.py` — Preserved as-is (dialect-specific surface)
- `tests/unit/test_databricks_dialect.py` — Preserved as-is
- `tests/unit/test_generic_dialect.py` — Preserved as-is
- `pyproject.toml` — `[tool.coverage.report]` `fail_under` update (70 → 85); `[tool.pytest.ini_options]` marker registration (`dialects`)

### Dialect Code Under Test
- `src/db/dialects/protocol.py` — DialectStrategy protocol surface
- `src/db/dialects/mssql.py`, `src/db/dialects/databricks.py`, `src/db/dialects/generic.py` — Three dialect implementations exercised via parameterized fixture
- `src/analysis/column_stats.py`, `src/analysis/pk_discovery.py`, `src/analysis/fk_candidates.py` — Phase 12 adapted modules
- `src/db/metadata.py` — MetadataService with dialect branching

### Prior Phase Context
- `.planning/phases/10-genericdialect-tool-interface/10-CONTEXT.md` — GenericDialect, Inspector-only metadata (code under test in generic path)
- `.planning/phases/11-databricksdialect/11-CONTEXT.md` — DESCRIBE EXTENDED parsing, supports_indexes gating
- `.planning/phases/12-analysis-module-adaptation/12-CONTEXT.md` — Hybrid Tier 1/2/3 strategy, SQLAlchemy isinstance type classification

### Codebase Maps
- `.planning/codebase/ARCHITECTURE.md` — MCS pattern, layer responsibilities
- `.planning/codebase/CONVENTIONS.md` — Naming patterns, test style conventions
- `.planning/codebase/STRUCTURE.md` — Module layout

</canonical_refs>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/conftest.py` fixtures (`mock_engine`, `mock_connection`, `mock_inspector`, `sample_columns`, `sample_indexes`) — good base for the MSSQL/Databricks MagicMock variants of the new `dialect` fixture
- `tests/fixtures/test_db_schema.sql` — MSSQL DDL; needs sqlite adaptation for the generic+SQLite path, or a parallel sqlite schema
- Dialect registry (`src/db/dialects/registry.py`) — real instances of MssqlDialect/DatabricksDialect/GenericDialect the fixture can construct
- Existing parametrized tests in `test_query.py` (`test_valid_queries_pass`) — reference pattern for pytest parameterization in this codebase

### Established Patterns
- Single `conftest.py` at `tests/` root with a smaller one under `tests/integration/`
- MagicMock-based mocks for Engine/Inspector, no vcr/recorded-replay infrastructure
- `frozen` dataclasses for response models (keeps Row-mock shapes simple)
- `pytest.mark.integration` already registered — `dialects` is a parallel marker to register
- `pytest-cov` wired through `addopts` implicitly via test suite invocations; `fail_under` in `[tool.coverage.report]`

### Integration Points
- The `dialect` fixture will mostly replace ad-hoc `mock_inspector` plumbing in analysis tests
- Coverage floor change is a single-line `pyproject.toml` edit (70 → 85)
- Marker registration for `dialects` goes in `[tool.pytest.ini_options] markers`
- No changes to `src/` expected — this is test infrastructure only

</code_context>

<specifics>
## Specific Ideas

- **Failure attribution via node ID**: `test_foo[mssql]` / `test_foo[databricks]` / `test_foo[generic]` makes it obvious which dialect broke a shared-behavior test — the core ergonomic win from the parametrized-fixture approach.
- **Hybrid selection heuristic**: tests exercising `Inspector.get_columns/get_pk_constraint/get_unique_constraints` on the generic dialect → SQLite backing. Tests asserting specific SQL text or response-row parsing → MagicMock. Planner will formalize how this is expressed (marker, two fixtures, or a parameter).
- **Canned Rows stay inline**: no JSON/YAML fixture files up front. If a DESCRIBE EXTENDED response block gets reused across >2 tests, planner can extract then.
- **85% ratchet rationale**: current is 89%; 85% leaves ~4 points of headroom for normal churn but blocks the ~20-point silent regression that 70% currently permits.
- **TEST-03 wording vs. reality**: requirement says "70%+ maintained" — D-11 exceeds this. Note in planning that the effective floor is 85% going forward.

</specifics>

<deferred>
## Deferred Ideas

- **CI / GitHub Actions workflow** — running pytest+cov on PR. Valuable but scope-inflates this phase; belongs in a dedicated infrastructure phase.
- **Per-module coverage floors** (e.g., 90% on `src/db/dialects/*`) — adds pyproject complexity; revisit if global floor proves too coarse.
- **Fold existing `test_*_dialect.py` files into parametrized structure** — rejected for this phase; revisit only if duplication emerges.
- **Property-based / hypothesis tests for sqlglot transpilation coverage** — higher-signal for Tier 2 aggregate correctness but out of scope here.
- **vcrpy-style recorded-replay from real connections** — rejected as over-engineering; revisit only if hand-built Row mocks become a maintenance burden.
- **Pre-commit hook running pytest** — local-only, not real enforcement; defer with CI.

</deferred>

---

*Phase: 13-test-infrastructure-coverage*
*Context gathered: 2026-04-24*
