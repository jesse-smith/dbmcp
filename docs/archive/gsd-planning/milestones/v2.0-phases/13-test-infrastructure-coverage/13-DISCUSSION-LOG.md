# Phase 13: Test Infrastructure & Coverage - Discussion Log

> **Audit trail only.** Do not use as input to planning, research, or execution agents.
> Decisions are captured in CONTEXT.md — this log preserves the alternatives considered.

**Date:** 2026-04-24
**Phase:** 13-test-infrastructure-coverage
**Areas discussed:** Fixture architecture, Mocking strategy, Parameterization scope, Coverage enforcement

---

## Fixture Architecture

### Q1: How should shared-behavior tests select which dialect they run against?

| Option | Description | Selected |
|--------|-------------|----------|
| Parametrized `dialect` fixture | Single fixture parametrized over ['mssql','databricks','generic'] yielding DialectStrategy + matching mock Engine/Inspector. Minimal boilerplate, clear attribution via node ID. | ✓ |
| Indirect parametrization per-test | Each test opts in via `@pytest.mark.parametrize('dialect', [...], indirect=True)`. More explicit, noisier. | |
| Parallel test classes per dialect | TestXMssql / TestXDatabricks / TestXGeneric with shared base. Max isolation, max duplication. | |

**User's choice:** Parametrized `dialect` fixture (Recommended)

### Q2: Default to all three dialects, or require explicit opt-in?

| Option | Description | Selected |
|--------|-------------|----------|
| Default all three, opt-out via marker | Fixture runs all 3 by default; dialect-narrow tests use `@pytest.mark.dialects('mssql')`. Matches "shared behavior should work everywhere". | ✓ |
| Opt-in via explicit list per test | Every test specifies `parametrize('dialect', [...])`. Safer but verbose; easy to forget. | |
| Three separate fixtures (mssql_dialect, ...) | Test author composes which to request. No automatic cross-dialect coverage. | |

**User's choice:** Default all three, opt-out via marker (Recommended)

---

## Mocking Strategy

### Q1: Backing for the `dialect='generic'` fixture variant

| Option | Description | Selected |
|--------|-------------|----------|
| Hybrid: SQLite for Inspector, MagicMock for SQL execution | Real SQLAlchemy + SQLite when tests drive Inspector/metadata; MagicMock when tests assert specific SQL responses. Two backings, smart selection. | ✓ |
| In-memory SQLite for everything generic | Single backing; leaves Tier 2 aggregate SQL untestable (DATEDIFF/LEN/STDDEV semantics differ). | |
| Pure MagicMock Engine + Inspector | All generic paths mocked. Shallow — doesn't exercise real Inspector + type objects. | |

**User's choice:** Hybrid (Recommended)
**Notes:** User asked for clarification on the hybrid option before answering. Rationale captured: the D-07 refactor in Phase 12 depends on `isinstance(TypeEngine)` checks — SQLite gives real type objects, while MagicMock would require hand-rolled type stubs that drift from SQLAlchemy.

### Q2: Mocking for Databricks and MSSQL (no in-memory option)

| Option | Description | Selected |
|--------|-------------|----------|
| MagicMock Engine + Inspector, canned Row objects | Pre-built Row-like objects for execute() responses. Conventional pytest-mock pattern. | ✓ |
| Fixture files (JSON/YAML) of canned DB responses | Store responses in `tests/fixtures/*.json`. Cleaner for large shapes, adds indirection. | |
| Recorded-replay (vcrpy-style) | Capture real responses, replay. Highest fidelity, heavy infrastructure. | |

**User's choice:** MagicMock Engine + Inspector, canned Row objects (Recommended)

---

## Parameterization Scope

### Q1: Which existing tests become dialect-parameterized?

| Option | Description | Selected |
|--------|-------------|----------|
| Analysis + Metadata shared-behavior tests | column_stats, pk_discovery, fk_candidates, and shared-behavior subset of metadata. Skip Query/validation. | ✓ |
| Everything dialect-touching (incl. Query/validation) | Broader but 3x runs with no new signal for some tests. | |
| Only analysis tools (narrowest) | Matches TEST-02 literally but leaves MetadataService under-covered across dialects. | |

**User's choice:** Analysis + Metadata shared-behavior tests (Recommended)

### Q2: Fate of existing dialect-specific test files

| Option | Description | Selected |
|--------|-------------|----------|
| Keep as-is — they test dialect-specific surface | Protocol methods, quoting, capability flags, DESCRIBE EXTENDED parsing. No overlap with parametrized tests. | ✓ |
| Fold MSSQL-specific assertions into parametrized tests with markers | Single source of truth per module. More work, more churn. | |
| Leave alone and revisit later | Defer decision to execution. | |

**User's choice:** Keep as-is (Recommended)

---

## Coverage Enforcement

### Q1: fail_under change

| Option | Description | Selected |
|--------|-------------|----------|
| Raise fail_under to 85% | Ratchet on current 89% with ~4 points headroom for normal churn. Single knob. | ✓ |
| Leave fail_under=70 | Matches TEST-03 literal wording; allows silent 20-point regression. | |
| Raise to 85% + per-module floors for dialect modules | Fine-grained but pyproject.toml complexity. | |

**User's choice:** Raise fail_under to 85% (Recommended)

### Q2: CI gate

| Option | Description | Selected |
|--------|-------------|----------|
| Defer CI — out of scope | `fail_under` blocks locally; CI is its own phase. | ✓ |
| Add GitHub Actions workflow (pytest+cov on PR) | Closes enforcement loop; inflates phase scope. | |
| Pre-commit hook only | Local-only, not real enforcement. | |

**User's choice:** Defer CI — out of scope for this phase (Recommended)

---

## Claude's Discretion

- Fixture file organization (conftest vs dedicated module vs subdirectory)
- Internal shape of the `dialect` fixture bundle (dataclass vs namedtuple vs dict vs helper class)
- How SQLite-vs-MagicMock selection is expressed on the generic path (marker vs two fixtures vs parameter)
- Whether to migrate existing MSSQL-only tests in-place or add parametrized tests alongside

## Deferred Ideas

- CI / GitHub Actions workflow
- Per-module coverage floors
- Fold existing `test_*_dialect.py` into parametrized structure
- Property-based / hypothesis tests for sqlglot transpilation
- vcrpy-style recorded-replay
- Pre-commit hook
