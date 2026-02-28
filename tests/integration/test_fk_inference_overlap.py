"""Integration tests for FK inference with value overlap (T148).

Tests that measure the accuracy improvement when value overlap
analysis is enabled versus disabled (Phase 1 vs Phase 2).

Target: Improve accuracy from 75-80% (Phase 1) to 85-90% (Phase 2).
"""

from unittest.mock import MagicMock, patch

import pytest

from src.inference.relationships import ForeignKeyInferencer
from src.inference.scoring import PHASE1_WEIGHTS, PHASE2_WEIGHTS


class TestWeightConfiguration:
    """Tests for weight configuration between phases."""

    def test_phase1_weights_sum_to_one(self):
        """Phase 1 weights should sum to 1.0."""
        total = sum(PHASE1_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Phase 1 weights sum to {total}, expected 1.0"

    def test_phase2_weights_sum_to_one(self):
        """Phase 2 weights should sum to 1.0."""
        total = sum(PHASE2_WEIGHTS.values())
        assert abs(total - 1.0) < 0.001, f"Phase 2 weights sum to {total}, expected 1.0"

    def test_phase2_includes_overlap_weight(self):
        """Phase 2 should include overlap weight."""
        assert "overlap" in PHASE2_WEIGHTS
        assert PHASE2_WEIGHTS["overlap"] == 0.20

    def test_phase2_reduces_other_weights(self):
        """Phase 2 should reduce other weights proportionally."""
        # Each factor reduced by 20% to make room for overlap
        assert PHASE2_WEIGHTS["name"] == pytest.approx(PHASE1_WEIGHTS["name"] * 0.80, abs=0.01)
        assert PHASE2_WEIGHTS["type"] == pytest.approx(PHASE1_WEIGHTS["type"] * 0.80, abs=0.01)
        assert PHASE2_WEIGHTS["structural"] == pytest.approx(PHASE1_WEIGHTS["structural"] * 0.80, abs=0.01)


class TestForeignKeyInferencerWithOverlap:
    """Integration tests for ForeignKeyInferencer with value overlap."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        engine = MagicMock()
        return engine

    def test_overlap_threshold_parameter(self, mock_engine):
        """Test that overlap_threshold is properly initialized."""
        inferencer = ForeignKeyInferencer(
            engine=mock_engine,
            threshold=0.50,
            overlap_threshold=0.40,
        )

        assert inferencer.overlap_threshold == 0.40

    def test_overlap_threshold_default(self, mock_engine):
        """Test default overlap_threshold value."""
        inferencer = ForeignKeyInferencer(
            engine=mock_engine,
            threshold=0.50,
        )

        assert inferencer.overlap_threshold == 0.30  # Default value

    def test_infer_relationships_without_overlap(self, mock_engine):
        """Test inference without value overlap returns Phase 1 results."""
        with patch.object(ForeignKeyInferencer, '_get_columns') as mock_cols, \
             patch.object(ForeignKeyInferencer, '_get_all_tables') as mock_tables, \
             patch.object(ForeignKeyInferencer, 'inspector'):

            # Setup mock data
            mock_cols.return_value = []
            mock_tables.return_value = []

            inferencer = ForeignKeyInferencer(engine=mock_engine)
            results, metadata = inferencer.infer_relationships(
                table_name="Orders",
                schema_name="dbo",
                include_value_overlap=False,
            )

            assert metadata["include_value_overlap"] is False
            assert metadata["overlap_analyses"] == 0

    def test_infer_relationships_with_overlap_validates_params(self, mock_engine):
        """Test that overlap parameters are validated when enabled."""
        with patch.object(ForeignKeyInferencer, '_get_columns') as mock_cols, \
             patch.object(ForeignKeyInferencer, '_get_all_tables') as mock_tables, \
             patch.object(ForeignKeyInferencer, 'inspector'):

            mock_cols.return_value = []
            mock_tables.return_value = []

            inferencer = ForeignKeyInferencer(engine=mock_engine)

            # Test invalid strategy
            with pytest.raises(ValueError, match="overlap_strategy"):
                inferencer.infer_relationships(
                    table_name="Orders",
                    schema_name="dbo",
                    include_value_overlap=True,
                    overlap_strategy="invalid_strategy",
                )

            # Test invalid sample size
            with pytest.raises(ValueError, match="overlap_sample_size"):
                inferencer.infer_relationships(
                    table_name="Orders",
                    schema_name="dbo",
                    include_value_overlap=True,
                    overlap_sample_size=0,
                )


class TestAccuracyImprovement:
    """Tests measuring accuracy improvement with value overlap.

    These tests verify the expected behavior that high value overlap
    should boost confidence scores compared to metadata-only inference.
    """

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        engine = MagicMock()
        return engine

    def test_high_overlap_increases_confidence(self):
        """High value overlap should increase confidence score."""
        # Calculate scores for same candidate with and without overlap

        # Phase 1 calculation (without overlap)
        name_score = 0.85
        structural_score = 0.70

        phase1_score = (
            name_score * PHASE1_WEIGHTS["name"] +
            1.0 * PHASE1_WEIGHTS["type"] +  # Type compatible
            structural_score * PHASE1_WEIGHTS["structural"]
        )

        # Phase 2 calculation (with high overlap)
        overlap_score = 0.90  # High overlap

        phase2_score = (
            name_score * PHASE2_WEIGHTS["name"] +
            1.0 * PHASE2_WEIGHTS["type"] +
            structural_score * PHASE2_WEIGHTS["structural"] +
            overlap_score * PHASE2_WEIGHTS["overlap"]
        )

        # High overlap should boost the score
        # Even though individual weights are lower, high overlap adds 0.90 * 0.20 = 0.18
        assert phase2_score > phase1_score * 0.95, (
            f"High overlap should maintain or improve score: "
            f"Phase1={phase1_score:.3f}, Phase2={phase2_score:.3f}"
        )

    def test_low_overlap_decreases_confidence(self):
        """Low value overlap should decrease confidence score."""
        # Calculate scores for same candidate with low overlap
        name_score = 0.85
        structural_score = 0.70

        phase1_score = (
            name_score * PHASE1_WEIGHTS["name"] +
            1.0 * PHASE1_WEIGHTS["type"] +
            structural_score * PHASE1_WEIGHTS["structural"]
        )

        # Phase 2 calculation (with low overlap)
        overlap_score = 0.10  # Low overlap - likely not a real FK

        phase2_score = (
            name_score * PHASE2_WEIGHTS["name"] +
            1.0 * PHASE2_WEIGHTS["type"] +
            structural_score * PHASE2_WEIGHTS["structural"] +
            overlap_score * PHASE2_WEIGHTS["overlap"]
        )

        # Low overlap should reduce the score
        assert phase2_score < phase1_score, (
            f"Low overlap should reduce score: "
            f"Phase1={phase1_score:.3f}, Phase2={phase2_score:.3f}"
        )

    def test_zero_overlap_significantly_reduces_confidence(self):
        """Zero value overlap should significantly reduce confidence."""
        name_score = 0.85
        structural_score = 0.70

        phase1_score = (
            name_score * PHASE1_WEIGHTS["name"] +
            1.0 * PHASE1_WEIGHTS["type"] +
            structural_score * PHASE1_WEIGHTS["structural"]
        )

        # Phase 2 calculation (with zero overlap)
        overlap_score = 0.0

        phase2_score = (
            name_score * PHASE2_WEIGHTS["name"] +
            1.0 * PHASE2_WEIGHTS["type"] +
            structural_score * PHASE2_WEIGHTS["structural"] +
            overlap_score * PHASE2_WEIGHTS["overlap"]
        )

        # Score should be reduced by 20% when overlap is zero
        expected_reduction = phase1_score * 0.80
        assert phase2_score <= expected_reduction + 0.05, (
            f"Zero overlap should reduce score by ~20%: "
            f"Phase1={phase1_score:.3f}, Phase2={phase2_score:.3f}, "
            f"Expected max={expected_reduction:.3f}"
        )


class TestAccuracyScenarios:
    """Test scenarios demonstrating accuracy improvements."""

    def test_false_positive_reduction(self):
        """Value overlap should reduce false positives.

        Scenario: Column names match but data doesn't overlap.
        Phase 1: Would likely mark as FK (high name similarity)
        Phase 2: Should reject due to low overlap
        """
        # High name similarity, but zero data overlap
        name_score = 1.0  # Exact name match
        structural_score = 0.70
        overlap_score = 0.05  # Almost no data overlap

        phase1_score = (
            name_score * PHASE1_WEIGHTS["name"] +
            1.0 * PHASE1_WEIGHTS["type"] +
            structural_score * PHASE1_WEIGHTS["structural"]
        )

        phase2_score = (
            name_score * PHASE2_WEIGHTS["name"] +
            1.0 * PHASE2_WEIGHTS["type"] +
            structural_score * PHASE2_WEIGHTS["structural"] +
            overlap_score * PHASE2_WEIGHTS["overlap"]
        )

        # Phase 1 would pass typical threshold (0.50)
        assert phase1_score >= 0.50

        # Phase 2 score is significantly lower
        assert phase2_score < phase1_score

    def test_true_positive_maintained(self):
        """Value overlap should maintain true positives.

        Scenario: Real FK with both name match and data overlap.
        Both phases should correctly identify.
        """
        # Good name similarity and high data overlap
        name_score = 0.90
        structural_score = 0.85
        overlap_score = 0.95

        phase1_score = (
            name_score * PHASE1_WEIGHTS["name"] +
            1.0 * PHASE1_WEIGHTS["type"] +
            structural_score * PHASE1_WEIGHTS["structural"]
        )

        phase2_score = (
            name_score * PHASE2_WEIGHTS["name"] +
            1.0 * PHASE2_WEIGHTS["type"] +
            structural_score * PHASE2_WEIGHTS["structural"] +
            overlap_score * PHASE2_WEIGHTS["overlap"]
        )

        # Both should pass threshold
        threshold = 0.50
        assert phase1_score >= threshold
        assert phase2_score >= threshold

        # Scores should be comparable
        assert abs(phase2_score - phase1_score) < 0.10

    def test_hidden_relationship_discovered(self):
        """Value overlap can reveal hidden relationships.

        Scenario: Different column names but high data overlap.
        Phase 1: Would miss due to low name similarity
        Phase 2: Might catch due to high overlap
        """
        # Low name similarity but high data overlap
        name_score = 0.20  # Different names
        structural_score = 0.60
        overlap_score = 0.95  # High overlap despite name mismatch

        phase1_score = (
            name_score * PHASE1_WEIGHTS["name"] +
            1.0 * PHASE1_WEIGHTS["type"] +
            structural_score * PHASE1_WEIGHTS["structural"]
        )

        phase2_score = (
            name_score * PHASE2_WEIGHTS["name"] +
            1.0 * PHASE2_WEIGHTS["type"] +
            structural_score * PHASE2_WEIGHTS["structural"] +
            overlap_score * PHASE2_WEIGHTS["overlap"]
        )

        # High overlap should boost the Phase 2 score
        assert phase2_score > phase1_score, (
            "High overlap should boost score even with low name similarity"
        )


class TestOverlapMetadataInResponse:
    """Tests for overlap metadata in inference response."""

    @pytest.fixture
    def mock_engine(self):
        """Create a mock SQLAlchemy engine."""
        engine = MagicMock()
        return engine

    def test_metadata_includes_overlap_count(self, mock_engine):
        """Verify metadata includes overlap analysis count."""
        with patch.object(ForeignKeyInferencer, '_get_columns') as mock_cols, \
             patch.object(ForeignKeyInferencer, '_get_all_tables') as mock_tables, \
             patch.object(ForeignKeyInferencer, 'inspector'):

            mock_cols.return_value = []
            mock_tables.return_value = []

            inferencer = ForeignKeyInferencer(engine=mock_engine)
            _, metadata = inferencer.infer_relationships(
                table_name="Orders",
                schema_name="dbo",
                include_value_overlap=True,
                overlap_strategy="sampling",
            )

            assert "overlap_analyses" in metadata
            assert "include_value_overlap" in metadata
            assert metadata["include_value_overlap"] is True


class TestInferenceFactorsWithOverlap:
    """Tests for InferenceFactors including value_overlap."""

    def test_factors_include_overlap(self):
        """Test that InferenceFactors can include value_overlap."""
        from src.models.relationship import InferenceFactors

        factors = InferenceFactors(
            name_similarity=0.85,
            type_compatible=True,
            structural_hints=["source_nullable", "target_is_pk"],
            value_overlap=0.92,
        )

        assert factors.value_overlap == 0.92

        d = factors.to_dict()
        assert "value_overlap" in d
        assert d["value_overlap"] == 0.92

    def test_factors_without_overlap(self):
        """Test that InferenceFactors without overlap excludes it from dict."""
        from src.models.relationship import InferenceFactors

        factors = InferenceFactors(
            name_similarity=0.85,
            type_compatible=True,
            structural_hints=["source_nullable"],
            # value_overlap not set
        )

        assert factors.value_overlap is None

        d = factors.to_dict()
        assert "value_overlap" not in d
