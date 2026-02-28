# Feature Specification: Codebase Refactor

**Feature Branch**: `006-codebase-refactor`
**Created**: 2026-02-27
**Status**: Draft
**Input**: User description: "Refactor: Simplify and optimize the dbmcp codebase"

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Developer Navigates and Modifies Source Code (Priority: P1)

A developer on the team needs to understand and modify any module in the codebase. Today, several modules exceed 500 lines with classes containing 18-26 methods, making it difficult to locate specific logic and understand control flow. After refactoring, each module should have a clear, focused responsibility and no single class should be so large that a developer needs to scroll extensively to understand its purpose.

**Why this priority**: Code readability and navigability directly determine how quickly the team can respond to bugs, add features, and onboard contributors. This is the core value of the refactor.

**Independent Test**: Can be verified by confirming that all modules remain under a target size, classes have focused responsibilities, and all existing tests pass without modification to public interfaces.

**Acceptance Scenarios**:

1. **Given** a developer opens any source module, **When** they review the file, **Then** it has a single clear responsibility and no class exceeds a manageable number of methods (guideline: ~10-12 per class)
2. **Given** a developer wants to find where query validation logic lives, **When** they look at the module structure, **Then** validation and execution are in separate, clearly-named modules
3. **Given** a developer opens server.py, **When** they review it, **Then** the MCP tool definitions are separated from server initialization and orchestration logic

---

### User Story 2 - Developer Runs and Maintains the Test Suite (Priority: P2)

A developer runs the test suite to verify changes. Today, the test suite has 368 tests across ~8,900 lines, with some duplication in query tests (115 tests in one file) and repeated fixture definitions across integration test files. After refactoring, tests should be concise, non-duplicative, and well-organized with shared fixtures centralized.

**Why this priority**: A lean, well-organized test suite catches regressions faster and is cheaper to maintain. Duplicate tests slow CI and obscure which behavior is actually being verified.

**Independent Test**: Can be verified by running the full test suite, confirming all tests pass, coverage is maintained or improved, and no two tests verify identical behavior.

**Acceptance Scenarios**:

1. **Given** a developer runs the full test suite, **When** tests complete, **Then** all tests pass and coverage is at or above the pre-refactor baseline
2. **Given** a developer reviews test_query.py, **When** they look for duplicate coverage, **Then** tests that previously verified the same behavior have been consolidated
3. **Given** a developer writes a new integration test, **When** they need database fixtures, **Then** shared fixtures are available from a centralized location rather than redefined per-file

---

### User Story 3 - Developer Re-enables Hidden Tools (Priority: P3)

A developer decides to re-enable one of the 5 currently hidden MCP tools (infer_relationships, analyze_column, export_documentation, load_cached_docs, check_drift). After refactoring, uncommenting the tool decorator should be sufficient to restore full functionality — no additional code changes should be required.

**Why this priority**: The hidden tools represent planned future functionality. The refactor must not break these code paths, even though they are currently inactive.

**Independent Test**: Can be verified by uncommenting each hidden tool's decorator individually and confirming the server starts and the tool functions correctly.

**Acceptance Scenarios**:

1. **Given** a hidden tool has its `@mcp.tool()` decorator uncommented, **When** the server starts, **Then** the tool is registered and callable
2. **Given** a hidden tool is re-enabled, **When** its associated tests are run, **Then** all tests pass without modification

---

### Edge Cases

- What happens when a module is decomposed but an external consumer imports from the original path? All existing import paths must continue to work or be updated consistently across the codebase.
- What happens when test consolidation removes a test that was the only coverage for an edge case? Coverage must be verified before and after to ensure no regression.
- What happens when shared fixtures are centralized but an integration test needs a fixture variant? The centralized fixture design must support parameterization or extension.
- What happens when a refactored module is imported by a hidden tool's code path? The hidden tool must still function correctly post-refactor.

## Clarifications

### Session 2026-02-27

- Q: When simplification and maintainability conflict, which priority wins? → A: Maintainability wins, but only accept very modest structural overhead (extra files, imports, wrappers).
- Q: Is the 10% source line reduction target a hard gate or aspirational? → A: Aspirational — aim for 10% but the hard gate is that total source lines must not increase. Accept less reduction if all other success criteria are met.

## Requirements *(mandatory)*

### Functional Requirements

- **FR-001**: All 6 active MCP tools MUST retain identical public interfaces and behavior after refactoring
- **FR-002**: All 5 hidden MCP tools MUST remain re-enableable by uncommenting their decorators with no additional code changes
- **FR-003**: Large classes (currently exceeding ~15 methods) MUST be decomposed into smaller, focused classes or modules
- **FR-004**: Query validation and query execution logic MUST be separated into distinct modules
- **FR-005**: MCP tool definitions in server.py MUST be separated from server initialization and orchestration logic
- **FR-006**: Dataclass models MUST be audited and any redundant or unused models removed
- **FR-007**: Duplicate unit tests (tests verifying identical behavior) MUST be consolidated
- **FR-008**: Integration test fixtures that are duplicated across files MUST be centralized
- **FR-009**: Test coverage MUST be maintained at or above the pre-refactor baseline
- **FR-010**: All existing import paths used by active code MUST continue to work, or all references MUST be updated consistently
- **FR-011**: Runtime complexity MUST not increase — refactoring should simplify or maintain existing complexity
- **FR-012**: When simplification and maintainability conflict, maintainability MUST be preferred — but only when the added structural overhead is very modest (e.g., one extra file or a thin delegation layer, not deep abstraction hierarchies)
- **FR-013**: Functions in active code paths with cognitive complexity >15 (as measured by complexipy) SHOULD be simplified to reduce nesting and branching

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Total source lines (src/) MUST NOT increase from the ~7,100 line baseline; aspirational target is a 10% reduction
- **SC-002**: No source module exceeds 400 lines (current largest: 1,144 lines; aligns with constitution complexity budget)
- **SC-003**: No single class contains more than 15 public methods (current largest: 26 methods)
- **SC-004**: Total test count reduced through consolidation while maintaining or improving code coverage percentage
- **SC-005**: All 368+ test scenarios' behavioral coverage preserved (no untested behavior lost)
- **SC-006**: Full test suite passes with zero failures and zero new warnings
- **SC-007**: Each of the 5 hidden tools can be re-enabled by uncommenting its decorator and passes its associated tests
- **SC-008**: No circular import dependencies introduced by module decomposition

## Assumptions

- "Hidden tools" refers to the 5 tools with commented-out `@mcp.tool()` decorators in server.py: infer_relationships, analyze_column, export_documentation, load_cached_docs, check_drift
- The pre-existing ruff warning in src/metrics.py (Generator import) is out of scope for this refactor unless it falls naturally into a module being refactored
- Performance benchmarks in tests/performance/ should continue to pass but are not a primary target for refactoring
- The 400-line and 15-method limits are guidelines, not hard rules — slight exceptions are acceptable if decomposition would harm clarity
- Import path stability applies only within this project, not to external consumers (this is an MCP server, not a library)
