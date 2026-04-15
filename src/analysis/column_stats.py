"""Column statistics collector for data-exposure analysis.

Adapts SQL patterns from former src/inference/column_stats.py with key differences:
- Supports batch column analysis (multiple columns in one call)
- Column filtering by name list or LIKE pattern
- Returns ColumnStatistics model instances (no inference fields)
- No interpretive logic (raw statistics only)
- Dialect-aware: transpiles TSQL base queries via sqlglot
- Databricks fast path via DESCRIBE EXTENDED precomputed stats
"""

import fnmatch
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy import types as sa_types
from sqlalchemy.engine import Connection

from src.analysis._sql import transpile_query
from src.models.analysis import (
    ColumnStatistics,
    DateTimeStats,
    NumericStats,
    StringStats,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Inspector

    from src.db.dialects.protocol import DialectStrategy


class ColumnStatsCollector:
    """Collect per-column statistical profiles for a table.

    Supports:
    - Basic stats: distinct count, null count, total rows, null percentage
    - Numeric stats: min, max, mean, standard deviation
    - DateTime stats: min/max date, range in days, time component detection
    - String stats: min/max/avg length, top frequent values
    - Batch column analysis with filtering
    - Cross-dialect support via sqlglot transpilation
    - Databricks DESCRIBE EXTENDED fast path
    """

    # SQL Server string-based type sets (fallback when Inspector unavailable)
    _NUMERIC_TYPES_STR = {
        "int", "bigint", "smallint", "tinyint", "decimal", "numeric",
        "float", "real", "money", "smallmoney",
    }
    _DATETIME_TYPES_STR = {
        "date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "time",
    }
    _STRING_TYPES_STR = {
        "char", "varchar", "text", "nchar", "nvarchar", "ntext",
    }

    def __init__(
        self,
        connection: Connection,
        schema_name: str,
        table_name: str,
        dialect: "DialectStrategy | None" = None,
        inspector: "Inspector | None" = None,
    ):
        """Initialize collector for a specific table.

        Args:
            connection: SQLAlchemy connection
            schema_name: Schema name
            table_name: Table name
            dialect: Target dialect strategy, or None for MSSQL default
            inspector: SQLAlchemy Inspector, or None for INFORMATION_SCHEMA fallback
        """
        self.connection = connection
        self.schema_name = schema_name
        self.table_name = table_name
        self._dialect = dialect
        self._inspector = inspector
        # Build qualified table using bracket quoting (TSQL base syntax for transpilation)
        self._qualified_table = f"[{schema_name}].[{table_name}]"

    def column_exists(self, column_name: str) -> bool:
        """Check if a column exists in the table."""
        if self._inspector is not None:
            columns = self._inspector.get_columns(self.table_name, schema=self.schema_name)
            return any(c["name"] == column_name for c in columns)
        # Fallback: INFORMATION_SCHEMA (MSSQL backward compat)
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

    def get_columns_by_pattern(
        self, pattern: str
    ) -> list[tuple[str, "sa_types.TypeEngine | str"]]:
        """Get columns matching a LIKE pattern.

        Args:
            pattern: SQL LIKE pattern (e.g., '%_id')

        Returns:
            List of (column_name, type_info) tuples.
            type_info is TypeEngine when Inspector available, else data_type string.
        """
        if self._inspector is not None:
            columns = self._inspector.get_columns(self.table_name, schema=self.schema_name)
            # Convert SQL LIKE pattern to fnmatch: % -> *, _ -> ?
            glob_pattern = pattern.replace("%", "*").replace("_", "?")
            return [
                (c["name"], c["type"])
                for c in columns
                if fnmatch.fnmatch(c["name"], glob_pattern)
            ]
        # Fallback: INFORMATION_SCHEMA
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
        return [(row[0], row[1]) for row in result.fetchall()]

    def get_column_data_type(
        self, column_name: str
    ) -> "sa_types.TypeEngine | str":
        """Get the data type for a column.

        Returns TypeEngine when Inspector available, else data_type string.
        """
        if self._inspector is not None:
            columns = self._inspector.get_columns(self.table_name, schema=self.schema_name)
            for c in columns:
                if c["name"] == column_name:
                    return c["type"]
            return sa_types.NullType()
        # Fallback: INFORMATION_SCHEMA
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

    def _get_type_category(self, data_type: "sa_types.TypeEngine | str") -> str:
        """Classify a type into analysis categories.

        Accepts either a SQLAlchemy TypeEngine object (isinstance-based) or
        a data type string (set-based fallback for backward compat).
        """
        if isinstance(data_type, sa_types.TypeEngine):
            if isinstance(data_type, (sa_types.Integer, sa_types.Numeric, sa_types.Float)):
                return "numeric"
            # MSSQL MONEY/SMALLMONEY don't inherit from Numeric
            type_name = type(data_type).__name__.upper()
            if type_name in ("MONEY", "SMALLMONEY"):
                return "numeric"
            if isinstance(data_type, (sa_types.DateTime, sa_types.Date, sa_types.Time)):
                return "datetime"
            if isinstance(data_type, (sa_types.String, sa_types.Text)):
                return "string"
            return "other"
        # String-based fallback
        data_type_lower = data_type.lower()
        if data_type_lower in self._NUMERIC_TYPES_STR:
            return "numeric"
        elif data_type_lower in self._DATETIME_TYPES_STR:
            return "datetime"
        elif data_type_lower in self._STRING_TYPES_STR:
            return "string"
        else:
            return "other"

    def get_basic_stats(self, column_name: str) -> dict:
        """Collect basic statistics for a column."""
        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT [{column_name}]) as distinct_count,
                SUM(CASE WHEN [{column_name}] IS NULL THEN 1 ELSE 0 END) as null_count
            FROM {self._qualified_table}
        """
        query = text(transpile_query(sql, self._dialect))

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
        """Collect numeric statistics for a column."""
        sql = f"""
            SELECT
                MIN(CAST([{column_name}] AS FLOAT)) as min_value,
                MAX(CAST([{column_name}] AS FLOAT)) as max_value,
                AVG(CAST([{column_name}] AS FLOAT)) as mean_value,
                STDEV(CAST([{column_name}] AS FLOAT)) as std_dev
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
        """
        query = text(transpile_query(sql, self._dialect))

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
        """Collect datetime statistics for a column."""
        # Time component detection varies by dialect
        if self._dialect and self._dialect.name in ("databricks", "generic"):
            time_check = (
                f"HOUR([{column_name}]) <> 0 "
                f"OR MINUTE([{column_name}]) <> 0 "
                f"OR SECOND([{column_name}]) <> 0"
            )
        else:
            time_check = f"CAST([{column_name}] AS TIME) <> '00:00:00'"

        sql = f"""
            SELECT
                MIN([{column_name}]) as min_date,
                MAX([{column_name}]) as max_date,
                DATEDIFF(day, MIN([{column_name}]), MAX([{column_name}])) as date_range_days,
                CASE
                    WHEN EXISTS (
                        SELECT 1
                        FROM {self._qualified_table}
                        WHERE {time_check}
                    )
                    THEN 1
                    ELSE 0
                END as has_time_component
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
        """
        query = text(transpile_query(sql, self._dialect))

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
        """Collect string statistics for a column."""
        # Get length statistics
        length_sql = f"""
            SELECT
                MIN(LEN([{column_name}])) as min_length,
                MAX(LEN([{column_name}])) as max_length,
                AVG(CAST(LEN([{column_name}]) AS FLOAT)) as avg_length
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
        """
        length_query = text(transpile_query(length_sql, self._dialect))

        length_result = self.connection.execute(length_query)
        length_row = length_result.fetchone()

        min_length = length_row[0] if length_row else None
        max_length = length_row[1] if length_row else None
        avg_length = length_row[2] if length_row else None

        # Get top frequent values
        sample_sql = f"""
            SELECT TOP {sample_size}
                [{column_name}] as value,
                COUNT(*) as frequency
            FROM {self._qualified_table}
            WHERE [{column_name}] IS NOT NULL
            GROUP BY [{column_name}]
            ORDER BY COUNT(*) DESC, [{column_name}]
        """
        sample_query = text(transpile_query(sample_sql, self._dialect))

        sample_result = self.connection.execute(sample_query)
        sample_values = [(row[0], row[1]) for row in sample_result.fetchall()]

        return StringStats(
            min_length=min_length,
            max_length=max_length,
            avg_length=avg_length,
            sample_values=sample_values,
        )

    def _try_describe_extended_stats(self, column_name: str) -> dict | None:
        """Try to get precomputed stats via Databricks DESCRIBE EXTENDED.

        Returns dict with stat keys if available, None if not.
        """
        if not self._dialect or self._dialect.name != "databricks":
            return None

        qi = self._dialect.quote_identifier
        qualified_table = f"{qi(self.schema_name)}.{qi(self.table_name)}"
        sql = f"DESCRIBE EXTENDED {qualified_table} {qi(column_name)}"

        try:
            result = self.connection.execute(text(sql))
            rows = result.fetchall()
        except Exception:
            return None

        stat_keys = {"min", "max", "num_nulls", "distinct_count", "avg_col_len", "max_col_len"}
        stats = {}
        for row in rows:
            key = (row[0] or "").strip().lower()
            val = (row[1] or "").strip()
            if key in stat_keys:
                stats[key] = val

        # Check if stats are actually populated
        if not stats or all(v in ("", "null", "NULL", "None") for v in stats.values()):
            return None
        return stats

    def _build_stats_from_describe_extended(
        self, column_name: str, type_obj: sa_types.TypeEngine, desc_stats: dict
    ) -> ColumnStatistics:
        """Build ColumnStatistics from DESCRIBE EXTENDED precomputed stats."""
        type_category = self._get_type_category(type_obj)

        def safe_int(v):
            try:
                return int(v)
            except (ValueError, TypeError):
                return None

        def safe_float(v):
            try:
                return float(v)
            except (ValueError, TypeError):
                return None

        null_count = safe_int(desc_stats.get("num_nulls")) or 0
        distinct_count = safe_int(desc_stats.get("distinct_count")) or 0

        numeric_stats = None
        if type_category == "numeric":
            numeric_stats = NumericStats(
                min_value=safe_float(desc_stats.get("min")),
                max_value=safe_float(desc_stats.get("max")),
                mean_value=None,  # DESCRIBE EXTENDED doesn't provide mean
                std_dev=None,     # DESCRIBE EXTENDED doesn't provide stddev
            )

        return ColumnStatistics(
            column_name=column_name,
            table_name=self.table_name,
            schema_name=self.schema_name,
            data_type=str(type_obj),
            total_rows=0,  # Not available from DESCRIBE EXTENDED column stats
            distinct_count=distinct_count,
            null_count=null_count,
            null_percentage=0.0,  # Can't compute without total_rows
            numeric_stats=numeric_stats,
        )

    def get_column_statistics(
        self, column_name: str, sample_size: int = 10
    ) -> ColumnStatistics:
        """Collect complete statistical profile for a single column."""
        if not self.column_exists(column_name):
            raise ValueError(
                f"Column '{column_name}' not found in table "
                f"'{self.schema_name}.{self.table_name}'"
            )

        # Get type info via Inspector or INFORMATION_SCHEMA
        type_info = self.get_column_data_type(column_name)
        if isinstance(type_info, sa_types.TypeEngine):
            type_obj = type_info
            data_type_str = str(type_info)
        else:
            type_obj = None
            data_type_str = type_info

        # Databricks fast path: try DESCRIBE EXTENDED precomputed stats
        if self._dialect and self._dialect.name == "databricks":
            desc_stats = self._try_describe_extended_stats(column_name)
            if desc_stats is not None and type_obj is not None:
                return self._build_stats_from_describe_extended(
                    column_name, type_obj, desc_stats
                )

        # Tier 2: Standard SQL aggregates (transpiled)
        basic_stats = self.get_basic_stats(column_name)

        if type_obj is not None:
            type_category = self._get_type_category(type_obj)
        else:
            type_category = self._get_type_category(data_type_str)

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
            data_type=data_type_str,
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
        columns: list[str] | None = None,
        column_pattern: str | None = None,
        sample_size: int = 10,
    ) -> list[ColumnStatistics]:
        """Collect statistics for multiple columns with optional filtering."""
        columns_to_analyze: list[str] = []

        if columns is not None:
            columns_to_analyze = columns
        elif column_pattern is not None:
            pattern_results = self.get_columns_by_pattern(column_pattern)
            columns_to_analyze = [col_name for col_name, _type_info in pattern_results]
        else:
            if self._inspector is not None:
                inspector_cols = self._inspector.get_columns(
                    self.table_name, schema=self.schema_name
                )
                columns_to_analyze = [c["name"] for c in inspector_cols]
            else:
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

        # Databricks fast path: probe first column to decide bulk strategy
        use_fast_path = False
        if (
            self._dialect
            and self._dialect.name == "databricks"
            and columns_to_analyze
        ):
            probe_stats = self._try_describe_extended_stats(columns_to_analyze[0])
            use_fast_path = probe_stats is not None

        results = []
        for column_name in columns_to_analyze:
            if use_fast_path:
                # Fast path for all columns (DESCRIBE EXTENDED has stats)
                type_info = self.get_column_data_type(column_name)
                if isinstance(type_info, sa_types.TypeEngine):
                    desc_stats = self._try_describe_extended_stats(column_name)
                    if desc_stats is not None:
                        results.append(
                            self._build_stats_from_describe_extended(
                                column_name, type_info, desc_stats
                            )
                        )
                        continue
            # Tier 2 fallback
            stats = self.get_column_statistics(column_name, sample_size)
            results.append(stats)

        return results
