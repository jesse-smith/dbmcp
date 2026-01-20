"""Integration tests for database discovery MCP tools.

Tests for list_schemas, list_tables MCP tools.
These tests require mocked MCP server responses.
"""

import json
import pytest
from unittest.mock import patch, MagicMock

from tests.utils import create_mock_engine, SAMPLE_SCHEMA_ROWS, SAMPLE_TABLE_ROWS


class TestListSchemasMCPTool:
    """Integration tests for list_schemas MCP tool - T014A"""

    @pytest.mark.asyncio
    async def test_list_schemas_returns_json(self):
        """T014A: Verify list_schemas returns valid JSON."""
        from src.mcp_server.server import list_schemas, get_connection_manager

        # Mock the connection manager
        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = create_mock_engine({
                "sys.schemas": SAMPLE_SCHEMA_ROWS,
            })
            mock_get_engine.return_value = mock_engine

            result = await list_schemas("test123")

            # Should be valid JSON
            data = json.loads(result)
            assert "schemas" in data
            assert "total_schemas" in data

    @pytest.mark.asyncio
    async def test_list_schemas_schema_grouping(self):
        """T014A: Verify schema grouping response format."""
        from src.mcp_server.server import list_schemas, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = create_mock_engine({
                "sys.schemas": SAMPLE_SCHEMA_ROWS,
            })
            mock_get_engine.return_value = mock_engine

            result = await list_schemas("test123")
            data = json.loads(result)

            # Each schema should have required fields
            for schema in data["schemas"]:
                assert "schema_name" in schema
                assert "table_count" in schema
                assert "view_count" in schema

    @pytest.mark.asyncio
    async def test_list_schemas_invalid_connection(self):
        """T014A: Verify error handling for invalid connection."""
        from src.mcp_server.server import list_schemas

        result = await list_schemas("nonexistent_connection")
        data = json.loads(result)

        assert "error" in data


class TestListTablesMCPTool:
    """Integration tests for list_tables MCP tool - T015A"""

    @pytest.mark.asyncio
    async def test_list_tables_schema_filter(self):
        """T015A: Verify schema_filter parameter works."""
        from src.mcp_server.server import list_tables, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            dbo_tables = [t for t in SAMPLE_TABLE_ROWS if t["schema_name"] == "dbo"]
            mock_engine = create_mock_engine({
                "sys.tables": dbo_tables,
            })
            mock_get_engine.return_value = mock_engine

            result = await list_tables("test123", schema_filter=["dbo"])
            data = json.loads(result)

            # All tables should be from dbo schema
            for table in data["tables"]:
                assert table["schema_name"] == "dbo"

    @pytest.mark.asyncio
    async def test_list_tables_name_pattern(self):
        """T015A: Verify name_pattern filter works."""
        from src.mcp_server.server import list_tables, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            # Filter to Customer% pattern
            customer_tables = [t for t in SAMPLE_TABLE_ROWS if t["table_name"].startswith("Customer")]
            mock_engine = create_mock_engine({
                "sys.tables": customer_tables,
            })
            mock_get_engine.return_value = mock_engine

            result = await list_tables("test123", name_pattern="Customer%")
            data = json.loads(result)

            for table in data["tables"]:
                assert table["table_name"].startswith("Customer")

    @pytest.mark.asyncio
    async def test_list_tables_min_row_count(self):
        """T015A: Verify min_row_count filter works."""
        from src.mcp_server.server import list_tables, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            # Filter to tables with >= 1000 rows
            large_tables = [t for t in SAMPLE_TABLE_ROWS if t["row_count"] >= 1000]
            mock_engine = create_mock_engine({
                "sys.tables": large_tables,
            })
            mock_get_engine.return_value = mock_engine

            result = await list_tables("test123", min_row_count=1000)
            data = json.loads(result)

            for table in data["tables"]:
                assert table["row_count"] >= 1000


class TestOutputMode:
    """Integration tests for output_mode parameter - T017A"""

    @pytest.mark.asyncio
    async def test_summary_mode_token_efficiency(self):
        """T017A: Verify summary mode reduces token size."""
        from src.mcp_server.server import list_tables, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = create_mock_engine({
                "sys.tables": SAMPLE_TABLE_ROWS,
            })
            mock_get_engine.return_value = mock_engine

            # Get summary mode result
            summary_result = await list_tables("test123", output_mode="summary")
            summary_data = json.loads(summary_result)

            # Summary should not include columns
            for table in summary_data["tables"]:
                assert "columns" not in table

    @pytest.mark.asyncio
    async def test_detailed_mode_includes_columns(self):
        """T017A: Verify detailed mode includes column information."""
        from src.mcp_server.server import list_tables, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = create_mock_engine({
                "sys.tables": SAMPLE_TABLE_ROWS,
            })
            mock_get_engine.return_value = mock_engine

            # Mock inspector for column retrieval
            with patch("src.db.metadata.inspect") as mock_inspect:
                mock_inspector = MagicMock()
                mock_inspector.get_columns.return_value = [
                    {"name": "ID", "type": MagicMock(__str__=lambda x: "INT"), "nullable": False}
                ]
                mock_inspector.get_pk_constraint.return_value = {"constrained_columns": ["ID"]}
                mock_inspector.get_foreign_keys.return_value = []
                mock_inspect.return_value = mock_inspector

                detailed_result = await list_tables("test123", output_mode="detailed")
                detailed_data = json.loads(detailed_result)

                # Detailed should include columns
                if detailed_data["tables"]:
                    assert "columns" in detailed_data["tables"][0]


class TestLimitEnforcement:
    """Integration tests for limit enforcement - T018A"""

    @pytest.mark.asyncio
    async def test_limit_parameter_enforced(self):
        """T018A: Verify limit parameter is respected."""
        from src.mcp_server.server import list_tables, get_connection_manager

        with patch.object(get_connection_manager(), "get_engine") as mock_get_engine:
            mock_engine = create_mock_engine({
                "sys.tables": SAMPLE_TABLE_ROWS,
            })
            mock_get_engine.return_value = mock_engine

            result = await list_tables("test123", limit=2)
            data = json.loads(result)

            assert len(data["tables"]) <= 2

    @pytest.mark.asyncio
    async def test_limit_error_on_exceeding_max(self):
        """T018A: Verify error when limit exceeds 1000."""
        from src.mcp_server.server import list_tables

        result = await list_tables("test123", limit=1500)
        data = json.loads(result)

        assert "error" in data
        assert "1000" in data["error"]

    @pytest.mark.asyncio
    async def test_limit_error_on_zero(self):
        """T018A: Verify error when limit is 0 or negative."""
        from src.mcp_server.server import list_tables

        result = await list_tables("test123", limit=0)
        data = json.loads(result)

        assert "error" in data
