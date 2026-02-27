"""Confidence scoring for foreign key inference.

Calculates weighted confidence scores using name similarity,
type compatibility, structural hints, and optional value overlap.
"""

from __future__ import annotations

from difflib import SequenceMatcher
from typing import TYPE_CHECKING

from src.models.relationship import InferenceFactors

if TYPE_CHECKING:
    from src.inference.relationships import ColumnInfo

# Weight configuration for Phase 1 (metadata-only)
PHASE1_WEIGHTS = {
    "name": 0.40,
    "type": 0.15,
    "structural": 0.45,
}

# Weight configuration for Phase 2 (with value overlap)
PHASE2_WEIGHTS = {
    "name": 0.32,
    "type": 0.12,
    "structural": 0.36,
    "overlap": 0.20,
}

# SQL Server compatible type groups
TYPE_GROUPS = {
    "NUMERIC": ["int", "bigint", "smallint", "tinyint", "numeric", "decimal", "float", "real", "money"],
    "STRING": ["varchar", "nvarchar", "char", "nchar", "text", "ntext"],
    "GUID": ["uniqueidentifier"],
    "DATE": ["datetime", "datetime2", "date", "time", "datetimeoffset", "smalldatetime"],
    "BINARY": ["binary", "varbinary", "image"],
}

# Common ID column suffixes (normalized)
ID_SUFFIXES = ["id", "key", "code", "num", "number", "no"]


class ConfidenceScorer:
    """Calculates confidence scores for FK candidate relationships."""

    def calculate_confidence(
        self,
        src_col: ColumnInfo,
        tgt_col: ColumnInfo,
        tgt_table: str,
        include_overlap: bool = False,
        overlap_score: float | None = None,
    ) -> tuple[float, InferenceFactors]:
        """Calculate confidence score using weighted scoring.

        Phase 1 (include_overlap=False): Three-factor scoring
        Phase 2 (include_overlap=True): Four-factor scoring with value overlap
        """
        type_compatible = self._check_type_compatibility(src_col.data_type, tgt_col.data_type)
        if not type_compatible:
            return 0.0, InferenceFactors(name_similarity=0, type_compatible=False)

        name_score = self._calculate_name_similarity(src_col.name, tgt_col.name, tgt_table)
        structural_score, hints = self._calculate_structural_score(src_col, tgt_col)

        if include_overlap and overlap_score is not None:
            weights = PHASE2_WEIGHTS
            final_score = (
                (name_score * weights["name"]) +
                (1.0 * weights["type"]) +
                (structural_score * weights["structural"]) +
                (overlap_score * weights["overlap"])
            )
            factors = InferenceFactors(
                name_similarity=round(name_score, 3),
                type_compatible=True,
                structural_hints=hints,
                value_overlap=round(overlap_score, 3),
            )
        else:
            weights = PHASE1_WEIGHTS
            final_score = (
                (name_score * weights["name"]) +
                (1.0 * weights["type"]) +
                (structural_score * weights["structural"])
            )
            factors = InferenceFactors(
                name_similarity=round(name_score, 3),
                type_compatible=True,
                structural_hints=hints,
            )

        return final_score, factors

    def _check_type_compatibility(self, src_type: str, tgt_type: str) -> bool:
        """Check if types are compatible for FK relationship."""
        src_type = src_type.lower()
        tgt_type = tgt_type.lower()

        if src_type == tgt_type:
            return True

        for group_types in TYPE_GROUPS.values():
            src_in = any(t in src_type for t in group_types)
            tgt_in = any(t in tgt_type for t in group_types)
            if src_in and tgt_in:
                return True

        return False

    def _calculate_name_similarity(self, src_name: str, tgt_name: str, tgt_table: str) -> float:
        """Calculate name similarity score (0.0-1.0)."""
        src_norm = _normalize_name(src_name)
        tgt_norm = _normalize_name(tgt_name)

        if src_norm == tgt_norm:
            return 1.0

        tgt_table_norm = _normalize_name(tgt_table).rstrip("s")
        if src_norm.startswith(tgt_table_norm):
            suffix = src_norm[len(tgt_table_norm):]
            if suffix in ID_SUFFIXES or suffix == "":
                return 0.90

        for suffix in ID_SUFFIXES:
            if src_norm.endswith(suffix):
                src_base = src_norm[:-len(suffix)]
                if src_base and (src_base in tgt_table_norm or tgt_table_norm in src_base):
                    return 0.85

        similarity = SequenceMatcher(None, src_norm, tgt_norm).ratio()

        if similarity > 0.85:
            return 0.80
        elif similarity > 0.70:
            return 0.55
        elif similarity > 0.60:
            return 0.30

        return 0.0

    def _calculate_structural_score(self, src_col: ColumnInfo, tgt_col: ColumnInfo) -> tuple[float, list[str]]:
        """Calculate structural hints score (0.0-1.0)."""
        score = 0.5
        hints = []

        if src_col.is_nullable:
            score += 0.2
            hints.append("source_nullable")
        else:
            score -= 0.1

        if tgt_col.is_primary_key:
            score += 0.3
            hints.append("target_is_primary_key")
        elif tgt_col.is_unique:
            score += 0.15
            hints.append("target_unique_index")

        return min(score, 1.0), hints

    def generate_reasoning(self, src_col: ColumnInfo, tgt_col: ColumnInfo, factors: InferenceFactors) -> str:
        """Generate human-readable explanation for the inference."""
        parts = []

        if factors.name_similarity >= 0.90:
            parts.append(f"Exact/strong name match ({factors.name_similarity:.0%})")
        elif factors.name_similarity >= 0.70:
            parts.append(f"High name similarity ({factors.name_similarity:.0%})")
        elif factors.name_similarity >= 0.50:
            parts.append(f"Moderate name similarity ({factors.name_similarity:.0%})")

        if factors.type_compatible:
            parts.append("type compatible")

        if factors.structural_hints:
            parts.append(" + ".join(factors.structural_hints))

        if factors.value_overlap is not None:
            if factors.value_overlap >= 0.80:
                parts.append(f"strong value overlap ({factors.value_overlap:.0%})")
            elif factors.value_overlap >= 0.50:
                parts.append(f"moderate value overlap ({factors.value_overlap:.0%})")
            elif factors.value_overlap >= 0.30:
                parts.append(f"weak value overlap ({factors.value_overlap:.0%})")

        return " + ".join(parts) if parts else "Pattern match"


def _normalize_name(name: str) -> str:
    """Normalize column/table name for comparison."""
    return name.lower().replace("_", "").replace("-", "")
