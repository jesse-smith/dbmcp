"""Unit tests for ColumnStatsCollector (US1).

Tests cover:
- Basic stats (distinct_count, null_count, total_rows)
- Numeric stats (min/max/mean/stddev)
- Datetime stats (min/max/range/has_time_component)
- String stats (min/max/avg length, sample_values)
- Column existence check
- Column filtering by name list and by LIKE pattern
- Edge cases (all-NULL column, zero-row table, empty pattern match)
- isinstance-based type classification (dialect-aware)
- Databricks DESCRIBE EXTENDED fast path
- SQL transpilation for non-MSSQL dialects
"""

from datetime import datetime
from unittest.mock import MagicMock, Mock

import pytest
from sqlalchemy import types as sa_types
from sqlalchemy.engine import Connection

from src.analysis.column_stats import ColumnStatsCollector
from src.models.analysis import (
    ColumnStatistics,
    DateTimeStats,
    NumericStats,
    StringStats,
)


@pytest.fixture
def mock_connection():
    """Mock SQLAlchemy connection."""
    conn = Mock(spec=Connection)
    return conn


@pytest.fixture
def stats_collector(mock_connection):
    """Create ColumnStatsCollector instance with mocked connection."""
    return ColumnStatsCollector(
        connection=mock_connection,
        schema_name="dbo",
        table_name="test_table",
    )


class TestColumnExistence:
    """Test column existence validation."""

    def test_column_exists(self, stats_collector, mock_connection):
        """Verify column existence check returns True for existing column."""
        # Mock query result: column exists
        mock_result = MagicMock()
        mock_result.scalar.return_value = 1
        mock_connection.execute.return_value = mock_result

        exists = stats_collector.column_exists("test_column")

        assert exists is True
        mock_connection.execute.assert_called_once()

    def test_column_not_exists(self, stats_collector, mock_connection):
        """Verify column existence check returns False for non-existent column."""
        # Mock query result: column does not exist
        mock_result = MagicMock()
        mock_result.scalar.return_value = 0
        mock_connection.execute.return_value = mock_result

        exists = stats_collector.column_exists("nonexistent_column")

        assert exists is False
        mock_connection.execute.assert_called_once()


class TestBasicStats:
    """Test basic statistics collection."""

    def test_basic_stats_normal_column(self, stats_collector, mock_connection):
        """Collect basic stats for a normal column."""
        # Mock query result: 100 total rows, 80 distinct, 5 nulls
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, 80, 5)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_basic_stats("test_column")

        assert stats["total_rows"] == 100
        assert stats["distinct_count"] == 80
        assert stats["null_count"] == 5
        assert stats["null_percentage"] == 5.0

    def test_basic_stats_all_null_column(self, stats_collector, mock_connection):
        """Collect basic stats for a column with all NULL values."""
        # Mock query result: 100 total rows, 0 distinct, 100 nulls
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, 0, 100)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_basic_stats("null_column")

        assert stats["total_rows"] == 100
        assert stats["distinct_count"] == 0
        assert stats["null_count"] == 100
        assert stats["null_percentage"] == 100.0

    def test_basic_stats_zero_rows(self, stats_collector, mock_connection):
        """Collect basic stats for an empty table."""
        # Mock query result: 0 total rows
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0, 0, 0)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_basic_stats("test_column")

        assert stats["total_rows"] == 0
        assert stats["distinct_count"] == 0
        assert stats["null_count"] == 0
        assert stats["null_percentage"] == 0.0


