"""Unit tests for asyncio.to_thread wrapping in MCP tools.

Verifies that all 9 MCP tools use asyncio.to_thread for DB operations,
preventing the async event loop from blocking.

Imports go through src.mcp_server.server to resolve circular imports.
"""

from unittest.mock import patch

# Import through server to resolve circular imports
from src.mcp_server.server import (
    connect_database,
    execute_query,
    find_fk_candidates,
    find_pk_candidates,
    get_column_info,
    get_sample_data,
    get_table_schema,
    list_schemas,
    list_tables,
)

# ---------------------------------------------------------------------------
# Schema Tools: asyncio.to_thread tests
# ---------------------------------------------------------------------------

class TestSchemaToolsAsyncWrapping:
    """Verify schema tools wrap sync DB work in asyncio.to_thread."""

    async def test_connect_database_uses_to_thread(self):
        """connect_database wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "connection_id": "abc123",
                "message": "Connected",
                "schema_count": 1,
                "has_cached_docs": False,
            }

            await connect_database(server="localhost", database="testdb")
            mock_to_thread.assert_called_once()

    async def test_list_schemas_uses_to_thread(self):
        """list_schemas wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "schemas": [],
                "total_schemas": 0,
            }

            await list_schemas(connection_id="test-conn")
            mock_to_thread.assert_called_once()

    async def test_list_tables_uses_to_thread(self):
        """list_tables wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "tables": [],
                "returned_count": 0,
                "total_count": 0,
                "offset": 0,
                "limit": 100,
                "has_more": False,
            }

            await list_tables(connection_id="test-conn")
            mock_to_thread.assert_called_once()

    async def test_get_table_schema_uses_to_thread(self):
        """get_table_schema wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "table": {"table_name": "test", "schema_name": "dbo", "columns": []},
            }

            await get_table_schema(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# Query Tools: asyncio.to_thread tests
# ---------------------------------------------------------------------------

class TestQueryToolsAsyncWrapping:
    """Verify query tools wrap sync DB work in asyncio.to_thread."""

    async def test_get_sample_data_uses_to_thread(self):
        """get_sample_data wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "sample_id": "s1",
                "table_id": "t1",
                "sample_size": 5,
                "actual_rows_returned": 0,
                "sampling_method": "top",
                "rows": [],
                "truncated_columns": [],
                "sampled_at": "2026-01-01T00:00:00",
            }

            await get_sample_data(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()

    async def test_execute_query_uses_to_thread(self):
        """execute_query wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "query_id": "q1",
                "query_type": "SELECT",
                "columns": [],
                "rows": [],
                "rows_returned": 0,
                "rows_available": 0,
                "limited": False,
                "execution_time_ms": 1.0,
            }

            await execute_query(connection_id="test-conn", query_text="SELECT 1")
            mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# Analysis Tools: asyncio.to_thread tests
# ---------------------------------------------------------------------------

