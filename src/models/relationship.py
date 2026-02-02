"""Data models for relationship entities.

These models represent declared and inferred foreign key relationships
between tables in the database.
"""

from dataclasses import dataclass, field
from enum import Enum


class RelationshipType(str, Enum):
    """How the relationship was discovered."""

    DECLARED = "declared"  # Schema-defined foreign key
    INFERRED = "inferred"  # Algorithm-inferred relationship


class CascadeAction(str, Enum):
    """FK cascade behavior on delete/update."""

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    NO_ACTION = "NO ACTION"
    SET_DEFAULT = "SET DEFAULT"


@dataclass
class InferenceFactors:
    """Breakdown of scoring factors for relationship inference.

    Phase 1 factors (metadata-only):
    - name_similarity: Score from name matching (0.0-1.0)
    - type_compatible: Whether data types are compatible
    - structural_hints: List of structural indicators

    Phase 2 factors (with value overlap):
    - value_overlap: Score from actual data overlap analysis (0.0-1.0)
    """

    name_similarity: float = 0.0
    type_compatible: bool = False
    structural_hints: list[str] = field(default_factory=list)
    value_overlap: float | None = None  # Phase 2: None if not analyzed

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        result = {
            "name_similarity": self.name_similarity,
            "type_compatible": self.type_compatible,
            "structural_hints": ", ".join(self.structural_hints) if self.structural_hints else "",
        }
        if self.value_overlap is not None:
            result["value_overlap"] = self.value_overlap
        return result


@dataclass
class Relationship:
    """Base representation of a join relationship between tables.

    Attributes:
        relationship_id: Unique identifier (hash of source+target)
        source_table_id: Source table (foreign key side)
        source_column: Source column name
        target_table_id: Target table (referenced side)
        target_column: Target column name
        relationship_type: How relationship was discovered
    """

    relationship_id: str
    source_table_id: str
    source_column: str
    target_table_id: str
    target_column: str
    relationship_type: RelationshipType


@dataclass
class DeclaredFK(Relationship):
    """Foreign key explicitly declared in database schema.

    Attributes:
        constraint_name: FK constraint name
        on_delete: Delete cascade behavior
        on_update: Update cascade behavior
    """

    # Override with default to allow positional args from parent
    relationship_type: RelationshipType = field(default=RelationshipType.DECLARED)
    constraint_name: str = ""
    on_delete: CascadeAction | None = None
    on_update: CascadeAction | None = None


@dataclass
class InferredFK(Relationship):
    """Relationship inferred by algorithm.

    The inference algorithm uses three-factor weighted scoring:
    - Name similarity (40% weight): Column name pattern matching
    - Type compatibility (15% weight, veto if incompatible): Data type groups
    - Structural hints (45% weight): PK, nullable, unique index indicators

    Attributes:
        confidence_score: Confidence in inference (0.0-1.0)
        reasoning: Human-readable explanation of inference
        inference_factors: Breakdown of scoring factors
    """

    # Override with default to allow positional args from parent
    relationship_type: RelationshipType = field(default=RelationshipType.INFERRED)
    confidence_score: float = 0.0
    reasoning: str = ""
    inference_factors: InferenceFactors = field(default_factory=InferenceFactors)

    def to_dict(self) -> dict:
        """Convert to dictionary for serialization."""
        return {
            "source_table": self.source_table_id,
            "source_column": self.source_column,
            "target_table": self.target_table_id,
            "target_column": self.target_column,
            "confidence_score": self.confidence_score,
            "reasoning": self.reasoning,
            "factors": self.inference_factors.to_dict(),
        }


def create_relationship_id(
    source_table: str, source_column: str, target_table: str, target_column: str
) -> str:
    """Generate a unique relationship ID.

    Args:
        source_table: Source table name
        source_column: Source column name
        target_table: Target table name
        target_column: Target column name

    Returns:
        Unique relationship identifier
    """
    import hashlib

    components = f"{source_table}.{source_column}:{target_table}.{target_column}"
    return hashlib.sha256(components.encode()).hexdigest()[:16]