class TestNumericStats:
    """Test numeric statistics collection."""

    def test_numeric_stats_integer_column(self, stats_collector, mock_connection):
        """Collect numeric stats for an integer column."""
        # Mock query result: min=1, max=100, mean=50.5, stddev=28.87
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (1.0, 100.0, 50.5, 28.87)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_numeric_stats("test_column")

        assert isinstance(stats, NumericStats)
        assert stats.min_value == 1.0
        assert stats.max_value == 100.0
        assert stats.mean_value == 50.5
        assert stats.std_dev == 28.87

    def test_numeric_stats_decimal_column(self, stats_collector, mock_connection):
        """Collect numeric stats for a decimal column."""
        # Mock query result: min=0.01, max=999.99, mean=500.0, stddev=288.68
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (0.01, 999.99, 500.0, 288.68)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_numeric_stats("price_column")

        assert isinstance(stats, NumericStats)
        assert stats.min_value == 0.01
        assert stats.max_value == 999.99
        assert stats.mean_value == 500.0
        assert stats.std_dev == 288.68

    def test_numeric_stats_all_null(self, stats_collector, mock_connection):
        """Collect numeric stats for a column with all NULL values."""
        # Mock query result: all None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (None, None, None, None)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_numeric_stats("null_column")

        assert isinstance(stats, NumericStats)
        assert stats.min_value is None
        assert stats.max_value is None
        assert stats.mean_value is None
        assert stats.std_dev is None


class TestDateTimeStats:
    """Test datetime statistics collection."""

    def test_datetime_stats_with_time_component(self, stats_collector, mock_connection):
        """Collect datetime stats for a column with time components."""
        # Mock query result: min='2025-01-01 08:30:00', max='2025-12-31 17:45:00', range=364 days, has_time=True
        min_date = datetime(2025, 1, 1, 8, 30, 0)
        max_date = datetime(2025, 12, 31, 17, 45, 0)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (min_date, max_date, 364, True)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_datetime_stats("timestamp_column")

        assert isinstance(stats, DateTimeStats)
        assert stats.min_date == min_date
        assert stats.max_date == max_date
        assert stats.date_range_days == 364
        assert stats.has_time_component is True

    def test_datetime_stats_dates_only(self, stats_collector, mock_connection):
        """Collect datetime stats for a column with date-only values (midnight)."""
        # Mock query result: all values at midnight, has_time=False
        min_date = datetime(2025, 1, 1, 0, 0, 0)
        max_date = datetime(2025, 12, 31, 0, 0, 0)
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (min_date, max_date, 364, False)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_datetime_stats("date_column")

        assert isinstance(stats, DateTimeStats)
        assert stats.min_date == min_date
        assert stats.max_date == max_date
        assert stats.date_range_days == 364
        assert stats.has_time_component is False

    def test_datetime_stats_all_null(self, stats_collector, mock_connection):
        """Collect datetime stats for a column with all NULL values."""
        # Mock query result: all None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (None, None, None, False)
        mock_connection.execute.return_value = mock_result

        stats = stats_collector.get_datetime_stats("null_date_column")

        assert isinstance(stats, DateTimeStats)
        assert stats.min_date is None
        assert stats.max_date is None
        assert stats.date_range_days is None
        assert stats.has_time_component is False


class TestStringStats:
    """Test string statistics collection."""

    def test_string_stats_normal_column(self, stats_collector, mock_connection):
        """Collect string stats for a normal varchar column."""
        # Mock length stats query
        mock_lengths = MagicMock()
        mock_lengths.fetchone.return_value = (3, 50, 25.5)

        # Mock sample values query
        mock_samples = MagicMock()
        mock_samples.fetchall.return_value = [("Smith", 42), ("Johnson", 38), ("Williams", 35)]

        # Configure side_effect to return different mocks for each call
        mock_connection.execute.side_effect = [mock_lengths, mock_samples]

        stats = stats_collector.get_string_stats("name_column", sample_size=10)

        assert isinstance(stats, StringStats)
        assert stats.min_length == 3
        assert stats.max_length == 50
        assert stats.avg_length == 25.5
        assert len(stats.sample_values) == 3
        assert stats.sample_values[0] == ("Smith", 42)

    def test_string_stats_with_custom_sample_size(self, stats_collector, mock_connection):
        """Collect string stats with custom sample size."""
        # Mock length stats
        mock_lengths = MagicMock()
        mock_lengths.fetchone.return_value = (1, 100, 50.0)

        # Mock sample values query with 5 results
        mock_samples = MagicMock()
        mock_samples.fetchall.return_value = [
            ("A", 100), ("B", 90), ("C", 80), ("D", 70), ("E", 60)
        ]

        # Return different results for different queries
        mock_connection.execute.side_effect = [mock_lengths, mock_samples]

        stats = stats_collector.get_string_stats("code_column", sample_size=5)

        assert isinstance(stats, StringStats)
        assert len(stats.sample_values) == 5
        assert stats.sample_values[0] == ("A", 100)
        assert stats.sample_values[4] == ("E", 60)

    def test_string_stats_all_null(self, stats_collector, mock_connection):
        """Collect string stats for a column with all NULL values."""
        # Mock query result: all None
        mock_result = MagicMock()
        mock_result.fetchone.return_value = (None, None, None)
        mock_connection.execute.return_value = mock_result

        # Mock empty sample values
        mock_samples = MagicMock()
        mock_samples.fetchall.return_value = []
        mock_connection.execute.side_effect = [mock_result, mock_samples]

        stats = stats_collector.get_string_stats("null_string_column")

        assert isinstance(stats, StringStats)
        assert stats.min_length is None
        assert stats.max_length is None
        assert stats.avg_length is None
        assert len(stats.sample_values) == 0


