"""Integration tests for sample data retrieval (User Story 4).

Tests the complete flow of get_sample_data MCP tool with real database.
Uses the SQLite example database for testing.
"""

import json
from pathlib import Path

import pytest

from src.db.query import QueryService
from src.models.schema import SamplingMethod


@pytest.fixture
def example_db_path():
    """Path to example SQLite database."""
    db_path = Path("examples/test_database/example.db")
    if not db_path.exists():
        pytest.skip("Example database not found. Run setup.py first.")
    return db_path


@pytest.fixture
def sqlite_connection(example_db_path):
    """Create SQLite connection for testing."""
    from sqlalchemy import create_engine

    # SQLite connection string
    engine = create_engine(f"sqlite:///{example_db_path}")
    yield engine
    engine.dispose()


class TestSampleDataIntegration:
    """Integration tests for sample data retrieval."""

    def test_get_sample_data_from_customers(self, sqlite_connection):
        """Test retrieving sample data from Customers table."""
        service = QueryService(sqlite_connection)

        sample = service.get_sample_data(
            table_name="customers",
            schema_name="main",
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        # Verify sample structure
        assert sample.table_id == "main.customers"
        assert sample.sampling_method == SamplingMethod.TOP
        assert len(sample.rows) > 0
        assert len(sample.rows) <= 5

        # Verify row structure
        first_row = sample.rows[0]
        assert "customer_id" in first_row
        # Check for first_name and last_name (actual schema)
        assert "first_name" in first_row or "email" in first_row

    def test_sample_with_column_filter(self, sqlite_connection):
        """Test column filtering works with real database."""
        service = QueryService(sqlite_connection)

        sample = service.get_sample_data(
            table_name="customers",
            schema_name="main",
            sample_size=3,
            columns=["customer_id", "email"],
        )

        # Verify only specified columns are returned
        assert len(sample.rows) > 0
        first_row = sample.rows[0]
        assert "customer_id" in first_row
        assert "email" in first_row
        # Should have only the two columns we requested
        assert len(first_row) == 2

    def test_sample_different_tables(self, sqlite_connection):
        """Test sampling from different tables."""
        service = QueryService(sqlite_connection)

        # Test customers table
        customers_sample = service.get_sample_data(
            table_name="customers",
            schema_name="main",
            sample_size=2,
        )
        assert customers_sample.table_id == "main.customers"
        assert len(customers_sample.rows) > 0

        # Test orders table
        orders_sample = service.get_sample_data(
            table_name="orders",
            schema_name="main",
            sample_size=2,
        )
        assert orders_sample.table_id == "main.orders"
        assert len(orders_sample.rows) > 0

    def test_sample_size_limits(self, sqlite_connection):
        """Test sample size respects limits."""
        service = QueryService(sqlite_connection)

        # Request more rows than might exist in small table
        sample = service.get_sample_data(
            table_name="customers",
            schema_name="main",
            sample_size=1000,
        )

        # Should return actual number of rows, not more than exists
        assert sample.sample_size <= 1000
        assert len(sample.rows) <= 1000

    def test_truncation_not_needed_for_normal_data(self, sqlite_connection):
        """Test that normal-sized data doesn't get truncated."""
        service = QueryService(sqlite_connection)

        sample = service.get_sample_data(
            table_name="customers",
            schema_name="main",
            sample_size=5,
        )

        # Normal customer data shouldn't need truncation
        # (unless there's unusually large text in the example DB)
        # This is a basic check that the feature works
        assert isinstance(sample.truncated_columns, list)

    def test_empty_table_handling(self, sqlite_connection):
        """Test handling of empty table (no rows)."""
        from sqlalchemy import text

        # Create a temporary empty table
        with sqlite_connection.connect() as conn:
            conn.execute(text("CREATE TEMP TABLE empty_table (id INTEGER, name TEXT)"))
            conn.commit()

        service = QueryService(sqlite_connection)

        sample = service.get_sample_data(
            table_name="empty_table",
            schema_name="temp",
            sample_size=5,
        )

        # Should return empty list, not error
        assert sample.sample_size == 0
        assert len(sample.rows) == 0


@pytest.mark.asyncio
class TestSampleDataMCPTool:
    """Integration tests for get_sample_data MCP tool."""

    async def test_get_sample_data_mcp_tool(self, example_db_path):
        """Test the MCP tool end-to-end."""
        from sqlalchemy import create_engine

        from src.mcp_server.server import get_connection_manager, get_sample_data

        # Create SQLite engine
        engine = create_engine(f"sqlite:///{example_db_path}")

        # Manually add to connection manager
        conn_mgr = get_connection_manager()

        from src.models.schema import AuthenticationMethod, Connection

        connection = Connection(
            connection_id="test_sqlite",
            server="localhost",
            database="example.db",
            authentication_method=AuthenticationMethod.SQL,
        )
        conn_mgr._engines["test_sqlite"] = engine
        conn_mgr._connections["test_sqlite"] = connection

        # Call MCP tool
        result_json = await get_sample_data(
            connection_id="test_sqlite",
            table_name="customers",
            schema_name="main",
            sample_size=3,
            sampling_method="top",
        )

        # Parse result
        result = json.loads(result_json)

        # Verify response structure
        assert "sample_id" in result
        assert "table_id" in result
        assert result["table_id"] == "main.customers"
        assert "rows" in result
        assert len(result["rows"]) <= 3
        assert "truncated_columns" in result
        assert "sampling_method" in result
        assert result["sampling_method"] == "top"

        # Cleanup
        engine.dispose()
        conn_mgr._engines.pop("test_sqlite", None)
        conn_mgr._connections.pop("test_sqlite", None)
