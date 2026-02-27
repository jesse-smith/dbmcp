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
- AST-based denylist query validation
"""

from unittest.mock import MagicMock

import pytest

from src.db.query import QueryService, validate_query
from src.models.schema import DenialCategory, QueryType, SamplingMethod


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

    def test_datetime_serialization(self, mock_engine):
        """Test datetime values are converted to ISO format strings."""
        from datetime import datetime, date, time as dt_time

        mock_result = MagicMock()
        mock_row = MagicMock()
        test_dt = datetime(2025, 6, 15, 10, 30, 0)
        test_date = date(2025, 6, 15)
        test_time = dt_time(10, 30, 0)
        mock_row._mapping = {
            "ID": 1,
            "CreatedAt": test_dt,
            "BirthDate": test_date,
            "StartTime": test_time,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Events",
            schema_name="dbo",
            sample_size=1,
        )

        assert sample.rows[0]["CreatedAt"] == "2025-06-15T10:30:00"
        assert sample.rows[0]["BirthDate"] == "2025-06-15"
        assert sample.rows[0]["StartTime"] == "10:30:00"
        # datetime/date/time should not be marked as truncated
        assert len(sample.truncated_columns) == 0

    def test_decimal_serialization(self, mock_engine):
        """Test Decimal values are converted to float."""
        from decimal import Decimal

        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "ID": 1,
            "Amount": Decimal("123.45"),
            "Rate": Decimal("0.0750000000"),
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Transactions",
            schema_name="dbo",
            sample_size=1,
        )

        assert sample.rows[0]["Amount"] == 123.45
        assert sample.rows[0]["Rate"] == 0.075
        assert isinstance(sample.rows[0]["Amount"], float)
        assert len(sample.truncated_columns) == 0


class TestCTEQueryParsing:
    """Test CTE (Common Table Expression) query parsing and handling."""

    def test_parse_cte_select_query(self, mock_engine):
        """Test CTE followed by SELECT is classified as SELECT."""
        service = QueryService(mock_engine)
        # Simple CTE + SELECT
        query = "WITH cte AS (SELECT 1 AS val) SELECT * FROM cte"
        assert service.parse_query_type(query) == QueryType.SELECT
        # Multiple lines
        query = """
        WITH recent_orders AS (
            SELECT * FROM orders WHERE order_date > '2026-01-01'
        )
        SELECT * FROM recent_orders
        """
        assert service.parse_query_type(query) == QueryType.SELECT

    def test_parse_cte_multiple_ctes(self, mock_engine):
        """Test multiple CTEs chained together are classified correctly."""
        service = QueryService(mock_engine)
        query = """
        WITH
            orders_2026 AS (SELECT * FROM orders WHERE YEAR(order_date) = 2026),
            high_value AS (SELECT * FROM orders_2026 WHERE total > 1000)
        SELECT COUNT(*) as count FROM high_value
        """
        assert service.parse_query_type(query) == QueryType.SELECT

    def test_parse_cte_with_comments(self, mock_engine):
        """Test CTE queries containing SQL comments are parsed correctly."""
        service = QueryService(mock_engine)
        # Single-line comment before CTE
        query = """
        -- Get active users
        WITH active AS (SELECT * FROM users WHERE status = 'active')
        SELECT * FROM active
        """
        assert service.parse_query_type(query) == QueryType.SELECT
        # Multi-line comment inside CTE
        query = """
        WITH cte AS (
            /* This is a comment */
            SELECT id FROM users
        )
        SELECT * FROM cte
        """
        assert service.parse_query_type(query) == QueryType.SELECT

    def test_cte_select_allowed(self, mock_engine):
        """Test CTE+SELECT queries pass validation."""
        result = validate_query("WITH cte AS (SELECT 1) SELECT * FROM cte")
        assert result.is_safe is True

    def test_inject_row_limit_cte_sqlserver(self, mock_engine):
        """Test TOP injection in CTE queries for SQL Server."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)
        query = "WITH cte AS (SELECT * FROM users) SELECT * FROM cte"
        result = service.inject_row_limit(query, 100)
        # TOP should be injected into the final SELECT, not the CTE
        assert "TOP" in result.upper()
        assert "100" in result
        # The CTE part should remain unchanged
        assert "WITH cte AS (SELECT * FROM users)" in result

    def test_inject_row_limit_cte_sqlite(self, mock_engine):
        """Test LIMIT injection in CTE queries for SQLite."""
        mock_engine.dialect.name = "sqlite"
        service = QueryService(mock_engine)
        query = "WITH cte AS (SELECT * FROM users) SELECT * FROM cte"
        result = service.inject_row_limit(query, 100)
        assert "LIMIT 100" in result.upper()

    def test_parse_cte_insert_query(self, mock_engine):
        """Test CTE followed by INSERT is classified as INSERT."""
        service = QueryService(mock_engine)
        query = """
        WITH source AS (SELECT * FROM staging WHERE validated = 1)
        INSERT INTO target SELECT * FROM source
        """
        assert service.parse_query_type(query) == QueryType.INSERT

    def test_parse_cte_update_query(self, mock_engine):
        """Test CTE followed by UPDATE is classified as UPDATE."""
        service = QueryService(mock_engine)
        query = """
        WITH updates AS (SELECT id, new_value FROM changes)
        UPDATE target SET value = u.new_value
        FROM target t JOIN updates u ON t.id = u.id
        """
        assert service.parse_query_type(query) == QueryType.UPDATE

    def test_parse_cte_delete_query(self, mock_engine):
        """Test CTE followed by DELETE is classified as DELETE."""
        service = QueryService(mock_engine)
        query = """
        WITH old_records AS (SELECT id FROM records WHERE created_at < '2020-01-01')
        DELETE FROM records WHERE id IN (SELECT id FROM old_records)
        """
        assert service.parse_query_type(query) == QueryType.DELETE

    def test_cte_write_blocked_by_default(self, mock_engine):
        """Test CTE+write queries are blocked by default."""
        result = validate_query("WITH src AS (SELECT 1) INSERT INTO t SELECT * FROM src")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.CTE_WRAPPED_WRITE

    def test_cte_write_allowed_with_flag(self, mock_engine):
        """Test CTE+write queries pass validation when allow_write=True."""
        result = validate_query(
            "WITH src AS (SELECT 1 as val) INSERT INTO t SELECT * FROM src",
            allow_write=True,
        )
        assert result.is_safe is True

    def test_existing_write_controls_unchanged(self, mock_engine):
        """Regression test: existing write controls still work as before."""
        # Regular INSERT blocked
        result = validate_query("INSERT INTO users (name) VALUES ('test')")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

        # Regular UPDATE blocked
        result = validate_query("UPDATE users SET name='x' WHERE id=1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

        # Regular DELETE blocked
        result = validate_query("DELETE FROM users WHERE id=1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML


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


class TestDeniedOperations:
    """Test AST-based denial of dangerous operations (replaces TestBlockedKeywords)."""

    def test_create_denied(self, mock_engine):
        """Test CREATE operations are denied."""
        result = validate_query("CREATE TABLE users (id INT)")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_drop_denied(self, mock_engine):
        """Test DROP operations are denied."""
        result = validate_query("DROP TABLE users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_alter_denied(self, mock_engine):
        """Test ALTER operations are denied."""
        result = validate_query("ALTER TABLE users ADD col INT")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_truncate_denied(self, mock_engine):
        """Test TRUNCATE operations are denied."""
        result = validate_query("TRUNCATE TABLE users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_exec_unknown_denied(self, mock_engine):
        """Test EXEC of unknown procedures is denied."""
        result = validate_query("EXEC unknown_proc")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE

    def test_grant_denied(self, mock_engine):
        """Test GRANT operations are denied."""
        result = validate_query("GRANT SELECT ON users TO role1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DCL

    def test_revoke_denied(self, mock_engine):
        """Test REVOKE operations are denied (parse failure)."""
        result = validate_query("REVOKE SELECT ON users FROM role")
        assert result.is_safe is False

    def test_deny_denied(self, mock_engine):
        """Test DENY operations are denied (parse failure)."""
        result = validate_query("DENY SELECT ON users TO role")
        assert result.is_safe is False

    def test_denied_error_message_in_execute_query(self, mock_engine):
        """Test that denied query error messages include category info."""
        service = QueryService(mock_engine)
        query = service.execute_query(
            connection_id="test123",
            query_text="CREATE TABLE test (id INT)",
            row_limit=1000,
        )
        assert query.is_allowed is False
        assert "DDL" in query.error_message
        assert query.denial_reasons is not None
        assert query.denial_reasons[0].category == DenialCategory.DDL


class TestReadOnlyEnforcement:
    """Test read-only enforcement via validate_query."""

    def test_select_allowed_by_default(self, mock_engine):
        """Test SELECT queries pass validation by default."""
        result = validate_query("SELECT * FROM users")
        assert result.is_safe is True

    def test_insert_blocked_by_default(self, mock_engine):
        """Test INSERT queries are denied by default."""
        result = validate_query("INSERT INTO users VALUES (1)")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

    def test_update_blocked_by_default(self, mock_engine):
        """Test UPDATE queries are denied by default."""
        result = validate_query("UPDATE users SET name='x'")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

    def test_delete_blocked_by_default(self, mock_engine):
        """Test DELETE queries are denied by default."""
        result = validate_query("DELETE FROM users WHERE id=1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

    def test_ddl_blocked(self, mock_engine):
        """Test DDL queries are denied."""
        result = validate_query("CREATE TABLE test (id INT)")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_write_allowed_when_enabled(self, mock_engine):
        """Test write operations pass when allow_write=True."""
        assert validate_query("INSERT INTO users VALUES (1)", allow_write=True).is_safe is True
        assert validate_query("UPDATE users SET name='x'", allow_write=True).is_safe is True
        assert validate_query("DELETE FROM users WHERE id=1", allow_write=True).is_safe is True


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
        assert "DML" in query.error_message
        assert query.denial_reasons is not None

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
        assert "DML" in results["error_message"]


# =============================================================================
# AST-Based Denylist Validation Tests (Feature 005)
# =============================================================================


class TestValidateQuerySafe:
    """T005: Tests for safe query validation — queries that should pass."""

    def test_simple_select(self):
        """Plain SELECT passes validation."""
        result = validate_query("SELECT * FROM users")
        assert result.is_safe is True
        assert result.reasons == []

    def test_select_with_where(self):
        """SELECT with WHERE clause passes."""
        result = validate_query("SELECT id, name FROM users WHERE active = 1")
        assert result.is_safe is True

    def test_select_with_keyword_overlapping_column_create_date(self):
        """SELECT referencing 'create_date' column must not false-positive on CREATE."""
        result = validate_query("SELECT create_date FROM orders")
        assert result.is_safe is True

    def test_select_with_keyword_overlapping_column_execute_count(self):
        """SELECT referencing 'execute_count' column must not false-positive on EXECUTE."""
        result = validate_query("SELECT execute_count FROM stats")
        assert result.is_safe is True

    def test_select_with_keyword_overlapping_column_drop_reason(self):
        """SELECT referencing 'drop_reason' column must not false-positive on DROP."""
        result = validate_query("SELECT drop_reason FROM audit_log")
        assert result.is_safe is True

    def test_cte_select(self):
        """CTE followed by SELECT passes."""
        result = validate_query(
            "WITH cte AS (SELECT id FROM users) SELECT * FROM cte"
        )
        assert result.is_safe is True

    def test_multiple_ctes_select(self):
        """Multiple CTEs followed by SELECT passes."""
        result = validate_query(
            "WITH a AS (SELECT 1 AS x), b AS (SELECT 2 AS y) SELECT * FROM a, b"
        )
        assert result.is_safe is True

    def test_select_with_subquery(self):
        """SELECT with subquery passes."""
        result = validate_query(
            "SELECT * FROM users WHERE id IN (SELECT user_id FROM active_users)"
        )
        assert result.is_safe is True

    def test_select_union(self):
        """UNION queries pass."""
        result = validate_query("SELECT 1 AS x UNION SELECT 2 AS x")
        assert result.is_safe is True


class TestValidateQueryDenied:
    """T006: Tests for denied operations — categorized denial reasons."""

    # --- DML ---

    def test_insert_denied(self):
        result = validate_query("INSERT INTO users (name) VALUES ('x')")
        assert result.is_safe is False
        assert len(result.reasons) >= 1
        assert result.reasons[0].category == DenialCategory.DML

    def test_update_denied(self):
        result = validate_query("UPDATE users SET name = 'x' WHERE id = 1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

    def test_delete_denied(self):
        result = validate_query("DELETE FROM users WHERE id = 1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

    def test_merge_denied(self):
        result = validate_query(
            "MERGE INTO target USING source ON target.id = source.id "
            "WHEN MATCHED THEN UPDATE SET name = source.name"
        )
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DML

    # --- DDL ---

    def test_create_table_denied(self):
        result = validate_query("CREATE TABLE test (id INT)")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_alter_table_denied(self):
        result = validate_query("ALTER TABLE users ADD col INT")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_drop_table_denied(self):
        result = validate_query("DROP TABLE users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_truncate_denied(self):
        result = validate_query("TRUNCATE TABLE users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    # --- DCL ---

    def test_grant_denied(self):
        result = validate_query("GRANT SELECT ON users TO role1")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DCL

    def test_revoke_denied(self):
        """REVOKE can't be parsed by sqlglot → PARSE_FAILURE (still denied)."""
        result = validate_query("REVOKE SELECT ON users FROM role1")
        assert result.is_safe is False

    def test_deny_denied(self):
        """DENY can't be parsed by sqlglot → PARSE_FAILURE (still denied)."""
        result = validate_query("DENY SELECT ON users TO role1")
        assert result.is_safe is False

    # --- Operational ---

    def test_backup_denied(self):
        """BACKUP can't be parsed by sqlglot → PARSE_FAILURE (still denied)."""
        result = validate_query("BACKUP DATABASE mydb TO DISK = 'path'")
        assert result.is_safe is False

    def test_restore_denied(self):
        """RESTORE can't be parsed by sqlglot → PARSE_FAILURE (still denied)."""
        result = validate_query("RESTORE DATABASE mydb FROM DISK = 'path'")
        assert result.is_safe is False

    def test_kill_denied(self):
        result = validate_query("KILL 55")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.OPERATIONAL

    # --- SELECT INTO ---

    def test_select_into_denied(self):
        result = validate_query("SELECT * INTO newtable FROM users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.SELECT_INTO

    # --- CTE-wrapped writes ---

    def test_cte_insert_denied(self):
        result = validate_query(
            "WITH cte AS (SELECT 1 AS val) INSERT INTO t SELECT * FROM cte"
        )
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.CTE_WRAPPED_WRITE

    def test_cte_update_denied(self):
        result = validate_query(
            "WITH cte AS (SELECT id, 'x' AS name FROM users) "
            "UPDATE t SET name = cte.name FROM t JOIN cte ON t.id = cte.id"
        )
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.CTE_WRAPPED_WRITE

    def test_cte_delete_denied(self):
        result = validate_query(
            "WITH old AS (SELECT id FROM users WHERE created < '2020-01-01') "
            "DELETE FROM users WHERE id IN (SELECT id FROM old)"
        )
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.CTE_WRAPPED_WRITE

    # --- Case variation (FR-013) ---

    def test_case_insensitive_drop(self):
        result = validate_query("drop table users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_case_insensitive_grant(self):
        result = validate_query("Grant SELECT ON t TO r")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DCL

    def test_case_insensitive_truncate(self):
        result = validate_query("TRUNCATE table users")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    # --- Stored procedures (all denied in Phase 3, allowlist added Phase 4) ---

    def test_exec_unknown_proc_denied(self):
        """Unknown stored procedures are denied."""
        result = validate_query("EXEC user_defined_proc")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE


class TestValidateQueryAllowWrite:
    """T007: Tests for allow_write=True bypass behavior."""

    def test_insert_allowed_with_write(self):
        result = validate_query("INSERT INTO users (name) VALUES ('x')", allow_write=True)
        assert result.is_safe is True

    def test_update_allowed_with_write(self):
        result = validate_query("UPDATE users SET name = 'x'", allow_write=True)
        assert result.is_safe is True

    def test_delete_allowed_with_write(self):
        result = validate_query("DELETE FROM users WHERE id = 1", allow_write=True)
        assert result.is_safe is True

    def test_merge_allowed_with_write(self):
        result = validate_query(
            "MERGE INTO target USING source ON target.id = source.id "
            "WHEN MATCHED THEN UPDATE SET name = source.name",
            allow_write=True,
        )
        assert result.is_safe is True

    def test_ddl_still_denied_with_write(self):
        """DDL is NOT bypassed by allow_write."""
        result = validate_query("CREATE TABLE test (id INT)", allow_write=True)
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DDL

    def test_dcl_still_denied_with_write(self):
        """DCL is NOT bypassed by allow_write."""
        result = validate_query("GRANT SELECT ON t TO r", allow_write=True)
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.DCL

    def test_operational_still_denied_with_write(self):
        """Operational commands are NOT bypassed by allow_write."""
        result = validate_query("KILL 55", allow_write=True)
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.OPERATIONAL

    def test_select_into_still_denied_with_write(self):
        """SELECT INTO is NOT bypassed by allow_write."""
        result = validate_query("SELECT * INTO newtable FROM users", allow_write=True)
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.SELECT_INTO


class TestStoredProcedureAllowlist:
    """T010: Tests for stored procedure allowlist (US3)."""

    # All 22 safe procedures should pass

    @pytest.mark.parametrize("proc", [
        "sp_column_privileges", "sp_columns", "sp_databases", "sp_fkeys",
        "sp_pkeys", "sp_server_info", "sp_special_columns", "sp_sproc_columns",
        "sp_statistics", "sp_stored_procedures", "sp_table_privileges", "sp_tables",
        "sp_help", "sp_helptext", "sp_helpindex", "sp_helpconstraint",
        "sp_who", "sp_who2", "sp_spaceused",
        "sp_describe_first_result_set", "sp_describe_undeclared_parameters",
    ])
    def test_safe_procedure_allowed(self, proc):
        """Each of the 22 safe system procedures passes validation."""
        result = validate_query(f"EXEC {proc}")
        assert result.is_safe is True, f"{proc} should be safe but got: {result.reasons}"

    def test_safe_procedure_with_schema_prefix(self):
        """Multi-part name master.dbo.sp_help resolves correctly."""
        result = validate_query("EXEC master.dbo.sp_help")
        assert result.is_safe is True

    def test_safe_procedure_with_dbo_prefix(self):
        """dbo.sp_columns resolves correctly."""
        result = validate_query("EXEC dbo.sp_columns")
        assert result.is_safe is True

    def test_sp_executesql_denied(self):
        """sp_executesql is explicitly denied despite matching sp_ pattern."""
        result = validate_query("EXEC sp_executesql")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE
        assert "sp_executesql" in result.reasons[0].detail

    def test_unknown_procedure_denied(self):
        """User-defined procedures are denied."""
        result = validate_query("EXEC my_custom_proc")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE

    def test_case_insensitive_sp_tables(self):
        """SP_TABLES (uppercase) matches case-insensitively."""
        result = validate_query("EXEC SP_TABLES")
        assert result.is_safe is True

    def test_case_insensitive_sp_help(self):
        """Sp_Help (mixed case) matches case-insensitively."""
        result = validate_query("EXEC Sp_Help")
        assert result.is_safe is True

    def test_execute_keyword(self):
        """EXECUTE (not just EXEC) works for safe procedures."""
        result = validate_query("EXECUTE sp_tables")
        assert result.is_safe is True

    def test_execute_unknown_denied(self):
        """EXECUTE unknown procedure is denied."""
        result = validate_query("EXECUTE unknown_proc")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.STORED_PROCEDURE


class TestObfuscationResistance:
    """T013: Tests for obfuscation resistance (US4)."""

    # --- Multi-statement batches ---

    def test_batch_with_denied_statement(self):
        """A batch with one denied statement → entire batch denied with statement_index."""
        result = validate_query("SELECT 1; DROP TABLE users")
        assert result.is_safe is False
        # Should have at least one denial reason with correct index
        drop_reasons = [r for r in result.reasons if r.category == DenialCategory.DDL]
        assert len(drop_reasons) >= 1
        assert drop_reasons[0].statement_index == 1  # Second statement (0-indexed)

    def test_batch_all_safe(self):
        """A batch of all safe statements passes."""
        result = validate_query("SELECT 1; SELECT 2")
        assert result.is_safe is True

    def test_batch_multiple_denied(self):
        """A batch with multiple denied statements reports all denials."""
        result = validate_query("DROP TABLE a; INSERT INTO b VALUES(1)")
        assert result.is_safe is False
        assert len(result.reasons) >= 2

    # --- Nested denied operations in control flow ---

    def test_begin_end_block_with_drop(self):
        """Denied operation inside BEGIN/END block detected."""
        result = validate_query("BEGIN DROP TABLE x END")
        assert result.is_safe is False

    def test_if_else_with_denied(self):
        """Denied operation inside IF/ELSE block detected."""
        result = validate_query("IF 1=1 DROP TABLE x")
        assert result.is_safe is False

    def test_while_with_denied(self):
        """Denied operation inside WHILE block detected."""
        result = validate_query("WHILE 1=1 DELETE FROM users")
        assert result.is_safe is False

    # --- Parse failures ---

    def test_malformed_sql_denied(self):
        """Malformed SQL is denied as PARSE_FAILURE."""
        result = validate_query("THIS IS NOT VALID SQL !@#$%")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.PARSE_FAILURE

    def test_empty_query_denied(self):
        """Empty string is denied."""
        result = validate_query("")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.PARSE_FAILURE

    def test_whitespace_only_denied(self):
        """Whitespace-only string is denied."""
        result = validate_query("   \n\t  ")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.PARSE_FAILURE
