# Implementation Plan: Codebase Refactor

**Branch**: `006-codebase-refactor` | **Date**: 2026-02-27 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/006-codebase-refactor/spec.md`

## Summary

Simplify and restructure the dbmcp codebase (~7,100 source lines, ~8,900 test lines) to improve readability, reduce module sizes, and consolidate duplicate tests — without changing any public behavior. Decompose 5 oversized modules by extracting logical responsibility groupings, parametrize duplicate tests, and centralize shared fixtures. Use the code-simplifier agent for targeted within-module simplification after structural splits.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: mcp[cli], sqlalchemy, pyodbc, sqlglot, azure-identity (all existing, no changes)
**Storage**: N/A (no data model changes)
**Testing**: pytest with pytest-asyncio, pytest-cov (existing)
**Target Platform**: MCP server (cross-platform)
**Project Type**: MCP server tool
**Performance Goals**: No regression from baseline; existing performance tests must pass
**Constraints**: Source lines must not increase; aspirational 10% reduction
**Scale/Scope**: ~7,100 src lines → ≤7,100; ~115 query tests → ~60-70 via parametrize

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First (YAGNI) | PASS | Refactor removes complexity, adds no new features |
| II. DRY | PASS | Test consolidation and fixture centralization directly serve DRY |
| III. Test-First | PASS | Existing tests preserved; refactoring commits are behavior-preserving |
| IV. Robustness | PASS | No error handling changes; existing patterns preserved |
| V. Performance by Design | PASS | No performance changes; existing benchmarks must pass |
| VI. Code Quality Through Clarity | PASS | Primary goal of this feature |
| VII. Minimal Dependencies | PASS | No new dependencies |

**Quality Gates**:

| Gate | Status | Notes |
|------|--------|-------|
| Max file length: 400 lines | VIOLATION | 5 modules exceed this today; refactor aims to bring all ≤400 lines (aligned with constitution) |
| Max function length: 50 lines | VIOLATION | Multiple God methods (130-191 lines); decomposition planned |
| Max cyclomatic complexity: 10 | CHECK | God methods likely exceed this; decomposition will address |
| Max cognitive complexity: 15 | VIOLATION | 5 active functions exceed 15 (complexipy); bonus phase added |

## Project Structure

### Documentation (this feature)

```text
specs/006-codebase-refactor/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── quickstart.md        # Phase 1 output
└── tasks.md             # Phase 2 output (/speckit.tasks)
```

### Source Code — Current → Target

```text
src/
├── mcp_server/
│   ├── server.py (1,140 → ~200)    # Thin: init + tool registration
│   ├── schema_tools.py (new, ~200)  # list_schemas, list_tables, get_table_schema, infer_relationships*
│   ├── query_tools.py (new, ~200)   # get_sample_data, execute_query, analyze_column*
│   └── doc_tools.py (new, ~200)     # export_documentation*, load_cached_docs*, check_drift*
├── db/
│   ├── connection.py (342, minimal change)
│   ├── metadata.py (708, simplify God methods)
│   ├── query.py (908 → ~300)        # QueryService: execution + sampling only
│   ├── validation.py (new, ~250)    # validate_query + helpers (extracted from query.py)
│   └── azure_auth.py (87, no change)
├── inference/
│   ├── columns.py (1,144 → ~350)   # ColumnAnalyzer: orchestration + public API
│   ├── column_stats.py (new, ~250)  # Database stats collection (extracted from columns.py)
│   ├── column_patterns.py (new, ~250) # Purpose pattern matching (extracted from columns.py)
│   ├── relationships.py (566 → ~300) # ForeignKeyInferencer: orchestration
│   ├── scoring.py (new, ~150)       # Confidence scoring (extracted from relationships.py)
│   └── value_overlap.py (421, simplify within)
├── cache/
│   ├── storage.py (766 → ~300)      # CacheManager: orchestration + metadata
│   ├── doc_generator.py (new, ~250) # Markdown generation (extracted from storage.py)
│   └── drift.py (223, no change)
├── models/
│   ├── schema.py (304, naming audit only)
│   └── relationship.py (146, no change)
├── metrics.py (258, no change)
└── logging_config.py (97, no change)

# * = hidden tool (commented decorator)

