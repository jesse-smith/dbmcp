"""Column statistics collector for data-exposure analysis.

Adapts SQL patterns from former src/inference/column_stats.py with key differences:
- Supports batch column analysis (multiple columns in one call)
- Column filtering by name list or LIKE pattern
- Returns ColumnStatistics model instances (no inference fields)
- No interpretive logic (raw statistics only)
"""

from typing import Optional
from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.models.analysis import (
    ColumnStatistics,
    NumericStats,
    DateTimeStats,
    StringStats,
)


class ColumnStatsCollector:
    """Collect per-column statistical profiles for a table.

    Supports:
    - Basic stats: distinct count, null count, total rows, null percentage
    - Numeric stats: min, max, mean, standard deviation
    - DateTime stats: min/max date, range in days, time component detection
    - String stats: min/max/avg length, top frequent values
    - Batch column analysis with filtering
    """

    # SQL Server numeric types
    NUMERIC_TYPES = {
        "int",
        "bigint",
        "smallint",
        "tinyint",
        "decimal",
        "numeric",
        "float",
        "real",
        "money",
        "smallmoney",
    }

    # SQL Server datetime types
    DATETIME_TYPES = {
        "date",
        "datetime",
        "datetime2",
        "smalldatetime",
        "datetimeoffset",
        "time",
    }

    # SQL Server string types
    STRING_TYPES = {
        "char",
        "varchar",
        "text",
        "nchar",
        "nvarchar",
        "ntext",
    }

    def __init__(
        self,
        connection: Connection,
        schema_name: str,
        table_name: str,
    ):
        """Initialize collector for a specific table.

        Args:
            connection: SQLAlchemy connection
            schema_name: Schema name
            table_name: Table name
        """
        self.connection = connection
        self.schema_name = schema_name
        self.table_name = table_name
        self._qualified_table = f"[{schema_name}].[{table_name}]"

    def column_exists(self, column_name: str) -> bool:
        """Check if a column exists in the table.

        Args:
            column_name: Column name to check

        Returns:
            True if column exists, False otherwise
        """
        query = text("""
            SELECT COUNT(*)
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :schema_name
                AND TABLE_NAME = :table_name
                AND COLUMN_NAME = :column_name
        """)

        result = self.connection.execute(
            query,
            {
                "schema_name": self.schema_name,
                "table_name": self.table_name,
                "column_name": column_name,
            },
        )
        return result.scalar() > 0

    def get_columns_by_pattern(self, pattern: str) -> list[tuple[str, str]]:
        """Get columns matching a LIKE pattern.

        Args:
            pattern: SQL LIKE pattern (e.g., '%_id')

        Returns:
            List of (column_name, data_type) tuples
        """
        query = text("""
            SELECT COLUMN_NAME, DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :schema_name
                AND TABLE_NAME = :table_name
                AND COLUMN_NAME LIKE :pattern
            ORDER BY ORDINAL_POSITION
        """)

        result = self.connection.execute(
            query,
            {
                "schema_name": self.schema_name,
                "table_name": self.table_name,
                "pattern": pattern,
            },
        )
        return result.fetchall()

    def get_column_data_type(self, column_name: str) -> str:
        """Get the data type for a column.

        Args:
            column_name: Column name

        Returns:
            SQL data type string
        """
        query = text("""
            SELECT DATA_TYPE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :schema_name
                AND TABLE_NAME = :table_name
                AND COLUMN_NAME = :column_name
        """)

        result = self.connection.execute(
            query,
            {
                "schema_name": self.schema_name,
                "table_name": self.table_name,
                "column_name": column_name,
            },
        )
        row = result.fetchone()
        return row[0] if row else "unknown"

    def get_basic_stats(self, column_name: str, data_type: str) -> dict:
        """Collect basic statistics for a column.

        Args:
            column_name: Column name
            data_type: SQL data type

        Returns:
            Dictionary with total_rows, distinct_count, null_count, null_percentage
        """
        # Build query for basic stats
        query = text(f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT [{column_name}]) as distinct_count,
                SUM(CASE WHEN [{column_name}] IS NULL THEN 1 ELSE 0 END) as null_count
            FROM {self._qualified_table}
        """)

        result = self.connection.execute(query)
        row = result.fetchone()

        total_rows = row[0] if row else 0
        distinct_count = row[1] if row else 0
        null_count = row[2] if row else 0

        null_percentage = (null_count / total_rows * 100.0) if total_rows > 0 else 0.0

        return {
            "total_rows": total_rows,
            "distinct_count": distinct_count,
            "null_count": null_count,
            "null_percentage": null_percentage,
        }

    def get_numeric_stats(self, column_name: str) -> NumericStats:
        """Collect numeric statistics for a column.

        Adapted from former ColumnStatsCollector (lines 175-241).

        Args:
            column_name: Column name

        Returns:
            NumericStats instance (fields may be None if all values are NULL)
        """
        query = text(f"""
            SELECT
                MIN(CAST([{column_name}] AS FLOAT)) as min_value,
                MAX(CAST([{column_name}] AS FLOAT)) as max_value,
                AVG(CAST([{column_name}] AS FLOAT)) as mean_value,
                STDEV(CAST([{column_name}] AS FLOAT)) as std_dev
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
        """)

        result = self.connection.execute(query)
        row = result.fetchone()

        if not row:
            return NumericStats(
                min_value=None,
                max_value=None,
                mean_value=None,
                std_dev=None,
            )

        return NumericStats(
            min_value=row[0],
            max_value=row[1],
            mean_value=row[2],
            std_dev=row[3],
        )

    def get_datetime_stats(self, column_name: str) -> DateTimeStats:
        """Collect datetime statistics for a column.

        Adapted from former ColumnStatsCollector (lines 243-332).

        Args:
            column_name: Column name

        Returns:
            DateTimeStats instance (fields may be None if all values are NULL)
        """
        query = text(f"""
            SELECT
                MIN([{column_name}]) as min_date,
                MAX([{column_name}]) as max_date,
                DATEDIFF(day, MIN([{column_name}]), MAX([{column_name}])) as date_range_days,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM {self._qualified_table}
                        WHERE CAST([{column_name}] AS TIME) <> '00:00:00'
                    )
                    THEN 1
                    ELSE 0
                END as has_time_component
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
        """)

        result = self.connection.execute(query)
        row = result.fetchone()

        if not row or row[0] is None:
            return DateTimeStats(
                min_date=None,
                max_date=None,
                date_range_days=None,
                has_time_component=False,
            )

        return DateTimeStats(
            min_date=row[0],
            max_date=row[1],
            date_range_days=row[2],
            has_time_component=bool(row[3]),
        )

    def get_string_stats(
        self, column_name: str, sample_size: int = 10
    ) -> StringStats:
        """Collect string statistics for a column.

        Adapted from former ColumnStatsCollector (lines 334-408).

        Args:
            column_name: Column name
            sample_size: Number of top frequent values to return

        Returns:
            StringStats instance (fields may be None if all values are NULL)
        """
        # Get length statistics
        length_query = text(f"""
            SELECT
                MIN(LEN([{column_name}])) as min_length,
                MAX(LEN([{column_name}])) as max_length,
                AVG(CAST(LEN([{column_name}]) AS FLOAT)) as avg_length
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
        """)

        length_result = self.connection.execute(length_query)
        length_row = length_result.fetchone()

        min_length = length_row[0] if length_row else None
        max_length = length_row[1] if length_row else None
        avg_length = length_row[2] if length_row else None

        # Get top frequent values
        sample_query = text(f"""
            SELECT TOP {sample_size}
                [{column_name}] as value,
                COUNT(*) as frequency
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
            GROUP BY [{column_name}]
            ORDER BY COUNT(*) DESC, [{column_name}]
        """)

        sample_result = self.connection.execute(sample_query)
        sample_values = [(row[0], row[1]) for row in sample_result.fetchall()]

        return StringStats(
            min_length=min_length,
            max_length=max_length,
            avg_length=avg_length,
            sample_values=sample_values,
        )

    def _get_type_category(self, data_type: str) -> str:
        """Determine the category of a data type.

        Args:
            data_type: SQL data type string

        Returns:
            'numeric', 'datetime', 'string', or 'other'
        """
        data_type_lower = data_type.lower()

        if data_type_lower in self.NUMERIC_TYPES:
            return "numeric"
        elif data_type_lower in self.DATETIME_TYPES:
            return "datetime"
        elif data_type_lower in self.STRING_TYPES:
            return "string"
        else:
            return "other"

    def get_column_statistics(
        self, column_name: str, sample_size: int = 10
    ) -> ColumnStatistics:
        """Collect complete statistical profile for a single column.

        Args:
            column_name: Column name
            sample_size: Number of top frequent values for string columns

        Returns:
            ColumnStatistics instance

        Raises:
            ValueError: If column does not exist
        """
        # Verify column exists
        if not self.column_exists(column_name):
            raise ValueError(
                f"Column '{column_name}' not found in table "
                f"'{self.schema_name}.{self.table_name}'"
            )

        # Get data type
        data_type = self.get_column_data_type(column_name)

        # Get basic stats
        basic_stats = self.get_basic_stats(column_name, data_type)

        # Get type-specific stats
        type_category = self._get_type_category(data_type)

        numeric_stats = None
        datetime_stats = None
        string_stats = None

        if type_category == "numeric":
            numeric_stats = self.get_numeric_stats(column_name)
        elif type_category == "datetime":
            datetime_stats = self.get_datetime_stats(column_name)
        elif type_category == "string":
            string_stats = self.get_string_stats(column_name, sample_size)

        return ColumnStatistics(
            column_name=column_name,
            table_name=self.table_name,
            schema_name=self.schema_name,
            data_type=data_type,
            total_rows=basic_stats["total_rows"],
            distinct_count=basic_stats["distinct_count"],
            null_count=basic_stats["null_count"],
            null_percentage=basic_stats["null_percentage"],
            numeric_stats=numeric_stats,
            datetime_stats=datetime_stats,
            string_stats=string_stats,
        )

    def get_columns_info(
        self,
        columns: Optional[list[str]] = None,
        column_pattern: Optional[str] = None,
        sample_size: int = 10,
    ) -> list[ColumnStatistics]:
        """Collect statistics for multiple columns with optional filtering.

        Args:
            columns: Explicit list of column names (takes precedence over pattern)
            column_pattern: SQL LIKE pattern for column names
            sample_size: Number of top frequent values for string columns

        Returns:
            List of ColumnStatistics instances

        Raises:
            ValueError: If explicit column does not exist
        """
        # Determine which columns to analyze
        columns_to_analyze = []

        if columns is not None:
            # Explicit list takes precedence - just use column names
            columns_to_analyze = columns
        elif column_pattern is not None:
            # Use pattern matching - get (column_name, data_type) tuples
            pattern_results = self.get_columns_by_pattern(column_pattern)
            columns_to_analyze = [col_name for col_name, _dtype in pattern_results]
        else:
            # Get all columns
            all_columns_query = text("""
                SELECT COLUMN_NAME
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME = :table_name
                ORDER BY ORDINAL_POSITION
            """)
            result = self.connection.execute(
                all_columns_query,
                {
                    "schema_name": self.schema_name,
                    "table_name": self.table_name,
                },
            )
            columns_to_analyze = [row[0] for row in result.fetchall()]

        # Collect statistics for each column
        results = []
        for column_name in columns_to_analyze:
            stats = self.get_column_statistics(column_name, sample_size)
            results.append(stats)

        return results
