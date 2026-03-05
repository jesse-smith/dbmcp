"""Integration tests for get_column_info MCP tool (US1).

Tests cover:
- All-columns request (no filters)
- Column name list filter
- Column pattern filter
- Default schema behavior
- Invalid connection/table/column error responses
- Columns-takes-precedence-over-pattern behavior

Tests end-to-end behavior against a real SQL Server test database.
Requires TEST_DB_SERVER, TEST_DB_DATABASE, TEST_DB_USERNAME, TEST_DB_PASSWORD
environment variables.
"""

import os

import pytest

from tests.helpers import parse_tool_response

# Skip all integration tests if env vars not set
pytestmark = pytest.mark.skipif(
    not os.environ.get("TEST_DB_SERVER"),
    reason="Integration test requires TEST_DB_SERVER environment variable",
)


@pytest.fixture(scope="module")
def connection_id():
    """Create a test database connection and return connection_id."""
    server = os.environ["TEST_DB_SERVER"]
    database = os.environ["TEST_DB_DATABASE"]
    username = os.environ.get("TEST_DB_USERNAME")
    password = os.environ.get("TEST_DB_PASSWORD")

    import asyncio

    from src.mcp_server.schema_tools import connect_database

    result = asyncio.get_event_loop().run_until_complete(
        connect_database(
            server=server,
            database=database,
            username=username,
            password=password,
            trust_server_cert=True,
        )
    )
    data = parse_tool_response(result)
    assert data["status"] == "success", f"Connection failed: {data}"
    return data["connection_id"]


@pytest.fixture(scope="module")
def db_engine():
    """Create a SQLAlchemy engine for direct SQL execution in test setup."""
    from sqlalchemy import create_engine

    server = os.environ["TEST_DB_SERVER"]
    database = os.environ["TEST_DB_DATABASE"]
    username = os.environ.get("TEST_DB_USERNAME", "")
    password = os.environ.get("TEST_DB_PASSWORD", "")

    conn_str = (
        f"mssql+pyodbc://{username}:{password}@{server}/{database}"
        "?driver=ODBC+Driver+18+for+SQL+Server&TrustServerCertificate=yes"
    )
    return create_engine(conn_str)


@pytest.fixture(autouse=True)
def cleanup_test_tables(db_engine):
    """Drop test tables after each test to avoid collisions."""
    yield
    from sqlalchemy import text

    test_tables = [
        "test_all_columns", "test_filter", "test_pattern", "test_precedence",
        "test_empty_pattern", "test_default_schema", "test_sample_size",
        "test_column_error", "test_all_null", "test_empty", "test_mixed_types",
    ]
    with db_engine.connect() as conn:
        for table in test_tables:
            conn.execute(text(f"IF OBJECT_ID('dbo.{table}', 'U') IS NOT NULL DROP TABLE dbo.{table}"))
        conn.commit()


