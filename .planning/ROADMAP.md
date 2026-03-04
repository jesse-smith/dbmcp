# Roadmap: TOON Response Format Migration

## Overview

Migrate all 9 dbmcp MCP tool responses from JSON to TOON format in an atomic swap (tools, tests, docstrings together to avoid mixed-format state), then add an automated staleness guard to prevent future docstring-schema drift. Two phases: one delivers the migration, the other locks in correctness going forward.

## Phases

**Phase Numbering:**
- Integer phases (1, 2, 3): Planned milestone work
- Decimal phases (2.1, 2.2): Urgent insertions (marked with INSERTED)

Decimal phases appear between their surrounding integers in numeric order.

- [ ] **Phase 1: Atomic TOON Migration** - Replace JSON serialization with TOON across all 9 tools, tests, and docstrings in a single coordinated swap
- [ ] **Phase 2: Staleness Guard** - Automated test that catches docstring-schema drift on every commit

## Phase Details

### Phase 1: Atomic TOON Migration
**Goal**: Every MCP tool returns TOON-encoded responses, all tests pass against TOON output, and all docstrings document the TOON format
**Depends on**: Nothing (first phase)
**Requirements**: SRLZ-01, SRLZ-02, SRLZ-03, SRLZ-04, TEST-01, TEST-02, TEST-03, DOCS-01
**Success Criteria** (what must be TRUE):
  1. All 9 MCP tools return TOON-encoded strings (no `json.dumps` calls remain in tool modules)
  2. A `parse_tool_response()` test helper abstracts deserialization, and no test file contains direct `json.loads` calls on tool responses
  3. Every tool's docstring shows TOON format examples (no JSON curly-brace examples remain in Returns sections)
  4. Non-primitive types (datetime, Decimal, Enum) are explicitly pre-serialized before encoding (no silent null coercion)
  5. All existing tests pass (zero regressions)
  6. New code (wrapper module, test helper, pre-serialization logic) has 90%+ test coverage
**Plans**: TBD

Plans:
- [ ] 01-01: TBD
- [ ] 01-02: TBD

### Phase 2: Staleness Guard
**Goal**: An automated test prevents docstring-schema drift, catching mismatches between tool response fields and their documented descriptions
**Depends on**: Phase 1
**Requirements**: DOCS-02
**Success Criteria** (what must be TRUE):
  1. A staleness test exists that fails when a tool's response schema changes without a corresponding docstring update
  2. The staleness test passes in the current codebase (baseline correctness after Phase 1 migration)
  3. CI runs the staleness test on every commit (no special invocation required -- it lives in the standard test suite)
  4. Staleness test module has 90%+ test coverage
**Plans**: TBD

Plans:
- [ ] 02-01: TBD

## Progress

**Execution Order:**
Phases execute in numeric order: 1 -> 2

| Phase | Plans Complete | Status | Completed |
|-------|----------------|--------|-----------|
| 1. Atomic TOON Migration | 0/? | Not started | - |
| 2. Staleness Guard | 0/? | Not started | - |
