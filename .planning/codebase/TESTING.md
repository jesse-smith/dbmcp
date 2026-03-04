# Testing Patterns

**Analysis Date:** 2026-03-03

## Test Framework

**Runner:**
- pytest 7.0.0+
- Config: `pyproject.toml` under `[tool.pytest.ini_options]`

**Assertion Library:**
- pytest built-in assertions: `assert x == y`, `assert condition`
- pytest.raises() for exception testing: `with pytest.raises(ValueError, match="pattern"):`

**Run Commands:**
```bash
uv run pytest tests/                           # Run all tests
uv run pytest tests/unit/                      # Run unit tests only
uv run pytest tests/integration/               # Run integration tests only
uv run pytest tests/ -m "not integration"      # Skip integration tests
uv run pytest tests/ -m "not slow"             # Skip slow tests
uv run pytest tests/ -v                        # Verbose output
uv run pytest tests/ --tb=short                # Shorter tracebacks (configured default)
uv run pytest tests/ --cov=src --cov-report=html  # Coverage report
```

**Async Support:**
- Framework: pytest-asyncio 0.21.0+
- Config: `asyncio_mode = "auto"` (in pytest.ini_options)
- Scope: `asyncio_default_fixture_loop_scope = "function"` (per-function loop)
- All MCP tools are async: `async def tool_name():`

## Test File Organization

**Location:**
- Unit tests: `tests/unit/` directory
- Integration tests: `tests/integration/` directory
- Co-located is NOT used (separate directory structure)

**Naming:**
- Pattern: `test_<module_name>.py` (e.g., `test_connection.py`, `test_validation.py`)
- Maps to source module: `test_connection.py` tests `src/db/connection.py`
- Follows pytest convention: `python_files = ["test_*.py"]`

**Structure:**
```
tests/
├── conftest.py                  # Root fixtures shared by all tests
├── unit/
│   ├── __init__.py
│   ├── test_connection.py
│   ├── test_validation.py
│   ├── test_query.py
│   ├── test_metadata.py
│   ├── test_azure_auth.py
│   ├── test_analysis_models.py
│   ├── test_pk_discovery.py
│   ├── test_column_stats.py
│   └── test_fk_candidates.py
├── integration/
│   ├── __init__.py
│   ├── conftest.py              # Integration-specific fixtures
│   ├── test_azure_ad_auth.py
│   ├── test_discovery.py
│   ├── test_sample_data.py
│   ├── test_query_execution.py
│   ├── test_pk_discovery.py
│   ├── test_get_column_info.py
│   └── test_fk_candidates.py
```

## Test Structure

**Suite Organization:**
```python
class TestFeatureName:
    """Group of related tests for a feature."""

    def test_specific_behavior(self):
        """Test a single, specific behavior."""
        # Arrange: Set up test data
        # Act: Call the function/method
        # Assert: Check results
```

**Patterns:**

1. **Test class organization:**
   - One class per logical feature/component
   - Example: `TestConnectionValidation`, `TestNFR005CredentialSafety`, `TestConnectionIdGeneration`
   - Allows shared fixtures at class level

2. **Test method naming:**
   - Pattern: `test_<behavior_being_tested>` (e.g., `test_password_not_in_connect_logs`)
   - Describe the outcome, not the action
   - Matches pytest convention: `python_functions = ["test_*"]`

3. **Arrangement pattern (Arrange-Act-Assert):**
```python
def test_get_sample_data_top_method(self, mock_engine):
    """Test TOP sampling method returns expected data."""
    # Arrange
    mock_result = MagicMock()
    mock_row = MagicMock()
    mock_row._mapping = {"CustomerID": 1, "CustomerName": "Test"}
    mock_result.__iter__ = lambda x: iter([mock_row])

    mock_conn = MagicMock()
    mock_conn.execute.return_value = mock_result
    mock_engine.connect.return_value.__enter__.return_value = mock_conn

    # Act
    service = QueryService(mock_engine)
    sample = service.get_sample_data(
        table_name="Customers",
        schema_name="dbo",
        sample_size=5,
    )

    # Assert
    assert sample.table_id == "dbo.Customers"
    assert sample.sample_size == 1
    assert sample.rows[0]["CustomerID"] == 1
```

## Mocking

**Framework:** `unittest.mock` (standard library)
- `MagicMock`: Create mock objects with automatic attribute/method creation
- `patch()`: Replace objects during test execution (context manager or decorator)
- `mock.side_effect`: Configure mock to raise exceptions or return different values on successive calls
- `mock.call_args`: Inspect how a mocked function was called

**Patterns:**

1. **Mock SQLAlchemy engine:**
```python
@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine."""
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock()
    engine.connect.return_value.__exit__ = MagicMock()
    return engine
```

2. **Mock database results:**
```python
mock_result = MagicMock()
mock_row = MagicMock()
mock_row._mapping = {"column": value}
mock_result.__iter__ = lambda x: iter([mock_row])
```

3. **Mock function with side_effect (exception):**
```python
with patch("src.db.connection.create_engine") as mock_engine:
    mock_engine.side_effect = Exception("Connection refused")
    with pytest.raises(ConnectionError):
        manager.connect(...)
```

4. **Mock Azure token provider:**
```python
@patch("src.db.connection.AzureTokenProvider")
@patch("src.db.connection.create_engine")
def test_with_azure(mock_create_engine, mock_provider_cls):
    mock_provider = MagicMock()
    mock_provider.get_token.return_value = "fake-token"
    mock_provider_cls.return_value = mock_provider
```

**What to Mock:**
- External dependencies: databases, file systems, network services
- Third-party library objects: `create_engine`, `pyodbc.connect`, `AzureTokenProvider`
- Environment-dependent services for unit tests

