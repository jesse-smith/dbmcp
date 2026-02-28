"""Database statistics collection for column analysis.

Provides methods to query the database for column-level statistics
including basic counts, type-specific stats, and data type information.
Also defines the stats dataclass types returned by these methods.
"""

from dataclasses import dataclass, field
from datetime import datetime

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.logging_config import get_logger


@dataclass
class NumericStats:
    """Statistics for numeric columns."""

    min_value: float | None = None
    max_value: float | None = None
    mean_value: float | None = None
    median_value: float | None = None
    std_dev: float | None = None
    is_integer: bool = True


@dataclass
class DateTimeStats:
    """Statistics for date/time columns."""

    min_date: datetime | None = None
    max_date: datetime | None = None
    date_range_days: int | None = None
    has_time_component: bool = False
    business_hours_percentage: float | None = None


@dataclass
class StringStats:
    """Statistics for string columns."""

    top_values: list[tuple[str, int]] = field(default_factory=list)
    avg_length: float | None = None
    min_length: int | None = None
    max_length: int | None = None
    all_uppercase: bool = False
    contains_numbers: bool = False

logger = get_logger(__name__)


class ColumnStatsCollector:
    """Collects database statistics for column analysis.

    Attributes:
        engine: SQLAlchemy engine for database connection
    """

    def __init__(self, engine: Engine):
        self.engine = engine

    @property
    def _dialect(self) -> str:
        return self.engine.dialect.name

    def column_exists(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> bool:
        """Check if a column exists in the specified table."""
        if self._dialect == "sqlite":
            query = f"""
                SELECT 1 FROM pragma_table_info('{table_name}')
                WHERE name = '{column_name}'
            """
        else:
            query = """
                SELECT 1 FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name
                AND TABLE_NAME = :table_name
                AND COLUMN_NAME = :column_name
            """

        try:
            with self.engine.connect() as conn:
                if self._dialect == "sqlite":
                    result = conn.execute(text(query))
                else:
                    result = conn.execute(
                        text(query),
                        {"schema_name": schema_name, "table_name": table_name, "column_name": column_name},
                    )
                return result.fetchone() is not None
        except Exception as e:
            logger.error(f"Error checking column existence: {e}")
            return False

    def get_basic_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> tuple[int, int, int]:
        """Get basic column statistics.

        Returns:
            Tuple of (distinct_count, null_count, total_rows)
        """
        if self._dialect == "sqlite":
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
                    return (row[0] or 0, row[1] or 0, row[2] or 0)
                return (0, 0, 0)
        except Exception as e:
            logger.error(f"Error getting basic stats: {e}")
            return (0, 0, 0)

    def get_column_type(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> str:
        """Get the SQL data type of a column."""
        if self._dialect == "sqlite":
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

    def get_numeric_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> NumericStats:
        """Get statistics for numeric columns."""
        if self._dialect == "sqlite":
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

    def get_datetime_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> DateTimeStats:
        """Get statistics for datetime columns."""
        from datetime import datetime

        if self._dialect == "sqlite":
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

                    has_time = self._check_has_time_component(
                        column_name, table_name, schema_name
                    )

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
        """Check if datetime column has non-midnight time values."""
        if self._dialect == "sqlite":
            return False

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

    def get_string_stats(
        self,
        column_name: str,
        table_name: str,
        schema_name: str,
    ) -> StringStats:
        """Get statistics for string columns."""
        if self._dialect == "sqlite":
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
                result = conn.execute(text(top_query))
                top_values = [(str(row[0]), int(row[1])) for row in result]

                result = conn.execute(text(len_query))
                row = result.fetchone()
                avg_len = float(row[0]) if row and row[0] is not None else None
                min_len = int(row[1]) if row and row[1] is not None else None
                max_len = int(row[2]) if row and row[2] is not None else None

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