class TestColumnFiltering:
    """Test column filtering by name list and LIKE pattern."""

    def test_filter_by_column_name_list(self, stats_collector, mock_connection):
        """Get column info filtered by explicit column name list."""
        columns = ["id", "name", "email"]

        # Helper to create fresh mocks for each call (avoid state issues)
        def create_exists_mock():
            mock = MagicMock()
            mock.scalar.return_value = 1  # Configure return_value on existing MagicMock attribute
            return mock

        def create_dtype_mock():
            mock = MagicMock()
            mock.fetchone.return_value = ("int",)
            return mock

        def create_stats_mock():
            mock = MagicMock()
            mock.fetchone.return_value = (100, 100, 0)
            return mock

        def create_numeric_mock():
            mock = MagicMock()
            mock.fetchone.return_value = (1.0, 100.0, 50.5, 28.87)
            return mock

        # Set up side_effect for all execute calls (3 columns × 4 calls each: exists, dtype, stats, numeric)
        mock_connection.execute.side_effect = [
            create_exists_mock(), create_dtype_mock(), create_stats_mock(), create_numeric_mock(),  # id
            create_exists_mock(), create_dtype_mock(), create_stats_mock(), create_numeric_mock(),  # name
            create_exists_mock(), create_dtype_mock(), create_stats_mock(), create_numeric_mock(),  # email
        ]

        result = stats_collector.get_columns_info(columns=columns)

        assert len(result) == 3
        assert all(isinstance(stat, ColumnStatistics) for stat in result)
        assert [stat.column_name for stat in result] == ["id", "name", "email"]

    def test_filter_by_like_pattern(self, stats_collector, mock_connection):
        """Get column info filtered by LIKE pattern."""
        # Mock pattern match query returning columns ending in _id
        mock_pattern_result = MagicMock()
        mock_pattern_result.fetchall = MagicMock(return_value=[
            ("customer_id", "int"),
            ("order_id", "int"),
            ("product_id", "int"),
        ])

        # Helper to create fresh mocks for each call
        def create_exists_mock():
            mock = MagicMock()
            mock.scalar.return_value = 1
            return mock

        def create_dtype_mock():
            mock = MagicMock()
            mock.fetchone.return_value = ("int",)
            return mock

        def create_stats_mock():
            mock = MagicMock()
            mock.fetchone.return_value = (100, 100, 0)
            return mock

        def create_numeric_mock():
            mock = MagicMock()
            mock.fetchone.return_value = (1.0, 100.0, 50.5, 28.87)
            return mock

        # Set up side_effect: 1 pattern query + (3 columns × 4 calls each: exists, dtype, stats, numeric)
        mock_connection.execute.side_effect = [
            mock_pattern_result,  # pattern match query
            create_exists_mock(), create_dtype_mock(), create_stats_mock(), create_numeric_mock(),  # customer_id
            create_exists_mock(), create_dtype_mock(), create_stats_mock(), create_numeric_mock(),  # order_id
            create_exists_mock(), create_dtype_mock(), create_stats_mock(), create_numeric_mock(),  # product_id
        ]

        result = stats_collector.get_columns_info(column_pattern="%_id")

        assert len(result) == 3
        assert all("_id" in stat.column_name for stat in result)

    def test_columns_takes_precedence_over_pattern(self, stats_collector, mock_connection):
        """When both columns and pattern provided, columns takes precedence."""
        columns = ["id"]
        pattern = "%_id"

        # Helper to create fresh mocks
        def create_exists_mock():
            mock = MagicMock()
            mock.scalar.return_value = 1
            return mock

        def create_dtype_mock():
            mock = MagicMock()
            mock.fetchone.return_value = ("int",)
            return mock

        def create_stats_mock():
            mock = MagicMock()
            mock.fetchone.return_value = (100, 100, 0)
            return mock

        def create_numeric_mock():
            mock = MagicMock()
            mock.fetchone.return_value = (1.0, 100.0, 50.5, 28.87)
            return mock

        # Set up side_effect for 1 column: exists, dtype, basic_stats, numeric_stats (since dtype is "int")
        mock_connection.execute.side_effect = [
            create_exists_mock(),
            create_dtype_mock(),
            create_stats_mock(),
            create_numeric_mock(),  # Added: needed for numeric type column
        ]

        result = stats_collector.get_columns_info(columns=columns, column_pattern=pattern)

        # Should only process explicit columns list, not pattern
        assert len(result) == 1
        assert result[0].column_name == "id"

    def test_empty_pattern_match(self, stats_collector, mock_connection):
        """Handle case where pattern matches no columns."""
        # Mock pattern match query returning empty result
        mock_pattern_result = MagicMock()
        mock_pattern_result.fetchall.return_value = []
        mock_connection.execute.return_value = mock_pattern_result

        result = stats_collector.get_columns_info(column_pattern="%_xyz")

        assert len(result) == 0

    def test_nonexistent_column_in_list_raises_error(self, stats_collector, mock_connection):
        """Raise error when explicit column does not exist."""
        # Mock existence check returning 0 (not found)
        mock_exists = MagicMock()
        mock_exists.scalar.return_value = 0
        mock_connection.execute.return_value = mock_exists

        with pytest.raises(ValueError, match="Column.*not found"):
            stats_collector.get_columns_info(columns=["nonexistent_column"])


