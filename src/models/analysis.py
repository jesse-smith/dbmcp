"""Data models for data-exposure analysis tools.

These models expose raw statistics and structural metadata without interpretation.
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class NumericStats:
    """Per-column statistics for numeric types."""

    min_value: float | None
    max_value: float | None
    mean_value: float | None
    std_dev: float | None

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary."""
        return {
            "min_value": self.min_value,
            "max_value": self.max_value,
            "mean_value": self.mean_value,
            "std_dev": self.std_dev,
        }


@dataclass
class DateTimeStats:
    """Per-column statistics for date/time types."""

    min_date: datetime | None
    max_date: datetime | None
    date_range_days: int | None
    has_time_component: bool

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary."""
        return {
            "min_date": self.min_date.isoformat() if self.min_date else None,
            "max_date": self.max_date.isoformat() if self.max_date else None,
            "date_range_days": self.date_range_days,
            "has_time_component": self.has_time_component,
        }


@dataclass
class StringStats:
    """Per-column statistics for string types."""

    min_length: int | None
    max_length: int | None
    avg_length: float | None
    sample_values: list[tuple[str, int]]

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary."""
        return {
            "min_length": self.min_length,
            "max_length": self.max_length,
            "avg_length": self.avg_length,
            "sample_values": self.sample_values,
        }


@dataclass
class ColumnStatistics:
    """Complete statistical profile for a single column."""

    column_name: str
    table_name: str
    schema_name: str
    data_type: str
    total_rows: int
    distinct_count: int
    null_count: int
    null_percentage: float
    numeric_stats: NumericStats | None = None
    datetime_stats: DateTimeStats | None = None
    string_stats: StringStats | None = None

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary.

        Type-specific stats only included when not None.
        """
        result = {
            "column_name": self.column_name,
            "table_name": self.table_name,
            "schema_name": self.schema_name,
            "data_type": self.data_type,
            "total_rows": self.total_rows,
            "distinct_count": self.distinct_count,
            "null_count": self.null_count,
            "null_percentage": self.null_percentage,
        }

        # Only include type-specific stats if present
        if self.numeric_stats is not None:
            result["numeric_stats"] = self.numeric_stats.to_dict()
        if self.datetime_stats is not None:
            result["datetime_stats"] = self.datetime_stats.to_dict()
        if self.string_stats is not None:
            result["string_stats"] = self.string_stats.to_dict()

        return result


@dataclass
class PKCandidate:
    """A column meeting primary key candidacy criteria."""

    column_name: str
    data_type: str
    is_constraint_backed: bool
    constraint_type: str | None
    is_unique: bool
    is_non_null: bool
    is_pk_type: bool

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary."""
        return {
            "column_name": self.column_name,
            "data_type": self.data_type,
            "is_constraint_backed": self.is_constraint_backed,
            "constraint_type": self.constraint_type,
            "is_unique": self.is_unique,
            "is_non_null": self.is_non_null,
            "is_pk_type": self.is_pk_type,
        }


@dataclass
class FKCandidateData:
    """Raw data for a single source-to-target FK candidate pair."""

    source_column: str
    source_table: str
    source_schema: str
    source_data_type: str
    target_column: str
    target_table: str
    target_schema: str
    target_data_type: str
    target_is_primary_key: bool
    target_is_unique: bool
    target_is_nullable: bool
    target_has_index: bool
    overlap_count: int | None = None
    overlap_percentage: float | None = None

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary.

        Overlap fields omitted when None.
        """
        result = {
            "source_column": self.source_column,
            "source_table": self.source_table,
            "source_schema": self.source_schema,
            "source_data_type": self.source_data_type,
            "target_column": self.target_column,
            "target_table": self.target_table,
            "target_schema": self.target_schema,
            "target_data_type": self.target_data_type,
            "target_is_primary_key": self.target_is_primary_key,
            "target_is_unique": self.target_is_unique,
            "target_is_nullable": self.target_is_nullable,
            "target_has_index": self.target_has_index,
        }

        # Only include overlap fields if present
        if self.overlap_count is not None:
            result["overlap_count"] = self.overlap_count
        if self.overlap_percentage is not None:
            result["overlap_percentage"] = self.overlap_percentage

        return result


@dataclass
class FKCandidateResult:
    """Wrapper for FK candidate search results."""

    candidates: list[FKCandidateData]
    total_found: int
    was_limited: bool
    search_scope: str

    def to_dict(self) -> dict:
        """Convert to JSON-safe dictionary."""
        return {
            "candidates": [c.to_dict() for c in self.candidates],
            "total_found": self.total_found,
            "was_limited": self.was_limited,
            "search_scope": self.search_scope,
        }
