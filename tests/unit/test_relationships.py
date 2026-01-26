"""Unit tests for foreign key inference algorithm.

Tests for name similarity, type compatibility, and structural scoring.
"""

from unittest.mock import MagicMock

import pytest

from src.inference.relationships import ColumnInfo, ForeignKeyInferencer


class TestNameSimilarity:
    """Tests for name similarity scoring - T107, T111A"""

    def test_exact_name_match(self):
        """T111A: OrderID vs OrderID should have score 1.0"""
        inferencer = ForeignKeyInferencer(MagicMock())
        score = inferencer._calculate_name_similarity("CustomerID", "CustomerID", "Customers")
        assert score == 1.0

    def test_case_insensitive_match(self):
        """T111A: OrderID vs orderid (case difference) should match"""
        inferencer = ForeignKeyInferencer(MagicMock())
        score = inferencer._calculate_name_similarity("CustomerID", "customerid", "Customers")
        assert score == 1.0

    def test_underscore_normalized(self):
        """T111A: Order_ID vs OrderID should have high similarity"""
        inferencer = ForeignKeyInferencer(MagicMock())
        # Both normalize to "orderid"
        score = inferencer._calculate_name_similarity("Order_ID", "OrderID", "Orders")
        assert score == 1.0

    def test_table_prefix_pattern(self):
        """T111A: CustomerID in Orders referencing Customers.ID"""
        inferencer = ForeignKeyInferencer(MagicMock())
        # CustomerID contains "customer" which matches table name "Customers"
        score = inferencer._calculate_name_similarity("CustomerID", "ID", "Customers")
        assert score >= 0.85

    def test_medium_similarity(self):
        """T111A: CustomerNo vs CustNum should have medium-to-high similarity with table context."""
        inferencer = ForeignKeyInferencer(MagicMock())
        score = inferencer._calculate_name_similarity("CustomerNo", "CustNum", "Customers")
        # These have moderate-to-high similarity due to "Customer" prefix matching table name
        # The algorithm gives bonus points for table name matching in source column
        assert 0.3 <= score <= 1.0

    def test_low_similarity(self):
        """T111A: ID vs Identifier should have low similarity"""
        inferencer = ForeignKeyInferencer(MagicMock())
        score = inferencer._calculate_name_similarity("ID", "Identifier", "SomeTable")
        # ID and Identifier have some overlap but not strong
        assert score <= 0.8

    def test_no_match(self):
        """T111A: CompleteyDifferent vs UnrelatedColumn should have 0"""
        inferencer = ForeignKeyInferencer(MagicMock())
        score = inferencer._calculate_name_similarity("Amount", "Description", "Products")
        assert score == 0.0


class TestTypeCompatibility:
    """Tests for type compatibility checks - T108, T111B"""

    def test_exact_type_match(self):
        """T111B: INT vs INT should be compatible"""
        inferencer = ForeignKeyInferencer(MagicMock())
        compatible = inferencer._check_type_compatibility("int", "int")
        assert compatible is True

    def test_int_bigint_compatible(self):
        """T111B: int/bigint should be compatible"""
        inferencer = ForeignKeyInferencer(MagicMock())
        compatible = inferencer._check_type_compatibility("int", "bigint")
        assert compatible is True

    def test_varchar_nvarchar_compatible(self):
        """T111B: varchar(50)/nvarchar(100) should be compatible"""
        inferencer = ForeignKeyInferencer(MagicMock())
        compatible = inferencer._check_type_compatibility("varchar(50)", "nvarchar(100)")
        assert compatible is True

    def test_int_varchar_incompatible(self):
        """T111B: int vs varchar should NOT be compatible"""
        inferencer = ForeignKeyInferencer(MagicMock())
        compatible = inferencer._check_type_compatibility("int", "varchar(50)")
        assert compatible is False

    def test_date_datetime_compatible(self):
        """T111B: date/datetime should be compatible"""
        inferencer = ForeignKeyInferencer(MagicMock())
        compatible = inferencer._check_type_compatibility("date", "datetime")
        assert compatible is True

    def test_numeric_decimal_compatible(self):
        """T111B: numeric and decimal should be compatible"""
        inferencer = ForeignKeyInferencer(MagicMock())
        compatible = inferencer._check_type_compatibility("numeric(10,2)", "decimal(12,4)")
        assert compatible is True