class TestFullColumnStatistics:
    """Test complete ColumnStatistics model construction."""

    def test_column_statistics_with_numeric_stats(self, stats_collector, mock_connection):
        """Build full ColumnStatistics for a numeric column."""
        # Mock existence check
        mock_exists = MagicMock()
        mock_exists.scalar.return_value = 1

        # Mock get_column_data_type query
        mock_dtype = MagicMock()
        mock_dtype.fetchone.return_value = ("int",)

        # Mock basic stats
        mock_basic = MagicMock()
        mock_basic.fetchone.return_value = (1000, 950, 50)  # total, distinct, nulls

        # Mock numeric stats
        mock_numeric = MagicMock()
        mock_numeric.fetchone.return_value = (1.0, 1000.0, 500.5, 288.68)

        mock_connection.execute.side_effect = [mock_exists, mock_dtype, mock_basic, mock_numeric]

        result = stats_collector.get_columns_info(columns=["id"])

        assert len(result) == 1
        stat = result[0]
        assert stat.column_name == "id"
        assert stat.table_name == "test_table"
        assert stat.schema_name == "dbo"
        assert stat.total_rows == 1000
        assert stat.distinct_count == 950
        assert stat.null_count == 50
        assert stat.null_percentage == 5.0
        assert stat.numeric_stats is not None
        assert stat.numeric_stats.min_value == 1.0
        assert stat.datetime_stats is None
        assert stat.string_stats is None

    def test_column_statistics_with_datetime_stats(self, stats_collector, mock_connection):
        """Build full ColumnStatistics for a datetime column."""
        # Mock existence check
        mock_exists = MagicMock()
        mock_exists.scalar.return_value = 1

        # Mock get_column_data_type query
        mock_dtype = MagicMock()
        mock_dtype.fetchone.return_value = ("datetime",)

        # Mock basic stats
        mock_basic = MagicMock()
        mock_basic.fetchone.return_value = (365, 365, 0)

        # Mock datetime stats
        min_date = datetime(2025, 1, 1, 0, 0, 0)
        max_date = datetime(2025, 12, 31, 23, 59, 59)
        mock_datetime = MagicMock()
        mock_datetime.fetchone.return_value = (min_date, max_date, 364, True)

        mock_connection.execute.side_effect = [mock_exists, mock_dtype, mock_basic, mock_datetime]

        result = stats_collector.get_columns_info(columns=["created_at"])

        assert len(result) == 1
        stat = result[0]
        assert stat.datetime_stats is not None
        assert stat.datetime_stats.has_time_component is True
        assert stat.numeric_stats is None
        assert stat.string_stats is None

    def test_column_statistics_with_string_stats(self, stats_collector, mock_connection):
        """Build full ColumnStatistics for a string column."""
        # Mock existence check
        mock_exists = MagicMock()
        mock_exists.scalar.return_value = 1

        # Mock get_column_data_type query
        mock_dtype = MagicMock()
        mock_dtype.fetchone.return_value = ("varchar",)

        # Mock basic stats
        mock_basic = MagicMock()
        mock_basic.fetchone.return_value = (1000, 850, 12)

        # Mock string length stats
        mock_lengths = MagicMock()
        mock_lengths.fetchone.return_value = (3, 87, 24.5)

        # Mock sample values
        mock_samples = MagicMock()
        mock_samples.fetchall.return_value = [("Smith", 42), ("Johnson", 38)]

        mock_connection.execute.side_effect = [mock_exists, mock_dtype, mock_basic, mock_lengths, mock_samples]

        result = stats_collector.get_columns_info(columns=["name"])

        assert len(result) == 1
        stat = result[0]
        assert stat.string_stats is not None
        assert stat.string_stats.min_length == 3
        assert len(stat.string_stats.sample_values) == 2
        assert stat.numeric_stats is None
        assert stat.datetime_stats is None


