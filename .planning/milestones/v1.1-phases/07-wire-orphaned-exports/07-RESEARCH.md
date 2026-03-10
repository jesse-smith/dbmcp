# Phase 7: Wire Orphaned Exports - Research

**Researched:** 2026-03-10
**Domain:** Internal integration wiring (config plumbing + error classification)
**Confidence:** HIGH

## Summary

Phase 7 is a focused integration phase that wires two orphaned exports into production code paths. First, `text_truncation_limit` from the TOML config system (Phase 6) must replace hardcoded `1000` values in `query.py` at two call sites. Second, `_classify_db_error` from `connection.py` (Phase 4) must be wired into the 9 MCP tool safety nets across three tool modules so caught exceptions produce actionable error messages.

Both changes are straightforward plumbing with established patterns already in the codebase. The `get_config()` singleton is already imported and used in `query_tools.py` for `sample_size` and `row_limit`. The `_classify_db_error` function is a module-level function specifically designed for cross-module reuse. No new dependencies are needed.

**Primary recommendation:** Two plans -- one for config plumbing (small, 2 files), one for error classification wiring (larger, 3 tool modules + tests). Both follow patterns already established in the codebase.

<user_constraints>
## User Constraints (from CONTEXT.md)

### Locked Decisions
- Wire `_classify_db_error` into all 9 MCP tool safety nets (schema_tools, query_tools, analysis_tools)
- Safety nets remain `except Exception:` -- classification makes them smarter, not narrower
- When caught exception IS a SQLAlchemyError: pass through `_classify_db_error` for actionable guidance
- Non-SQLAlchemy errors: keep generic `str(e)` fallback as before
- Error format: guidance first + raw exception detail in parens -- e.g., "Authentication failure: Check your credentials and verify the account has access. (Login failed for user 'bob')"
- Import `_classify_db_error` from `src.db.connection` into each tool module
- Read config inline at each call site: `get_config().defaults.text_truncation_limit`
- Replace hardcoded `1000` at query.py lines ~333 and ~667
- Same pattern already used in query_tools.py for sample_size and row_limit
- No API changes to QueryService -- internal-only change
- Unit test with mocked `get_config`: patch to return limit=500, run query with 700-char string, assert truncation occurs
- Verify the inverse: patch with limit=1000, assert same string is NOT truncated
- No integration test with real TOML file needed -- unit coverage sufficient

### Claude's Discretion
- Exact `isinstance` check pattern for SQLAlchemyError detection in safety nets
- Whether to extract a shared helper for the classify-and-format pattern or inline it in each tool
- Test structure for `_classify_db_error` wiring (per-tool tests vs parametrized)

### Deferred Ideas (OUT OF SCOPE)
None -- discussion stayed within phase scope
</user_constraints>

<phase_requirements>
## Phase Requirements

| ID | Description | Research Support |
|----|-------------|-----------------|
| CONN-02 | Database connections cleaned up when MCP session ends via `atexit` handler | `_classify_db_error` wiring completes the error classification circuit started in Phase 4; the function was created alongside the cleanup handler and is the remaining unwired CONN-02 artifact |
| INFRA-02 | Optional TOML config file supporting named connections, default parameters, and SP allowlist extensions | `text_truncation_limit` config plumbing completes INFRA-02 by ensuring the config value actually flows into the truncation code path rather than being silently ignored |
</phase_requirements>

## Standard Stack

### Core
| Library | Version | Purpose | Why Standard |
|---------|---------|---------|--------------|
| sqlalchemy | >=2.0.0 | `SQLAlchemyError` base class for isinstance checks | Already in project; provides the exception hierarchy |
| pytest | >=7.0.0 | Test framework | Already configured in pyproject.toml |
| pytest-asyncio | >=0.21.0 | Async tool function testing | Already configured with `asyncio_mode = "auto"` |

### Supporting
No new dependencies needed. All imports come from existing project modules.

## Architecture Patterns

