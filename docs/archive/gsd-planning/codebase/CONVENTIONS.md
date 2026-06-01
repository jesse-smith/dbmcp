# Coding Conventions

**Analysis Date:** 2026-03-03

## Naming Patterns

**Files:**
- Module files use lowercase with underscores: `connection.py`, `column_stats.py`
- Test files follow pattern: `test_<module>.py` (e.g., `test_connection.py`, `test_validation.py`)
- Tool modules grouped by feature: `schema_tools.py`, `query_tools.py`, `analysis_tools.py`

**Functions:**
- Private functions (internal to module/class): prefixed with `_` (e.g., `_build_odbc_connection_string()`, `_test_connection()`)
- Public functions: no prefix (e.g., `connect()`, `validate_query()`, `get_sample_data()`)
- MCP tools decorated with `@mcp.tool()`: use clear action verb names (e.g., `get_sample_data`, `execute_query`, `find_pk_candidates`)
- Async functions: use `async def` when required by MCP (e.g., `async def get_sample_data()`)

**Variables:**
- Instance variables: private with leading underscore (e.g., `self._engines`, `self._connections`, `self._pool_config`)
- Constant sets/dicts: SCREAMING_SNAKE_CASE (e.g., `NUMERIC_TYPES`, `DATETIME_TYPES`, `DENIED_TYPES`, `SAFE_PROCEDURES`)
- Local variables: lowercase_snake_case (e.g., `conn_str`, `mock_result`, `connection_id`)

**Types:**
- Dataclasses use CamelCase (e.g., `Connection`, `Schema`, `Table`, `Column`, `ValidationResult`)
- Enums inherit from `StrEnum` (e.g., `AuthenticationMethod`, `TableType`, `QueryType`, `DenialCategory`)
- Type hints use union syntax: `str | None` instead of `Optional[str]` (Python 3.10+)
- Return type annotations always present: `def function() -> ReturnType:`

## Code Style

**Formatting:**
- Line length: 120 characters (configured in `pyproject.toml`)
- Indentation: 4 spaces (enforced)
- Imports: alphabetically ordered within groups

**Linting:**
- Tool: Ruff
- Active rule groups (from `pyproject.toml`):
  - E: pycodestyle errors
  - W: pycodestyle warnings
  - F: Pyflakes (unused imports, undefined names)
  - I: isort (import ordering)
  - B: flake8-bugbear (common bugs)
  - C4: flake8-comprehensions
  - UP: pyupgrade (modern Python syntax)
- Ignored rules:
  - E501: line too long (handled by formatter only)
  - B008: do not perform function calls in argument defaults
- First-party imports: `src` (configured in `isort` section)

## Import Organization

**Order:**
1. Standard library imports (e.g., `import json`, `from pathlib import Path`)
2. Third-party imports (e.g., `from sqlalchemy import create_engine`, `import pytest`)
3. First-party imports (e.g., `from src.db.connection import ConnectionManager`)

**Path Aliases:**
- No path aliases configured
- All imports use absolute imports from project root: `from src.db.connection import ...`
- Relative imports never used

**Example import block:**
```python
import json
import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Optional
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy import create_engine, text

from src.db.connection import ConnectionManager
from src.logging_config import get_logger
from src.models.schema import Connection, AuthenticationMethod
```

## Error Handling

**Patterns:**
- Custom exception classes inherit from built-in exceptions: `class ConnectionError(Exception):`
- Exceptions include docstrings explaining purpose
- Error messages are descriptive and actionable: `"Connection to {server}:{port}/{database} failed after {elapsed_ms}ms: {type(e).__name__}"`
- Never log full exception stack for credential-related failures (NFR-005 compliance)
- Use specific exception types, not bare `Exception`: catch `ConnectionError`, `ValueError`, `KeyError` explicitly
- Validation raises `ValueError` for parameter validation failures
- Database operations catch and wrap generic exceptions: `except Exception as e: raise ConnectionError(...) from e`

**Example error handling from `connection.py`:**
```python
try:
    engine = self._create_engine(odbc_conn_str, authentication_method, tenant_id)
    self._test_connection(engine, start_time, server, database, port)
except ConnectionError:
    raise
except Exception as e:
    elapsed_ms = int((time.time() - start_time) * 1000)
    logger.error(f"Connection to {server}:{port}/{database} failed after {elapsed_ms}ms: {type(e).__name__}")
    raise ConnectionError(f"Could not connect to {server}:{port}/{database}: {str(e)}") from e
```

