# Implementation Plan: Database Schema Explorer MCP Server

**Branch**: `001-db-schema-explorer` | **Date**: 2026-01-19 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/001-db-schema-explorer/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build an MCP server for efficient database exploration that enables AI agents to understand database structure, infer relationships in legacy databases with missing foreign keys, and generate reusable documentation to avoid token-heavy repeated discovery. Core focus on SQL Server with token-efficient responses and caching.

## Technical Context

**Language/Version**: Python 3.11+
**Primary Dependencies**: FastMCP (MCP SDK), pyodbc (SQL Server driver), SQLAlchemy (connection pooling + metadata introspection)
**Storage**: Local filesystem (for cached documentation in markdown format) + SQL Server database connections
**Testing**: pytest with pytest-asyncio for async tool testing
**Target Platform**: Local process (cross-platform: macOS, Linux, Windows)
**Project Type**: Single project (MCP server)
**Performance Goals**: Metadata queries <30s for 1000 tables (NFR-001), sample data <10s per table (NFR-002)
**Constraints**: Token-efficient responses, read-only by default, no credential logging (NFR-005)
**Scale/Scope**: Support databases with 500-1000 tables, documentation <1MB for 500 tables (NFR-003)

**Key Technical Decisions from Research** ([research.md](./research.md)):
- Python chosen over TypeScript: Faster iteration with FastMCP, adequate I/O performance, mature DB ecosystem
- pyodbc + SQLAlchemy: Industry standard, excellent metadata introspection, built-in connection pooling
- Custom FK inference: BUILD Phase 1 (metadata-only, 75-80% accuracy, 200 LOC), no suitable libraries exist
- Zero new dependencies for inference: Uses Python stdlib (difflib)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

### Pre-Design Gate (Completed)

| Principle | Status | Assessment |
|-----------|--------|------------|
| **I. Simplicity First (YAGNI)** | ✅ PASS | All features tied to concrete user stories (P1-P3). SQL Server only in initial scope. No speculative multi-DB support. |
| **II. Don't Repeat Yourself (DRY)** | ✅ PASS | Single source of truth for metadata (cached docs). Schema info, relationships, column metadata centralized. |
| **III. Test-First Development** | ⚠️ VERIFY | Success criteria defined (SC-001 through SC-007). Must ensure test-first workflow in implementation phase. |
| **IV. Robustness Through Explicit Error Handling** | ✅ PASS | FR-015 requires graceful connection errors. FR-005 handles missing permissions explicitly. Input validation at MCP boundary. |
| **V. Performance by Design** | ✅ PASS | Performance requirements defined upfront (NFR-001, NFR-002, NFR-003). Token efficiency is primary design constraint. |
| **VI. Code Quality Through Clarity** | ⚠️ VERIFY | Must ensure during implementation: descriptive names, focused functions, clear error messages for AI agents. |
| **VII. Minimal Dependencies** | ⚠️ VERIFY | MCP SDK required (justified). SQL Server driver required (justified). Relationship inference algorithm NEEDS RESEARCH - build vs buy decision required. |

**Pre-Design Gate Status**: CONDITIONAL PASS - proceed to Phase 0 research to resolve NEEDS CLARIFICATION items and verify test-first workflow will be followed.

---

### Post-Design Gate (Phase 1 Complete)

| Principle | Status | Assessment |
|-----------|--------|------------|
| **I. Simplicity First (YAGNI)** | ✅ PASS | Design remains focused on concrete requirements. No over-engineering detected. Single project structure appropriate for MCP server. |
| **II. Don't Repeat Yourself (DRY)** | ✅ PASS | Centralized metadata service, single connection manager, reusable data models. No duplication in design. |
| **III. Test-First Development** | ✅ PASS | Test structure defined (unit/integration). Quickstart includes test examples. pytest + pytest-asyncio selected. Clear success criteria enable test-first workflow. |
| **IV. Robustness Through Explicit Error Handling** | ✅ PASS | All MCP tools define error schemas. Connection validation, permission checks, query type validation. Logging configured (never stdout in MCP). |
| **V. Performance by Design** | ✅ PASS | Connection pooling via SQLAlchemy QueuePool. Efficient metadata queries via DMVs. Caching strategy defined. O(n*m) inference complexity acknowledged with caching mitigation. |
| **VI. Code Quality Through Clarity** | ✅ PASS | Descriptive entity names (Connection, Schema, Table, etc.). MCP tools have clear docstrings. Data model well-documented. Quickstart provides clear examples. |
| **VII. Minimal Dependencies** | ✅ PASS | Only 5 core dependencies (Python, FastMCP, pyodbc, SQLAlchemy, ODBC Driver 18). Zero new dependencies for inference (uses stdlib difflib). Build decision for FK inference eliminates external algorithm dependencies. |

**Post-Design Gate Status**: ✅ **PASS** - All principles satisfied or have clear verification path during implementation.

## Project Structure

### Documentation (this feature)

```text
specs/[###-feature]/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command)
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
src/
├── mcp_server/           # MCP protocol implementation
│   ├── server.py/ts      # Main MCP server entry point
│   └── tools.py/ts       # Tool definitions per MCP spec
├── db/                   # Database connectivity
│   ├── connection.py/ts  # Connection management
│   ├── metadata.py/ts    # Schema/table metadata queries
│   └── query.py/ts       # Query execution
├── inference/            # Relationship and column analysis
│   ├── relationships.py/ts  # Foreign key inference
│   └── columns.py/ts     # Column purpose analysis
├── cache/                # Documentation caching
│   ├── storage.py/ts     # Markdown file I/O
│   └── drift.py/ts       # Schema drift detection
└── models/               # Data structures
    ├── schema.py/ts      # Schema, Table, Column entities
    └── relationship.py/ts # Relationship entity

tests/
├── integration/          # Full workflow tests with test DB
├── unit/                 # Individual component tests
└── fixtures/             # Test database schemas

docs/                     # Generated documentation cache
└── [connection-hash]/    # Per-database cached docs
```

**Structure Decision**: Single project structure. This is an MCP server daemon with no UI, single runtime, and cohesive functionality. All code serves a unified purpose: database exploration via MCP protocol.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

No violations requiring justification. All VERIFY items will be confirmed during implementation.
