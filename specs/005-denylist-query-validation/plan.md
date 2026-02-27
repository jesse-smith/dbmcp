# Implementation Plan: Denylist Query Validation

**Branch**: `005-denylist-query-validation` | **Date**: 2026-02-26 | **Spec**: [spec.md](spec.md)
**Input**: Feature specification from `/specs/005-denylist-query-validation/spec.md`

## Summary

Replace the current keyword-based query blocklist (`BLOCKED_KEYWORDS` frozenset + regex tokenization) with an AST-based denylist using `sqlglot`. This eliminates false positives on legitimate queries, enables categorized denial reasons, and allows execution of 22 known-safe SQL Server system stored procedures. The validation becomes a single-pass AST walk instead of the current two-layer keyword + query-type check.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: sqlglot (new), SQLAlchemy >=2.0.0 (existing), pyodbc >=5.0.0 (existing), mcp[cli] >=1.0.0 (existing)
**Storage**: N/A (in-memory query validation only)
**Testing**: pytest (existing)
**Target Platform**: Cross-platform (MCP server)
**Project Type**: Library (MCP tool server)
**Performance Goals**: Single-query validation in <10ms (sqlglot parses in microseconds)
**Constraints**: Pure Python dependencies preferred; no native build toolchain required
**Scale/Scope**: Single queries validated on submission; no batch processing pipeline

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First | PASS | Replacing two-layer validation with single-pass AST walk is simpler. sqlglot dependency justified: the alternative (regex keyword matching) is the current brittle approach we're replacing. |
| II. DRY | PASS | Single validation function replaces three separate functions (`_is_blocked_keyword`, `parse_query_type`, `is_query_allowed`). Safe procedure list defined once as a frozenset. |
| III. Test-First | PASS | Will follow red-green-refactor. Validation is a pure function — highly testable. |
| IV. Explicit Error Handling | PASS | Categorized `DenialReason` with typed `DenialCategory` enum replaces generic error strings. Parse failures caught explicitly. |
| V. Performance by Design | PASS | sqlglot parses single queries in microseconds. No I/O in validation path. |
| VI. Code Quality | PASS | `isinstance()` checks on typed AST nodes are clearer than regex tokenization. Descriptive enum values for denial categories. |
| VII. Minimal Dependencies | PASS | sqlglot is pure Python, zero transitive dependencies, actively maintained (~8k stars). Achieves what would require 500+ lines of fragile regex code. Well above the 50-line threshold. |

**Post-Phase 1 re-check**: All gates still pass. The data model adds three small types (enum + two dataclasses). No unnecessary abstractions.

## Project Structure

### Documentation (this feature)

```text
specs/005-denylist-query-validation/
├── spec.md
├── plan.md
├── research.md
├── data-model.md
├── quickstart.md
├── contracts/
│   └── validation.md
├── checklists/
│   └── requirements.md
└── tasks.md              # Phase 2 output (/speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── db/
│   └── query.py           # Replace validation logic, add validate_query()
├── models/
│   └── schema.py          # Add DenialCategory, DenialReason, ValidationResult; extend Query
└── mcp_server/
    └── server.py           # No changes needed (calls execute_query unchanged)

tests/
└── unit/
    └── test_query.py       # Replace keyword/type tests with AST validation tests
```

**Structure Decision**: Existing single-project layout. Changes confined to `query.py` (validation logic), `schema.py` (new types), and `test_query.py` (tests). No new files or directories in source tree.

## Complexity Tracking

No constitution violations to justify.
