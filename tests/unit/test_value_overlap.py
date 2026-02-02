"""Unit tests for value overlap analysis (T147).

Tests both full_comparison and sampling strategies for the
ValueOverlapAnalyzer class.
"""

from unittest.mock import MagicMock

import pytest

from src.inference.value_overlap import (
    OverlapResult,
    OverlapStrategy,
    ValueOverlapAnalyzer,
)


class TestOverlapResult:
    """Tests for OverlapResult dataclass."""

    def test_to_dict(self):
        """Test OverlapResult serialization."""
        result = OverlapResult(
            source_table="dbo.Orders",
            source_column="CustomerID",
            target_table="dbo.Customers",
            target_column="CustomerID",
            overlap_score=0.85,
            source_distinct_count=100,
            target_distinct_count=50,
            intersection_count=42,
            strategy=OverlapStrategy.SAMPLING,
            sample_size=1000,
            analysis_time_ms=150,
            timed_out=False,
        )

        d = result.to_dict()

        assert d["source_table"] == "dbo.Orders"
        assert d["source_column"] == "CustomerID"
        assert d["target_table"] == "dbo.Customers"
        assert d["target_column"] == "CustomerID"
        assert d["overlap_score"] == 0.85
        assert d["source_distinct_count"] == 100
        assert d["target_distinct_count"] == 50
        assert d["intersection_count"] == 42
        assert d["strategy"] == "sampling"
        assert d["sample_size"] == 1000
        assert d["analysis_time_ms"] == 150
        assert d["timed_out"] is False

    def test_to_dict_full_comparison(self):
        """Test OverlapResult serialization for full_comparison strategy."""
        result = OverlapResult(
            source_table="dbo.Orders",
            source_column="CustomerID",
            target_table="dbo.Customers",
            target_column="CustomerID",
            overlap_score=0.92,
            source_distinct_count=1000,
            target_distinct_count=500,
            intersection_count=460,
            strategy=OverlapStrategy.FULL_COMPARISON,
            sample_size=None,
            analysis_time_ms=500,
            timed_out=False,
        )

        d = result.to_dict()

        assert d["strategy"] == "full_comparison"
        assert d["sample_size"] is None


class TestOverlapStrategy:
    """Tests for OverlapStrategy enum."""

    def test_strategy_values(self):
        """Test strategy enum values."""
        assert OverlapStrategy.FULL_COMPARISON.value == "full_comparison"
        assert OverlapStrategy.SAMPLING.value == "sampling"

    def test_strategy_from_string(self):
        """Test creating strategy from string."""
        assert OverlapStrategy("full_comparison") == OverlapStrategy.FULL_COMPARISON
        assert OverlapStrategy("sampling") == OverlapStrategy.SAMPLING


