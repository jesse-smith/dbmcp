<!--
================================================================================
SYNC IMPACT REPORT
================================================================================
Version change: N/A (initial) → 1.0.0
Modified principles: N/A (initial creation)
Added sections:
  - Core Principles (7 principles)
  - Quality Gates section
  - Development Workflow section
  - Governance section
Removed sections: None
Templates requiring updates:
  - .specify/templates/plan-template.md ✅ (Constitution Check section already present)
  - .specify/templates/spec-template.md ✅ (Success Criteria aligns with measurability principle)
  - .specify/templates/tasks-template.md ✅ (Test-first pattern aligned with Principle III)
  - .specify/templates/checklist-template.md ✅ (Compatible)
  - .specify/templates/agent-file-template.md ✅ (Compatible)
Follow-up TODOs: None
================================================================================
-->

# DBMCP Constitution

## Core Principles

### I. Simplicity First (YAGNI)

Every feature, abstraction, and line of code MUST justify its existence against immediate,
concrete requirements. Speculative features are prohibited.

**Non-negotiables:**
- MUST NOT add code "for future use" or "just in case"
- MUST NOT create abstractions until at least two concrete use cases exist
- MUST prefer inline code over premature extraction
- MUST delete unused code immediately—no commented-out blocks, no `// TODO: remove later`
- MUST choose the simplest solution that meets current requirements

**Rationale:** Unused code is a maintenance burden. Future requirements are unpredictable.
Code written for imagined needs often requires rewriting when real needs emerge.

### II. Don't Repeat Yourself (DRY)

Duplication of logic, configuration, or domain knowledge MUST be eliminated through
appropriate abstraction, but only when duplication is proven (rule of three).

**Non-negotiables:**
- MUST extract shared logic after the third occurrence (not before)
- MUST use single source of truth for configuration values
- MUST NOT duplicate business rules across layers (e.g., validation in both client and server
  without shared definition)
- MUST prefer composition over inheritance for code reuse
- MUST keep related code co-located; distant duplication is harder to detect than nearby

**Rationale:** Duplication leads to inconsistency when one copy is updated but others are not.
However, premature abstraction creates coupling worse than duplication—wait for patterns
to emerge.

### III. Test-First Development

Tests MUST be written before implementation code. Tests define the contract; implementation
fulfills it.

**Non-negotiables:**
- MUST write failing tests before writing implementation (Red-Green-Refactor)
- MUST NOT mark a feature complete until all tests pass
- Tests MUST be deterministic—no flaky tests allowed in main branch
- Tests MUST run fast; slow tests indicate design problems
- Test names MUST describe behavior, not implementation (`user_can_login` not `test_login_function`)
- MUST maintain test isolation—no shared mutable state between tests

**Rationale:** Tests written after implementation tend to test what was built rather than what
was needed. Test-first forces clear thinking about requirements and produces naturally
testable designs.

### IV. Robustness Through Explicit Error Handling

All error conditions MUST be handled explicitly at system boundaries. Internal code MAY
propagate errors; boundary code MUST catch and handle them.

**Non-negotiables:**
- MUST validate all external input (user input, API responses, file contents)
- MUST NOT swallow errors silently—log, return, or re-raise with context
- MUST define and document all possible error states for public interfaces
- MUST use typed errors or error codes, not magic strings
- MUST fail fast on programmer errors (assertions); recover gracefully from user errors
- MUST NOT use exceptions for control flow

**Rationale:** Silent failures cause data corruption and debugging nightmares. Explicit error
handling at boundaries creates a "correctness perimeter" while keeping internal code clean.

### V. Performance by Design

Performance characteristics MUST be considered during design, not retrofitted. Measure
before optimizing, but design to avoid known pitfalls.

**Non-negotiables:**
- MUST define performance requirements before implementation (response time, throughput,
  memory limits)
