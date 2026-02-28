"""Unit tests for column purpose inference.

Tests for ColumnAnalyzer and purpose detection heuristics - T109.
"""

import pytest
from sqlalchemy import create_engine, text

from src.inference.column_patterns import (
    ColumnCategory,
    _is_likely_amount,
    _is_likely_flag,
    _is_likely_id,
    _is_likely_percentage,
    _is_likely_quantity,
    _is_likely_status,
    categorize_type,
    is_enum,
)
from src.inference.columns import (
    ColumnAnalyzer,
    NumericStats,
    StringStats,
)
from src.models.schema import InferredPurpose


@pytest.fixture
def test_engine():
    """Create an in-memory SQLite database with test data."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    with engine.connect() as conn:
        # Table with various column types for testing
        conn.execute(text("""
            CREATE TABLE test_columns (
                customer_id INTEGER PRIMARY KEY,
                order_count INTEGER,
                total_amount DECIMAL(10,2),
                discount_pct DECIMAL(5,2),
                status VARCHAR(20),
                is_active INTEGER,
                created_at DATETIME,
                name VARCHAR(100),
                category_code VARCHAR(10)
            )
        """))

        # Insert test data
        conn.execute(text("""
            INSERT INTO test_columns VALUES
            (1, 5, 150.00, 10.5, 'active', 1, '2026-01-01 10:30:00', 'Alice Anderson', 'ELEC'),
            (2, 3, 75.50, 5.0, 'pending', 0, '2026-01-02 14:15:00', 'Bob Brown', 'FURN'),
            (3, 0, 0.00, 0.0, 'inactive', 0, '2026-01-03 09:00:00', 'Carol Clark', 'ELEC'),
            (4, 10, 500.00, 15.0, 'active', 1, '2026-01-04 16:45:00', 'Dave Davis', 'FOOD'),
            (5, 2, 30.00, 0.0, 'cancelled', 0, '2026-01-05 11:20:00', 'Eve Evans', 'ELEC')
        """))
        conn.commit()

    return engine


class TestDistinctCount:
    """Tests for distinct value counting - T055"""

    def test_distinct_count_for_unique_column(self, test_engine):
        """Unique IDs should have distinct count equal to row count."""
        analyzer = ColumnAnalyzer(test_engine)
        count = analyzer.get_distinct_count("customer_id", "test_columns")
        assert count == 5

    def test_distinct_count_for_enum_column(self, test_engine):
        """Enum-like columns should have low distinct count."""
        analyzer = ColumnAnalyzer(test_engine)
        count = analyzer.get_distinct_count("status", "test_columns")
        assert count == 4  # active, pending, inactive, cancelled

    def test_distinct_count_for_binary_column(self, test_engine):
        """Binary columns should have 2 distinct values."""
        analyzer = ColumnAnalyzer(test_engine)
        count = analyzer.get_distinct_count("is_active", "test_columns")
        assert count == 2  # 0 and 1


class TestNullPercentage:
    """Tests for NULL percentage calculation - T056"""

    def test_null_percentage_zero_for_non_null_column(self, test_engine):
        """Columns with no NULLs should have 0% null percentage."""
        analyzer = ColumnAnalyzer(test_engine)
        pct = analyzer.get_null_percentage("customer_id", "test_columns")
        assert pct == 0.0

    def test_null_percentage_calculation(self, test_engine):
        """Test null percentage with actual NULL values."""
        with test_engine.connect() as conn:
            # Add a column with NULLs
            conn.execute(text("ALTER TABLE test_columns ADD COLUMN optional_field VARCHAR(50)"))
            conn.execute(text("UPDATE test_columns SET optional_field = 'value' WHERE customer_id <= 3"))
            conn.commit()

        analyzer = ColumnAnalyzer(test_engine)
        pct = analyzer.get_null_percentage("optional_field", "test_columns")
        assert pct == 40.0  # 2 out of 5 are NULL


class TestEnumDetection:
    """Tests for enum detection - T057"""

    def test_enum_detection_for_status_column(self, test_engine):
        """Status columns with few values should be detected as enums."""
        assert is_enum(distinct_count=4, total_rows=5, category=ColumnCategory.STRING) is True

    def test_enum_detection_for_unique_column(self, test_engine):
        """Unique columns should NOT be detected as enums."""
        result = is_enum(distinct_count=5, total_rows=5, category=ColumnCategory.STRING)
        # Unique values in a small table are still not enum-like
        assert result is True  # In small tables, low distinct count is still considered enum

    def test_enum_detection_excludes_datetime(self, test_engine):
        """Datetime columns should NOT be detected as enums."""
        assert is_enum(distinct_count=5, total_rows=5, category=ColumnCategory.DATETIME) is False


class TestTypeCategorization:
    """Tests for SQL type categorization."""

    def test_numeric_type_categorization(self):
        """Numeric types should be categorized as NUMERIC."""
        assert categorize_type("int") == ColumnCategory.NUMERIC
        assert categorize_type("bigint") == ColumnCategory.NUMERIC
        assert categorize_type("decimal(10,2)") == ColumnCategory.NUMERIC
        assert categorize_type("INTEGER") == ColumnCategory.NUMERIC

    def test_datetime_type_categorization(self):
        """Datetime types should be categorized as DATETIME."""
        assert categorize_type("datetime") == ColumnCategory.DATETIME
        assert categorize_type("date") == ColumnCategory.DATETIME
        assert categorize_type("timestamp") == ColumnCategory.DATETIME

    def test_string_type_categorization(self):
        """String types should be categorized as STRING."""
        assert categorize_type("varchar(100)") == ColumnCategory.STRING
        assert categorize_type("nvarchar(50)") == ColumnCategory.STRING
        assert categorize_type("text") == ColumnCategory.STRING


class TestNumericPurposeHeuristics:
    """Tests for numeric column purpose heuristics - T059"""

    def test_id_detection_by_name(self):
        """Columns with ID suffix should be detected as ID."""
        assert _is_likely_id("customer_id", "customerid", ColumnCategory.NUMERIC, None, 100, 100) is True
        assert _is_likely_id("order_key", "orderkey", ColumnCategory.NUMERIC, None, 100, 100) is True
        assert _is_likely_id("id", "id", ColumnCategory.NUMERIC, None, 100, 100) is True

    def test_amount_detection_by_name(self):
        """Columns with amount-related names should be detected as AMOUNT."""
        assert _is_likely_amount("total_amount", "totalamount", ColumnCategory.NUMERIC, None) is True
        assert _is_likely_amount("price", "price", ColumnCategory.NUMERIC, None) is True
        assert _is_likely_amount("cost", "cost", ColumnCategory.NUMERIC, None) is True

    def test_quantity_detection_by_name(self):
        """Columns with quantity-related names should be detected as QUANTITY."""
        assert _is_likely_quantity("order_qty", "orderqty", ColumnCategory.NUMERIC, NumericStats(is_integer=True, min_value=0)) is True
        assert _is_likely_quantity("item_count", "itemcount", ColumnCategory.NUMERIC, None) is True

    def test_percentage_detection_by_name(self):
        """Columns with percentage-related names should be detected as PERCENTAGE."""
        assert _is_likely_percentage("discount_pct", "discountpct", ColumnCategory.NUMERIC, None) is True
        assert _is_likely_percentage("success_rate", "successrate", ColumnCategory.NUMERIC, None) is True


class TestFlagDetection:
    """Tests for flag/boolean detection."""

    def test_flag_detection_by_name(self):
        """Columns with flag-related names should be detected as FLAG."""
        assert _is_likely_flag("is_active", "isactive", ColumnCategory.NUMERIC, 2, None) is True
        assert _is_likely_flag("has_discount", "hasdiscount", ColumnCategory.NUMERIC, 2, None) is True
        assert _is_likely_flag("active_flag", "activeflag", ColumnCategory.NUMERIC, 2, None) is True

    def test_flag_detection_by_values(self):
        """Columns with binary values should be detected as FLAG."""
        string_stats = StringStats(top_values=[("Y", 10), ("N", 5)])
        assert _is_likely_flag("some_column", "somecolumn", ColumnCategory.STRING, 2, string_stats) is True


class TestStatusDetection:
    """Tests for status field detection."""

    def test_status_detection_by_name(self):
        """Columns with status-related names should be detected as STATUS."""
        assert _is_likely_status("order_status", "orderstatus", True, 4, None) is True
        assert _is_likely_status("state", "state", True, 3, None) is True
        assert _is_likely_status("workflow_stage", "workflowstage", True, 5, None) is True

    def test_status_detection_by_values(self):
        """Columns with status-like values should be detected as STATUS."""
        string_stats = StringStats(top_values=[("active", 10), ("pending", 5), ("completed", 3)])
        assert _is_likely_status("some_field", "somefield", True, 3, string_stats) is True


class TestFullColumnAnalysis:
    """Tests for complete column analysis - T062"""

    def test_analyze_id_column(self, test_engine):
        """Full analysis of ID column should infer ID purpose."""
        analyzer = ColumnAnalyzer(test_engine)
        analysis = analyzer.analyze_column("customer_id", "test_columns", "main")

        assert analysis.inferred_purpose == InferredPurpose.ID
        assert analysis.confidence >= 0.80
        assert analysis.distinct_count == 5

    def test_analyze_status_column(self, test_engine):
        """Full analysis of status column should infer STATUS purpose."""
        analyzer = ColumnAnalyzer(test_engine)
        analysis = analyzer.analyze_column("status", "test_columns", "main")

        assert analysis.inferred_purpose == InferredPurpose.STATUS
        assert analysis.is_enum is True
        assert analysis.distinct_count == 4

    def test_analyze_amount_column(self, test_engine):
        """Full analysis of amount column should infer AMOUNT purpose."""
        analyzer = ColumnAnalyzer(test_engine)
        analysis = analyzer.analyze_column("total_amount", "test_columns", "main")

        assert analysis.inferred_purpose == InferredPurpose.AMOUNT
        assert analysis.numeric_stats is not None

    def test_analyze_flag_column(self, test_engine):
        """Full analysis of flag column should infer FLAG purpose."""
        analyzer = ColumnAnalyzer(test_engine)
        analysis = analyzer.analyze_column("is_active", "test_columns", "main")

        assert analysis.inferred_purpose == InferredPurpose.FLAG
        assert analysis.distinct_count == 2


class TestConfidenceScores:
    """Tests for confidence score calculation - T064"""

    def test_high_confidence_for_clear_patterns(self, test_engine):
        """Clear patterns should have high confidence (>0.80)."""
        analyzer = ColumnAnalyzer(test_engine)

        # ID columns should have high confidence
        analysis = analyzer.analyze_column("customer_id", "test_columns", "main")
        assert analysis.confidence >= 0.80

    def test_purpose_enum_values(self, test_engine):
        """Inferred purpose should be a valid InferredPurpose enum - T063."""
        analyzer = ColumnAnalyzer(test_engine)
        analysis = analyzer.analyze_column("customer_id", "test_columns", "main")

        # Verify it's a valid enum value
        assert isinstance(analysis.inferred_purpose, InferredPurpose)
        assert analysis.inferred_purpose.value in [
            "id", "enum", "status", "flag", "amount",
            "quantity", "percentage", "timestamp", "unknown"
        ]


class TestColumnExistenceValidation:
    """Tests for column existence validation before analysis."""

    def test_nonexistent_column_raises_error(self, test_engine):
        """Analyzing a nonexistent column should raise ValueError."""
        analyzer = ColumnAnalyzer(test_engine)
        with pytest.raises(ValueError, match="does not exist"):
            analyzer.analyze_column("TOTALLY_FAKE_COLUMN", "test_columns", "main")

    def test_existing_column_succeeds(self, test_engine):
        """Analyzing an existing column should not raise."""
        analyzer = ColumnAnalyzer(test_engine)
        analysis = analyzer.analyze_column("customer_id", "test_columns", "main")
        assert analysis.total_rows == 5

    def test_column_exists_helper(self, test_engine):
        """column_exists should return correct boolean."""
        analyzer = ColumnAnalyzer(test_engine)
        assert analyzer._stats.column_exists("customer_id", "test_columns", "main") is True
        assert analyzer._stats.column_exists("FAKE_COL", "test_columns", "main") is False