class TestAnalysisToolsAsyncWrapping:
    """Verify analysis tools wrap sync DB work in asyncio.to_thread."""

    async def test_get_column_info_uses_to_thread(self):
        """get_column_info wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "table_name": "test",
                "schema_name": "dbo",
                "total_columns_analyzed": 0,
                "columns": [],
            }

            await get_column_info(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()

    async def test_find_pk_candidates_uses_to_thread(self):
        """find_pk_candidates wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "table_name": "test",
                "schema_name": "dbo",
                "candidates": [],
            }

            await find_pk_candidates(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()

    async def test_find_fk_candidates_uses_to_thread(self):
        """find_fk_candidates wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "source": {"column_name": "id", "table_name": "test", "schema_name": "dbo", "data_type": "int"},
                "candidates": [],
                "total_found": 0,
                "was_limited": False,
                "search_scope": "dbo",
            }

            await find_fk_candidates(
                connection_id="test-conn",
                table_name="test",
                column_name="id",
            )
            mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling still works through to_thread
# ---------------------------------------------------------------------------

class TestAsyncErrorHandling:
    """Verify error handling works correctly through asyncio.to_thread wrapping."""

    async def test_list_schemas_value_error_returns_error_response(self):
        """ValueError in sync work is caught and returns error TOON response."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = ValueError("Connection 'bad' not found")

            result = await list_schemas(connection_id="bad")
            assert "error" in result
            assert "not found" in result

    async def test_execute_query_exception_returns_error_response(self):
        """General Exception in sync work is caught and returns error TOON response."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = RuntimeError("DB connection lost")

            result = await execute_query(connection_id="test-conn", query_text="SELECT 1")
            assert "error" in result
            assert "DB connection lost" in result

    async def test_get_column_info_exception_returns_error_response(self):
        """Exception in analysis tool sync work returns error response."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = Exception("Timeout expired")

            result = await get_column_info(connection_id="test-conn", table_name="test")
            assert "error" in result
            assert "Timeout expired" in result


# ---------------------------------------------------------------------------
# Error classification wiring tests
# ---------------------------------------------------------------------------

import pytest
from sqlalchemy.exc import SQLAlchemyError


# All 9 MCP tools with their module path (for patching _classify_db_error)
# and minimal kwargs needed to invoke them past parameter validation into
# the try/except safety net (where asyncio.to_thread is called).
_TOOL_PARAMS = [
    pytest.param(
        connect_database,
        "src.mcp_server.schema_tools",
        {"server": "localhost", "database": "testdb"},
        id="connect_database",
    ),
    pytest.param(
        list_schemas,
        "src.mcp_server.schema_tools",
        {"connection_id": "test-conn"},
        id="list_schemas",
    ),
    pytest.param(
        list_tables,
        "src.mcp_server.schema_tools",
        {"connection_id": "test-conn"},
        id="list_tables",
    ),
    pytest.param(
        get_table_schema,
        "src.mcp_server.schema_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="get_table_schema",
    ),
    pytest.param(
        get_sample_data,
        "src.mcp_server.query_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="get_sample_data",
    ),
    pytest.param(
        execute_query,
        "src.mcp_server.query_tools",
        {"connection_id": "test-conn", "query_text": "SELECT 1"},
        id="execute_query",
    ),
    pytest.param(
        get_column_info,
        "src.mcp_server.analysis_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="get_column_info",
    ),
    pytest.param(
        find_pk_candidates,
        "src.mcp_server.analysis_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="find_pk_candidates",
    ),
    pytest.param(
        find_fk_candidates,
        "src.mcp_server.analysis_tools",
        {"connection_id": "test-conn", "table_name": "test", "column_name": "id"},
        id="find_fk_candidates",
    ),
]


class TestSafetyNetErrorClassification:
    """Verify all 9 MCP tool safety nets wire _classify_db_error for SQLAlchemy errors."""

    @pytest.mark.parametrize("tool_fn,module_path,kwargs", _TOOL_PARAMS)
    async def test_safety_net_classifies_sqlalchemy_errors(
        self, tool_fn, module_path, kwargs
    ):
        """SQLAlchemyError in a tool triggers _classify_db_error and includes guidance."""
        fake_guidance = "Check your credentials (username/password) and verify the account has access to the database."
        raw_error_text = "Login failed for user 'bob'"

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch(
                f"{module_path}._classify_db_error",
                return_value=("auth_failure", fake_guidance),
                create=True,
            ) as mock_classify,
        ):
            mock_to_thread.side_effect = SQLAlchemyError(raw_error_text)
            result = await tool_fn(**kwargs)

            mock_classify.assert_called_once()
            # Guidance text should appear in the response
            assert fake_guidance in result
            # Raw error should also appear (in parens)
            assert raw_error_text in result

    @pytest.mark.parametrize("tool_fn,module_path,kwargs", _TOOL_PARAMS)
    async def test_safety_net_generic_error_fallback(
        self, tool_fn, module_path, kwargs
    ):
        """Non-SQLAlchemy error uses generic fallback, does NOT call _classify_db_error."""
        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch(
                f"{module_path}._classify_db_error",
                create=True,
            ) as mock_classify,
        ):
            mock_to_thread.side_effect = ValueError("something broke")
            result = await tool_fn(**kwargs)

            mock_classify.assert_not_called()
            # Generic fallback should contain the error text
            assert "something broke" in result