### Current Safety Net Pattern (ALL 9 tools)
```python
# schema_tools.py, query_tools.py: with logger
except Exception as e:
    logger.exception("Error in <tool_name>")
    return encode_response({"status": "error", "error_message": f"Failed to ...: {str(e)}"})

# analysis_tools.py: NO logger import
except Exception as e:
    return encode_response({"status": "error", "error_message": f"Unexpected error: {str(e)}"})
```

### Target Safety Net Pattern (after wiring)
```python
from sqlalchemy.exc import SQLAlchemyError
from src.db.connection import _classify_db_error

# In each except Exception block:
except Exception as e:
    logger.exception("Error in <tool_name>")  # where logger exists
    if isinstance(e, SQLAlchemyError):
        category, guidance = _classify_db_error(e)
        msg = f"{guidance} ({e})"
    else:
        msg = f"Failed to ...: {str(e)}"  # preserve existing message format
    return encode_response({"status": "error", "error_message": msg})
```

### Config Plumbing Pattern (already established)
```python
# Already in query_tools.py -- this is the exact pattern to follow:
config = get_config()
sample_size = config.defaults.sample_size
row_limit = config.defaults.row_limit

# Target in query.py (two call sites):
from src.config import get_config
# Line ~333:
truncated_value, was_truncated = convert(value, get_config().defaults.text_truncation_limit)
# Line ~667:
truncated_value, _ = convert(value, get_config().defaults.text_truncation_limit)
```

### Import Differences Across Tool Modules

| Module | Has `get_config` | Has `logger` | Has `SQLAlchemyError` | Has `_classify_db_error` | Safety Nets |
|--------|------------------|--------------|-----------------------|--------------------------|-------------|
| `schema_tools.py` | YES | YES (from server) | NO | NO | 4 |
| `query_tools.py` | YES | YES (from server) | NO | NO | 2 (+1 in execute_query) |
| `analysis_tools.py` | NO | NO | NO | NO | 3 |

**Key observation:** `analysis_tools.py` needs additional imports: `SQLAlchemyError`, `_classify_db_error`, and optionally `logger` from server module. The `schema_tools.py` already imports `ConnectionError` from `src.db.connection`, so adding `_classify_db_error` to that import line is natural.

### Anti-Patterns to Avoid
- **Narrowing the except clause:** Safety nets MUST remain `except Exception`. The user explicitly decided classification happens INSIDE the handler, not by narrowing the catch.
- **Calling `_classify_db_error` on non-SQLAlchemy errors:** The function signature requires `SQLAlchemyError`. Always guard with `isinstance` check first.
- **Caching `get_config()` at module level:** Config must be read at call time so runtime config changes take effect. The inline `get_config().defaults.text_truncation_limit` pattern is correct.

## Don't Hand-Roll

| Problem | Don't Build | Use Instead | Why |
|---------|-------------|-------------|-----|
| Error classification | Custom pattern matching per tool | `_classify_db_error` from connection.py | Already tested with 9 tests, handles SQLSTATE codes and message patterns |
| Config access | Passing truncation limit as parameter | `get_config().defaults.text_truncation_limit` | Singleton pattern already established, no API changes needed |

## Common Pitfalls

### Pitfall 1: Forgetting isinstance Guard
**What goes wrong:** Calling `_classify_db_error(e)` when `e` is not a `SQLAlchemyError` raises an error or produces nonsense.
**Why it happens:** The except clause catches ALL exceptions, not just SQLAlchemy ones.
**How to avoid:** Always wrap with `if isinstance(e, SQLAlchemyError)` before calling classify.
**Warning signs:** Test with a non-SQLAlchemy error (e.g., `ValueError`) hitting the safety net.

### Pitfall 2: analysis_tools.py Missing logger
**What goes wrong:** `analysis_tools.py` currently has no `logger` import. The safety nets there don't log exceptions.
**Why it happens:** Different authorship/phase for this module.
**How to avoid:** Decide upfront whether to add logger to analysis_tools or keep it logger-free. The user's discretion allows this choice. Recommendation: add `logger` import from server module for consistency, but this is optional scope.

### Pitfall 3: Config Import Missing in query.py
**What goes wrong:** `query.py` currently does NOT import `get_config`. Adding the inline call without the import causes NameError.
**Why it happens:** The config import exists in `query_tools.py` but not in `query.py` (the service layer).
**How to avoid:** Add `from src.config import get_config` to `query.py` imports.
**Warning signs:** ImportError on first test run.

