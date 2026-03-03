"""Data models for relationship entities.

These models represent declared foreign key relationships between tables
in the database.
"""

from dataclasses import dataclass, field
from enum import StrEnum


class RelationshipType(StrEnum):
    """How the relationship was discovered."""

    DECLARED = "declared"  # Schema-defined foreign key


class CascadeAction(StrEnum):
    """FK cascade behavior on delete/update."""

    CASCADE = "CASCADE"
    SET_NULL = "SET NULL"
    NO_ACTION = "NO ACTION"
    SET_DEFAULT = "SET DEFAULT"


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