class TestGetColumnInfoBasic:
    """Test basic get_column_info functionality."""

    @pytest.mark.asyncio
    async def test_all_columns_request(self, connection_id, db_engine):
        """Request column info for all columns in a table."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_all_columns (
                    id INT PRIMARY KEY,
                    name VARCHAR(100),
                    created_date DATETIME,
                    price DECIMAL(10,2),
                    is_active BIT
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_all_columns VALUES
                (1, 'Product A', '2025-01-01 10:30:00', 99.99, 1),
                (2, 'Product B', '2025-01-02 14:45:00', 149.50, 1),
                (3, 'Product C', '2025-01-03 09:15:00', 79.99, 0)
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_all_columns",
            schema_name="dbo",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["table_name"] == "test_all_columns"
        assert result["schema_name"] == "dbo"
        assert result["total_columns_analyzed"] == 5

        column_names = [col["column_name"] for col in result["columns"]]
        assert set(column_names) == {"id", "name", "created_date", "price", "is_active"}

        # Verify numeric stats for id column
        id_col = next(col for col in result["columns"] if col["column_name"] == "id")
        assert id_col["data_type"] == "int"
        assert id_col["total_rows"] == 3
        assert id_col["distinct_count"] == 3
        assert id_col["null_count"] == 0
        assert "numeric_stats" in id_col
        assert id_col["numeric_stats"]["min_value"] == 1.0
        assert id_col["numeric_stats"]["max_value"] == 3.0

        # Verify string stats for name column
        name_col = next(col for col in result["columns"] if col["column_name"] == "name")
        assert "string_stats" in name_col
        assert name_col["string_stats"]["min_length"] == 9
        assert name_col["string_stats"]["max_length"] == 9

        # Verify datetime stats for created_date column
        date_col = next(col for col in result["columns"] if col["column_name"] == "created_date")
        assert "datetime_stats" in date_col
        assert date_col["datetime_stats"]["has_time_component"] is True


class TestGetColumnInfoFiltering:
    """Test column filtering behavior."""

    @pytest.mark.asyncio
    async def test_filter_by_column_name_list(self, connection_id, db_engine):
        """Filter by explicit column name list."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_filter (
                    id INT,
                    name VARCHAR(50),
                    email VARCHAR(100),
                    phone VARCHAR(20),
                    address VARCHAR(200)
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_filter VALUES
                (1, 'Alice', 'alice@example.com', '555-1234', '123 Main St'),
                (2, 'Bob', 'bob@example.com', '555-5678', '456 Oak Ave')
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_filter",
            schema_name="dbo",
            columns=["id", "name", "email"],
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["total_columns_analyzed"] == 3
        column_names = [col["column_name"] for col in result["columns"]]
        assert column_names == ["id", "name", "email"]

    @pytest.mark.asyncio
    async def test_filter_by_like_pattern(self, connection_id, db_engine):
        """Filter by SQL LIKE pattern."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_pattern (
                    customer_id INT,
                    order_id INT,
                    product_id INT,
                    name VARCHAR(50),
                    description TEXT
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_pattern VALUES
                (1, 100, 200, 'Order A', 'First order'),
                (2, 101, 201, 'Order B', 'Second order')
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_pattern",
            schema_name="dbo",
            column_pattern="%_id",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["total_columns_analyzed"] == 3
        column_names = [col["column_name"] for col in result["columns"]]
        assert set(column_names) == {"customer_id", "order_id", "product_id"}

    @pytest.mark.asyncio
    async def test_columns_takes_precedence_over_pattern(self, connection_id, db_engine):
        """When both columns and pattern provided, columns takes precedence."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_precedence (
                    id INT,
                    customer_id INT,
                    order_id INT,
                    name VARCHAR(50)
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_precedence VALUES
                (1, 100, 200, 'Test')
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_precedence",
            schema_name="dbo",
            columns=["id", "name"],
            column_pattern="%_id",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["total_columns_analyzed"] == 2
        column_names = [col["column_name"] for col in result["columns"]]
        assert column_names == ["id", "name"]

    @pytest.mark.asyncio
    async def test_empty_pattern_match(self, connection_id, db_engine):
        """Pattern matches no columns returns empty result (not error)."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_empty_pattern (
                    id INT,
                    name VARCHAR(50)
                )
            """))
            conn.execute(text("INSERT INTO dbo.test_empty_pattern VALUES (1, 'Test')"))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_empty_pattern",
            schema_name="dbo",
            column_pattern="%_xyz",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["total_columns_analyzed"] == 0
        assert result["columns"] == []


class TestGetColumnInfoDefaultSchema:
    """Test default schema behavior."""

    @pytest.mark.asyncio
    async def test_default_schema_dbo(self, connection_id, db_engine):
        """When schema_name not provided, defaults to 'dbo'."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_default_schema (
                    id INT,
                    name VARCHAR(50)
                )
            """))
            conn.execute(text("INSERT INTO dbo.test_default_schema VALUES (1, 'Test')"))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_default_schema",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["schema_name"] == "dbo"
        assert result["total_columns_analyzed"] > 0