### Pitfall 4: Circular Import Risk
**What goes wrong:** `query.py` importing from `config.py` could theoretically create circular imports.
**Why it happens:** Deep dependency chains in Python.
**How to avoid:** Verify: `config.py` has no imports from `db/` modules. Confirmed: `config.py` imports only stdlib (`dataclasses`, `pathlib`, `tomllib`, `os`, `re`, `logging`) -- no circular risk.
**Warning signs:** ImportError at module load time.

## Code Examples

### text_truncation_limit Replacement (query.py line ~333)
```python
# Before:
truncated_value, was_truncated = convert(value, 1000)

# After:
truncated_value, was_truncated = convert(value, get_config().defaults.text_truncation_limit)
```

### Safety Net Enhancement (schema_tools.py example)
```python
# Before (line ~315):
except Exception as e:
    logger.exception("Error in list_schemas")
    return encode_response({"status": "error", "error_message": f"Failed to list schemas: {str(e)}"})

# After:
except Exception as e:
    logger.exception("Error in list_schemas")
    if isinstance(e, SQLAlchemyError):
        _cat, guidance = _classify_db_error(e)
        error_msg = f"{guidance} ({e})"
    else:
        error_msg = f"Failed to list schemas: {str(e)}"
    return encode_response({"status": "error", "error_message": error_msg})
```

### Test Pattern for Truncation Config
```python
from unittest.mock import patch, MagicMock

def test_truncation_uses_config_limit():
    """Setting text_truncation_limit=500 in config truncates 700-char strings."""
    mock_config = MagicMock()
    mock_config.defaults.text_truncation_limit = 500

    with patch("src.db.query.get_config", return_value=mock_config):
        # Execute query that returns a 700-char string
        # Assert the value is truncated to 500 chars
        pass

def test_truncation_default_limit_preserves_short_strings():
    """With default limit=1000, a 700-char string is NOT truncated."""
    mock_config = MagicMock()
    mock_config.defaults.text_truncation_limit = 1000

    with patch("src.db.query.get_config", return_value=mock_config):
        # Execute query that returns a 700-char string
        # Assert the value is NOT truncated
        pass
```

### Test Pattern for Error Classification Wiring
```python
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
from sqlalchemy.exc import SQLAlchemyError

@pytest.mark.parametrize("tool_func,tool_module", [
    ("list_schemas", "src.mcp_server.schema_tools"),
    ("list_tables", "src.mcp_server.schema_tools"),
    # ... etc for all 9 tools
])
async def test_safety_net_classifies_sqlalchemy_errors(tool_func, tool_module):
    """Safety nets pass SQLAlchemyError through _classify_db_error."""
    # Mock asyncio.to_thread to raise a SQLAlchemyError
    # Assert response contains guidance text, not raw str(e)
    pass
```

## Specific Integration Points

### query.py Changes (2 sites)
| Line | Current Code | New Code | Method |
|------|-------------|----------|--------|
| ~333 | `convert(value, 1000)` | `convert(value, get_config().defaults.text_truncation_limit)` | `_process_result_rows` |
| ~667 | `convert(value, 1000)` | `convert(value, get_config().defaults.text_truncation_limit)` | `_process_sp_results` |

New import needed: `from src.config import get_config`

### Tool Module Safety Nets (9 sites)

| Module | Tool Function | Line | Has Logger |
|--------|--------------|------|------------|
| schema_tools.py | `connect_database` | ~257 | YES |
| schema_tools.py | `list_schemas` | ~315 | YES |
| schema_tools.py | `list_tables` | ~420 | YES |
| schema_tools.py | `get_table_schema` | ~506 | YES |
| query_tools.py | `get_sample_data` | ~116 | YES |
| query_tools.py | `execute_query` | ~203 | YES |
| analysis_tools.py | `get_column_info` | ~136 | NO |
| analysis_tools.py | `find_pk_candidates` | ~236 | NO |
| analysis_tools.py | `find_fk_candidates` | ~399 | NO |

