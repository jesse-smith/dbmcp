"""Column purpose inference module.

This module provides analysis of database columns to infer their purpose
based on data patterns, value distributions, and usage context.

Example cryptic columns that benefit from analysis:
- FLG_1, STATUS_CD, AMT_3 -> infer as flag, status enum, amount
"""

import re
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.models.schema import InferredPurpose

logger = get_logger(__name__)


class ColumnCategory(str, Enum):
    """Categories of column data types for analysis."""

    NUMERIC = "numeric"
    STRING = "string"
    DATETIME = "datetime"
    BINARY = "binary"
    BOOLEAN = "boolean"
    UNKNOWN = "unknown"


@dataclass
class NumericStats:
    """Statistics for numeric columns.

    Attributes:
        min_value: Minimum value
        max_value: Maximum value
        mean_value: Average value
        median_value: Median value
        std_dev: Standard deviation
        is_integer: Whether all values are integers
    """

    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None
    median_value: float | None = None
    std_dev: float | None = None
    is_integer: bool = True


@dataclass
class DateTimeStats:
    """Statistics for date/time columns.

    Attributes:
        min_date: Earliest date
        max_date: Latest date
        date_range_days: Number of days between min and max
        has_time_component: Whether values include time
        business_hours_percentage: Percentage of values in business hours (9-17)
    """

    min_date: datetime | None = None
    max_date: datetime | None = None
    date_range_days: int | None = None
    has_time_component: bool = False
    business_hours_percentage: float | None = None


@dataclass
class StringStats:
    """Statistics for string columns.

    Attributes:
        top_values: List of (value, frequency) tuples
        avg_length: Average string length
        min_length: Minimum string length
        max_length: Maximum string length
        all_uppercase: Whether all values are uppercase
        contains_numbers: Whether values contain numeric characters
    """

    top_values: list[tuple[str, int]] = field(default_factory=list)
    avg_length: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    all_uppercase: bool = False
    contains_numbers: bool = False