class TestValueOverlapAnalyzer:
    """Tests for ValueOverlapAnalyzer class."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        engine = MagicMock()
        return engine

    @pytest.fixture
    def analyzer(self, mock_engine):
        """Create a ValueOverlapAnalyzer instance."""
        return ValueOverlapAnalyzer(
            engine=mock_engine,
            timeout_seconds=10,
            default_sample_size=1000,
        )

    def test_initialization(self, mock_engine):
        """Test analyzer initialization."""
        analyzer = ValueOverlapAnalyzer(
            engine=mock_engine,
            timeout_seconds=5,
            default_sample_size=500,
        )

        assert analyzer.engine == mock_engine
        assert analyzer.timeout_seconds == 5
        assert analyzer.default_sample_size == 500

    def test_initialization_defaults(self, mock_engine):
        """Test analyzer initialization with defaults."""
        analyzer = ValueOverlapAnalyzer(engine=mock_engine)

        assert analyzer.timeout_seconds == 10  # DEFAULT_OVERLAP_TIMEOUT_SECONDS
        assert analyzer.default_sample_size == 1000  # DEFAULT_SAMPLE_SIZE


class TestFullComparisonStrategy:
    """Tests for full_comparison strategy."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine with connection."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=None)
        return engine, conn

    def test_full_comparison_perfect_overlap(self, mock_engine):
        """Test full comparison with 100% overlap."""
        engine, conn = mock_engine

        # Mock query results
        # Source distinct count: 10
        # Target distinct count: 10
        # Intersection: 10
        # Jaccard = 10 / (10 + 10 - 10) = 10/10 = 1.0
        conn.execute.return_value.scalar.side_effect = [10, 10, 10]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="CustomerID",
            source_schema="dbo",
            target_table="Customers",
            target_column="CustomerID",
            target_schema="dbo",
            strategy=OverlapStrategy.FULL_COMPARISON,
        )

        assert result.overlap_score == 1.0
        assert result.source_distinct_count == 10
        assert result.target_distinct_count == 10
        assert result.intersection_count == 10
        assert result.strategy == OverlapStrategy.FULL_COMPARISON
        assert result.sample_size is None

    def test_full_comparison_partial_overlap(self, mock_engine):
        """Test full comparison with partial overlap."""
        engine, conn = mock_engine

        # Source distinct count: 100
        # Target distinct count: 50
        # Intersection: 40
        # Jaccard = 40 / (100 + 50 - 40) = 40/110 = 0.3636
        conn.execute.return_value.scalar.side_effect = [100, 50, 40]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="CustomerID",
            source_schema="dbo",
            target_table="Customers",
            target_column="CustomerID",
            target_schema="dbo",
            strategy=OverlapStrategy.FULL_COMPARISON,
        )

        assert 0.36 <= result.overlap_score <= 0.37
        assert result.source_distinct_count == 100
        assert result.target_distinct_count == 50
        assert result.intersection_count == 40

    def test_full_comparison_no_overlap(self, mock_engine):
        """Test full comparison with no overlap."""
        engine, conn = mock_engine

        # Source distinct count: 100
        # Target distinct count: 50
        # Intersection: 0
        # Jaccard = 0 / (100 + 50 - 0) = 0/150 = 0.0
        conn.execute.return_value.scalar.side_effect = [100, 50, 0]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="StatusCode",
            source_schema="dbo",
            target_table="Products",
            target_column="CategoryID",
            target_schema="dbo",
            strategy=OverlapStrategy.FULL_COMPARISON,
        )

        assert result.overlap_score == 0.0
        assert result.intersection_count == 0

    def test_full_comparison_empty_columns(self, mock_engine):
        """Test full comparison with empty columns."""
        engine, conn = mock_engine

        # All counts are 0
        conn.execute.return_value.scalar.side_effect = [0, 0, 0]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="EmptyTable",
            source_column="ID",
            source_schema="dbo",
            target_table="OtherEmpty",
            target_column="ID",
            target_schema="dbo",
            strategy=OverlapStrategy.FULL_COMPARISON,
        )

        assert result.overlap_score == 0.0


