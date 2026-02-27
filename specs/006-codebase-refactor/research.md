# Research: Codebase Refactor

**Feature**: 006-codebase-refactor
**Date**: 2026-02-27

## Decision 1: Module Decomposition Strategy

**Decision**: Decompose by logical responsibility grouping within each module, not by extracting a cross-cutting abstraction layer.

**Rationale**: Each large module has 3-4 clear internal groupings (e.g., query.py has validation, sampling, execution, formatting). Extracting along these seams preserves existing coupling patterns and minimizes import churn. A cross-cutting approach (e.g., a shared SQLBuilder) would create new coupling between modules that are currently independent.

**Alternatives considered**:
- Cross-cutting abstractions (shared SQLBuilder, ErrorSerializer): Rejected — creates new coupling, violates YAGNI for a small project
- Flat module split (one function per file): Rejected — too granular, increases navigation overhead
- Leave as-is with internal refactoring only: Rejected — modules exceed constitution's 400-line limit

## Decision 2: server.py Decomposition Approach

**Decision**: Extract tool definitions into logical grouping modules (schema tools, query tools, etc.) with a thin server.py that registers them. Hidden tools stay in their respective group modules with commented decorators.

**Rationale**: server.py's 1,140 lines are ~70% boilerplate (error handling, JSON serialization, validation). Grouping tools by domain (schema, query, documentation) aligns with existing service boundaries. Hidden tools naturally belong with their active counterparts (e.g., `infer_relationships` groups with schema tools).

**Alternatives considered**:
- Single tools.py extraction: Rejected — still too large
- One file per tool: Rejected — 11 files is excessive for this project size
- Shared error-handling decorator: Considered as complement, but adds abstraction — defer unless boilerplate reduction is clearly >50%

## Decision 3: Test Consolidation Strategy

**Decision**: Use `pytest.mark.parametrize` to consolidate tests that verify the same behavior with different inputs. Centralize duplicated fixtures to conftest.py or category-specific conftest files.

**Rationale**: test_query.py has ~25 denial-category tests that are structurally identical (validate → assert not safe → check category). Parametrize preserves behavioral coverage while reducing ~115 tests to ~60-70. Integration fixtures (sample_schemas, mock_engine) are defined 3-4 times across files.

**Alternatives considered**:
- Leave tests as-is, only fix fixtures: Rejected — test_query.py density obscures what's actually tested
- Aggressive consolidation (merge test classes): Rejected — some classes represent meaningfully different test categories
- Subtests instead of parametrize: Rejected — parametrize is idiomatic pytest and provides better failure reporting

## Decision 4: Dataclass Handling

**Decision**: No consolidation needed. Standardize field naming (`is_pk` vs `is_primary_key`) and document lifecycle distinction between `ColumnInfo` (ephemeral) and `Column` (persistent).

**Rationale**: 19 dataclasses across the project serve distinct purposes with minimal overlap. The only redundancy is `ColumnInfo` (relationships.py) vs `Column` (schema.py), but they serve different lifecycle stages and merging them would add unnecessary fields to each use case.

**Alternatives considered**:
- Merge ColumnInfo into Column: Rejected — Column has 16 fields, ColumnInfo needs only 7
- Create shared base class: Rejected — only 4 overlapping fields, composition over inheritance per constitution

## Decision 5: Code-Simplifier Agent Usage

**Decision**: Use the code-simplifier agent for targeted refactors of individual modules after structural decomposition is complete. Best suited for: simplifying God methods, reducing conditional nesting, and cleaning up boilerplate within already-split modules.

**Rationale**: The code-simplifier agent excels at focused, file-level simplification. Structural changes (splitting modules, moving classes) require cross-file coordination better handled manually. The ideal workflow is: manually split → code-simplifier cleans each piece.

**Alternatives considered**:
- Code-simplifier for everything: Rejected — structural splits need cross-file awareness
- No code-simplifier: Rejected — it's well-suited for the "simplify within module" portion of the work