# --- Inspector shape fixture (dialect fixtures live in tests/conftest.py) ---


@pytest.fixture
def sa_types_inspector():
    """Mock SQLAlchemy Inspector populated with sa_types.TypeEngine column dicts.

    Local file-level fixture. Named to avoid shadowing the conftest-level
    `mock_inspector` fixture (which has a different column shape).
    """
    inspector = Mock()
    inspector.get_columns.return_value = [
        {"name": "id", "type": sa_types.Integer()},
        {"name": "price", "type": sa_types.Numeric()},
        {"name": "name", "type": sa_types.String(length=100)},
        {"name": "created_at", "type": sa_types.DateTime()},
        {"name": "data", "type": sa_types.LargeBinary()},
    ]
    return inspector


class TestTypeClassification:
    """Test isinstance-based _get_type_category() method."""

    def test_integer_is_numeric(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.Integer()) == "numeric"

    def test_numeric_is_numeric(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.Numeric()) == "numeric"

    def test_float_is_numeric(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.Float()) == "numeric"

    def test_money_is_numeric(self, mock_connection):
        """MONEY type classified via name fallback (doesn't inherit Numeric)."""
        # Create a mock type with class name MONEY
        money_type = type("MONEY", (sa_types.TypeEngine,), {})()
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(money_type) == "numeric"

    def test_smallmoney_is_numeric(self, mock_connection):
        """SMALLMONEY type classified via name fallback."""
        smallmoney_type = type("SMALLMONEY", (sa_types.TypeEngine,), {})()
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(smallmoney_type) == "numeric"

    def test_datetime_is_datetime(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.DateTime()) == "datetime"

    def test_date_is_datetime(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.Date()) == "datetime"

    def test_time_is_datetime(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.Time()) == "datetime"

    def test_string_is_string(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.String()) == "string"

    def test_text_is_string(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.Text()) == "string"

    def test_largebinary_is_other(self, mock_connection):
        collector = ColumnStatsCollector(mock_connection, "dbo", "t")
        assert collector._get_type_category(sa_types.LargeBinary()) == "other"


