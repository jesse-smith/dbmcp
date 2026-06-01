# Phase 3: Code Quality & Test Coverage - Context

**Gathered:** 2026-03-09
**Status:** Ready for planning

<domain>
## Phase Boundary

Make the codebase honest about its error handling and verify every module with tests. Remove dead code, narrow all broad exception catches to specific types, fix type suppressions, and establish 70%+ test coverage with CI enforcement. No new features or capabilities.

</domain>

<decisions>
## Implementation Decisions

### Dead code removal
- Delete `src/metrics.py` entirely — no archiving, no skeleton, no salvage
- Delete the file and grep for remaining imports; if something breaks, the test suite catches it
- The PerformanceMetrics API design and percentile logic are disposable (had bugs anyway — truncated indexing)
- Performance metrics integration is a deferred idea for a future milestone, not this phase

### Exception narrowing
- Only the 9 MCP tool entry points (`@mcp.tool()` decorated functions) may keep `except Exception:` as safety nets
- All other code (services, db layer, metadata, analysis) must catch specific exception types
- SQLAlchemy exception hierarchy only — do not also catch pyodbc exceptions (SQLAlchemy wraps them; if a raw pyodbc error leaks, that's worth knowing about)
- Reuse existing exception classes (ConnectionError, ValueError) plus SQLAlchemy's hierarchy — no new custom exception classes
- When narrowing exceptions, improve error messages with specificity (e.g., "Connection timeout" instead of generic "Connection failed") — Claude judges per case whether a more specific message helps

### CI enforcement
- Add `fail_under = 70` to `[tool.coverage.report]` in pyproject.toml
- Update `codecov.yml` to enforce absolute 70% target (not just `auto` regression guard) alongside threshold: 1% for regression protection
- The 70% baseline applies to unit-only test runs (`-m "not integration"`) — both in CI and locally
- Integration tests run separately as bonus coverage with no hard threshold
- CI continues to skip integration tests (no database in CI); local development runs both but the coverage gate is unit-only

### Claude's Discretion
- Type ignore fix approach in `src/db/query.py` (extend Query dataclass, TypedDict, or other)
- Which modules need the most new tests to reach 70% (metrics.py removal helps; metadata.py at 67% needs attention)
- Exact SQLAlchemy exception types per catch block (OperationalError, ProgrammingError, DatabaseError, etc.)
- Test organization for new coverage tests (new test files vs extending existing)

</decisions>

<specifics>
## Specific Ideas

- User wants pyproject.toml fail_under synced with codecov.yml — both must enforce the same 70% floor
- Integration tests should still run locally (just not gated on the 70% threshold)
- Error messages should be more helpful when exceptions are narrowed — include exception type context for debugging

</specifics>

<code_context>
## Existing Code Insights

### Reusable Assets
- `tests/conftest.py`: Root fixtures (mock_engine, sample data) shared across all tests
- `tests/integration/conftest.py`: Integration-specific fixtures with real database setup
- Existing parametrized test patterns in `test_validation.py` — good template for new coverage tests
- `.github/workflows/ci.yml`: Already runs `pytest --cov` with Codecov upload on Python 3.11-3.14, macOS/Linux/Windows

### Established Patterns
- Coverage config already in `pyproject.toml` with branch coverage and exclude_lines — just needs `fail_under`
- `codecov.yml` exists with range "70...90" and auto targets — needs absolute target update
- Exception pattern in `connection.py` already demonstrates proper narrowing (catches ConnectionError, re-raises, wraps generic)
- Async test support configured (`asyncio_mode = "auto"`)

### Integration Points
- Removing metrics.py may affect `__init__.py` or other barrel imports (need grep verification)
- Exception narrowing in metadata.py (11 catches) affects all schema exploration tools
- Coverage changes touch pyproject.toml which is shared config for ruff, pytest, and coverage

</code_context>

<deferred>
## Deferred Ideas

- Performance metrics integration (track p50/p95/p99 latencies for MCP tools) — future milestone, build fresh with proper tests
- Integration test CI setup (Docker SQL Server in GitHub Actions) — would improve coverage accuracy but significant setup work

</deferred>

---

*Phase: 03-code-quality-test-coverage*
*Context gathered: 2026-03-09*
