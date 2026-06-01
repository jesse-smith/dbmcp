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
- Config-driven truncation limit
"""

import re
from unittest.mock import MagicMock, patch

import pytest

from src.db.query import QueryService
from src.db.validation import validate_query
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

        # Verify both tablesample and fallback top queries were executed
        assert mock_conn.execute.call_count == 2
        # When tablesample returns 0 rows, it falls back to TOP
        assert sample.sampling_method == SamplingMethod.TOP

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
        from datetime import date, datetime
        from datetime import time as dt_time

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


class TestGetSampleDataCatalogThreading:
    """Catalog threading into the get_sample_data SQL build (IDENT-05 / SC3).

    The executed query's table reference must become a 3-part backtick-quoted
    `cat`.`sch`.`tbl` on Databricks when a catalog is supplied, while the
    2-part (schema.table) and unqualified (no-dialect) paths stay unchanged.
    """

    def _captured_sql(self, mock_engine) -> str:
        """Run get_sample_data with one mocked row and return the executed SQL."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"id": 1}
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        return mock_conn

    def test_databricks_catalog_builds_three_part_reference(self, mock_engine):
        """catalog + schema + table on Databricks -> `cat`.`sch`.`tbl`."""
        mock_engine.dialect.name = "databricks"
        mock_conn = self._captured_sql(mock_engine)

        service = QueryService(mock_engine)
        service.get_sample_data(
            table_name="tbl",
            schema_name="sch",
            catalog="cat",
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "`cat`.`sch`.`tbl`" in executed_sql

    def test_databricks_no_catalog_builds_two_part_reference(self, mock_engine):
        """catalog=None on Databricks keeps the existing 2-part reference."""
        mock_engine.dialect.name = "databricks"
        mock_conn = self._captured_sql(mock_engine)

        service = QueryService(mock_engine)
        service.get_sample_data(
            table_name="tbl",
            schema_name="sch",
            catalog=None,
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "`sch`.`tbl`" in executed_sql
        assert "`cat`" not in executed_sql

    def test_no_dialect_catalog_none_builds_unqualified_reference(self, mock_engine):
        """dialect=None (SQLite/test) with catalog=None stays unqualified."""
        # mock_engine.dialect.name defaults to a MagicMock; force the no-dialect
        # path by using a name the registry does not recognize.
        mock_engine.dialect.name = "sqlite"
        mock_conn = self._captured_sql(mock_engine)

        service = QueryService(mock_engine)
        assert service._dialect is None  # sqlite not in registry -> no dialect
        service.get_sample_data(
            table_name="tbl",
            catalog=None,
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "FROM tbl" in executed_sql


class TestCTEQueryParsing:
    """Test CTE (Common Table Expression) query parsing and handling."""

    @pytest.mark.parametrize(
        "sql,expected",
        [
            ("WITH cte AS (SELECT 1 AS val) SELECT * FROM cte", QueryType.SELECT),
            (
                "WITH recent_orders AS (\n"
                "    SELECT * FROM orders WHERE order_date > '2026-01-01'\n"
                ")\n"
                "SELECT * FROM recent_orders",
                QueryType.SELECT,
            ),
            (
                "WITH\n"
                "    orders_2026 AS (SELECT * FROM orders WHERE YEAR(order_date) = 2026),\n"
                "    high_value AS (SELECT * FROM orders_2026 WHERE total > 1000)\n"
                "SELECT COUNT(*) as count FROM high_value",
                QueryType.SELECT,
            ),
            (
                "-- Get active users\n"
                "WITH active AS (SELECT * FROM users WHERE status = 'active')\n"
                "SELECT * FROM active",
                QueryType.SELECT,
            ),
            (
                "WITH cte AS (\n"
                "    /* This is a comment */\n"
                "    SELECT id FROM users\n"
                ")\n"
                "SELECT * FROM cte",
                QueryType.SELECT,
            ),
            (
                "WITH source AS (SELECT * FROM staging WHERE validated = 1)\n"
                "INSERT INTO target SELECT * FROM source",
                QueryType.INSERT,
            ),
            (
                "WITH updates AS (SELECT id, new_value FROM changes)\n"
                "UPDATE target SET value = u.new_value\n"
                "FROM target t JOIN updates u ON t.id = u.id",
                QueryType.UPDATE,
            ),
            (
                "WITH old_records AS (SELECT id FROM records WHERE created_at < '2020-01-01')\n"
                "DELETE FROM records WHERE id IN (SELECT id FROM old_records)",
                QueryType.DELETE,
            ),
        ],
        ids=[
            "simple_cte_select",
            "multiline_cte_select",
            "multiple_ctes_select",
            "cte_with_line_comment",
            "cte_with_block_comment",
            "cte_insert",
            "cte_update",
            "cte_delete",
        ],
    )
    def test_parse_cte_query_type(self, mock_engine, sql, expected):
        """Test CTE queries are classified by their terminal statement."""
        service = QueryService(mock_engine)
        assert service.parse_query_type(sql) == expected

    def test_cte_select_allowed(self, mock_engine):
        """Test CTE+SELECT queries pass validation."""
        result = validate_query("WITH cte AS (SELECT 1) SELECT * FROM cte", dialect="tsql")
        assert result.is_safe is True

    @pytest.mark.parametrize(
        "dialect,sql,check_keyword",
        [
            (
                "mssql",
                "WITH cte AS (SELECT * FROM users) SELECT * FROM cte",
                "TOP",
            ),
            (
                "sqlite",
                "WITH cte AS (SELECT * FROM users) SELECT * FROM cte",
                "LIMIT",
            ),
        ],
        ids=["cte_top_sqlserver", "cte_limit_sqlite"],
    )
    def test_inject_row_limit_cte(self, mock_engine, dialect, sql, check_keyword):
        """Test row limit injection in CTE queries for different dialects."""
        mock_engine.dialect.name = dialect
        service = QueryService(mock_engine)
        result = service.inject_row_limit(sql, 100)
        assert check_keyword in result.upper()
        assert "100" in result
        # The CTE part should remain unchanged
        assert "WITH cte AS (SELECT * FROM users)" in result

    def test_cte_write_blocked_by_default(self, mock_engine):
        """Test CTE+write queries are blocked by default."""
        result = validate_query("WITH src AS (SELECT 1) INSERT INTO t SELECT * FROM src", dialect="tsql")
        assert result.is_safe is False
        assert result.reasons[0].category == DenialCategory.CTE_WRAPPED_WRITE

    def test_cte_write_allowed_with_flag(self, mock_engine):
        """Test CTE+write queries pass validation when allow_write=True."""
        result = validate_query(
            "WITH src AS (SELECT 1 as val) INSERT INTO t SELECT * FROM src",
            dialect="tsql",
            allow_write=True,
        )
        assert result.is_safe is True

    @pytest.mark.parametrize(
        "sql,category",
        [
            ("INSERT INTO users (name) VALUES ('test')", DenialCategory.DML),
            ("UPDATE users SET name='x' WHERE id=1", DenialCategory.DML),
            ("DELETE FROM users WHERE id=1", DenialCategory.DML),
        ],
        ids=["insert_still_blocked", "update_still_blocked", "delete_still_blocked"],
    )
    def test_existing_write_controls_unchanged(self, mock_engine, sql, category):
        """Regression test: existing write controls still work as before."""
        result = validate_query(sql, dialect="tsql")
        assert result.is_safe is False
        assert result.reasons[0].category == category


class TestQueryTypeParser:
    """Test query type parsing functionality."""

    @pytest.mark.parametrize(
        "sql,expected",
        [
            ("SELECT * FROM Users", QueryType.SELECT),
            ("select * from Users", QueryType.SELECT),
            ("  SELECT * FROM Users", QueryType.SELECT),
            ("INSERT INTO Users VALUES (1)", QueryType.INSERT),
            ("insert into Users values (1)", QueryType.INSERT),
            ("UPDATE Users SET name='x'", QueryType.UPDATE),
            ("update Users set name='x'", QueryType.UPDATE),
            ("DELETE FROM Users WHERE id=1", QueryType.DELETE),
            ("delete from Users where id=1", QueryType.DELETE),
            ("CREATE TABLE Users (id INT)", QueryType.OTHER),
            ("DROP TABLE Users", QueryType.OTHER),
            ("ALTER TABLE Users ADD col INT", QueryType.OTHER),
        ],
        ids=[
            "select_upper",
            "select_lower",
            "select_leading_space",
            "insert_upper",
            "insert_lower",
            "update_upper",
            "update_lower",
            "delete_upper",
            "delete_lower",
            "create_table",
            "drop_table",
            "alter_table",
        ],
    )
    def test_parse_query_type(self, mock_engine, sql, expected):
        """Test query type is correctly identified."""
        service = QueryService(mock_engine)
        assert service.parse_query_type(sql) == expected

    @pytest.mark.parametrize(
        "sql",
        [
            "-- This is a comment\nSELECT * FROM Users",
            "/* comment */ SELECT * FROM Users",
        ],
        ids=["single_line_comment", "block_comment"],
    )
    def test_parse_query_with_comments(self, mock_engine, sql):
        """Test queries with SQL comments are parsed as SELECT."""
        service = QueryService(mock_engine)
        assert service.parse_query_type(sql) == QueryType.SELECT

    @pytest.mark.parametrize(
        "sql",
        ["", "   "],
        ids=["empty_string", "whitespace_only"],
    )
    def test_parse_empty_query(self, mock_engine, sql):
        """Test empty/whitespace query returns OTHER."""
        service = QueryService(mock_engine)
        assert service.parse_query_type(sql) == QueryType.OTHER


class TestReadOnlyEnforcement:
    """Test read-only enforcement via validate_query."""

    def test_select_allowed_by_default(self, mock_engine):
        """Test SELECT queries pass validation by default."""
        result = validate_query("SELECT * FROM users", dialect="tsql")
        assert result.is_safe is True

    @pytest.mark.parametrize(
        "sql,category",
        [
            ("INSERT INTO users VALUES (1)", DenialCategory.DML),
            ("UPDATE users SET name='x'", DenialCategory.DML),
            ("DELETE FROM users WHERE id=1", DenialCategory.DML),
            ("CREATE TABLE test (id INT)", DenialCategory.DDL),
        ],
        ids=["insert_blocked", "update_blocked", "delete_blocked", "ddl_blocked"],
    )
    def test_write_blocked_by_default(self, mock_engine, sql, category):
        """Test write and DDL queries are denied by default."""
        result = validate_query(sql, dialect="tsql")
        assert result.is_safe is False
        assert result.reasons[0].category == category

    @pytest.mark.parametrize(
        "sql",
        [
            "INSERT INTO users VALUES (1)",
            "UPDATE users SET name='x'",
            "DELETE FROM users WHERE id=1",
        ],
        ids=["insert_allowed", "update_allowed", "delete_allowed"],
    )
    def test_write_allowed_when_enabled(self, mock_engine, sql):
        """Test write operations pass when allow_write=True."""
        assert validate_query(sql, dialect="tsql", allow_write=True).is_safe is True


class TestRowLimitInjection:
    """Test row limit injection into queries."""

    @pytest.mark.parametrize(
        "dialect,sql,check_keyword,limit_val",
        [
            ("mssql", "SELECT * FROM Users", "TOP", "100"),
            ("sqlite", "SELECT * FROM Users", "LIMIT 100", None),
            ("databricks", "SELECT * FROM Users", "LIMIT 100", None),
        ],
        ids=["top_sqlserver", "limit_sqlite", "limit_databricks"],
    )
    def test_inject_row_limit(self, mock_engine, dialect, sql, check_keyword, limit_val):
        """Test row limit clause is injected for different dialects."""
        mock_engine.dialect.name = dialect
        service = QueryService(mock_engine)
        result = service.inject_row_limit(sql, 100)
        assert check_keyword in result.upper()
        if limit_val:
            assert limit_val in result

    @pytest.mark.parametrize(
        "dialect,sql",
        [
            ("databricks", "SELECT * FROM Users;"),
            ("databricks", "WITH cte AS (SELECT * FROM Users) SELECT * FROM cte;"),
            ("sqlite", "SELECT * FROM Users  ;  "),
        ],
        ids=["databricks_trailing_semicolon", "databricks_cte_trailing_semicolon", "sqlite_trailing_semicolon_whitespace"],
    )
    def test_limit_with_trailing_semicolon(self, mock_engine, dialect, sql):
        """LIMIT must be inserted before any trailing statement terminator."""
        mock_engine.dialect.name = dialect
        service = QueryService(mock_engine)
        result = service.inject_row_limit(sql, 100)
        # LIMIT must not appear after a semicolon
        assert "; LIMIT" not in result.upper()
        assert ";LIMIT" not in result.upper().replace(" ", "")
        # LIMIT N must be present, and the trailing ; must be preserved
        assert re.search(r'LIMIT\s+100', result, re.IGNORECASE)
        assert result.rstrip().endswith(";")

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


class TestSafeOperationalCommandExecution:
    """Tests for result materialization of SHOW/DESCRIBE on Databricks.

    Safe operational commands (SHOW, DESCRIBE, EXPLAIN) are result-producing
    reads that must return rows, not just a rowcount.
    """

    def _make_mock_dialect(self, safe_ops=frozenset({"SHOW", "DESCRIBE"})):
        """Create a mock dialect with safe_operational_commands."""
        from unittest.mock import PropertyMock
        dialect = MagicMock()
        type(dialect).safe_operational_commands = PropertyMock(return_value=safe_ops)
        type(dialect).safe_procedures = PropertyMock(return_value=frozenset())
        type(dialect).sqlglot_dialect = PropertyMock(return_value="databricks")
        dialect.name = "databricks"
        return dialect

    def test_show_catalogs_materializes_rows(self, mock_engine):
        """execute_query('SHOW CATALOGS') returns actual rows, not 0."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["catalog"]
        mock_result.fetchall.return_value = [("bmtct",), ("main",)]

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.dialect.name = "databricks"

        dialect = self._make_mock_dialect()
        service = QueryService(mock_engine, dialect=dialect)
        query = service.execute_query(
            connection_id="test123",
            query_text="SHOW CATALOGS",
            row_limit=1000,
        )

        assert query.is_allowed is True
        assert query.rows == [{"catalog": "bmtct"}, {"catalog": "main"}]
        assert query.rows_affected == 2

    def test_describe_table_materializes_rows(self, mock_engine):
        """execute_query('DESCRIBE TABLE t') returns rows."""
        mock_result = MagicMock()
        mock_result.keys.return_value = ["col_name", "data_type", "comment"]
        mock_result.fetchall.return_value = [("id", "int", ""), ("name", "string", "")]

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.dialect.name = "databricks"

        dialect = self._make_mock_dialect()
        service = QueryService(mock_engine, dialect=dialect)
        query = service.execute_query(
            connection_id="test123",
            query_text="DESCRIBE TABLE catalog.schema.t",
            row_limit=1000,
        )

        assert query.is_allowed is True
        assert len(query.rows) == 2
        assert query.rows[0]["col_name"] == "id"

    def test_show_without_databricks_dialect_is_blocked(self, mock_engine):
        """SHOW CATALOGS with no safe_operational_commands is blocked by validator."""
        mock_engine.dialect.name = "sqlite"

        # No dialect set — safe_operational_commands will be empty frozenset
        service = QueryService(mock_engine, dialect=None)
        query = service.execute_query(
            connection_id="test123",
            query_text="SHOW CATALOGS",
            row_limit=1000,
        )

        assert query.is_allowed is False
        assert query.rows == []

    def test_insert_still_uses_write_path(self, mock_engine):
        """INSERT queries still use rowcount + commit, not row materialization."""
        mock_result = MagicMock()
        mock_result.rowcount = 1

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn
        mock_engine.dialect.name = "databricks"

        dialect = self._make_mock_dialect()
        service = QueryService(mock_engine, dialect=dialect)
        # INSERT is a write; allow_write=True to get past the validator
        query = service.execute_query(
            connection_id="test123",
            query_text="INSERT INTO t VALUES (1)",
            row_limit=1000,
            allow_write=True,
        )

        # Should have taken the write/commit path (rows empty, rows_affected==1)
        assert query.rows == []
        assert mock_conn.commit.called


class TestTruncationConfig:
    """Test that truncation limit is driven by config, not hardcoded."""

    def _make_mock_result(self, row_mapping: dict):
        """Create a mock SQLAlchemy result with a single row."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = MagicMock()
        mock_row._mapping.items.return_value = list(row_mapping.items())
        mock_result.__iter__ = lambda self: iter([mock_row])
        return mock_result

    def _make_mock_config(self, text_truncation_limit: int):
        """Create a mock config with the given truncation limit."""
        mock_config = MagicMock()
        mock_config.defaults.text_truncation_limit = text_truncation_limit
        return mock_config

    @patch("src.db.query.get_config")
    def test_truncation_uses_config_limit_500(self, mock_get_config, mock_engine):
        """With text_truncation_limit=500, a 700-char string is truncated."""
        mock_get_config.return_value = self._make_mock_config(500)

        long_text = "a" * 700
        mock_result = self._make_mock_result({"ID": 1, "Description": long_text})

        service = QueryService(mock_engine)
        rows: list = []
        truncated_cols: list = []
        service._process_rows(mock_result, rows, truncated_cols)

        assert len(rows) == 1
        # String should be truncated (shorter than original 700 chars)
        assert len(rows[0]["Description"]) < 700
        assert "Description" in truncated_cols

    @patch("src.db.query.get_config")
    def test_truncation_default_limit_preserves_short_strings(
        self, mock_get_config, mock_engine
    ):
        """With text_truncation_limit=1000, a 700-char string is NOT truncated."""
        mock_get_config.return_value = self._make_mock_config(1000)

        text_700 = "b" * 700
        mock_result = self._make_mock_result({"ID": 1, "Description": text_700})

        service = QueryService(mock_engine)
        rows: list = []
        truncated_cols: list = []
        service._process_rows(mock_result, rows, truncated_cols)

        assert len(rows) == 1
        # String should NOT be truncated (700 < 1000 limit)
        assert rows[0]["Description"] == text_700
        assert "Description" not in truncated_cols


class TestQueryServiceDialectDelegation:
    """QueryService delegates sample-query SQL generation to the dialect."""

    def _make_stub(self, sentinel="STUB_SQL"):
        stub = MagicMock()
        stub.build_sample_query = MagicMock(return_value=sentinel)
        stub.quote_identifier = lambda ident: f"[{ident}]"
        return stub

    def test_build_top_query_delegates_to_dialect(self, mock_engine):
        stub = self._make_stub()
        service = QueryService(mock_engine, dialect=stub)
        assert service._build_top_query("[dbo].[T]", "*", 5) == "STUB_SQL"
        stub.build_sample_query.assert_called_once_with(
            SamplingMethod.TOP, "[dbo].[T]", "*", 5
        )

    def test_build_tablesample_query_delegates_to_dialect(self, mock_engine):
        stub = self._make_stub()
        service = QueryService(mock_engine, dialect=stub)
        assert service._build_tablesample_query("[dbo].[T]", "*", 5) == "STUB_SQL"
        stub.build_sample_query.assert_called_once_with(
            SamplingMethod.TABLESAMPLE, "[dbo].[T]", "*", 5
        )

    def test_build_modulo_query_delegates_to_dialect(self, mock_engine):
        stub = self._make_stub()
        service = QueryService(mock_engine, dialect=stub)
        assert service._build_modulo_query("[dbo].[T]", "*", 5) == "STUB_SQL"
        stub.build_sample_query.assert_called_once_with(
            SamplingMethod.MODULO, "[dbo].[T]", "*", 5
        )


class TestSampleDataSchemaDefault:
    """Tests for the None schema_name default (D-11: no hardcoded 'dbo')."""

    def test_get_sample_data_schema_name_default_is_none(self):
        """get_sample_data must default schema_name to None, not 'dbo'."""
        import inspect

        param = inspect.signature(QueryService.get_sample_data).parameters["schema_name"]
        assert param.default is None

    def test_get_sample_data_none_schema_builds_unqualified_reference(self, mock_engine):
        """With no dialect and schema_name=None, the table reference is unqualified.

        The ``self._dialect is None`` branch (query.py) emits the bare table name
        with no schema prefix — the generic/SQLite no-prefix path. The built query
        must therefore contain the table name without a ``schema.`` qualifier.
        """
        captured = {}

        def fake_execute(stmt):
            captured["sql"] = str(stmt)
            result = MagicMock()
            result.__iter__ = lambda x: iter([])
            return result

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = fake_execute
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)  # no dialect -> _dialect is None
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name=None,
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        # Unqualified reference: no synthetic 'dbo.' (or any schema) prefix.
        assert "Customers" in captured["sql"]
        assert "dbo." not in captured["sql"]
        # table_id reflects the unqualified reference, not 'dbo.Customers'.
        assert sample.table_id == "Customers"

    def test_get_sample_data_none_schema_real_generic_dialect_unqualified(self, mock_engine):
        """Real dialect + schema_name=None must build an unqualified reference.

        Regression for the Phase 15 SC3 blocker: when a real dialect has
        ``default_schema=None`` and ``schema_name`` reaches ``get_sample_data``
        as ``None``, the ``else`` branch must not pass ``None`` to
        ``quote_identifier`` — doing so emits a synthetic ``"None"`` schema
        segment (and raises ``AttributeError`` on dialects that escape via
        ``str.replace``). The reference must be the bare quoted table only.
        """
        from src.db.dialects import GenericDialect

        captured = {}

        def fake_execute(stmt):
            captured["sql"] = str(stmt)
            result = MagicMock()
            result.__iter__ = lambda x: iter([])
            return result

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = fake_execute
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine, dialect=GenericDialect())
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name=None,
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        sql = captured["sql"]
        # The bare, quoted table reference is present (ANSI double-quote).
        assert '"Customers"' in sql
        # No synthetic None schema segment in any form.
        assert "None." not in sql
        assert '"None"' not in sql
        # table_id reflects the unqualified reference.
        assert sample.table_id == "Customers"

    def test_get_sample_data_mssql_two_part_reference_preserved(self, mock_engine):
        """MSSQL 2-part schema.table reference is unchanged when schema is given.

        No-regression guard: the schema-present path must still emit the
        bracketed ``[schema].[table]`` reference after the None-schema fix.
        """
        from src.db.dialects import MssqlDialect

        captured = {}

        def fake_execute(stmt):
            captured["sql"] = str(stmt)
            result = MagicMock()
            result.__iter__ = lambda x: iter([])
            return result

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = fake_execute
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine, dialect=MssqlDialect())
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name="sales",
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        assert "[sales].[Customers]" in captured["sql"]
        assert sample.table_id == "sales.Customers"

    def test_get_sample_data_databricks_catalog_without_schema(self, mock_engine):
        r"""Databricks catalog + schema_name=None builds a 2-part catalog.table ref.

        Covers the cross-catalog branch in ``_build_sample_table_ref`` where a
        catalog is supplied but the schema is absent: the reference must be
        ``\`catalog\`.\`table\``` (no schema segment, no synthetic ``None.``),
        without emitting ``USE CATALOG``.
        """
        from src.db.dialects import DatabricksDialect

        captured = {}

        def fake_execute(stmt):
            captured["sql"] = str(stmt)
            result = MagicMock()
            result.__iter__ = lambda x: iter([])
            return result

        mock_conn = MagicMock()
        mock_conn.execute.side_effect = fake_execute
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine, dialect=DatabricksDialect())
        service.get_sample_data(
            table_name="events",
            schema_name=None,
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
            catalog="analytics",
        )

        sql = captured["sql"]
        # 2-part catalog.table reference, both segments backtick-quoted.
        assert "`analytics`.`events`" in sql
        # No synthetic None schema segment crept in between catalog and table.
        assert "None" not in sql
        assert "USE CATALOG" not in sql

    def test_build_sample_query_unknown_method_raises(self, mock_engine):
        """_build_sample_query raises ValueError for an unrecognized method.

        The enum dispatch has a fallthrough guard; a non-enum sentinel must hit
        the ``raise ValueError`` rather than silently returning None. Exercised
        directly because the public API cannot pass a bad SamplingMethod.
        """
        service = QueryService(mock_engine)
        with pytest.raises(ValueError, match="Unknown sampling method"):
            service._build_sample_query(
                sampling_method="bogus_method",
                full_table_name='"Customers"',
                column_sql="*",
                sample_size=5,
            )
