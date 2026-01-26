"""Unit tests for QueryService (sample data retrieval and query execution).

Tests cover:
- Sample data retrieval with different sampling methods
- Parameter validation
- Binary and text truncation
- Column filtering
- Query type parsing
- Read-only enforcement
- Row limit injection
- Query execution
"""

from unittest.mock import MagicMock

import pytest

from src.db.query import QueryService
from src.models.schema import QueryType, SamplingMethod


class TestQueryService:
    """Test QueryService functionality."""

    def test_get_sample_data_top_method(self, mock_engine):
        """Test TOP sampling method returns expected data."""
        # Mock database response
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "CustomerID": 1,
            "CustomerName": "Test Customer",
            "Status": "Active",
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Execute query
        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name="dbo",
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        # Assertions
        assert sample.table_id == "dbo.Customers"
        assert sample.sample_size == 1  # One row returned
        assert sample.sampling_method == SamplingMethod.TOP
        assert len(sample.rows) == 1
        assert sample.rows[0]["CustomerID"] == 1
        assert sample.rows[0]["CustomerName"] == "Test Customer"

    def test_get_sample_data_with_column_filter(self, mock_engine):
        """Test column filtering works correctly."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "CustomerID": 1,
            "CustomerName": "Test Customer",
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name="dbo",
            sample_size=5,
            columns=["CustomerID", "CustomerName"],
        )

        assert len(sample.rows) == 1
        assert "CustomerID" in sample.rows[0]
        assert "CustomerName" in sample.rows[0]

    def test_binary_truncation(self, mock_engine):
        """Test binary data is truncated and displayed as hex."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        # Binary data longer than 32 bytes
        long_binary = b"x" * 100
        mock_row._mapping = {
            "DocumentID": 1,
            "BinaryData": long_binary,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Documents",
            schema_name="dbo",
            sample_size=1,
        )

        assert len(sample.truncated_columns) == 1
        assert "BinaryData" in sample.truncated_columns
        assert "<binary:" in sample.rows[0]["BinaryData"]
        assert "100 bytes" in sample.rows[0]["BinaryData"]

    def test_text_truncation(self, mock_engine):
        """Test large text is truncated."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        # Text longer than 1000 characters
        long_text = "a" * 1500
        mock_row._mapping = {
            "ID": 1,
            "Description": long_text,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Articles",
            schema_name="dbo",
            sample_size=1,
        )

        assert len(sample.truncated_columns) == 1
        assert "Description" in sample.truncated_columns
        assert len(sample.rows[0]["Description"]) < 1500
        assert "1500 chars total" in sample.rows[0]["Description"]

    def test_sample_size_validation(self, mock_engine):
        """Test sample_size parameter validation."""
        service = QueryService(mock_engine)

        # Test sample_size < 1
        with pytest.raises(ValueError, match="sample_size must be between 1 and 1000"):
            service.get_sample_data(
                table_name="Customers",
                schema_name="dbo",
                sample_size=0,
            )

        # Test sample_size > 1000
        with pytest.raises(ValueError, match="sample_size must be between 1 and 1000"):
            service.get_sample_data(
                table_name="Customers",
                schema_name="dbo",
                sample_size=1001,
            )

    def test_empty_table_name(self, mock_engine):
        """Test empty table_name raises ValueError."""
        service = QueryService(mock_engine)

        with pytest.raises(ValueError, match="table_name is required"):
            service.get_sample_data(
                table_name="",
                schema_name="dbo",
                sample_size=5,
            )

    def test_tablesample_query_generation(self, mock_engine):
        """Test TABLESAMPLE query is generated correctly."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda x: iter([])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="LargeTable",
            schema_name="dbo",
            sample_size=10,
            sampling_method=SamplingMethod.TABLESAMPLE,
        )

        # Verify the call was made
        assert mock_conn.execute.called
        # Verify sampling method in result
        assert sample.sampling_method == SamplingMethod.TABLESAMPLE

    def test_modulo_query_generation(self, mock_engine):
        """Test modulo-based sampling query is generated."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda x: iter([])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="SequentialTable",
            schema_name="dbo",
            sample_size=10,
            sampling_method=SamplingMethod.MODULO,
        )

        assert sample.sampling_method == SamplingMethod.MODULO

    def test_null_values_handled(self, mock_engine):
        """Test NULL values are handled correctly."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "ID": 1,
            "OptionalField": None,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="TestTable",
            schema_name="dbo",
            sample_size=1,
        )

        assert sample.rows[0]["OptionalField"] is None
        assert len(sample.truncated_columns) == 0

    def test_small_binary_not_truncated(self, mock_engine):
        """Test small binary data (<= 32 bytes) is not truncated."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        small_binary = b"small"
        mock_row._mapping = {
            "ID": 1,
            "SmallBinary": small_binary,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="TestTable",
            schema_name="dbo",
            sample_size=1,
        )

        # Small binary should still be marked as truncated (displayed as hex)
        # but won't have "..." suffix
        assert "<binary:" in sample.rows[0]["SmallBinary"]
        assert "5 bytes" in sample.rows[0]["SmallBinary"]
        assert "..." not in sample.rows[0]["SmallBinary"]


class TestQueryTypeParser:
    """Test query type parsing functionality."""

    def test_parse_select_query(self, mock_engine):
        """Test SELECT query is correctly identified."""
        service = QueryService(mock_engine)
        assert service.parse_query_type("SELECT * FROM Users") == QueryType.SELECT
        assert service.parse_query_type("select * from Users") == QueryType.SELECT
        assert service.parse_query_type("  SELECT * FROM Users") == QueryType.SELECT

    def test_parse_insert_query(self, mock_engine):
        """Test INSERT query is correctly identified."""
        service = QueryService(mock_engine)
        assert service.parse_query_type("INSERT INTO Users VALUES (1)") == QueryType.INSERT
        assert service.parse_query_type("insert into Users values (1)") == QueryType.INSERT

    def test_parse_update_query(self, mock_engine):
        """Test UPDATE query is correctly identified."""
        service = QueryService(mock_engine)
        assert service.parse_query_type("UPDATE Users SET name='x'") == QueryType.UPDATE
        assert service.parse_query_type("update Users set name='x'") == QueryType.UPDATE

    def test_parse_delete_query(self, mock_engine):
        """Test DELETE query is correctly identified."""
        service = QueryService(mock_engine)
        assert service.parse_query_type("DELETE FROM Users WHERE id=1") == QueryType.DELETE
        assert service.parse_query_type("delete from Users where id=1") == QueryType.DELETE

    def test_parse_other_query(self, mock_engine):
        """Test other queries are classified as OTHER."""
        service = QueryService(mock_engine)
        assert service.parse_query_type("CREATE TABLE Users (id INT)") == QueryType.OTHER
        assert service.parse_query_type("DROP TABLE Users") == QueryType.OTHER
        assert service.parse_query_type("ALTER TABLE Users ADD col INT") == QueryType.OTHER

    def test_parse_query_with_comments(self, mock_engine):
        """Test queries with SQL comments are parsed correctly."""
        service = QueryService(mock_engine)
        # Single-line comment
        assert service.parse_query_type("-- This is a comment\nSELECT * FROM Users") == QueryType.SELECT
        # Multi-line comment
        assert service.parse_query_type("/* comment */ SELECT * FROM Users") == QueryType.SELECT

    def test_parse_empty_query(self, mock_engine):
        """Test empty query returns OTHER."""
        service = QueryService(mock_engine)
        assert service.parse_query_type("") == QueryType.OTHER
        assert service.parse_query_type("   ") == QueryType.OTHER


class TestReadOnlyEnforcement:
    """Test read-only enforcement for query execution."""

    def test_select_allowed_by_default(self, mock_engine):
        """Test SELECT queries are allowed by default."""
        service = QueryService(mock_engine)
        is_allowed, error = service.is_query_allowed(QueryType.SELECT)
        assert is_allowed is True
        assert error is None

    def test_insert_blocked_by_default(self, mock_engine):
        """Test INSERT queries are blocked by default."""
        service = QueryService(mock_engine)
        is_allowed, error = service.is_query_allowed(QueryType.INSERT)
        assert is_allowed is False
        assert "INSERT" in error
        assert "blocked" in error.lower()

    def test_update_blocked_by_default(self, mock_engine):
        """Test UPDATE queries are blocked by default."""
        service = QueryService(mock_engine)
        is_allowed, error = service.is_query_allowed(QueryType.UPDATE)
        assert is_allowed is False
        assert "UPDATE" in error

    def test_delete_blocked_by_default(self, mock_engine):
        """Test DELETE queries are blocked by default."""
        service = QueryService(mock_engine)
        is_allowed, error = service.is_query_allowed(QueryType.DELETE)
        assert is_allowed is False
        assert "DELETE" in error

    def test_other_blocked(self, mock_engine):
        """Test OTHER (DDL etc.) queries are blocked."""
        service = QueryService(mock_engine)
        is_allowed, error = service.is_query_allowed(QueryType.OTHER)
        assert is_allowed is False
        assert "only SELECT" in error.lower() or "DDL" in error

    def test_write_allowed_when_enabled(self, mock_engine):
        """Test write operations are allowed when explicitly enabled."""
        service = QueryService(mock_engine)

        is_allowed, error = service.is_query_allowed(QueryType.INSERT, allow_write=True)
        assert is_allowed is True
        assert error is None

        is_allowed, error = service.is_query_allowed(QueryType.UPDATE, allow_write=True)
        assert is_allowed is True
        assert error is None

        is_allowed, error = service.is_query_allowed(QueryType.DELETE, allow_write=True)
        assert is_allowed is True
        assert error is None


class TestRowLimitInjection:
    """Test row limit injection into queries."""

    def test_inject_top_clause_sqlserver(self, mock_engine):
        """Test TOP clause is injected for SQL Server."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)

        query = "SELECT * FROM Users"
        result = service.inject_row_limit(query, 100)

        assert "TOP" in result.upper()
        assert "100" in result

    def test_inject_limit_clause_sqlite(self, mock_engine):
        """Test LIMIT clause is added for SQLite."""
        mock_engine.dialect.name = "sqlite"
        service = QueryService(mock_engine)

        query = "SELECT * FROM Users"
        result = service.inject_row_limit(query, 100)

        assert "LIMIT 100" in result.upper()

    def test_no_duplicate_top(self, mock_engine):
        """Test TOP is not duplicated if already present."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)

        query = "SELECT TOP (50) * FROM Users"
        result = service.inject_row_limit(query, 100)

        # Should keep original TOP (50), not add another
        assert result.count("TOP") == 1

    def test_no_duplicate_limit(self, mock_engine):
        """Test LIMIT is not duplicated if already present."""
        mock_engine.dialect.name = "sqlite"
        service = QueryService(mock_engine)

        query = "SELECT * FROM Users LIMIT 50"
        result = service.inject_row_limit(query, 100)

        # Should keep original LIMIT
        assert result.upper().count("LIMIT") == 1

    def test_select_distinct_handled(self, mock_engine):
        """Test SELECT DISTINCT queries have TOP injected correctly."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)

        query = "SELECT DISTINCT Name FROM Users"
        result = service.inject_row_limit(query, 100)

        assert "TOP" in result.upper()
        # TOP should come after DISTINCT
        assert result.upper().index("TOP") > result.upper().index("DISTINCT")

    def test_non_select_unchanged(self, mock_engine):
        """Test non-SELECT queries are not modified."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)

        query = "INSERT INTO Users (name) VALUES ('test')"
        result = service.inject_row_limit(query, 100)

        assert result == query  # Unchanged


class TestQueryExecution:
    """Test query execution functionality."""

    def test_execute_select_query(self, mock_engine):
        """Test executing a SELECT query returns results."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name"]
        mock_result.fetchall.return_value = [
            (1, "Alice"),
            (2, "Bob"),
        ]

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.dialect.name = "sqlite"

        service = QueryService(mock_engine)
        query = service.execute_query(
            connection_id="test123",
            query_text="SELECT id, name FROM Users",
            row_limit=1000,
        )

        assert query.is_allowed is True
        assert query.query_type == QueryType.SELECT
        assert query.execution_time_ms is not None
        assert query.rows_affected == 2

    def test_execute_blocked_write_query(self, mock_engine):
        """Test write queries are blocked."""
        service = QueryService(mock_engine)

        query = service.execute_query(
            connection_id="test123",
            query_text="DELETE FROM Users WHERE id = 1",
            row_limit=1000,
        )

        assert query.is_allowed is False
        assert query.query_type == QueryType.DELETE
        assert "blocked" in query.error_message.lower()

    def test_execute_query_with_results(self, mock_engine):
        """Test get_query_results returns proper structure."""
        # Setup mock
        mock_result = MagicMock()
        mock_result.keys.return_value = ["id", "name"]
        mock_result.fetchall.return_value = [(1, "Test")]

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.dialect.name = "sqlite"

        service = QueryService(mock_engine)
        query = service.execute_query(
            connection_id="test123",
            query_text="SELECT id, name FROM Users",
            row_limit=1000,
        )

        results = service.get_query_results(query)

        assert results["status"] == "success"
        assert results["columns"] == ["id", "name"]
        assert len(results["rows"]) == 1
        assert results["rows_returned"] == 1

    def test_execute_empty_query_raises(self, mock_engine):
        """Test empty query raises ValueError."""
        service = QueryService(mock_engine)

        with pytest.raises(ValueError, match="query_text is required"):
            service.execute_query(
                connection_id="test123",
                query_text="",
                row_limit=1000,
            )

    def test_execute_invalid_row_limit(self, mock_engine):
        """Test invalid row_limit raises ValueError."""
        service = QueryService(mock_engine)

        with pytest.raises(ValueError, match="row_limit must be between 1 and 10000"):
            service.execute_query(
                connection_id="test123",
                query_text="SELECT * FROM Users",
                row_limit=0,
            )

        with pytest.raises(ValueError, match="row_limit must be between 1 and 10000"):
            service.execute_query(
                connection_id="test123",
                query_text="SELECT * FROM Users",
                row_limit=10001,
            )

    def test_execute_query_blocked_status(self, mock_engine):
        """Test blocked query returns proper status in results."""
        service = QueryService(mock_engine)

        query = service.execute_query(
            connection_id="test123",
            query_text="UPDATE Users SET name='x'",
            row_limit=1000,
        )

        results = service.get_query_results(query)

        assert results["status"] == "blocked"
        assert results["is_allowed"] is False
        assert results["query_type"] == "update"