- MUST NOT use O(n²) or worse algorithms on unbounded data without explicit justification
- MUST NOT perform I/O inside loops when batch operations are available
- MUST profile before optimizing—gut feelings about performance are often wrong
- MUST cache deliberately with explicit invalidation strategy, not hopefully
- MUST prefer streaming over loading entire datasets into memory for large data

**Rationale:** Performance problems are architectural; they cannot be fixed with micro-
optimizations. Designing for performance constraints upfront avoids costly rewrites.

### VI. Code Quality Through Clarity

Code MUST be written for human readers first, compilers second. Self-documenting code
is preferred over comments explaining obscure code.

**Non-negotiables:**
- MUST use descriptive names—abbreviations only for universally understood terms (URL, HTTP, ID)
- MUST keep functions focused—one clear purpose, ideally under 30 lines
- MUST limit function parameters (≤4 preferred; use objects for more)
- MUST NOT nest conditionals beyond 2-3 levels; extract or refactor
- MUST NOT add comments that restate what code does; add comments only for WHY
- MUST format consistently—automated formatting tools are mandatory

**Rationale:** Code is read 10x more than it is written. Clear code reduces bugs, speeds
onboarding, and makes refactoring safer.

### VII. Minimal Dependencies

External dependencies MUST be evaluated for necessity, maintenance status, and security
posture before adoption.

**Non-negotiables:**
- MUST NOT add a dependency for functionality achievable in <50 lines of code
- MUST prefer well-maintained dependencies with active security response
- MUST pin dependency versions and audit updates before upgrading
- MUST NOT expose dependency types in public interfaces (wrap external types)
- MUST have a fallback plan for critical dependencies (can we fork? replace?)
- MUST periodically audit and remove unused dependencies

**Rationale:** Every dependency is a liability—security vulnerabilities, breaking changes,
abandoned projects. The cost of dependencies compounds over project lifetime.

## Quality Gates

**GATE: All code changes MUST pass before merge:**

| Gate | Requirement |
|------|-------------|
| Tests | All tests pass, no skipped tests without documented reason |
| Coverage | New code covered by tests; no reduction in overall coverage |
| Lint | Zero warnings from configured linters |
| Types | Full type coverage where language supports it |
| Build | Clean build with no warnings treated as errors |
| Review | At least one approval from code owner |

**Complexity Budget:**
- Maximum cyclomatic complexity per function: 10
- Maximum file length: 400 lines (excluding tests)
- Maximum function length: 50 lines
- Maximum parameters per function: 5

Violations require documented justification in code review.

## Development Workflow

**Branch Strategy:**
- `main` is always deployable
- Feature branches branch from and merge to `main`
- No direct commits to `main`

**Commit Standards:**
- Atomic commits—one logical change per commit
- Commit messages follow conventional format: `type(scope): description`
- All commits must pass CI before push (pre-commit hooks)

**Code Review Requirements:**
- All changes require review before merge
- Reviewers MUST verify constitution compliance
- Reviews focus on: correctness, clarity, constitution adherence
- "LGTM" without substantive review is prohibited

**Refactoring Discipline:**
- Refactoring commits MUST be separate from feature commits
- No behavior changes in refactoring commits
- Refactoring MUST maintain or improve test coverage

## Governance

This constitution is the authoritative source for development standards. Conflicts between
this document and other guidelines resolve in favor of this constitution.

**Amendment Process:**
1. Propose change via pull request to constitution file
2. Provide rationale and impact assessment
3. Require approval from project lead(s)
4. Update version following semantic versioning:
   - MAJOR: Principle removal or fundamental redefinition
   - MINOR: New principle or significant guidance expansion
   - PATCH: Clarification, typo fix, non-semantic refinement
5. All dependent templates must be reviewed for consistency

**Compliance:**
- All pull requests MUST include constitution compliance verification
- Violations require explicit justification and approval
- Repeated unjustified violations trigger process review

**Version**: 1.0.0 | **Ratified**: 2026-01-17 | **Last Amended**: 2026-01-17
