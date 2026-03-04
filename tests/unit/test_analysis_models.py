"""Unit tests for analysis data models."""

from datetime import datetime

from src.models.analysis import (
    ColumnStatistics,
    DateTimeStats,
    FKCandidateData,
    FKCandidateResult,
    NumericStats,
    PKCandidate,
    StringStats,
)


class TestNumericStats:
    """Tests for NumericStats model."""

    def test_construction(self):
        """Test NumericStats can be constructed with valid values."""
        stats = NumericStats(
            min_value=1.0, max_value=100.0, mean_value=50.5, std_dev=28.87
        )
        assert stats.min_value == 1.0
        assert stats.max_value == 100.0
        assert stats.mean_value == 50.5
        assert stats.std_dev == 28.87

    def test_construction_with_none_values(self):
        """Test NumericStats can be constructed with None values."""
        stats = NumericStats(
            min_value=None, max_value=None, mean_value=None, std_dev=None
        )
        assert stats.min_value is None
        assert stats.max_value is None
        assert stats.mean_value is None
        assert stats.std_dev is None

    def test_to_dict(self):
        """Test to_dict returns JSON-safe dictionary."""
        stats = NumericStats(
            min_value=1.0, max_value=100.0, mean_value=50.5, std_dev=28.87
        )
        result = stats.to_dict()
        assert result == {
            "min_value": 1.0,
            "max_value": 100.0,
            "mean_value": 50.5,
            "std_dev": 28.87,
        }

    def test_to_dict_with_none_values(self):
        """Test to_dict handles None values correctly."""
        stats = NumericStats(
            min_value=None, max_value=None, mean_value=None, std_dev=None
        )
        result = stats.to_dict()
        assert result == {
            "min_value": None,
            "max_value": None,
            "mean_value": None,
            "std_dev": None,
        }


class TestDateTimeStats:
    """Tests for DateTimeStats model."""

    def test_construction(self):
        """Test DateTimeStats can be constructed with valid values."""
        min_date = datetime(2025, 1, 1, 0, 0, 0)
        max_date = datetime(2025, 12, 31, 23, 59, 59)
        stats = DateTimeStats(
            min_date=min_date,
            max_date=max_date,
            date_range_days=364,
            has_time_component=True,
        )
        assert stats.min_date == min_date
        assert stats.max_date == max_date
        assert stats.date_range_days == 364
        assert stats.has_time_component is True

    def test_construction_with_none_dates(self):
        """Test DateTimeStats can be constructed with None dates."""
        stats = DateTimeStats(
            min_date=None, max_date=None, date_range_days=None, has_time_component=False
        )
        assert stats.min_date is None
        assert stats.max_date is None
        assert stats.date_range_days is None
        assert stats.has_time_component is False

    def test_to_dict(self):
        """Test to_dict returns JSON-safe dictionary with ISO format dates."""
        min_date = datetime(2025, 1, 1, 0, 0, 0)
        max_date = datetime(2025, 12, 31, 23, 59, 59)
        stats = DateTimeStats(
            min_date=min_date,
            max_date=max_date,
            date_range_days=364,
            has_time_component=True,
        )
        result = stats.to_dict()
        assert result == {
            "min_date": "2025-01-01T00:00:00",
            "max_date": "2025-12-31T23:59:59",
            "date_range_days": 364,
            "has_time_component": True,
        }

    def test_to_dict_with_none_dates(self):
        """Test to_dict handles None dates correctly."""
        stats = DateTimeStats(
            min_date=None, max_date=None, date_range_days=None, has_time_component=False
        )
        result = stats.to_dict()
        assert result == {
            "min_date": None,
            "max_date": None,
            "date_range_days": None,
            "has_time_component": False,
        }


class TestStringStats:
    """Tests for StringStats model."""

    def test_construction(self):
        """Test StringStats can be constructed with valid values."""
        sample_values = [("Smith", 42), ("Johnson", 38), ("Williams", 35)]
        stats = StringStats(
            min_length=3,
            max_length=87,
            avg_length=24.5,
            sample_values=sample_values,
        )
        assert stats.min_length == 3
        assert stats.max_length == 87
        assert stats.avg_length == 24.5
        assert stats.sample_values == sample_values

    def test_construction_with_none_values(self):
        """Test StringStats can be constructed with None values."""
        stats = StringStats(
            min_length=None, max_length=None, avg_length=None, sample_values=[]
        )
        assert stats.min_length is None
        assert stats.max_length is None
        assert stats.avg_length is None
        assert stats.sample_values == []

    def test_to_dict(self):
        """Test to_dict returns JSON-safe dictionary."""
        sample_values = [("Smith", 42), ("Johnson", 38), ("Williams", 35)]
        stats = StringStats(
            min_length=3,
            max_length=87,
            avg_length=24.5,
            sample_values=sample_values,
        )
        result = stats.to_dict()
        assert result == {
            "min_length": 3,
            "max_length": 87,
            "avg_length": 24.5,
            "sample_values": sample_values,
        }