**What NOT to Mock:**
- Pure functions: validation, parsing, calculation logic
- In-memory data structures: dataclasses, enums, lists/dicts
- Error handling paths (let them use real exceptions)
- Application code being tested (only mock its dependencies)

## Fixtures and Factories

**Test Data:**

```python
@pytest.fixture
def sample_schemas():
    """Sample schema data for testing."""
    return [
        Schema(
            schema_id="test_dbo",
            connection_id="test123abc",
            schema_name="dbo",
            table_count=10,
            view_count=2,
        ),
        # ... more schemas
    ]

@pytest.fixture
def sample_columns():
    """Sample column data for testing."""
    return [
        Column(
            column_id="dbo.Customers.CustomerID",
            table_id="dbo.Customers",
            column_name="CustomerID",
            ordinal_position=1,
            data_type="INT",
            is_nullable=False,
            is_identity=True,
            is_primary_key=True,
        ),
        # ... more columns
    ]
```

**Location:**
- Root fixtures (shared by all tests): `tests/conftest.py`
- Unit-specific fixtures: `tests/conftest.py` (same file, imported by unit tests)
- Integration-specific fixtures: `tests/integration/conftest.py`

**Fixture scope:**
- Default scope: `"function"` (fresh instance per test)
- Class-scoped fixtures: specified in conftest for efficiency
- Session-scoped fixtures: rare (used for expensive setup like db schema)

## Coverage

**Requirements:** Coverage report enabled but target not enforced in CI

**View Coverage:**
```bash
uv run pytest tests/ --cov=src --cov-report=html
# Opens htmlcov/index.html in browser
```

**Configuration (from `pyproject.toml`):**
```toml
[tool.coverage.run]
source = ["src"]
branch = true

[tool.coverage.report]
exclude_lines = [
    "pragma: no cover",
    "def __repr__",
    "raise NotImplementedError",
    "if __name__ == .__main__.:",
]
```

**Current status:** 385 tests across unit and integration suites (as of 2026-02-27)

## Test Types

**Unit Tests (tests/unit/):**
- Scope: Single function or method in isolation
- Dependencies: Mocked (no real database, network, or file I/O)
- Execution: Fast (< 1 second per test)
- Examples:
  - `test_connection.py`: Connection string building, ID generation, validation
  - `test_validation.py`: Query AST parsing, denial categorization
  - `test_query.py`: Sample data retrieval logic, column filtering
  - `test_metadata.py`: Schema/table discovery logic
  - `test_azure_auth.py`: Token provider behavior

**Integration Tests (tests/integration/):**
- Scope: Multiple components working together
- Dependencies: Real (requires actual SQL Server database connection)
- Execution: Slower (up to several seconds per test)
- Marked with `@pytest.mark.integration`
- Database required: Configured via environment (not in tests)
- Examples:
  - `test_azure_ad_auth.py`: Full Azure AD authentication flow
  - `test_discovery.py`: Schema/table discovery against real database
  - `test_sample_data.py`: Sample data retrieval from real tables
  - `test_query_execution.py`: Query validation and execution
  - `test_pk_discovery.py`: Primary key candidate detection

**E2E Tests:**
- Not currently implemented
- Would require full MCP server deployment + client interaction

## Common Patterns

**Parametrized Testing:**
```python
@pytest.mark.parametrize(
    "sql,category",
    [
        ("INSERT INTO users (name) VALUES ('x')", DenialCategory.DML),
        ("UPDATE users SET name = 'x' WHERE id = 1", DenialCategory.DML),
        ("DELETE FROM users WHERE id = 1", DenialCategory.DML),
        ("CREATE TABLE test (id INT)", DenialCategory.DDL),
    ],
    ids=[
        "insert_statement",
        "update_statement",
        "delete_statement",
        "create_table_statement",
    ]
)
def test_denied_query_categories(self, sql, category):
    """Test that different query types get correct denial category."""
    result = validate_query(sql)
    assert result.is_safe is False
    assert result.reasons[0].category == category
```

**Async Testing:**
```python
@pytest.mark.asyncio
async def test_async_tool_execution():
    """Test MCP tool async execution."""
    result = await get_sample_data(
        connection_id="test123",
        table_name="Customers",
    )
    assert "success" in result  # JSON string response
```

**Error Testing:**
```python
def test_password_not_in_logs(self):
    """Verify password is not logged."""
    with patch("src.db.connection.create_engine") as mock_engine:
        mock_engine.side_effect = Exception("Connection refused")

        with pytest.raises(ConnectionError):
            manager.connect(
                server="localhost",
                database="testdb",
                username="testuser",
                password="SuperSecret!123",
            )

    # Log capture fixture checks logs
    all_logs = " ".join(log_capture)
    assert "SuperSecret!123" not in all_logs
```

**Context Manager Mocking:**
```python
# Mock engine.connect() context manager
mock_connection = MagicMock()
mock_result = MagicMock()
mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019")
mock_connection.execute.return_value = mock_result

mock_engine_instance = MagicMock()
mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
```

## Test Markers

**Markers defined (in pyproject.toml):**

```python
markers = [
    "integration: marks tests as integration tests (deselect with '-m \"not integration\"')",
    "performance: marks tests as performance tests (deselect with '-m \"not performance\"')",
    "slow: marks tests as slow (deselect with '-m \"not slow\"')",
]
```

**Usage:**
```python
@pytest.mark.integration
def test_real_database_connection():
    """This test requires a real database."""
    pass

@pytest.mark.slow
def test_complex_computation():
    """This test takes a long time."""
    pass

@pytest.mark.performance
def test_query_performance():
    """This test measures query performance."""
    pass
```

**Running without slow/integration:**
```bash
uv run pytest tests/ -m "not integration and not slow"
```

---

*Testing analysis: 2026-03-03*
