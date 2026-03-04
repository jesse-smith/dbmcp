# Implementation Plan: Data-Exposure Analysis Tools

> **STATUS: COMPLETE** | Merged: 2026-03-03 | Branch: `007-analysis-tools`

**Branch**: `007-analysis-tools` | **Date**: 2026-03-03 | **Spec**: [spec.md](./spec.md)
**Input**: Feature specification from `/specs/007-analysis-tools/spec.md`

## Summary

Replace all disabled inference tools and documentation caching infrastructure with three new data-exposure MCP tools: `get_column_info` (column statistics), `find_pk_candidates` (PK discovery), and `find_fk_candidates` (FK candidate search with optional value overlap). Remove all inference scoring, confidence calculations, pattern matching, and caching modules. The new tools expose raw statistics and structural metadata only — no interpretation.

## Technical Context

**Language/Version**: Python 3.11+ (existing)
**Primary Dependencies**: mcp[cli] >=1.0.0, sqlalchemy >=2.0.0, pyodbc >=5.0.0, azure-identity >=1.14.0 (all existing — no new dependencies)
**Storage**: N/A (in-memory, on-demand results only)
**Testing**: pytest + pytest-asyncio (existing)
**Target Platform**: MCP server over stdio (existing)
**Project Type**: Library / MCP server
**Performance Goals**: Column stats <5s per table; PK candidates <5s per table; FK candidates <10s per search (metadata-only), <30s with value overlap (measured on SQL Server 2019+ with 4-core CPU, 16GB RAM, SSD storage, under idle query load)
**Constraints**: Default FK candidate limit of 100; default scope to source column's schema; value overlap is opt-in
**Scale/Scope**: Typical SQL Server databases (100s-1000s of tables)

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

| Principle | Status | Notes |
|-----------|--------|-------|
| I. Simplicity First (YAGNI) | PASS | Three tools with clear requirements. No speculative features. Reuses proven query patterns from existing inference code. |
| II. DRY | PASS | Column stats collector logic reused (adapted, not duplicated). PK discovery used by both `find_pk_candidates` and `find_fk_candidates`. |
| III. Test-First Development | PASS | Each tool has clear acceptance scenarios. TDD approach per constitution. |
| IV. Robustness Through Explicit Error Handling | PASS | Spec defines error cases for invalid connections, tables, columns. Clear error messages required. |
| V. Performance by Design | PASS | Performance goals defined above. Value overlap opt-in for expensive operations. Default result limits prevent unbounded queries. FK search defaults to source schema, never full-database. |
| VI. Code Quality Through Clarity | PASS | Clean separation: one tool module for analysis tools, clean data models. |
| VII. Minimal Dependencies | PASS | Zero new dependencies. All functionality built with existing stack. |

**Quality Gates:**

| Gate | Plan |
|------|------|
| Tests | All new tools covered by unit + integration tests; removed code tests also removed |
| Coverage | New code fully covered; overall coverage maintained or improved |
| Lint | Zero ruff warnings |
| Types | Full type annotations on all new code |
| Build | Clean build |
| Complexity | Functions <50 lines, cyclomatic complexity <10, files <400 lines |

## Project Structure

### Documentation (this feature)

```text
specs/007-analysis-tools/
├── plan.md              # This file
├── research.md          # Phase 0 output
├── data-model.md        # Phase 1 output
├── contracts/           # Phase 1 output
│   └── mcp-tools.md     # MCP tool interface contracts
└── tasks.md             # Phase 2 output (via /speckit.tasks)
```

### Source Code (repository root)

```text
src/
├── models/
│   ├── schema.py          # MODIFY: Remove InferredPurpose, inferred fields from Column, DocumentationCache
│   ├── relationship.py    # MODIFY: Remove InferredFK, InferenceFactors; add FKCandidateData
│   └── analysis.py        # NEW: ColumnStatistics, PKCandidate data models
├── db/
│   ├── metadata.py        # EXISTING: Reuse for constraint/index queries
│   ├── query.py           # EXISTING: Unchanged
│   ├── connection.py      # EXISTING: Unchanged
│   ├── azure_auth.py      # EXISTING: Unchanged
│   └── validation.py      # EXISTING: Unchanged
├── analysis/              # NEW: Replaces src/inference/
│   ├── __init__.py
│   ├── column_stats.py    # Adapted from inference/column_stats.py (direct exposure, no purpose inference)
│   ├── pk_discovery.py    # NEW: PK candidate identification
│   └── fk_candidates.py   # NEW: FK candidate search with optional value overlap
├── mcp_server/
│   ├── server.py          # MODIFY: Remove inference/cache imports, add analysis imports
│   ├── schema_tools.py    # MODIFY: Remove infer_relationships function
│   ├── query_tools.py     # MODIFY: Remove analyze_column function
│   ├── analysis_tools.py  # NEW: get_column_info, find_pk_candidates, find_fk_candidates
│   └── doc_tools.py       # DELETE: Entire file removed
├── inference/             # DELETE: Entire directory removed
├── cache/                 # DELETE: Entire directory removed
├── metrics.py             # EXISTING: Unchanged
└── logging_config.py      # EXISTING: Unchanged

tests/
├── unit/
│   ├── test_column_stats.py       # NEW: Replaces test_columns.py
│   ├── test_pk_discovery.py       # NEW
│   ├── test_fk_candidates.py      # NEW: Replaces test_relationships.py, test_value_overlap.py
│   ├── test_analysis_models.py    # NEW: Model tests
│   ├── test_metadata.py           # EXISTING: May need updates for removed imports
│   ├── test_query.py              # EXISTING: Unchanged
│   ├── test_connection.py         # EXISTING: Unchanged
│   ├── test_azure_auth.py         # EXISTING: Unchanged
│   └── test_validation.py         # EXISTING: Unchanged
├── integration/
│   ├── test_get_column_info.py    # NEW: Replaces test_fk_inference.py
│   ├── test_pk_discovery.py       # NEW
│   ├── test_fk_candidates.py      # NEW: Replaces test_fk_inference_overlap.py
│   ├── test_discovery.py          # EXISTING: May need updates for removed imports
│   ├── test_query_execution.py    # EXISTING: Unchanged
│   ├── test_sample_data.py        # EXISTING: Unchanged
│   └── test_azure_ad_auth.py      # EXISTING: Unchanged
├── performance/
│   ├── test_nfr001.py             # EXISTING: Unchanged
│   ├── test_nfr003.py             # MODIFY or DELETE: May reference caching
│   └── test_analysis_perf.py      # NEW: Replaces test_inference_scaling.py
└── fixtures/                      # EXISTING: May need new fixtures for analysis tests
```

**Structure Decision**: Single-project structure maintained. New `src/analysis/` module replaces `src/inference/` and `src/cache/`. New `src/mcp_server/analysis_tools.py` houses all three analysis tool registrations. New `src/models/analysis.py` houses analysis-specific data models to keep schema.py and relationship.py focused.

## Complexity Tracking

No constitution violations anticipated. All new functions should stay well within complexity budgets:
- Column stats: adapts existing proven query patterns
- PK discovery: straightforward constraint + structural check
- FK candidates: iterates PK candidates per target table (linear, bounded by limit)