class TestColumnStatistics:
    """Tests for ColumnStatistics model."""

    def test_construction_basic(self):
        """Test ColumnStatistics can be constructed with basic fields."""
        stats = ColumnStatistics(
            column_name="order_id",
            table_name="orders",
            schema_name="dbo",
            data_type="int",
            total_rows=10000,
            distinct_count=10000,
            null_count=0,
            null_percentage=0.0,
        )
        assert stats.column_name == "order_id"
        assert stats.table_name == "orders"
        assert stats.schema_name == "dbo"
        assert stats.data_type == "int"
        assert stats.total_rows == 10000
        assert stats.distinct_count == 10000
        assert stats.null_count == 0
        assert stats.null_percentage == 0.0
        assert stats.numeric_stats is None
        assert stats.datetime_stats is None
        assert stats.string_stats is None

    def test_construction_with_numeric_stats(self):
        """Test ColumnStatistics with numeric stats."""
        numeric = NumericStats(
            min_value=1.0, max_value=10000.0, mean_value=5000.5, std_dev=2886.89
        )
        stats = ColumnStatistics(
            column_name="order_id",
            table_name="orders",
            schema_name="dbo",
            data_type="int",
            total_rows=10000,
            distinct_count=10000,
            null_count=0,
            null_percentage=0.0,
            numeric_stats=numeric,
        )
        assert stats.numeric_stats == numeric

    def test_construction_zero_rows(self):
        """Test ColumnStatistics with zero rows (edge case)."""
        stats = ColumnStatistics(
            column_name="empty_column",
            table_name="empty_table",
            schema_name="dbo",
            data_type="varchar(50)",
            total_rows=0,
            distinct_count=0,
            null_count=0,
            null_percentage=0.0,
        )
        assert stats.total_rows == 0
        assert stats.distinct_count == 0

    def test_to_dict_basic(self):
        """Test to_dict without type-specific stats."""
        stats = ColumnStatistics(
            column_name="order_id",
            table_name="orders",
            schema_name="dbo",
            data_type="int",
            total_rows=10000,
            distinct_count=10000,
            null_count=0,
            null_percentage=0.0,
        )
        result = stats.to_dict()
        assert result == {
            "column_name": "order_id",
            "table_name": "orders",
            "schema_name": "dbo",
            "data_type": "int",
            "total_rows": 10000,
            "distinct_count": 10000,
            "null_count": 0,
            "null_percentage": 0.0,
        }
        assert "numeric_stats" not in result
        assert "datetime_stats" not in result
        assert "string_stats" not in result

    def test_to_dict_with_numeric_stats(self):
        """Test to_dict includes numeric_stats when present."""
        numeric = NumericStats(
            min_value=1.0, max_value=10000.0, mean_value=5000.5, std_dev=2886.89
        )
        stats = ColumnStatistics(
            column_name="order_id",
            table_name="orders",
            schema_name="dbo",
            data_type="int",
            total_rows=10000,
            distinct_count=10000,
            null_count=0,
            null_percentage=0.0,
            numeric_stats=numeric,
        )
        result = stats.to_dict()
        assert "numeric_stats" in result
        assert result["numeric_stats"] == numeric.to_dict()

    def test_to_dict_with_datetime_stats(self):
        """Test to_dict includes datetime_stats when present."""
        dt_stats = DateTimeStats(
            min_date=datetime(2025, 1, 1),
            max_date=datetime(2025, 12, 31),
            date_range_days=364,
            has_time_component=True,
        )
        stats = ColumnStatistics(
            column_name="order_date",
            table_name="orders",
            schema_name="dbo",
            data_type="datetime",
            total_rows=10000,
            distinct_count=365,
            null_count=0,
            null_percentage=0.0,
            datetime_stats=dt_stats,
        )
        result = stats.to_dict()
        assert "datetime_stats" in result
        assert result["datetime_stats"] == dt_stats.to_dict()

    def test_to_dict_with_string_stats(self):
        """Test to_dict includes string_stats when present."""
        str_stats = StringStats(
            min_length=3, max_length=87, avg_length=24.5, sample_values=[("Smith", 42)]
        )
        stats = ColumnStatistics(
            column_name="customer_name",
            table_name="orders",
            schema_name="dbo",
            data_type="varchar(100)",
            total_rows=10000,
            distinct_count=850,
            null_count=12,
            null_percentage=0.12,
            string_stats=str_stats,
        )
        result = stats.to_dict()
        assert "string_stats" in result
        assert result["string_stats"] == str_stats.to_dict()


