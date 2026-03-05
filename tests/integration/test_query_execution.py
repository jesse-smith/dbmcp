"""Integration tests for query execution MCP tool.

Tests cover:
- Execute SELECT queries
- Row limit enforcement
- Read-only blocking (INSERT, UPDATE, DELETE)
- Result formatting
- Error handling
"""

from unittest.mock import MagicMock, patch

import pytest

from tests.helpers import parse_tool_response


class TestExecuteQueryMCPTool:
    """Integration tests for execute_query MCP tool."""

    @pytest.mark.asyncio
    async def test_execute_select_query(self):
        """Test executing a basic SELECT query."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            # Setup mock engine with query result
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"

            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "name", "email"]
            mock_result.fetchall.return_value = [
                (1, "Alice", "alice@example.com"),
                (2, "Bob", "bob@example.com"),
            ]

            mock_conn = MagicMock()
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT * FROM customers",
                row_limit=10,
            )

            data = parse_tool_response(result)
            assert data["status"] == "success"
            assert "columns" in data
            assert "rows" in data
            assert data["rows_returned"] == 2
            assert "execution_time_ms" in data

    @pytest.mark.asyncio
    async def test_execute_query_with_where_clause(self):
        """Test executing SELECT with WHERE clause."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"

            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "name"]
            mock_result.fetchall.return_value = [(1, "Alice")]

            mock_conn = MagicMock()
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT * FROM customers WHERE customer_id = 1",
                row_limit=100,
            )

            data = parse_tool_response(result)
            assert data["status"] == "success"
            assert len(data["rows"]) == 1

    @pytest.mark.asyncio
    async def test_row_limit_enforced(self):
        """Test that row_limit is enforced via LIMIT clause."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"

            mock_result = MagicMock()
            mock_result.keys.return_value = ["id", "name"]
            mock_result.fetchall.return_value = [(1, "A"), (2, "B")]

            mock_conn = MagicMock()
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT * FROM customers",
                row_limit=2,
            )

            data = parse_tool_response(result)
            assert data["status"] == "success"
            # Verify LIMIT was added to the query (first call is the main query)
            first_call = mock_conn.execute.call_args_list[0]
            executed_query = first_call[0][0].text
            assert "LIMIT 2" in executed_query.upper()

    @pytest.mark.asyncio
    async def test_blocked_delete_query(self):
        """Test DELETE query is blocked."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="DELETE FROM customers WHERE customer_id = 9999",
                row_limit=100,
            )

            data = parse_tool_response(result)
            assert data["status"] == "blocked"
            assert data["is_allowed"] is False
            assert data["query_type"] == "delete"
            assert "error_message" in data

    @pytest.mark.asyncio
    async def test_blocked_update_query(self):
        """Test UPDATE query is blocked."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="UPDATE customers SET email='test' WHERE customer_id = 9999",
                row_limit=100,
            )

            data = parse_tool_response(result)
            assert data["status"] == "blocked"
            assert data["is_allowed"] is False
            assert data["query_type"] == "update"

    @pytest.mark.asyncio
    async def test_blocked_insert_query(self):
        """Test INSERT query is blocked."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="INSERT INTO customers (email) VALUES ('test@test.com')",
                row_limit=100,
            )

            data = parse_tool_response(result)
            assert data["status"] == "blocked"
            assert data["is_allowed"] is False
            assert data["query_type"] == "insert"

    @pytest.mark.asyncio
    async def test_row_limit_validation_min(self):
        """Test row_limit minimum validation."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT * FROM customers",
                row_limit=0,
            )

            data = parse_tool_response(result)
            assert data["status"] == "error"
            assert "row_limit" in data["error_message"].lower()

    @pytest.mark.asyncio
    async def test_row_limit_validation_max(self):
        """Test row_limit maximum validation."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT * FROM customers",
                row_limit=10001,
            )

            data = parse_tool_response(result)
            assert data["status"] == "error"
            assert "row_limit" in data["error_message"].lower()

    @pytest.mark.asyncio
    async def test_empty_query_validation(self):
        """Test empty query returns error."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="",
                row_limit=100,
            )

            data = parse_tool_response(result)
            assert data["status"] == "error"
            assert "query_text" in data["error_message"].lower() or "empty" in data["error_message"].lower()

    @pytest.mark.asyncio
    async def test_invalid_connection_id(self):
        """Test invalid connection_id returns error."""
        from src.mcp_server.server import execute_query

        result = await execute_query(
            connection_id="invalid_connection",
            query_text="SELECT 1",
            row_limit=100,
        )

        data = parse_tool_response(result)
        assert data["status"] == "error"
        assert "error_message" in data

    @pytest.mark.asyncio
    async def test_query_result_structure(self):
        """Test query result has expected structure."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"

            mock_result = MagicMock()
            mock_result.keys.return_value = ["customer_id", "first_name", "email"]
            mock_result.fetchall.return_value = [
                (1, "Alice", "alice@example.com"),
            ]

            mock_conn = MagicMock()
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT customer_id, first_name, email FROM customers",
                row_limit=5,
            )

            data = parse_tool_response(result)
            assert data["status"] == "success"

            # Check required fields
            assert "query_id" in data
            assert "query_type" in data
            assert "is_allowed" in data
            assert "columns" in data
            assert "rows" in data
            assert "rows_returned" in data
            assert "execution_time_ms" in data

            # Check column structure
            assert "customer_id" in data["columns"]
            assert "first_name" in data["columns"]
            assert "email" in data["columns"]

            # Check rows are dicts
            if data["rows"]:
                assert isinstance(data["rows"][0], dict)

    @pytest.mark.asyncio
    async def test_select_with_aggregation(self):
        """Test SELECT with COUNT aggregation."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"

            mock_result = MagicMock()
            mock_result.keys.return_value = ["total"]
            mock_result.fetchall.return_value = [(42,)]

            mock_conn = MagicMock()
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="SELECT COUNT(*) as total FROM customers",
                row_limit=100,
            )

            data = parse_tool_response(result)
            assert data["status"] == "success"
            assert len(data["rows"]) == 1
            assert "total" in data["columns"]
            assert data["rows"][0]["total"] == 42

    @pytest.mark.asyncio
    async def test_select_with_join(self):
        """Test SELECT with JOIN."""
        from src.mcp_server.server import execute_query, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = MagicMock()
            mock_engine.dialect.name = "sqlite"

            mock_result = MagicMock()
            mock_result.keys.return_value = ["first_name", "order_id"]
            mock_result.fetchall.return_value = [
                ("Alice", 101),
                ("Alice", 102),
                ("Bob", 201),
            ]

            mock_conn = MagicMock()
            mock_conn.execute.return_value = mock_result
            mock_engine.connect.return_value.__enter__.return_value = mock_conn
            mock_get_engine.return_value = mock_engine

            result = await execute_query(
                connection_id="test123",
                query_text="""
                    SELECT c.first_name, o.order_id
                    FROM customers c
                    JOIN orders o ON c.customer_id = o.customer_id
                """,
                row_limit=10,
            )

            data = parse_tool_response(result)
            assert data["status"] == "success"
            assert "first_name" in data["columns"]
            assert "order_id" in data["columns"]
            assert len(data["rows"]) == 3