@dataclass
class ColumnAnalysis:
    """Complete analysis result for a column.

    Attributes:
        column_name: Name of analyzed column
        table_name: Parent table name
        schema_name: Parent schema name
        data_type: SQL data type
        distinct_count: Number of distinct values
        null_count: Number of NULL values
        null_percentage: Percentage of NULL values
        total_rows: Total rows in table
        inferred_purpose: Inferred purpose of column
        confidence: Confidence score (0.0-1.0)
        reasoning: Human-readable explanation
        is_enum: Whether column appears to be an enumeration
        numeric_stats: Statistics if numeric type
        datetime_stats: Statistics if datetime type
        string_stats: Statistics if string type
        analyzed_at: When analysis was performed
    """

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

    Uses data patterns, value distributions, and naming conventions
    to determine the likely purpose of cryptic or undocumented columns.

    Attributes:
        engine: SQLAlchemy engine for database connection
    """

    # Type compatibility groups for categorization
    NUMERIC_TYPES = {
        "int", "bigint", "smallint", "tinyint", "bit",
        "decimal", "numeric", "float", "real", "money", "smallmoney",
        "integer",  # SQLite
    }

    DATETIME_TYPES = {
        "date", "datetime", "datetime2", "datetimeoffset",
        "smalldatetime", "time", "timestamp",
    }

    STRING_TYPES = {
        "char", "varchar", "nchar", "nvarchar", "text", "ntext",
    }

    BINARY_TYPES = {
        "binary", "varbinary", "image", "blob",
    }

    # Thresholds for enum detection
    ENUM_MAX_DISTINCT = 50  # Max distinct values to consider enum
    ENUM_MAX_PERCENTAGE = 10.0  # Max percentage of total rows

    def __init__(self, engine: Engine):
        """Initialize column analyzer.

        Args:
            engine: SQLAlchemy engine
        """
        self.engine = engine

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
        """
        logger.info(f"Analyzing column {schema_name}.{table_name}.{column_name}")

        # Get basic statistics
        distinct_count, null_count, total_rows = self._get_basic_stats(
            column_name, table_name, schema_name
        )

        # Calculate null percentage
        null_percentage = (null_count / total_rows * 100) if total_rows > 0 else 0.0

        # Detect enum
        is_enum = self._is_enum(distinct_count, total_rows)

        # Get data type if not provided
        if not data_type:
            data_type = self._get_column_type(column_name, table_name, schema_name)

        # Categorize the column type
        category = self._categorize_type(data_type)

        # Get type-specific statistics
        numeric_stats = None
        datetime_stats = None
        string_stats = None

        if category == ColumnCategory.NUMERIC:
            numeric_stats = self._get_numeric_stats(column_name, table_name, schema_name)
        elif category == ColumnCategory.DATETIME:
            datetime_stats = self._get_datetime_stats(column_name, table_name, schema_name)
        elif category == ColumnCategory.STRING:
            string_stats = self._get_string_stats(column_name, table_name, schema_name)

        # Infer purpose
        purpose, confidence, reasoning = self._infer_purpose(
            column_name=column_name,
            data_type=data_type,
            category=category,
            distinct_count=distinct_count,
            null_percentage=null_percentage,
            total_rows=total_rows,
            is_enum=is_enum,
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
            is_enum=is_enum,
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
        """Get count of distinct values in a column.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            Number of distinct values
        """
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
        """Calculate percentage of NULL values in a column.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            Percentage of NULL values (0.0-100.0)
        """
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

    def _get_basic_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> tuple[int, int, int]:
        """Get basic column statistics.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            Tuple of (distinct_count, null_count, total_rows)
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            query = f"""
                SELECT
                    COUNT(DISTINCT "{column_name}") as distinct_count,
                    SUM(CASE WHEN "{column_name}" IS NULL THEN 1 ELSE 0 END) as null_count,
                    COUNT(*) as total_rows
                FROM "{table_name}"
            """
        else:
            query = f"""
                SELECT
                    COUNT(DISTINCT [{column_name}]) as distinct_count,
                    SUM(CASE WHEN [{column_name}] IS NULL THEN 1 ELSE 0 END) as null_count,
                    COUNT(*) as total_rows
                FROM [{schema_name}].[{table_name}]
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                if row:
                    return (
                        row[0] or 0,
                        row[1] or 0,
                        row[2] or 0,
                    )
                return (0, 0, 0)
        except Exception as e:
            logger.error(f"Error getting basic stats: {e}")
            return (0, 0, 0)

    def _get_column_type(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> str:
        """Get the SQL data type of a column.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            SQL data type string
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            query = f"""
                SELECT type FROM pragma_table_info('{table_name}')
                WHERE name = '{column_name}'
            """
        else:
            query = f"""
                SELECT DATA_TYPE + CASE
                    WHEN CHARACTER_MAXIMUM_LENGTH IS NOT NULL
                    THEN '(' + CAST(CHARACTER_MAXIMUM_LENGTH AS VARCHAR) + ')'
                    ELSE ''
                END
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = '{schema_name}'
                AND TABLE_NAME = '{table_name}'
                AND COLUMN_NAME = '{column_name}'
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                return row[0] if row else "unknown"
        except Exception as e:
            logger.error(f"Error getting column type: {e}")
            return "unknown"

    def _categorize_type(self, data_type: str) -> ColumnCategory:
        """Categorize SQL data type into a category.

        Args:
            data_type: SQL data type string

        Returns:
            ColumnCategory enum value
        """
        # Normalize type name (remove precision, convert to lowercase)
        base_type = data_type.lower().split("(")[0].strip()

        if base_type in self.NUMERIC_TYPES:
            return ColumnCategory.NUMERIC
        elif base_type in self.DATETIME_TYPES:
            return ColumnCategory.DATETIME
        elif base_type in self.STRING_TYPES:
            return ColumnCategory.STRING
        elif base_type in self.BINARY_TYPES:
            return ColumnCategory.BINARY
        elif base_type == "bit":
            return ColumnCategory.BOOLEAN
        else:
            return ColumnCategory.UNKNOWN

    def _is_enum(self, distinct_count: int, total_rows: int) -> bool:
        """Detect if column appears to be an enumeration.

        An enum is detected when:
        - Distinct count is less than ENUM_MAX_DISTINCT (50)
        - Distinct count is less than ENUM_MAX_PERCENTAGE (10%) of total rows

        Args:
            distinct_count: Number of distinct values
            total_rows: Total number of rows

        Returns:
            True if column appears to be an enum
        """
        if total_rows == 0:
            return False

        percentage = (distinct_count / total_rows) * 100

        return (
            distinct_count <= self.ENUM_MAX_DISTINCT
            and percentage <= self.ENUM_MAX_PERCENTAGE
        )

    def _get_numeric_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> NumericStats:
        """Get statistics for numeric columns.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            NumericStats object
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite doesn't have STDEV, median requires subquery
            query = f"""
                SELECT
                    MIN("{column_name}") as min_val,
                    MAX("{column_name}") as max_val,
                    AVG("{column_name}") as mean_val,
                    (SELECT "{column_name}" FROM (
                        SELECT "{column_name}"
                        FROM "{table_name}"
                        WHERE "{column_name}" IS NOT NULL
                        ORDER BY "{column_name}"
                        LIMIT 1
                        OFFSET (SELECT COUNT(*) FROM "{table_name}" WHERE "{column_name}" IS NOT NULL) / 2
                    )) as median_val
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
            """
        else:
            query = f"""
                SELECT
                    MIN([{column_name}]) as min_val,
                    MAX([{column_name}]) as max_val,
                    AVG(CAST([{column_name}] AS FLOAT)) as mean_val,
                    PERCENTILE_CONT(0.5) WITHIN GROUP (ORDER BY [{column_name}])
                        OVER () as median_val,
                    STDEV(CAST([{column_name}] AS FLOAT)) as std_dev
                FROM [{schema_name}].[{table_name}]
                WHERE [{column_name}] IS NOT NULL
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                if row:
                    min_val = float(row[0]) if row[0] is not None else None
                    max_val = float(row[1]) if row[1] is not None else None
                    mean_val = float(row[2]) if row[2] is not None else None
                    median_val = float(row[3]) if row[3] is not None else None
                    std_dev = float(row[4]) if len(row) > 4 and row[4] is not None else None

                    # Check if values are integers
                    is_integer = (
                        min_val is not None
                        and max_val is not None
                        and min_val == int(min_val)
                        and max_val == int(max_val)
                    )

                    return NumericStats(
                        min_value=min_val,
                        max_value=max_val,
                        mean_value=mean_val,
                        median_value=median_val,
                        std_dev=std_dev,
                        is_integer=is_integer,
                    )
        except Exception as e:
            logger.error(f"Error getting numeric stats: {e}")

        return NumericStats()

    def _get_datetime_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> DateTimeStats:
        """Get statistics for datetime columns.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            DateTimeStats object
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite stores dates as strings/numbers
            query = f"""
                SELECT
                    MIN("{column_name}") as min_date,
                    MAX("{column_name}") as max_date,
                    CAST(julianday(MAX("{column_name}")) - julianday(MIN("{column_name}")) AS INTEGER) as range_days
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
            """
        else:
            query = f"""
                SELECT
                    MIN([{column_name}]) as min_date,
                    MAX([{column_name}]) as max_date,
                    DATEDIFF(day, MIN([{column_name}]), MAX([{column_name}])) as range_days,
                    SUM(CASE WHEN DATEPART(hour, [{column_name}]) BETWEEN 9 AND 17 THEN 1 ELSE 0 END) * 100.0 / COUNT(*) as business_hours_pct
                FROM [{schema_name}].[{table_name}]
                WHERE [{column_name}] IS NOT NULL
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                row = result.fetchone()
                if row:
                    min_date = row[0]
                    max_date = row[1]
                    range_days = int(row[2]) if row[2] is not None else None
                    business_hours_pct = float(row[3]) if len(row) > 3 and row[3] is not None else None

                    # Check if dates have time component (non-midnight times)
                    has_time = self._check_has_time_component(
                        column_name, table_name, schema_name
                    )

                    # Convert dates if needed
                    if isinstance(min_date, str):
                        try:
                            min_date = datetime.fromisoformat(min_date)
                        except (ValueError, TypeError):
                            min_date = None
                    if isinstance(max_date, str):
                        try:
                            max_date = datetime.fromisoformat(max_date)
                        except (ValueError, TypeError):
                            max_date = None

                    return DateTimeStats(
                        min_date=min_date,
                        max_date=max_date,
                        date_range_days=range_days,
                        has_time_component=has_time,
                        business_hours_percentage=business_hours_pct,
                    )
        except Exception as e:
            logger.error(f"Error getting datetime stats: {e}")

        return DateTimeStats()

    def _check_has_time_component(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> bool:
        """Check if datetime column has non-midnight time values.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            True if column has time component
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite date/time handling varies
            return False
        else:
            query = f"""
                SELECT TOP 1 1
                FROM [{schema_name}].[{table_name}]
                WHERE [{column_name}] IS NOT NULL
                AND CAST([{column_name}] AS TIME) <> '00:00:00'
            """

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking time component: {e}")
            return False

    def _get_string_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> StringStats:
        """Get statistics for string columns.

        Args:
            column_name: Column name
            table_name: Table name
            schema_name: Schema name

        Returns:
            StringStats object
        """
        dialect_name = self.engine.dialect.name

        # Get top values with frequencies
        if dialect_name == "sqlite":
            top_query = f"""
                SELECT "{column_name}", COUNT(*) as freq
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
                GROUP BY "{column_name}"
                ORDER BY freq DESC
                LIMIT 10
            """
            len_query = f"""
                SELECT
                    AVG(LENGTH("{column_name}")) as avg_len,
                    MIN(LENGTH("{column_name}")) as min_len,
                    MAX(LENGTH("{column_name}")) as max_len
                FROM "{table_name}"
                WHERE "{column_name}" IS NOT NULL
            """
        else:
            top_query = f"""
                SELECT TOP 10 [{column_name}], COUNT(*) as freq
                FROM [{schema_name}].[{table_name}]
                WHERE [{column_name}] IS NOT NULL
                GROUP BY [{column_name}]
                ORDER BY freq DESC
            """
            len_query = f"""
                SELECT
                    AVG(LEN([{column_name}])) as avg_len,
                    MIN(LEN([{column_name}])) as min_len,
                    MAX(LEN([{column_name}])) as max_len
                FROM [{schema_name}].[{table_name}]
                WHERE [{column_name}] IS NOT NULL
            """

        try:
            with self.engine.connect() as conn:
                # Get top values
                result = conn.execute(text(top_query))
                top_values = [(str(row[0]), int(row[1])) for row in result]

                # Get length statistics
                result = conn.execute(text(len_query))
                row = result.fetchone()
                avg_len = float(row[0]) if row and row[0] is not None else None
                min_len = int(row[1]) if row and row[1] is not None else None
                max_len = int(row[2]) if row and row[2] is not None else None

                # Check patterns
                all_uppercase = all(
                    val[0].isupper() or not val[0].isalpha()
                    for val in top_values
                    if val[0]
                )
                contains_numbers = any(
                    any(c.isdigit() for c in val[0])
                    for val in top_values
                    if val[0]
                )

                return StringStats(
                    top_values=top_values,
                    avg_length=avg_len,
                    min_length=min_len,
                    max_length=max_len,
                    all_uppercase=all_uppercase,
                    contains_numbers=contains_numbers,
                )
        except Exception as e:
            logger.error(f"Error getting string stats: {e}")

        return StringStats()

    def _infer_purpose(
        self,
        column_name: str,
        data_type: str,
        category: ColumnCategory,
        distinct_count: int,
        null_percentage: float,
        total_rows: int,
        is_enum: bool,
        numeric_stats: NumericStats | None,
        datetime_stats: DateTimeStats | None,
        string_stats: StringStats | None,
    ) -> tuple[InferredPurpose, float, str]:
        """Infer the purpose of a column based on analysis.

        Args:
            column_name: Column name
            data_type: SQL data type
            category: Column category
            distinct_count: Number of distinct values
            null_percentage: Percentage of NULL values
            total_rows: Total row count
            is_enum: Whether detected as enumeration
            numeric_stats: Numeric statistics (if applicable)
            datetime_stats: Datetime statistics (if applicable)
            string_stats: String statistics (if applicable)

        Returns:
            Tuple of (purpose, confidence, reasoning)
        """
        reasoning_parts = []
        purpose = InferredPurpose.UNKNOWN
        confidence = 0.0

        # Normalize column name for pattern matching
        name_lower = column_name.lower()
        name_normalized = re.sub(r'[_\-\s]', '', name_lower)

        # Check for ID patterns
        if self._is_likely_id(name_lower, name_normalized, category, numeric_stats, distinct_count, total_rows):
            purpose = InferredPurpose.ID
            confidence = 0.85
            reasoning_parts.append("Name pattern suggests identifier")
            if numeric_stats and numeric_stats.is_integer:
                reasoning_parts.append("Integer values")
                confidence += 0.05
            if distinct_count == total_rows:
                reasoning_parts.append("All values unique")
                confidence += 0.05

        # Check for flag/boolean patterns
        elif self._is_likely_flag(name_lower, name_normalized, category, distinct_count, string_stats):
            purpose = InferredPurpose.FLAG
            confidence = 0.85
            reasoning_parts.append("Name pattern suggests boolean flag")
            if distinct_count <= 2:
                reasoning_parts.append(f"Only {distinct_count} distinct values")
                confidence += 0.10

        # Check for status patterns
        elif self._is_likely_status(name_lower, name_normalized, is_enum, distinct_count, string_stats):
            purpose = InferredPurpose.STATUS
            confidence = 0.80
            reasoning_parts.append("Name pattern suggests status field")
            if is_enum:
                reasoning_parts.append(f"Enumeration with {distinct_count} values")
                confidence += 0.10

        # Check for enum patterns (when not status)
        elif is_enum and category == ColumnCategory.STRING:
            purpose = InferredPurpose.ENUM
            confidence = 0.75
            reasoning_parts.append(f"Low cardinality ({distinct_count} values)")
            if string_stats and string_stats.all_uppercase:
                reasoning_parts.append("All uppercase values (code-like)")
                confidence += 0.10

        # Check for amount/money patterns
        elif self._is_likely_amount(name_lower, name_normalized, category, numeric_stats):
            purpose = InferredPurpose.AMOUNT
            confidence = 0.80
            reasoning_parts.append("Name pattern suggests monetary amount")
            if numeric_stats:
                reasoning_parts.append(f"Range: {numeric_stats.min_value} to {numeric_stats.max_value}")

        # Check for quantity patterns
        elif self._is_likely_quantity(name_lower, name_normalized, category, numeric_stats):
            purpose = InferredPurpose.QUANTITY
            confidence = 0.75
            reasoning_parts.append("Name pattern suggests quantity/count")
            if numeric_stats and numeric_stats.is_integer:
                reasoning_parts.append("Integer values")
                confidence += 0.10

        # Check for percentage patterns
        elif self._is_likely_percentage(name_lower, name_normalized, category, numeric_stats):
            purpose = InferredPurpose.PERCENTAGE
            confidence = 0.80
            reasoning_parts.append("Name pattern suggests percentage")
            if numeric_stats and numeric_stats.min_value is not None and numeric_stats.max_value is not None:
                if 0 <= numeric_stats.min_value and numeric_stats.max_value <= 100:
                    reasoning_parts.append("Values in 0-100 range")
                    confidence += 0.10

        # Check for timestamp patterns
        elif category == ColumnCategory.DATETIME:
            purpose = InferredPurpose.TIMESTAMP
            confidence = 0.75
            reasoning_parts.append("DateTime data type")
            if datetime_stats and datetime_stats.has_time_component:
                reasoning_parts.append("Contains time component")
                confidence += 0.10
            if "created" in name_lower or "modified" in name_lower or "updated" in name_lower:
                reasoning_parts.append("Name suggests audit timestamp")
                confidence += 0.10

        # Default: unknown
        else:
            purpose = InferredPurpose.UNKNOWN
            confidence = 0.50
            reasoning_parts.append("No strong pattern detected")

        # Cap confidence at 1.0
        confidence = min(confidence, 1.0)

        return purpose, confidence, "; ".join(reasoning_parts)

    def _is_likely_id(
        self,
        name_lower: str,
        name_normalized: str,
        category: ColumnCategory,
        numeric_stats: NumericStats | None,
        distinct_count: int,
        total_rows: int,
    ) -> bool:
        """Check if column is likely an identifier."""
        # Suffixes that indicate ID columns
        id_suffixes = ["_id", "id", "_key", "key", "_no", "no", "_num", "num"]

        # Check name patterns
        if any(name_normalized.endswith(suffix.replace("_", "")) for suffix in id_suffixes):
            return True
        if name_lower == "id" or name_normalized == "id":
            return True

        # Check for unique numeric values
        if (
            category == ColumnCategory.NUMERIC
            and numeric_stats
            and numeric_stats.is_integer
            and distinct_count == total_rows
            and total_rows > 0
        ):
            return True

        return False

    def _is_likely_flag(
        self,
        name_lower: str,
        name_normalized: str,
        category: ColumnCategory,
        distinct_count: int,
        string_stats: StringStats | None,
    ) -> bool:
        """Check if column is likely a boolean flag."""
        # Name patterns for flags
        flag_patterns = ["flag", "flg", "is_", "has_", "can_", "should_", "active", "enabled", "disabled"]

        # Check name patterns
        for pattern in flag_patterns:
            if pattern in name_lower:
                return True

        # Check for binary values
        if distinct_count <= 2:
            if string_stats and string_stats.top_values:
                values = [v[0].lower() for v in string_stats.top_values]
                binary_pairs = [
                    {"y", "n"}, {"yes", "no"}, {"true", "false"},
                    {"1", "0"}, {"t", "f"}, {"on", "off"},
                    {"active", "inactive"}, {"enabled", "disabled"}
                ]
                for pair in binary_pairs:
                    if set(values).issubset(pair):
                        return True

        return False

    def _is_likely_status(
        self,
        name_lower: str,
        name_normalized: str,
        is_enum: bool,
        distinct_count: int,
        string_stats: StringStats | None,
    ) -> bool:
        """Check if column is likely a status field."""
        # Name patterns for status
        status_patterns = ["status", "state", "stage", "phase", "step"]

        # Check name patterns
        for pattern in status_patterns:
            if pattern in name_lower:
                return True

        # Check for enum with status-like values
        if is_enum and string_stats and string_stats.top_values:
            values = [v[0].lower() for v in string_stats.top_values]
            status_values = {"pending", "active", "inactive", "complete", "completed",
                           "cancelled", "canceled", "draft", "approved", "rejected",
                           "new", "open", "closed", "in_progress", "inprogress"}
            if any(v in status_values for v in values):
                return True

        return False

    def _is_likely_amount(
        self,
        name_lower: str,
        name_normalized: str,
        category: ColumnCategory,
        numeric_stats: NumericStats | None,
    ) -> bool:
        """Check if column is likely a monetary amount."""
        if category != ColumnCategory.NUMERIC:
            return False

        # Name patterns for amounts
        amount_patterns = ["amt", "amount", "price", "cost", "total", "sum",
                         "balance", "fee", "charge", "payment", "salary", "wage"]

        for pattern in amount_patterns:
            if pattern in name_lower:
                return True

        return False

    def _is_likely_quantity(
        self,
        name_lower: str,
        name_normalized: str,
        category: ColumnCategory,
        numeric_stats: NumericStats | None,
    ) -> bool:
        """Check if column is likely a quantity/count."""
        if category != ColumnCategory.NUMERIC:
            return False

        # Name patterns for quantities
        qty_patterns = ["qty", "quantity", "count", "cnt", "num", "units", "items"]

        for pattern in qty_patterns:
            if pattern in name_lower:
                return True

        # Check for non-negative integers
        if numeric_stats and numeric_stats.is_integer:
            if numeric_stats.min_value is not None and numeric_stats.min_value >= 0:
                return True

        return False

    def _is_likely_percentage(
        self,
        name_lower: str,
        name_normalized: str,
        category: ColumnCategory,
        numeric_stats: NumericStats | None,
    ) -> bool:
        """Check if column is likely a percentage."""
        if category != ColumnCategory.NUMERIC:
            return False

        # Name patterns for percentages
        pct_patterns = ["pct", "percent", "percentage", "rate", "ratio"]

        for pattern in pct_patterns:
            if pattern in name_lower:
                return True

        # Check for 0-100 or 0-1 range
        if numeric_stats:
            if numeric_stats.min_value is not None and numeric_stats.max_value is not None:
                # 0-100 range
                if 0 <= numeric_stats.min_value and numeric_stats.max_value <= 100:
                    return True
                # 0-1 range (decimal percentage)
                if 0 <= numeric_stats.min_value and numeric_stats.max_value <= 1:
                    return True

        return False