class TestPKCandidate:
    """Tests for PKCandidate model."""

    def test_construction_constraint_backed(self):
        """Test PKCandidate with constraint backing."""
        candidate = PKCandidate(
            column_name="order_id",
            data_type="int",
            is_constraint_backed=True,
            constraint_type="PRIMARY KEY",
            is_unique=True,
            is_non_null=True,
            is_pk_type=True,
        )
        assert candidate.column_name == "order_id"
        assert candidate.is_constraint_backed is True
        assert candidate.constraint_type == "PRIMARY KEY"

    def test_construction_structural_candidate(self):
        """Test PKCandidate as structural candidate (no constraint)."""
        candidate = PKCandidate(
            column_name="tracking_number",
            data_type="bigint",
            is_constraint_backed=False,
            constraint_type=None,
            is_unique=True,
            is_non_null=True,
            is_pk_type=True,
        )
        assert candidate.is_constraint_backed is False
        assert candidate.constraint_type is None

    def test_to_dict(self):
        """Test to_dict returns JSON-safe dictionary."""
        candidate = PKCandidate(
            column_name="order_id",
            data_type="int",
            is_constraint_backed=True,
            constraint_type="PRIMARY KEY",
            is_unique=True,
            is_non_null=True,
            is_pk_type=True,
        )
        result = candidate.to_dict()
        assert result == {
            "column_name": "order_id",
            "data_type": "int",
            "is_constraint_backed": True,
            "constraint_type": "PRIMARY KEY",
            "is_unique": True,
            "is_non_null": True,
            "is_pk_type": True,
        }


class TestFKCandidateData:
    """Tests for FKCandidateData model."""

    def test_construction_without_overlap(self):
        """Test FKCandidateData without overlap data."""
        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="orders",
            source_schema="dbo",
            source_data_type="int",
            target_column="id",
            target_table="customers",
            target_schema="dbo",
            target_data_type="int",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=True,
        )
        assert candidate.source_column == "customer_id"
        assert candidate.target_column == "id"
        assert candidate.overlap_count is None
        assert candidate.overlap_percentage is None

    def test_construction_with_overlap(self):
        """Test FKCandidateData with overlap data."""
        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="orders",
            source_schema="dbo",
            source_data_type="int",
            target_column="id",
            target_table="customers",
            target_schema="dbo",
            target_data_type="int",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=True,
            overlap_count=950,
            overlap_percentage=95.0,
        )
        assert candidate.overlap_count == 950
        assert candidate.overlap_percentage == 95.0

    def test_to_dict_without_overlap(self):
        """Test to_dict omits overlap fields when None."""
        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="orders",
            source_schema="dbo",
            source_data_type="int",
            target_column="id",
            target_table="customers",
            target_schema="dbo",
            target_data_type="int",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=True,
        )
        result = candidate.to_dict()
        assert "overlap_count" not in result
        assert "overlap_percentage" not in result
        assert result["source_column"] == "customer_id"
        assert result["target_column"] == "id"

    def test_to_dict_with_overlap(self):
        """Test to_dict includes overlap fields when present."""
        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="orders",
            source_schema="dbo",
            source_data_type="int",
            target_column="id",
            target_table="customers",
            target_schema="dbo",
            target_data_type="int",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=True,
            overlap_count=950,
            overlap_percentage=95.0,
        )
        result = candidate.to_dict()
        assert result["overlap_count"] == 950
        assert result["overlap_percentage"] == 95.0


class TestFKCandidateResult:
    """Tests for FKCandidateResult model."""

    def test_construction_empty(self):
        """Test FKCandidateResult with no candidates."""
        result = FKCandidateResult(
            candidates=[], total_found=0, was_limited=False, search_scope="schema: dbo"
        )
        assert len(result.candidates) == 0
        assert result.total_found == 0
        assert result.was_limited is False

    def test_construction_with_candidates(self):
        """Test FKCandidateResult with candidates."""
        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="orders",
            source_schema="dbo",
            source_data_type="int",
            target_column="id",
            target_table="customers",
            target_schema="dbo",
            target_data_type="int",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=True,
        )
        result = FKCandidateResult(
            candidates=[candidate],
            total_found=1,
            was_limited=False,
            search_scope="schema: dbo, pk_candidates_only: true",
        )
        assert len(result.candidates) == 1
        assert result.total_found == 1

    def test_construction_limited(self):
        """Test FKCandidateResult when results were limited."""
        result = FKCandidateResult(
            candidates=[],
            total_found=150,
            was_limited=True,
            search_scope="schema: dbo",
        )
        assert result.was_limited is True
        assert result.total_found == 150

    def test_to_dict(self):
        """Test to_dict returns JSON-safe dictionary."""
        candidate = FKCandidateData(
            source_column="customer_id",
            source_table="orders",
            source_schema="dbo",
            source_data_type="int",
            target_column="id",
            target_table="customers",
            target_schema="dbo",
            target_data_type="int",
            target_is_primary_key=True,
            target_is_unique=True,
            target_is_nullable=False,
            target_has_index=True,
        )
        wrapper = FKCandidateResult(
            candidates=[candidate],
            total_found=1,
            was_limited=False,
            search_scope="schema: dbo, pk_candidates_only: true",
        )
        result = wrapper.to_dict()
        assert result["total_found"] == 1
        assert result["was_limited"] is False
        assert result["search_scope"] == "schema: dbo, pk_candidates_only: true"
        assert len(result["candidates"]) == 1
        assert isinstance(result["candidates"][0], dict)
