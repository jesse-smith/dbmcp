"""Unit tests for foreign key inference algorithm.

Tests for name similarity, type compatibility, and structural scoring.
"""

from unittest.mock import MagicMock

import pytest

from src.inference.relationships import ColumnInfo, ForeignKeyInferencer
from src.inference.scoring import ConfidenceScorer


@pytest.fixture
def scorer():
    return ConfidenceScorer()


class TestNameSimilarity:
    """Tests for name similarity scoring - T107, T111A"""

    def test_exact_name_match(self, scorer):
        """T111A: OrderID vs OrderID should have score 1.0"""
        score = scorer._calculate_name_similarity("CustomerID", "CustomerID", "Customers")
        assert score == 1.0

    def test_case_insensitive_match(self, scorer):
        """T111A: OrderID vs orderid (case difference) should match"""
        score = scorer._calculate_name_similarity("CustomerID", "customerid", "Customers")
        assert score == 1.0

    def test_underscore_normalized(self, scorer):
        """T111A: Order_ID vs OrderID should have high similarity"""
        score = scorer._calculate_name_similarity("Order_ID", "OrderID", "Orders")
        assert score == 1.0

    def test_table_prefix_pattern(self, scorer):
        """T111A: CustomerID in Orders referencing Customers.ID"""
        score = scorer._calculate_name_similarity("CustomerID", "ID", "Customers")
        assert score >= 0.85

    def test_medium_similarity(self, scorer):
        """T111A: CustomerNo vs CustNum should have medium-to-high similarity with table context."""
        score = scorer._calculate_name_similarity("CustomerNo", "CustNum", "Customers")
        assert 0.3 <= score <= 1.0

    def test_low_similarity(self, scorer):
        """T111A: ID vs Identifier should have low similarity"""
        score = scorer._calculate_name_similarity("ID", "Identifier", "SomeTable")
        assert score <= 0.8

    def test_no_match(self, scorer):
        """T111A: CompleteyDifferent vs UnrelatedColumn should have 0"""
        score = scorer._calculate_name_similarity("Amount", "Description", "Products")
        assert score == 0.0


class TestTypeCompatibility:
    """Tests for type compatibility checks - T108, T111B"""

    def test_exact_type_match(self, scorer):
        """T111B: INT vs INT should be compatible"""
        assert scorer._check_type_compatibility("int", "int") is True

    def test_int_bigint_compatible(self, scorer):
        """T111B: int/bigint should be compatible"""
        assert scorer._check_type_compatibility("int", "bigint") is True

    def test_varchar_nvarchar_compatible(self, scorer):
        """T111B: varchar(50)/nvarchar(100) should be compatible"""
        assert scorer._check_type_compatibility("varchar(50)", "nvarchar(100)") is True

    def test_int_varchar_incompatible(self, scorer):
        """T111B: int vs varchar should NOT be compatible"""
        assert scorer._check_type_compatibility("int", "varchar(50)") is False

    def test_date_datetime_compatible(self, scorer):
        """T111B: date/datetime should be compatible"""
        assert scorer._check_type_compatibility("date", "datetime") is True

    def test_numeric_decimal_compatible(self, scorer):
        """T111B: numeric and decimal should be compatible"""
        assert scorer._check_type_compatibility("numeric(10,2)", "decimal(12,4)") is True


class TestStructuralScoring:
    """Tests for structural hints scoring - T108"""

    def test_nullable_source_increases_score(self, scorer):
        """Nullable source column should increase score"""
        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_primary_key=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_primary_key=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, hints = scorer._calculate_structural_score(src_col, tgt_col)

        assert "source_nullable" in hints
        assert score > 0.5

    def test_target_pk_increases_score(self, scorer):
        """Target being PK should increase score"""
        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_primary_key=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_primary_key=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, hints = scorer._calculate_structural_score(src_col, tgt_col)

        assert "target_is_primary_key" in hints
        assert score > 0.7

    def test_target_unique_index_helps(self, scorer):
        """Target with unique index (not PK) should help"""
        src_col = ColumnInfo(
            name="Code", data_type="varchar", is_nullable=True,
            is_primary_key=False, is_unique=False, table_name="Products", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="Code", data_type="varchar", is_nullable=False,
            is_primary_key=False, is_unique=True, table_name="Categories", schema_name="dbo"
        )

        score, hints = scorer._calculate_structural_score(src_col, tgt_col)

        assert "target_unique_index" in hints


class TestConfidenceCalculation:
    """Tests for overall confidence calculation"""

    def test_high_confidence_for_strong_match(self, scorer):
        """Strong matches should have >80% confidence"""
        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_primary_key=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_primary_key=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, factors = scorer.calculate_confidence(src_col, tgt_col, "Customers")

        assert score >= 0.80
        assert factors.type_compatible is True

    def test_type_mismatch_vetoes(self, scorer):
        """Type mismatch should veto the relationship (score=0)"""
        src_col = ColumnInfo(
            name="CustomerID", data_type="varchar", is_nullable=True,
            is_primary_key=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_primary_key=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        score, factors = scorer.calculate_confidence(src_col, tgt_col, "Customers")

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

    def test_value_overlap_validates_strategy(self):
        """include_value_overlap=True should validate overlap_strategy - T145 (Updated from T042A)"""
        inferencer = ForeignKeyInferencer(MagicMock())

        with pytest.raises(ValueError, match="overlap_strategy"):
            inferencer.infer_relationships(
                "Orders", "dbo",
                include_value_overlap=True,
                overlap_strategy="invalid",
            )


class TestReasoningGeneration:
    """Tests for human-readable reasoning generation"""

    def test_exact_match_reasoning(self, scorer):
        """Exact match should explain clearly"""
        src_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=True,
            is_primary_key=False, is_unique=False, table_name="Orders", schema_name="dbo"
        )
        tgt_col = ColumnInfo(
            name="CustomerID", data_type="int", is_nullable=False,
            is_primary_key=True, is_unique=True, table_name="Customers", schema_name="dbo"
        )

        _, factors = scorer.calculate_confidence(src_col, tgt_col, "Customers")
        reasoning = scorer.generate_reasoning(src_col, tgt_col, factors)

        assert "name" in reasoning.lower() or "match" in reasoning.lower()
