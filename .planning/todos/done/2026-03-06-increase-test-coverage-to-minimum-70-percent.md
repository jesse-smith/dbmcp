---
created: 2026-03-06T18:24:04.862Z
title: Increase test coverage to minimum 70%, ideally >= 90%
area: testing
files:
  - src/mcp_server/analysis_tools.py
  - src/mcp_server/schema_tools.py
  - src/db/metadata.py
  - src/db/validation.py
  - src/db/query.py
  - src/mcp_server/query_tools.py
  - src/mcp_server/server.py
---

## Problem

Several modules have significant test coverage gaps per the CONCERNS.md audit (2026-03-03):

| Module | Current | Target |
|---|---|---|
| `analysis_tools.py` | 16% | >= 70% (critical — user-facing API) |
| `schema_tools.py` | 53% | >= 70% |
| `metadata.py` | 67% | >= 70% |
| `validation.py` | 80% | >= 90% (security-critical) |
| `query.py` | 88% | >= 90% |
| `query_tools.py` | 75% | >= 90% |
| `server.py` | 88% | >= 90% |

The `metrics.py` module (0%) is tracked separately as a removal candidate.

Key untested areas include: MCP tool error handling paths, ConnectionManager integration, SQLite fallback paths in metadata, complex parse failures in validation, and query result type formatting edge cases.

## Solution

Prioritize by risk:
1. **analysis_tools.py** (16% → 70%+): Test get_column_info, find_fk_candidates, find_pk_candidates with mocked connections
2. **schema_tools.py** (53% → 70%+): Test connection establishment edge cases, schema listing error paths
3. **validation.py** (80% → 90%+): Add adversarial query test cases, complex parse failure scenarios
4. **metadata.py** (67% → 70%+): Test SQLite introspection fallbacks, row count edge cases
5. Remaining modules: fill gaps in error recovery paths and type formatting edge cases

Use `uv run pytest --cov=src --cov-report=term-missing` to track progress per module.