New imports needed per module:
- `schema_tools.py`: Add `_classify_db_error` to existing `from src.db.connection import ConnectionError` line; add `from sqlalchemy.exc import SQLAlchemyError`
- `query_tools.py`: Add `from src.db.connection import _classify_db_error`; add `from sqlalchemy.exc import SQLAlchemyError`
- `analysis_tools.py`: Add `from src.db.connection import _classify_db_error`; add `from sqlalchemy.exc import SQLAlchemyError`

### Discretion Recommendation: Shared Helper vs Inline

**Recommendation: Inline the isinstance+classify pattern in each safety net.** Reasons:
1. The pattern is 4 lines -- not enough to justify a helper function
2. Each safety net has slightly different fallback messages ("Failed to list schemas" vs "Query execution failed" vs "Unexpected error")
3. A shared helper would need the fallback message as a parameter, adding complexity without reducing code
4. 9 occurrences of a 4-line pattern is acceptable duplication

### Discretion Recommendation: Test Structure

**Recommendation: Parametrized tests for classification wiring, separate tests for truncation.**
1. Classification wiring: All 9 tools need the same behavior verified. A parametrized test with `(tool_function, setup_mocks)` tuples avoids 9 near-identical test functions.
2. Truncation: Two focused unit tests (limit=500 truncates, limit=1000 preserves) on the `_process_result_rows` method directly.

## Validation Architecture

### Test Framework
| Property | Value |
|----------|-------|
| Framework | pytest >=7.0.0 + pytest-asyncio >=0.21.0 |
| Config file | `pyproject.toml` [tool.pytest.ini_options] |
| Quick run command | `uv run pytest tests/unit/ -x -q` |
| Full suite command | `uv run pytest tests/ -x` |

### Phase Requirements to Test Map
| Req ID | Behavior | Test Type | Automated Command | File Exists? |
|--------|----------|-----------|-------------------|-------------|
| INFRA-02 | `text_truncation_limit` config flows into query.py truncation | unit | `uv run pytest tests/unit/test_query.py -x -k truncation_config` | No -- Wave 0 |
| INFRA-02 | Setting limit=500 actually truncates at 500 | unit | `uv run pytest tests/unit/test_query.py -x -k truncation_limit` | No -- Wave 0 |
| CONN-02 | `_classify_db_error` called in tool safety nets for SQLAlchemyError | unit | `uv run pytest tests/unit/test_async_tools.py -x -k classify` | No -- Wave 0 |
| CONN-02 | Non-SQLAlchemy errors still produce generic messages | unit | `uv run pytest tests/unit/test_async_tools.py -x -k generic_error` | No -- Wave 0 |

### Sampling Rate
- **Per task commit:** `uv run pytest tests/unit/ -x -q`
- **Per wave merge:** `uv run pytest tests/ -x`
- **Phase gate:** Full suite green before `/gsd:verify-work`

### Wave 0 Gaps
- [ ] Truncation config tests in `tests/unit/test_query.py` -- covers INFRA-02
- [ ] Error classification wiring tests in `tests/unit/test_async_tools.py` -- covers CONN-02
- No framework install needed -- pytest already configured

## Sources

### Primary (HIGH confidence)
- Direct source code inspection of `src/db/query.py`, `src/db/connection.py`, `src/config.py`, `src/type_registry.py`
- Direct source code inspection of `src/mcp_server/schema_tools.py`, `query_tools.py`, `analysis_tools.py`
- `pyproject.toml` for test framework configuration
- `.planning/phases/07-wire-orphaned-exports/07-CONTEXT.md` for user decisions

### Secondary (MEDIUM confidence)
- `.planning/STATE.md` for accumulated project decisions
- `.planning/REQUIREMENTS.md` for requirement definitions

## Metadata

**Confidence breakdown:**
- Standard stack: HIGH - no new dependencies, all existing code inspected directly
- Architecture: HIGH - patterns already established in codebase, just replicating them
- Pitfalls: HIGH - all integration points verified by direct code inspection

**Research date:** 2026-03-10
**Valid until:** 2026-04-10 (stable internal codebase, no external dependency changes)