class TestGetColumnInfoSampleSize:
    """Test sample_size parameter for string columns."""

    @pytest.mark.asyncio
    async def test_custom_sample_size(self, connection_id, db_engine):
        """Specify custom sample_size for string column top values."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_sample_size (
                    id INT,
                    category VARCHAR(50)
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_sample_size VALUES
                (1, 'A'), (2, 'A'), (3, 'A'),
                (4, 'B'), (5, 'B'),
                (6, 'C'), (7, 'D'), (8, 'E'),
                (9, 'F'), (10, 'G')
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_sample_size",
            schema_name="dbo",
            columns=["category"],
            sample_size=3,
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        category_col = result["columns"][0]
        assert "string_stats" in category_col
        assert len(category_col["string_stats"]["sample_values"]) <= 3
        assert category_col["string_stats"]["sample_values"][0][0] == "A"
        assert category_col["string_stats"]["sample_values"][0][1] == 3


class TestGetColumnInfoErrorHandling:
    """Test error responses."""

    @pytest.mark.asyncio
    async def test_invalid_connection_id(self):
        """Invalid connection_id returns error."""
        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id="nonexistent_connection",
            table_name="test_table",
            schema_name="dbo",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "error"
        assert "nonexistent_connection" in result["error_message"]

    @pytest.mark.asyncio
    async def test_table_not_found(self, connection_id):
        """Table not found returns error."""
        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="nonexistent_table",
            schema_name="dbo",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()
        assert "nonexistent_table" in result["error_message"]

    @pytest.mark.asyncio
    async def test_column_not_found_explicit_list(self, connection_id, db_engine):
        """Column not found in explicit list returns error."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_column_error (
                    id INT,
                    name VARCHAR(50)
                )
            """))
            conn.execute(text("INSERT INTO dbo.test_column_error VALUES (1, 'Test')"))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_column_error",
            schema_name="dbo",
            columns=["id", "nonexistent_column"],
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "error"
        assert "not found" in result["error_message"].lower()
        assert "nonexistent_column" in result["error_message"]


class TestGetColumnInfoEdgeCases:
    """Test edge cases."""

    @pytest.mark.asyncio
    async def test_all_null_column(self, connection_id, db_engine):
        """Column with all NULL values returns valid stats."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_all_null (
                    id INT,
                    nullable_col VARCHAR(50)
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_all_null VALUES
                (1, NULL),
                (2, NULL),
                (3, NULL)
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_all_null",
            schema_name="dbo",
            columns=["nullable_col"],
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        col = result["columns"][0]
        assert col["total_rows"] == 3
        assert col["distinct_count"] == 0
        assert col["null_count"] == 3
        assert col["null_percentage"] == 100.0

    @pytest.mark.asyncio
    async def test_zero_row_table(self, connection_id, db_engine):
        """Empty table returns valid stats with zero counts."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_empty (
                    id INT,
                    name VARCHAR(50)
                )
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_empty",
            schema_name="dbo",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["total_columns_analyzed"] == 2
        for col in result["columns"]:
            assert col["total_rows"] == 0
            assert col["distinct_count"] == 0
            assert col["null_count"] == 0
            assert col["null_percentage"] == 0.0

    @pytest.mark.asyncio
    async def test_mixed_data_types(self, connection_id, db_engine):
        """Table with all supported data types."""
        from sqlalchemy import text

        with db_engine.connect() as conn:
            conn.execute(text("""
                CREATE TABLE dbo.test_mixed_types (
                    int_col INT,
                    bigint_col BIGINT,
                    decimal_col DECIMAL(10,2),
                    varchar_col VARCHAR(100),
                    nvarchar_col NVARCHAR(100),
                    text_col TEXT,
                    date_col DATE,
                    datetime_col DATETIME,
                    datetime2_col DATETIME2,
                    bit_col BIT
                )
            """))
            conn.execute(text("""
                INSERT INTO dbo.test_mixed_types VALUES
                (1, 1000000, 99.99, 'text', N'unicode', 'long text',
                 '2025-01-01', '2025-01-01 10:00:00', '2025-01-01 10:00:00.123', 1)
            """))
            conn.commit()

        from src.mcp_server.analysis_tools import get_column_info

        result_json = await get_column_info(
            connection_id=connection_id,
            table_name="test_mixed_types",
            schema_name="dbo",
        )

        result = parse_tool_response(result_json)

        assert result["status"] == "success"
        assert result["total_columns_analyzed"] == 10

        for col in result["columns"]:
            if "int" in col["data_type"].lower() or "decimal" in col["data_type"].lower():
                assert "numeric_stats" in col
            elif "date" in col["data_type"].lower():
                assert "datetime_stats" in col
            elif "varchar" in col["data_type"].lower() or "text" in col["data_type"].lower():
                assert "string_stats" in col
