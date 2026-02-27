"""Column purpose inference module.

This module provides analysis of database columns to infer their purpose
based on data patterns, value distributions, and usage context.

Example cryptic columns that benefit from analysis:
- FLG_1, STATUS_CD, AMT_3 -> infer as flag, status enum, amount
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.inference.column_patterns import (
    ColumnCategory,
    categorize_type,
    infer_purpose,
    is_enum,
)
from src.inference.column_stats import (
    ColumnStatsCollector,
    DateTimeStats,
    NumericStats,
    StringStats,
)
from src.logging_config import get_logger
from src.models.schema import InferredPurpose

# Re-export for backward compatibility
__all__ = [
    "ColumnAnalysis",
    "ColumnAnalyzer",
    "ColumnCategory",
    "DateTimeStats",
    "NumericStats",
    "StringStats",
]

logger = get_logger(__name__)


@dataclass
class ColumnAnalysis:
    """Complete analysis result for a column."""

    column_name: str
    table_name: str
    schema_name: str
    data_type: str
    distinct_count: int = 0
    null_count: int = 0
    null_percentage: float = 0.0
    total_rows: int = 0
    inferred_purpose: InferredPurpose = InferredPurpose.UNKNOWN
    confidence: float = 0.0
    reasoning: str = ""
    is_enum: bool = False
    numeric_stats: NumericStats | None = None
    datetime_stats: DateTimeStats | None = None
    string_stats: StringStats | None = None
    analyzed_at: datetime = field(default_factory=datetime.now)


class ColumnAnalyzer:
    """Analyzes columns to infer their purpose.

    Delegates statistics collection to ColumnStatsCollector and
    pattern matching to column_patterns module functions.
    """

    def __init__(self, engine: Engine):
        self.engine = engine
        self._stats = ColumnStatsCollector(engine)

    def analyze_column(
        self,
        column_name: str,
        table_name: str,
        schema_name: str = "dbo",
        data_type: str = "",
    ) -> ColumnAnalysis:
        """Analyze a single column to infer its purpose.

        Args:
            column_name: Column name to analyze
            table_name: Parent table name
            schema_name: Schema name (default: 'dbo')
            data_type: SQL data type (optional, will be queried if not provided)

        Returns:
            ColumnAnalysis with inferred purpose and statistics

        Raises:
            ValueError: If the column does not exist in the specified table
        """
        logger.info(f"Analyzing column {schema_name}.{table_name}.{column_name}")

        if not self._stats.column_exists(column_name, table_name, schema_name):
            raise ValueError(
                f"Column '{column_name}' does not exist in "
                f"[{schema_name}].[{table_name}]"
            )

        distinct_count, null_count, total_rows = self._stats.get_basic_stats(
            column_name, table_name, schema_name
        )
        null_percentage = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        if not data_type:
            data_type = self._stats.get_column_type(column_name, table_name, schema_name)

        category = categorize_type(data_type)
        is_enum_flag = is_enum(distinct_count, total_rows, category)

        numeric_stats = None
        datetime_stats = None
        string_stats = None

        if category == ColumnCategory.NUMERIC:
            numeric_stats = self._stats.get_numeric_stats(column_name, table_name, schema_name)
        elif category == ColumnCategory.DATETIME:
            datetime_stats = self._stats.get_datetime_stats(column_name, table_name, schema_name)
        elif category == ColumnCategory.STRING:
            string_stats = self._stats.get_string_stats(column_name, table_name, schema_name)

        purpose, confidence, reasoning = infer_purpose(
            column_name=column_name,
            data_type=data_type,
            category=category,
            distinct_count=distinct_count,
            null_percentage=null_percentage,
            total_rows=total_rows,
            is_enum_flag=is_enum_flag,
            numeric_stats=numeric_stats,
            datetime_stats=datetime_stats,
            string_stats=string_stats,
        )

        return ColumnAnalysis(
            column_name=column_name,
            table_name=table_name,
            schema_name=schema_name,
            data_type=data_type,
            distinct_count=distinct_count,
            null_count=null_count,
            null_percentage=null_percentage,
            total_rows=total_rows,
            inferred_purpose=purpose,
            confidence=confidence,
            reasoning=reasoning,
            is_enum=is_enum_flag,
            numeric_stats=numeric_stats,
            datetime_stats=datetime_stats,
            string_stats=string_stats,
        )

    def get_distinct_count(
        self,
        column_name: str,
        table_name: str,
        schema_name: str = "dbo",
    ) -> int:
        """Get count of distinct values in a column."""
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            query = f"""
                SELECT COUNT(DISTINCT "{column_name}") as distinct_count
                FROM "{table_name}"
            """
        else:
            query = f"""
                SELECT COUNT(DISTINCT [{column_name}]) as distinct_count
                FROM [{schema_name}].[{table_name}]
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                return row[0] if row else 0
        except Exception as e:
            logger.error(f"Error getting distinct count: {e}")
            return 0

    def get_null_percentage(
        self,
        column_name: str,
        table_name: str,
        schema_name: str = "dbo",
    ) -> float:
        """Calculate percentage of NULL values in a column."""
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            query = f"""
                SELECT
                    SUM(CASE WHEN "{column_name}" IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as null_pct
                FROM "{table_name}"
            """
        else:
            query = f"""
                SELECT
                    SUM(CASE WHEN [{column_name}] IS NULL THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as null_pct
                FROM [{schema_name}].[{table_name}]
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                return float(row[0]) if row and row[0] is not None else 0.0
        except Exception as e:
            logger.error(f"Error getting null percentage: {e}")
            return 0.0