class TestInspectorColumnDiscovery:
    """Test Inspector-based column methods."""

    def test_column_exists_uses_inspector(self, mock_connection, sa_types_inspector):
        """column_exists uses Inspector.get_columns() when inspector provided."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", inspector=sa_types_inspector
        )
        assert collector.column_exists("id") is True
        assert collector.column_exists("nonexistent") is False
        # Connection should NOT have been called (Inspector used instead)
        mock_connection.execute.assert_not_called()

    def test_get_columns_by_pattern_uses_inspector(self, mock_connection, sa_types_inspector):
        """get_columns_by_pattern uses Inspector with Python fnmatch filtering."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", inspector=sa_types_inspector
        )
        # Pattern %_at should match created_at
        results = collector.get_columns_by_pattern("%_at")
        assert len(results) == 1
        assert results[0][0] == "created_at"
        assert isinstance(results[0][1], sa_types.TypeEngine)
        mock_connection.execute.assert_not_called()

    def test_get_column_data_type_returns_type_obj(self, mock_connection, sa_types_inspector):
        """get_column_data_type returns TypeEngine when inspector provided."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", inspector=sa_types_inspector
        )
        result = collector.get_column_data_type("id")
        assert isinstance(result, sa_types.TypeEngine)
        mock_connection.execute.assert_not_called()


class TestDatabricksFastPath:
    """Test Databricks DESCRIBE EXTENDED fast path."""

    @pytest.mark.dialects('databricks')
    def test_fast_path_returns_stats_when_present(
        self, mock_connection, dialect, sa_types_inspector
    ):
        """DESCRIBE EXTENDED returns stats -> fast path used."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t",
            dialect=dialect.dialect, inspector=sa_types_inspector,
        )

        # Mock DESCRIBE EXTENDED result
        desc_result = MagicMock()
        desc_result.fetchall.return_value = [
            ("col_name", "id"),
            ("data_type", "int"),
            ("min", "1"),
            ("max", "1000"),
            ("num_nulls", "5"),
            ("distinct_count", "995"),
            ("avg_col_len", "4"),
            ("max_col_len", "4"),
        ]
        mock_connection.execute.return_value = desc_result

        stats = collector._try_describe_extended_stats("id")
        assert stats is not None
        assert stats["min"] == "1"
        assert stats["max"] == "1000"
        assert stats["num_nulls"] == "5"
        assert stats["distinct_count"] == "995"

    @pytest.mark.dialects('databricks')
    def test_fast_path_returns_none_when_stats_absent(
        self, mock_connection, dialect, sa_types_inspector
    ):
        """DESCRIBE EXTENDED returns empty stats -> None (fall back to Tier 2)."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t",
            dialect=dialect.dialect, inspector=sa_types_inspector,
        )

        desc_result = MagicMock()
        desc_result.fetchall.return_value = [
            ("col_name", "id"),
            ("data_type", "int"),
            ("min", ""),
            ("max", ""),
            ("num_nulls", ""),
            ("distinct_count", ""),
        ]
        mock_connection.execute.return_value = desc_result

        stats = collector._try_describe_extended_stats("id")
        assert stats is None

    @pytest.mark.dialects('mssql', 'generic')
    def test_fast_path_skipped_for_non_databricks(
        self, mock_connection, dialect, sa_types_inspector
    ):
        """DESCRIBE EXTENDED is not attempted for non-databricks dialects.

        Parametrized across mssql and generic to verify both skip the fast
        path without hitting the connection. Databricks behavior is covered
        by test_fast_path_returns_stats_when_present.
        """
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t",
            dialect=dialect.dialect, inspector=sa_types_inspector,
        )
        stats = collector._try_describe_extended_stats("id")
        assert stats is None
        mock_connection.execute.assert_not_called()

    def test_fast_path_skipped_when_no_dialect(self, mock_connection, sa_types_inspector):
        """DESCRIBE EXTENDED not attempted when dialect is None."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", inspector=sa_types_inspector
        )
        stats = collector._try_describe_extended_stats("id")
        assert stats is None
        mock_connection.execute.assert_not_called()

    @pytest.mark.dialects('databricks')
    def test_build_stats_from_describe_extended_numeric(
        self, mock_connection, dialect, sa_types_inspector
    ):
        """Build ColumnStatistics from DESCRIBE EXTENDED for numeric column."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t",
            dialect=dialect.dialect, inspector=sa_types_inspector,
        )
        desc_stats = {
            "min": "1",
            "max": "1000",
            "num_nulls": "5",
            "distinct_count": "995",
        }
        result = collector._build_stats_from_describe_extended(
            "id", sa_types.Integer(), desc_stats
        )
        assert isinstance(result, ColumnStatistics)
        assert result.null_count == 5
        assert result.distinct_count == 995
        assert result.numeric_stats is not None
        assert result.numeric_stats.min_value == 1.0
        assert result.numeric_stats.max_value == 1000.0


class TestTranspilation:
    """Test SQL transpilation for non-MSSQL dialects."""

    def test_tsql_queries_unchanged_when_dialect_none(self, mock_connection):
        """SQL passes through unchanged when dialect is None (MSSQL backward compat)."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", dialect=None
        )

        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, 80, 5)
        mock_connection.execute.return_value = mock_result

        collector.get_basic_stats("col")

        # The SQL should contain TSQL bracket syntax unchanged
        call_args = mock_connection.execute.call_args
        sql_text = str(call_args[0][0])
        assert "[col]" in sql_text

    @pytest.mark.dialects('mssql')
    def test_tsql_queries_unchanged_when_dialect_is_mssql(
        self, mock_connection, dialect
    ):
        """SQL passes through unchanged when dialect is MSSQL."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", dialect=dialect.dialect
        )

        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, 80, 5)
        mock_connection.execute.return_value = mock_result

        collector.get_basic_stats("col")

        call_args = mock_connection.execute.call_args
        sql_text = str(call_args[0][0])
        assert "[col]" in sql_text

    @pytest.mark.dialects('databricks')
    def test_queries_transpiled_for_databricks(
        self, mock_connection, dialect
    ):
        """SQL is transpiled when dialect is Databricks."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", dialect=dialect.dialect
        )

        mock_result = MagicMock()
        mock_result.fetchone.return_value = (100, 80, 5)
        mock_connection.execute.return_value = mock_result

        collector.get_basic_stats("col")

        # The SQL should have been transpiled (bracket quotes converted to backticks)
        call_args = mock_connection.execute.call_args
        sql_text = str(call_args[0][0])
        # After transpilation, TSQL brackets should be replaced with backticks
        assert "[col]" not in sql_text

    @pytest.mark.dialects('databricks')
    def test_datetime_time_check_uses_hour_for_databricks(
        self, mock_connection, dialect
    ):
        """Databricks datetime query uses HOUR/MINUTE/SECOND for time check."""
        collector = ColumnStatsCollector(
            mock_connection, "dbo", "t", dialect=dialect.dialect
        )

        mock_result = MagicMock()
        mock_result.fetchone.return_value = (None, None, None, False)
        mock_connection.execute.return_value = mock_result

        collector.get_datetime_stats("ts_col")

        call_args = mock_connection.execute.call_args
        sql_text = str(call_args[0][0])
        # Should use HOUR/MINUTE/SECOND instead of CAST(... AS TIME)
        # Note: sqlglot may insert CAST(... AS TIMESTAMP) for DATEDIFF, so check
        # specifically that there's no "AS TIME)" pattern (the MSSQL time check)
        assert "AS TIME)" not in sql_text.upper()
        assert "HOUR" in sql_text.upper()