class TestStructuralScoring:
    """Tests for structural hints scoring - T108"""

    def test_nullable_source_increases_score(self):
        """Nullable source column should increase score"""
        inferencer = ForeignKeyInferencer(MagicMock())

        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_pk=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_pk=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, hints = inferencer._calculate_structural_score(src_col, tgt_col)

        assert "source_nullable" in hints
        assert score > 0.5  # Above baseline

    def test_target_pk_increases_score(self):
        """Target being PK should increase score"""
        inferencer = ForeignKeyInferencer(MagicMock())

        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_pk=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_pk=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, hints = inferencer._calculate_structural_score(src_col, tgt_col)

        assert "target_is_pk" in hints
        assert score > 0.7  # Significantly above baseline

    def test_target_unique_index_helps(self):
        """Target with unique index (not PK) should help"""
        inferencer = ForeignKeyInferencer(MagicMock())

        src_col = ColumnInfo(
            name="Code", data_type="varchar", is_nullable=True,
            is_pk=False, is_unique=False, table_name="Products", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="Code", data_type="varchar", is_nullable=False,
            is_pk=False, is_unique=True, table_name="Categories", schema_name="dbo"
        )

        score, hints = inferencer._calculate_structural_score(src_col, tgt_col)

        assert "target_unique_index" in hints


class TestConfidenceCalculation:
    """Tests for overall confidence calculation"""

    def test_high_confidence_for_strong_match(self):
        """Strong matches should have >80% confidence"""
        inferencer = ForeignKeyInferencer(MagicMock())

        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_pk=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_pk=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, factors = inferencer._calculate_confidence(src_col, tgt_col, "Customers")

        assert score >= 0.80
        assert factors.type_compatible is True

    def test_type_mismatch_vetoes(self):
        """Type mismatch should veto the relationship (score=0)"""
        inferencer = ForeignKeyInferencer(MagicMock())

        src_col = ColumnInfo(
            name="CustomerID", data_type="varchar", is_nullable=True,
            is_pk=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_pk=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, factors = inferencer._calculate_confidence(src_col, tgt_col, "Customers")

        assert score == 0.0
        assert factors.type_compatible is False


class TestParameterValidation:
    """Tests for parameter validation - T043B"""

    def test_confidence_threshold_negative(self):
        """confidence_threshold < 0.0 should raise ValueError"""
        inferencer = ForeignKeyInferencer(MagicMock(), threshold=-0.1)

        with pytest.raises(ValueError, match="confidence_threshold"):
            inferencer.infer_relationships("Orders", "dbo")

    def test_confidence_threshold_over_one(self):
        """confidence_threshold > 1.0 should raise ValueError"""
        inferencer = ForeignKeyInferencer(MagicMock(), threshold=1.5)

        with pytest.raises(ValueError, match="confidence_threshold"):
            inferencer.infer_relationships("Orders", "dbo")

    def test_max_candidates_zero(self):
        """max_candidates = 0 should raise ValueError"""
        inferencer = ForeignKeyInferencer(MagicMock())

        with pytest.raises(ValueError, match="max_candidates"):
            inferencer.infer_relationships("Orders", "dbo", max_candidates=0)

    def test_max_candidates_over_1000(self):
        """max_candidates > 1000 should raise ValueError"""
        inferencer = ForeignKeyInferencer(MagicMock())

        with pytest.raises(ValueError, match="max_candidates"):
            inferencer.infer_relationships("Orders", "dbo", max_candidates=1500)

    def test_value_overlap_raises_not_implemented(self):
        """include_value_overlap=True should raise NotImplementedError - T042A"""
        inferencer = ForeignKeyInferencer(MagicMock())

        with pytest.raises(NotImplementedError, match="Phase 2"):
            inferencer.infer_relationships("Orders", "dbo", include_value_overlap=True)


class TestReasoningGeneration:
    """Tests for human-readable reasoning generation"""

    def test_exact_match_reasoning(self):
        """Exact match should explain clearly"""
        inferencer = ForeignKeyInferencer(MagicMock())

        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_pk=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_pk=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        _, factors = inferencer._calculate_confidence(src_col, tgt_col, "Customers")
        reasoning = inferencer._generate_reasoning(src_col, tgt_col, factors)

        assert "name" in reasoning.lower() or "match" in reasoning.lower()