class TestSamplingStrategy:
    """Tests for sampling strategy."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine with connection."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=None)
        return engine, conn

    def test_sampling_high_containment(self, mock_engine):
        """Test sampling with high containment ratio."""
        engine, conn = mock_engine

        # Mock sample query - returns 100 sampled values
        sample_result = MagicMock()
        sample_result.fetchall.return_value = [(i,) for i in range(100)]

        # Mock target distinct count
        target_count_result = MagicMock()
        target_count_result.scalar.return_value = 50

        # Mock intersection query - 85 matches
        match_result = MagicMock()
        match_result.scalar.return_value = 85

        # Set up execute to return different results based on call order
        conn.execute.side_effect = [sample_result, target_count_result, match_result]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="CustomerID",
            source_schema="dbo",
            target_table="Customers",
            target_column="CustomerID",
            target_schema="dbo",
            strategy=OverlapStrategy.SAMPLING,
            sample_size=100,
        )

        # Containment = 85/100 = 0.85
        assert result.overlap_score == 0.85
        assert result.source_distinct_count == 100
        assert result.target_distinct_count == 50
        assert result.intersection_count == 85
        assert result.strategy == OverlapStrategy.SAMPLING
        assert result.sample_size == 100

    def test_sampling_low_containment(self, mock_engine):
        """Test sampling with low containment ratio."""
        engine, conn = mock_engine

        # Mock sample query - returns 50 sampled values
        sample_result = MagicMock()
        sample_result.fetchall.return_value = [(i,) for i in range(50)]

        # Mock target distinct count
        target_count_result = MagicMock()
        target_count_result.scalar.return_value = 100

        # Mock intersection query - only 5 matches
        match_result = MagicMock()
        match_result.scalar.return_value = 5

        conn.execute.side_effect = [sample_result, target_count_result, match_result]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="RandomCode",
            source_schema="dbo",
            target_table="Products",
            target_column="SKU",
            target_schema="dbo",
            strategy=OverlapStrategy.SAMPLING,
            sample_size=50,
        )

        # Containment = 5/50 = 0.10
        assert result.overlap_score == 0.10
        assert result.intersection_count == 5

    def test_sampling_empty_source(self, mock_engine):
        """Test sampling with empty source column."""
        engine, conn = mock_engine

        # Mock sample query - returns empty
        sample_result = MagicMock()
        sample_result.fetchall.return_value = []

        conn.execute.side_effect = [sample_result]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="EmptyTable",
            source_column="ID",
            source_schema="dbo",
            target_table="OtherTable",
            target_column="ID",
            target_schema="dbo",
            strategy=OverlapStrategy.SAMPLING,
        )

        assert result.overlap_score == 0.0
        assert result.source_distinct_count == 0

    def test_sampling_uses_default_sample_size(self, mock_engine):
        """Test that sampling uses default sample size when not specified."""
        engine, conn = mock_engine

        sample_result = MagicMock()
        sample_result.fetchall.return_value = [(i,) for i in range(100)]

        target_count_result = MagicMock()
        target_count_result.scalar.return_value = 100

        match_result = MagicMock()
        match_result.scalar.return_value = 100

        conn.execute.side_effect = [sample_result, target_count_result, match_result]

        analyzer = ValueOverlapAnalyzer(engine=engine, default_sample_size=500)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="ID",
            source_schema="dbo",
            target_table="Customers",
            target_column="ID",
            target_schema="dbo",
            strategy=OverlapStrategy.SAMPLING,
            # sample_size not specified, should use default
        )

        # Result should use default sample size
        assert result.sample_size == 500


class TestErrorHandling:
    """Tests for error handling in ValueOverlapAnalyzer."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine with connection."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=None)
        return engine, conn

    def test_database_error_returns_zero_overlap(self, mock_engine):
        """Test that database errors result in zero overlap."""
        engine, conn = mock_engine

        # Simulate database error
        conn.execute.side_effect = Exception("Database connection lost")

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="CustomerID",
            source_schema="dbo",
            target_table="Customers",
            target_column="CustomerID",
            target_schema="dbo",
            strategy=OverlapStrategy.FULL_COMPARISON,
        )

        assert result.overlap_score == 0.0
        assert result.timed_out is True  # Error treated as timeout


class TestPerformanceTracking:
    """Tests for performance metrics tracking (T146)."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine with connection."""
        engine = MagicMock()
        conn = MagicMock()
        engine.connect.return_value.__enter__ = MagicMock(return_value=conn)
        engine.connect.return_value.__exit__ = MagicMock(return_value=None)
        return engine, conn

    def test_analysis_time_tracked(self, mock_engine):
        """Test that analysis time is tracked in result."""
        engine, conn = mock_engine

        conn.execute.return_value.scalar.side_effect = [10, 10, 10]

        analyzer = ValueOverlapAnalyzer(engine=engine)
        result = analyzer.calculate_overlap(
            source_table="Orders",
            source_column="ID",
            source_schema="dbo",
            target_table="Customers",
            target_column="ID",
            target_schema="dbo",
            strategy=OverlapStrategy.FULL_COMPARISON,
        )

        # Analysis time should be recorded
        assert result.analysis_time_ms >= 0

    def test_get_overlap_stats(self, mock_engine):
        """Test retrieving performance statistics."""
        engine, _ = mock_engine

        analyzer = ValueOverlapAnalyzer(engine=engine)
        stats = analyzer.get_overlap_stats()

        # Should have entries for both strategies
        assert "full_comparison" in stats
        assert "sampling" in stats