## Logging

**Framework:** Python's built-in `logging` module

**Logger acquisition:**
- Modules use: `from src.logging_config import get_logger` then `logger = get_logger(__name__)`
- Produces logger name: `dbmcp.src.module_name`
- MCP server root logger initialized via `setup_logging()` in server.py

**Patterns:**
- **Connection events:** `logger.info()` for successful connections, including database name and timing
- **Connection errors:** `logger.error()` with sanitized details (never password)
- **Performance warnings:** `logger.warning()` when operations exceed thresholds (e.g., connection time > 5s)
- **Debug info:** `logger.debug()` for SQL version and detailed state
- **Exceptions:** `logger.exception()` only for truly unexpected errors (includes full traceback)
- **Token operations:** Log only success/failure, never token content

**Critical rule:** NO credentials ever logged. Use `CredentialFilter` (in `logging_config.py`) which detects and redacts patterns like `password=`, `pwd=`, `secret=`, `token=`, `key=`, `credential=` in log messages.

**Logging output destinations (MCP compliance):**
- File: Primary destination (always safe)
- Stderr: Only for WARNING and above (safe, does not corrupt JSON-RPC)
- Stdout: NEVER (corrupts JSON-RPC protocol)

## Comments

**When to Comment:**
- Module docstrings always present (explain purpose, not obvious from filename)
- Class docstrings always present (explain responsibility and constraints)
- Function docstrings always present (explain purpose, args, return, raises)
- Complex business logic with explanatory comments (why, not what)
- Multi-step validation sequences with inline comments explaining each check
- Critical security/compliance notes in comments (e.g., "NFR-005 compliance")

**JSDoc/TSDoc:**
- Python uses docstrings (not JSDoc)
- All public functions include Args, Returns, Raises sections
- Format: Google-style docstrings

**Example docstring:**
```python
def connect(
    self,
    server: str,
    database: str,
    username: str | None = None,
    password: str | None = None,
    port: int = 1433,
    authentication_method: AuthenticationMethod = AuthenticationMethod.SQL,
) -> Connection:
    """Create a database connection and return Connection object.

    Args:
        server: SQL Server host (hostname or IP)
        database: Database name
        username: Username (required for SQL/Azure AD auth)
        password: Password (required for SQL/Azure AD auth)
        port: SQL Server port (default: 1433)
        authentication_method: Authentication method

    Returns:
        Connection object with connection metadata

    Raises:
        ConnectionError: If connection fails
        ValueError: If required credentials are missing
    """
```

## Function Design

**Size:** Functions kept reasonably scoped (typically < 50 lines for non-trivial functions)

**Parameters:**
- Use keyword arguments for functions with multiple boolean or enum parameters
- Validate all input parameters at function start
- Use default values for optional parameters
- Avoid mutable defaults (use `field(default_factory=list)` in dataclasses)

**Return Values:**
- Always include return type annotation
- Return None explicitly if no return value
- Return typed objects (dataclasses) not dicts for structured data
- Use context managers (`with` statements) for resource cleanup

**Example function structure:**
```python
def validate_list_tables_params(
    limit: int,
    offset: int,
    object_type: str | None,
    sort_by: str,
) -> str | None:
    """Validate parameters, returning error message or None on success."""
    # Validation checks
    if limit < 1:
        return "limit must be at least 1"
    if limit > 1000:
        return "limit cannot exceed 1000"
    if offset < 0:
        return "offset cannot be negative"
    # ...
    return None  # All valid
```

## Module Design

**Exports:**
- Each module has clear responsibility
- Private functions/classes prefixed with `_` are not exported
- MCP tools explicitly imported in `server.py` via `from src.mcp_server.xxx_tools import tool_name`
- Service classes used internally by tools: `QueryService`, `MetadataService`, `ColumnStatsCollector`

**Barrel Files:**
- `__init__.py` files exist but are mostly empty
- Explicit imports preferred over barrel imports
- No `from module import *` anywhere in codebase

**Example module organization:**
```python
"""Module docstring explaining purpose."""

# Imports organized by group

# Logging setup
logger = get_logger(__name__)

# Constants
CONSTANT_NAME = value

# Custom exceptions
class CustomError(Exception):
    """Docstring."""
    pass

# Main classes/functions
class MainService:
    """Docstring."""
    pass

def public_function():
    """Docstring."""
    pass

def _private_helper():
    """Docstring."""
    pass
```

---

*Convention analysis: 2026-03-03*
