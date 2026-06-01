# Phase 3: Code Quality & Test Coverage - Research

**Researched:** 2026-03-09
**Domain:** Python code quality, exception handling, type safety, test coverage
**Confidence:** HIGH

## Summary

Phase 3 is a pure cleanup phase with no new features. The work divides into four distinct tracks: (1) dead code removal of `src/metrics.py`, (2) narrowing 17 broad `except Exception:` blocks in service/db layer code to specific SQLAlchemy exception types, (3) eliminating three `# type: ignore` comments in `src/db/query.py` by extending the `Query` dataclass, and (4) raising test coverage to 70%+ per module with CI enforcement.

The codebase is already at 80% overall coverage. Only `src/metrics.py` (0%, being deleted) drags things down. After deletion, the main coverage gap is `src/db/metadata.py` at 67% -- the only module currently below the 70% threshold. All other modules are already above 70%. The `type: ignore` problem is straightforward: three dynamic attributes (`_columns`, `_rows`, `_total_rows_available`) are monkey-patched onto the `Query` dataclass. The fix is to add these as proper dataclass fields with defaults.

**Primary recommendation:** Sequence as dead code removal first (changes coverage baseline), then exception narrowing (biggest risk of regressions), then type fixes (isolated), then coverage config + gap filling last (validates everything).

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Delete `src/metrics.py` entirely -- no archiving, no skeleton, no salvage
- Delete the file and grep for remaining imports; if something breaks, the test suite catches it
- The PerformanceMetrics API design and percentile logic are disposable (had bugs anyway -- truncated indexing)
- Performance metrics integration is a deferred idea for a future milestone, not this phase
- Only the 9 MCP tool entry points (`@mcp.tool()` decorated functions) may keep `except Exception:` as safety nets
- All other code (services, db layer, metadata, analysis) must catch specific exception types
- SQLAlchemy exception hierarchy only -- do not also catch pyodbc exceptions (SQLAlchemy wraps them; if a raw pyodbc error leaks, that's worth knowing about)
- Reuse existing exception classes (ConnectionError, ValueError) plus SQLAlchemy's hierarchy -- no new custom exception classes
- When narrowing exceptions, improve error messages with specificity (e.g., "Connection timeout" instead of generic "Connection failed") -- Claude judges per case whether a more specific message helps
- Add `fail_under = 70` to `[tool.coverage.report]` in pyproject.toml
- Update `codecov.yml` to enforce absolute 70% target (not just `auto` regression guard) alongside threshold: 1% for regression protection
- The 70% baseline applies to unit-only test runs (`-m "not integration"`) -- both in CI and locally
- Integration tests run separately as bonus coverage with no hard threshold
- CI continues to skip integration tests (no database in CI); local development runs both but the coverage gate is unit-only

### Claude's Discretion
- Type ignore fix approach in `src/db/query.py` (extend Query dataclass, TypedDict, or other)
- Which modules need the most new tests to reach 70% (metrics.py removal helps; metadata.py at 67% needs attention)
- Exact SQLAlchemy exception types per catch block (OperationalError, ProgrammingError, DatabaseError, etc.)
- Test organization for new coverage tests (new test files vs extending existing)

### Deferred Ideas (OUT OF SCOPE)
- Performance metrics integration (track p50/p95/p99 latencies for MCP tools) -- future milestone, build fresh with proper tests
- Integration test CI setup (Docker SQL Server in GitHub Actions) -- would improve coverage accuracy but significant setup work
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| QUAL-01 | Dead metrics module removed with no remaining references | No imports of `src/metrics.py` found anywhere in project code. Safe to delete. Only self-references exist. |
| QUAL-02 | All 25 broad `except Exception:` blocks replaced with specific exception types | Identified 17 `except Exception:` blocks in service/db layer (metadata: 11, query: 3, connection: 1, logging_config implicit). 9 MCP tool safety nets remain. SQLAlchemy hierarchy documented below. |
| QUAL-03 | Three `# type: ignore` in query.py eliminated by proper typing | All three are on lines 546-548, monkey-patching `_columns`, `_rows`, `_total_rows_available` onto Query dataclass. Fix by adding fields to dataclass. |
| TEST-01 | All source modules at 70%+ test coverage | After metrics.py deletion, only `metadata.py` (67%) is below 70%. All others already pass. |
| TEST-02 | Coverage reporting configured with CI enforcement baseline | `pyproject.toml` already has `[tool.coverage]` config. Need to add `fail_under = 70`. `codecov.yml` needs absolute target update. CI already runs `pytest --cov`. |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| pytest | >=7.0.0 | Test framework | Already in use, configured in pyproject.toml |
| pytest-cov | >=4.0.0 | Coverage reporting | Already in use, runs in CI |
| pytest-asyncio | >=0.21.0 | Async test support | Already in use, asyncio_mode = "auto" |
| ruff | >=0.1.0 | Linting | Already in use for E/W/F/I/B/C4/UP rules |

### Supporting
| Library | Version | Purpose | When to Use |
|---------|---------|---------|-------------|
| pyright | >=1.1.0 | Type checking | QUAL-03 requires zero type suppressions; need a type checker to validate. Add to dev dependencies. |

### Alternatives Considered
| Instead of | Could Use | Tradeoff |
|------------|-----------|----------|
| pyright | mypy | Both work; pyright is faster and handles dataclass field additions better. Either satisfies the success criteria. Pyright is recommended. |

**Installation:**
```bash
uv add --group dev pyright
```

## Architecture Patterns

### Current Exception Pattern (Good -- in connection.py)
```python
# src/db/connection.py lines 143-148
try:
    engine = self._create_engine(...)
    self._test_connection(...)
except ConnectionError:
    raise
except Exception as e:
    raise ConnectionError(f"Could not connect to {server}:{port}/{database}: {str(e)}") from e
```
This pattern catches specific first, wraps generic. The service/db layer blocks need to follow this pattern but with SQLAlchemy-specific types.

### Pattern: Extending Dataclass for Type Safety
**What:** Add the three dynamic attributes as proper dataclass fields with `field(default_factory=list)` or `None` defaults
**When to use:** For QUAL-03 -- eliminating `# type: ignore` on Query
**Recommended approach:**
```python
@dataclass
class Query:
    # ... existing fields ...
    denial_reasons: list[DenialReason] | None = None
    # New fields to replace monkey-patched attributes
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    total_rows_available: int | None = None
```
Then update `execute_query()` to set these directly and update `get_query_results()` to read from them instead of using `getattr()`. This is cleaner than underscore-prefixed fields since these are legitimate result data.

**Impact:** The `get_query_results()` method (lines 707-753) reads these via `getattr(query, '_columns', [])` etc. Must update to use the new field names. Also check test files that construct `Query` objects.

### Anti-Patterns to Avoid
- **Catching `Exception` then doing nothing:** Several metadata.py blocks catch `Exception` and `pass` (lines 290, 314, 330, 712). These should catch `SQLAlchemyError` specifically.
- **Re-raising without wrapping:** `except Exception as e: raise` is pointless. Either catch specific or add context before re-raising.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Coverage enforcement | Custom coverage scripts | `fail_under = 70` in pyproject.toml | Built-in to coverage.py, one line |
| Type checking | Manual review of type ignores | pyright strict mode on query.py | Catches issues humans miss |
| Exception type discovery | Guessing which SQLAlchemy errors occur | SQLAlchemy exception hierarchy (documented below) | Hierarchy is well-defined |

## Common Pitfalls

### Pitfall 1: Narrowing Exceptions Too Aggressively
**What goes wrong:** Catch only `OperationalError` but miss `ProgrammingError` that occurs on invalid table names, leading to unhandled exceptions bubbling up as 500s.
**Why it happens:** Each metadata operation can fail for different reasons -- connection loss, bad SQL, permission denied, timeout.
**How to avoid:** Use `SQLAlchemyError` as the catch-all for database operations in the service layer. Only narrow further when the handling differs by type.
**Warning signs:** Tests pass but integration tests or manual testing reveals crashes on edge cases.

### Pitfall 2: Breaking get_query_results() When Fixing Type Ignores
**What goes wrong:** Changing `_columns`/`_rows`/`_total_rows_available` from monkey-patched attributes to dataclass fields changes how they serialize, or breaks tests that construct Query objects without the new fields.
**Why it happens:** Dataclass fields are positional unless they have defaults. Adding required fields breaks existing construction.
**How to avoid:** Use `field(default_factory=list)` for list fields and `None` for optional fields. Always add new fields AFTER existing ones with defaults.
**Warning signs:** Tests that create `Query(query_id=..., connection_id=..., ...)` fail with TypeError about unexpected arguments.

### Pitfall 3: Coverage Threshold Blocking CI
**What goes wrong:** Setting `fail_under = 70` causes CI to fail because a module dips below 70% after metrics.py deletion changes the baseline.
**Why it happens:** `fail_under` applies to the TOTAL coverage, not per-module. Per-module enforcement requires `--cov-fail-under` per package or codecov configuration.
**How to avoid:** The `fail_under = 70` in pyproject.toml enforces total coverage. For per-module enforcement, rely on codecov.yml. Current total is 80% so the floor is safe.
**Warning signs:** CI fails immediately after adding fail_under.

### Pitfall 4: Metrics Module Has No Importers But May Have Test References
**What goes wrong:** Delete metrics.py, tests still reference it or import it.
**Why it happens:** Test files might test the metrics module directly.
**How to avoid:** Grep tests/ for metrics references too. Check `tests/fixtures/perf_test_db.py` and `tests/performance/` files.
**Warning signs:** Import errors after deletion.

## Code Examples

### Exception Narrowing in Metadata Service
The 11 `except Exception:` blocks in `src/db/metadata.py` fall into two categories:

**Category 1: Inspector operations (schema introspection)**
Lines 130, 145, 290, 314, 330, 712 -- these call `self.inspector.get_*()` methods.
```python
# BEFORE (line 130):
try:
    schema_names = self.inspector.get_schema_names()
except Exception:
    schema_names = [None]

# AFTER:
from sqlalchemy.exc import SQLAlchemyError

try:
    schema_names = self.inspector.get_schema_names()
except SQLAlchemyError:
    schema_names = [None]
```
`SQLAlchemyError` is the correct level for inspector operations. These can raise `OperationalError` (connection lost), `ProgrammingError` (permission denied), or `NotSupportedError` (database doesn't support the operation).

**Category 2: Data operations (queries)**
Lines 372, 555, 591, 608, 624 -- these execute SQL or process results.
```python
# BEFORE (line 372):
except Exception as e:
    logger.debug(f"Could not get row count for {table_name}: {e}")
    return None

# AFTER:
except SQLAlchemyError as e:
    logger.debug(f"Could not get row count for {table_name}: {type(e).__name__}: {e}")
    return None
```

### Exception Narrowing in Query Service
`src/db/query.py` has 3 `except Exception:` blocks (lines 130, 616, 686):

```python
# Line 130 -- get_sample_data error handler
# BEFORE:
except Exception as e:
    logger.error(f"Error sampling data from {schema_name}.{table_name}: {e}")
    raise

# AFTER:
except SQLAlchemyError as e:
    logger.error(f"Error sampling {schema_name}.{table_name}: {type(e).__name__}: {e}")
    raise

# Line 616 -- _run_query error handler
# BEFORE:
except Exception as e:
    error_message = f"Query execution failed: {type(e).__name__}: {str(e)}"

# AFTER:
except SQLAlchemyError as e:
    error_message = f"Query execution failed: {type(e).__name__}: {str(e)}"

# Line 686 -- _get_total_row_count (silent catch)
# BEFORE:
except Exception:
    pass

# AFTER:
except SQLAlchemyError:
    pass
```

### Connection Service Exception (line 145)
```python
# BEFORE:
except Exception as e:
    raise ConnectionError(f"Could not connect to {server}:{port}/{database}: {str(e)}") from e

# AFTER:
except SQLAlchemyError as e:
    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.error(f"Connection to {server}:{port}/{database} failed after {elapsed_ms}ms: {type(e).__name__}")
    raise ConnectionError(f"Could not connect to {server}:{port}/{database}: {type(e).__name__}: {str(e)}") from e
```

### MCP Tool Safety Nets (KEEP AS-IS)
9 `@mcp.tool()` functions with `except Exception as e:` -- these are the top-level safety nets per user decision:
- `analysis_tools.py`: lines 136, 236, 399
- `query_tools.py`: lines 110, 194
- `schema_tools.py`: lines 172, 230, 335, 421

### Type Ignore Fix
```python
# BEFORE (query.py lines 544-548):
query._columns = columns  # type: ignore
query._rows = rows  # type: ignore
query._total_rows_available = total_rows_available  # type: ignore

# AFTER -- add fields to Query dataclass (schema.py):
@dataclass
class Query:
    # ... existing fields through denial_reasons ...
    columns: list[str] = field(default_factory=list)
    rows: list[dict[str, Any]] = field(default_factory=list)
    total_rows_available: int | None = None

# AFTER -- update execute_query (query.py):
query.columns = columns
query.rows = rows
query.total_rows_available = total_rows_available

# AFTER -- update get_query_results (query.py lines 716-718):
columns = query.columns
rows = query.rows
total_rows_available = query.total_rows_available
```

### Coverage Configuration
```toml
# pyproject.toml addition:
[tool.coverage.report]
fail_under = 70
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

```yaml
# codecov.yml update:
coverage:
  range: "70...90"
  status:
    project:
      default:
        target: 70%
        threshold: 1%
    patch:
      default:
        target: auto
        threshold: 1%
```

## SQLAlchemy Exception Hierarchy Reference

Key exceptions relevant to this codebase:

| Exception | Parent | When Raised |
|-----------|--------|-------------|
| `SQLAlchemyError` | `Exception` | Base for all SQLAlchemy errors -- broadest safe catch |
| `OperationalError` | `DatabaseError` | Connection lost, timeout, server unavailable |
| `ProgrammingError` | `DatabaseError` | Bad SQL, invalid table/column names, permission denied |
| `InterfaceError` | `DBAPIError` | Driver-level failures (pyodbc can't communicate) |
| `DatabaseError` | `DBAPIError` | Generic database-side error |
| `InvalidRequestError` | `SQLAlchemyError` | Invalid SQLAlchemy API usage (stale session, etc.) |
| `NoSuchTableError` | `InvalidRequestError` | Table not found during reflection |
| `ResourceClosedError` | `InvalidRequestError` | Result set already consumed |

**Recommendation:** For most service-layer catches, `SQLAlchemyError` is the right level. Only narrow further when different error types need different handling (e.g., `OperationalError` for connection retry logic vs `ProgrammingError` for user feedback).

## Coverage Gap Analysis

Current per-module coverage (unit tests only, after metrics.py deletion):

| Module | Coverage | Status | Action Needed |
|--------|----------|--------|---------------|
| `src/db/metadata.py` | 67% | BELOW 70% | Need ~8-10 new test cases for uncovered lines |
| `src/db/connection.py` | 81% | OK | No action |
| `src/db/query.py` | 88% | OK | No action |
| `src/db/validation.py` | 80% | OK | No action |
| `src/logging_config.py` | 79% | OK | No action |
| `src/mcp_server/schema_tools.py` | 78% | OK | No action |
| `src/mcp_server/analysis_tools.py` | 85% | OK | No action |
| `src/mcp_server/query_tools.py` | 85% | OK | No action |
| `src/models/relationship.py` | 89% | OK | No action |
| All others | 93%+ | OK | No action |

**Key finding:** Only `metadata.py` needs new tests. The uncovered lines (89-120, 229-231, 389-508, 579-592, 622-626, 709-713) are primarily:
- Lines 89-120: MSSQL-specific schema listing (`_list_schemas_mssql`)
- Lines 389-508: MSSQL-specific table listing (`_list_tables_mssql`)
- Lines 579-592: `get_indexes()` error paths
- Lines 622-626: `get_primary_key()` error paths
- Lines 709-713: `table_exists()` error paths

These are testable with SQLite-based mocks or by testing the generic code paths that delegate to inspector.

## State of the Art

| Old Approach | Current Approach | When Changed | Impact |
|--------------|------------------|--------------|--------|
| `# type: ignore` for dynamic attrs | Proper dataclass fields | N/A (this phase) | Type checker validates all code |
| Bare `except Exception:` | Specific SQLAlchemy exceptions | N/A (this phase) | Clearer error reporting, no swallowed non-DB errors |
| No coverage floor | `fail_under = 70` | N/A (this phase) | CI prevents coverage regression |

## Open Questions

1. **pyright vs mypy for QUAL-03 validation**
   - What we know: Neither is currently installed. Success criteria says "passes `uv run pyright` (or mypy) without suppression"
   - Recommendation: Add pyright to dev dependencies. It's faster and handles dataclass inference well. Run it only on `src/db/query.py` initially to satisfy the requirement without adding project-wide type checking burden.

2. **MSSQL-specific code in metadata.py**
   - What we know: Lines 89-120 and 389-508 are MSSQL-specific paths that execute raw SQL against DMVs. These are hard to unit test with SQLite.
   - Recommendation: Mark these with `# pragma: no cover` since they're integration-only paths, OR mock the connection to return expected DMV result shapes. The generic paths already have good coverage.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0.0 with pytest-cov >=4.0.0 |
| Config file | pyproject.toml `[tool.pytest.ini_options]` |
| Quick run command | `uv run pytest tests/unit/ -x -q -m "not integration"` |
| Full suite command | `uv run pytest -m "not integration" --cov --cov-report=term-missing` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| QUAL-01 | metrics.py deleted, no import references | smoke | `uv run python -c "import src; import src.db; import src.mcp_server"` + grep verification | N/A (deletion check) |
| QUAL-02 | No bare `except Exception:` outside MCP tools | smoke | `grep -rn "except Exception" src/ \| grep -v mcp_server/` should return 0 lines | N/A (grep check) |
| QUAL-03 | query.py passes pyright with no suppressions | unit | `uv run pyright src/db/query.py` | N/A (type checker) |
| TEST-01 | All modules 70%+ coverage | unit | `uv run pytest -m "not integration" --cov --cov-report=term-missing` | Existing + new tests for metadata.py |
| TEST-02 | Coverage config with CI enforcement | smoke | `grep "fail_under" pyproject.toml` + `grep "target: 70" codecov.yml` | N/A (config check) |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q -m "not integration"`
- **Per wave merge:** `uv run pytest -m "not integration" --cov --cov-report=term-missing`
- **Phase gate:** Full suite green + all modules 70%+ before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] `pyright` -- needs to be added to dev dependencies for QUAL-03 validation
- [ ] New tests in `tests/unit/test_metadata.py` -- covers metadata.py gap for TEST-01

## Sources

### Primary (HIGH confidence)
- Codebase analysis: `src/metrics.py`, `src/db/query.py`, `src/db/metadata.py`, all `except` blocks
- Coverage report: `uv run pytest --cov=src -m "not integration"` -- live run showing exact per-module coverage
- SQLAlchemy exception hierarchy: runtime introspection of `sqlalchemy.exc` module
- `pyproject.toml`, `codecov.yml`, `.github/workflows/ci.yml` -- current config

### Secondary (MEDIUM confidence)
- SQLAlchemy exception semantics (which exceptions map to which database errors) -- based on SQLAlchemy 2.x documentation patterns

### Tertiary (LOW confidence)
- None

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - all tools already in use except pyright (well-known, simple addition)
- Architecture: HIGH - patterns derived from existing codebase analysis, not external sources
- Pitfalls: HIGH - based on direct code inspection of the specific files being modified

**Research date:** 2026-03-09
**Valid until:** 2026-04-09 (stable domain, no moving targets)