tests/
├── unit/
│   ├── test_query.py (1,178 → ~700) # Parametrize duplicates
│   ├── test_validation.py (new)      # Tests for extracted validation module
│   ├── test_connection.py (662, minimal)
│   ├── test_metadata.py (435, minimal)
│   ├── test_columns.py (326, update imports)
│   ├── test_relationships.py (update imports)
│   ├── test_value_overlap.py (455, minimal)
│   └── test_azure_auth.py (no change)
├── integration/
│   ├── conftest.py (new, centralized fixtures)
│   └── ... (existing files, remove local fixture dups)
├── performance/ (no change)
├── compliance/ (no change)
└── conftest.py (325, add shared integration fixtures)
```

**Structure Decision**: Single project, existing layout preserved. New files are extractions from existing modules, not new abstractions. Each extraction follows the seam identified in research: logical responsibility groupings within each oversized module.

## Complexity Tracking

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| 5 new source files | Decomposing modules that exceed 400-line constitution limit | Keeping monolithic files violates constitution; new files are pure extractions, not new abstractions |
| Some modules may slightly exceed 400 lines | Constitution limit is 400; spec now aligned | Forcing below 400 in all cases would create excessive fragmentation for a small project; slight exceptions require documented justification per constitution |
| Commented-out `@mcp.tool()` decorators retained | 5 hidden tools use commented decorators as an enablement mechanism (uncomment to activate) | This is not dead code per Constitution I — it is a deliberate toggle for planned tools. Deleting them would require reimplementation when tools are activated. |
| Test-first waived for refactoring tasks | Existing 368+ tests serve as the regression suite; no new behavior is introduced | Constitution III (test-first) is satisfied by the Refactoring Discipline section: "Refactoring MUST maintain or improve test coverage." Behavior-preserving splits are verified by running existing tests after each change. |

## Implementation Phases

### Phase 1: Source Module Decomposition (P1)

Decompose the 5 oversized source modules. Each module split is an independent unit of work. Use the code-simplifier agent after each structural split to clean up the resulting files.

**Order**: query.py → server.py → columns.py → relationships.py → storage.py

Rationale for ordering:
- query.py first: cleanest separation (validation is already module-level functions), establishes the pattern
- server.py second: depends on understanding where service code lives post-split
- columns.py third: largest module, benefits from pattern established by prior splits
- relationships.py fourth: similar pattern to columns.py
- storage.py last: similar generation/parsing split

**For each module**:
1. Create new file(s) with extracted code
2. Update imports in all consumers
3. Run tests to verify no regressions
4. Use code-simplifier agent to clean up both the original and extracted files
5. Run tests again post-simplification

### Phase 2: Test Refactoring (P2)

**Step 1**: Record coverage baseline (`uv run pytest --cov=src --cov-report=term-missing`)

**Step 2**: Parametrize test_query.py duplicates:
- Denial category tests (~25 → 4 parametrized)
- Query type parsing tests (5 → 2 parametrized)
- CTE tests (13 → 3 parametrized)
- Row limit injection tests (6 → 2 parametrized)

**Step 3**: Create test_validation.py for the extracted validation module (move relevant tests from test_query.py)

**Step 4**: Centralize integration fixtures:
- Move `sample_schemas`, `sample_tables`, `sample_columns` duplicates to tests/integration/conftest.py
- Remove `mock_engine` redefinitions (4 sites → 1 in tests/conftest.py)
- Ensure fixture variants support parameterization

**Step 5**: Verify coverage is maintained or improved

### Phase 3: Verification & Cleanup (P3)

1. Run full test suite: `uv run pytest tests/`
2. Run linter: `uv run ruff check src/ tests/`
3. Verify no circular imports: `uv run python -c "import src.mcp_server.server"`
4. Test each hidden tool re-enablement (uncomment decorator → import check → re-comment)
5. Compare final metrics against baseline (line counts, test counts, coverage)
6. Standardize `ColumnInfo.is_pk` → `is_primary_key` naming
7. **Manual integration testing (collaborative)**: Restart the MCP server and jointly verify all 6 active tools work end-to-end against a live database. This step requires user participation since the MCP server must be restarted.

## Agent Usage Strategy

The **code-simplifier agent** should be used for:
- Simplifying God methods after structural extraction (e.g., cleaning up `infer_relationships` after scoring logic is extracted)
- Reducing conditional nesting within individual files
- Cleaning up boilerplate patterns within tool definition files
- Simplifying complex regex or SQL generation patterns

### Phase 4: Cognitive Complexity Reduction (Bonus)

Post-verification analysis with complexipy identified 5 active functions exceeding the cognitive complexity threshold of 15. These are behavior-preserving simplifications targeting deep nesting, long conditional chains, and interleaved concerns within individual functions. No new files or abstractions — just clearer control flow within existing functions.

| Score | Function | File | Strategy |
|-------|----------|------|----------|
| 43 | `execute_query` | query.py | Extract SELECT result processing and total-row-count logic into helpers |
| 42 | `_list_tables_generic` | metadata.py | Extract table collection and view collection into helpers to reduce nesting |
| 22 | `connect` | connection.py | Extract engine creation into helper to separate auth-method branching from connection lifecycle |
| 19 | `list_tables` | schema_tools.py | Extract validation and response building into helpers |
| 16 | `inject_row_limit` | query.py | Flatten conditional branches with early returns |

The code-simplifier should NOT be used for:
- Cross-file structural splits (manual coordination needed)
- Import path updates (requires whole-project awareness)
- Test parametrization (requires understanding of test semantics)
