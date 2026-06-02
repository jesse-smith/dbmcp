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
from sqlalchemy.exc import SQLAlchemyError

from src.analysis._sql import (
    CatalogAwareReflector,
    quote_tsql_identifier,
    transpile_query,
    type_category,
)
from src.models.analysis import (
    ColumnStatistics,
    DateTimeStats,
    NumericStats,
    StringStats,
)

if TYPE_CHECKING:
    from sqlalchemy.engine import Inspector

    from src.db.dialects.protocol import DialectStrategy


def _databricks_type_string_to_engine(type_string: str) -> sa_types.TypeEngine:
    """Convert a Databricks DESCRIBE-TABLE type token to a SQLAlchemy TypeEngine.

    WR-05 (Option B): the cross-catalog reflector yields raw DESCRIBE-TABLE type
    strings (e.g. ``"int"``, ``"string"``, ``"decimal(10,2)"``). Returning a
    ``TypeEngine`` lets the ``isinstance(..., TypeEngine)`` fast-path gate fire
    cross-catalog. Reuses the Databricks dialect's own ``GET_COLUMNS_TYPE_MAP``
    (DRY — no hand-rolled type table), special-casing ``decimal`` to preserve
    precision/scale, and falling back to ``NullType()`` for any unmapped token
    (symmetric with the default-catalog Inspector path, which also returns
    ``NullType()`` for unknowns — both still TypeEngines, so they take the fast
    path and land in the "other" category).

    The ``databricks.sqlalchemy`` import is local so non-Databricks paths never
    import the package.
    """
    from databricks.sqlalchemy._parse import (
        GET_COLUMNS_TYPE_MAP,
        parse_numeric_type_precision_and_scale,
    )

    # DESCRIBE tokens are lowercase ("decimal(10,2)"); the map is keyed on the
    # leading word ("decimal").
    token = type_string.strip().lower()
    base = token.split("(", 1)[0].strip()
    mapped = GET_COLUMNS_TYPE_MAP.get(base)
    if mapped is None:
        return sa_types.NullType()
    if base == "decimal":
        # parse_numeric_type_precision_and_scale needs an uppercase
        # DECIMAL(p,s); a bare "decimal" (no precision) → plain Numeric.
        if "(" in token:
            return parse_numeric_type_precision_and_scale(token.upper())
        return sa_types.Numeric()
    return mapped()


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

    def __init__(
        self,
        connection: Connection,
        schema_name: str,
        table_name: str,
        dialect: "DialectStrategy | None" = None,
        inspector: "Inspector | None" = None,
        catalog: str | None = None,
    ):
        """Initialize collector for a specific table.

        Args:
            connection: SQLAlchemy connection
            schema_name: Schema name
            table_name: Table name
            dialect: Target dialect strategy, or None for MSSQL default
            inspector: SQLAlchemy Inspector, or None for INFORMATION_SCHEMA fallback
            catalog: Resolved catalog for cross-catalog Databricks access
                (IDENT-08), or None for the default-catalog path.
        """
        self.connection = connection
        self.schema_name = schema_name
        self.table_name = table_name
        self._dialect = dialect
        self._inspector = inspector
        self._catalog = catalog
        # Build qualified table using bracket quoting (TSQL base syntax for
        # transpilation). When a catalog is set, emit a 3-part name so the
        # transpiled aggregate SQL targets the requested catalog (IDENT-08).
        q = quote_tsql_identifier
        if catalog:
            self._qualified_table = (
                f"{q(catalog)}.{q(schema_name)}.{q(table_name)}"
            )
        else:
            self._qualified_table = f"{q(schema_name)}.{q(table_name)}"

    @property
    def _is_cross_catalog_databricks(self) -> bool:
        """True when reads must be catalog-scoped via raw Databricks reflection."""
        return bool(
            self._catalog
            and self._dialect is not None
            and self._dialect.name == "databricks"
        )

    def _reflect_catalog_columns(self) -> list[dict]:
        """Reflect columns from the requested catalog (Databricks cross-catalog).

        Returns ``list[dict]`` with keys ``name``/``data_type`` (per
        CatalogAwareReflector — NOT Column objects), reusing the live
        ``self.connection`` rather than opening a fresh engine connection.
        """
        reflector = CatalogAwareReflector(self.connection, self._dialect)
        return reflector.reflect_columns(
            self._catalog, self.schema_name, self.table_name
        )

    def column_exists(self, column_name: str) -> bool:
        """Check if a column exists in the table."""
        if self._is_cross_catalog_databricks:
            cols = self._reflect_catalog_columns()
            return any(c["name"] == column_name for c in cols)
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
        if self._is_cross_catalog_databricks:
            cols = self._reflect_catalog_columns()
            glob_pattern = pattern.replace("%", "*").replace("_", "?")
            return [
                (c["name"], c["data_type"])
                for c in cols
                if fnmatch.fnmatch(c["name"], glob_pattern)
            ]
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

        Returns a ``TypeEngine`` on the Inspector path AND on the cross-catalog
        Databricks path (WR-05: the cross-catalog DESCRIBE-TABLE type string is
        converted to a ``TypeEngine`` so the fast-path ``isinstance`` gate fires
        — see :func:`_databricks_type_string_to_engine`). Only the
        INFORMATION_SCHEMA fallback (no Inspector, non-cross-catalog) returns a
        bare string.
        """
        if self._is_cross_catalog_databricks:
            for c in self._reflect_catalog_columns():
                if c["name"] == column_name:
                    return _databricks_type_string_to_engine(c["data_type"])
            # Symmetric with the Inspector path: unknown column → NullType()
            # (still a TypeEngine, so the gate behaves predictably).
            return sa_types.NullType()
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

        Thin delegator to the shared :func:`src.analysis._sql.type_category`
        (one categorizer, two callers — column stats and FK candidate search).
        """
        return type_category(data_type)

    def get_basic_stats(self, column_name: str) -> dict:
        """Collect basic statistics for a column."""
        col_q = quote_tsql_identifier(column_name)
        sql = f"""
            SELECT
                COUNT(*) as total_rows,
                COUNT(DISTINCT {col_q}) as distinct_count,
                SUM(CASE WHEN {col_q} IS NULL THEN 1 ELSE 0 END) as null_count
            FROM {self._qualified_table}
        """
        query = text(transpile_query(sql, self._dialect))

        result = self.connection.execute(query)
        # WR-02: a no-GROUP-BY aggregate always returns exactly one full-width
        # row, so index directly and trust the contract. The former
        # `row[N] if row else 0` guards were misleading — they guarded None but
        # still blindly indexed row[1]/row[2], so a short row would IndexError
        # anyway.
        row = result.fetchone()
        total_rows, distinct_count, null_count = row[0], row[1], row[2]

        null_percentage = (null_count / total_rows * 100.0) if total_rows > 0 else 0.0

        return {
            "total_rows": total_rows,
            "distinct_count": distinct_count,
            "null_count": null_count,
            "null_percentage": null_percentage,
        }

    def get_numeric_stats(self, column_name: str) -> NumericStats:
        """Collect numeric statistics for a column."""
        col_q = quote_tsql_identifier(column_name)
        sql = f"""
            SELECT
                MIN(CAST({col_q} AS FLOAT)) as min_value,
                MAX(CAST({col_q} AS FLOAT)) as max_value,
                AVG(CAST({col_q} AS FLOAT)) as mean_value,
                STDEV(CAST({col_q} AS FLOAT)) as std_dev
            FROM {self._qualified_table}
            WHERE {col_q} IS NOT NULL
        """
        query = text(transpile_query(sql, self._dialect))

        result = self.connection.execute(query)
        # WR-02: the aggregate always returns one full-width row; the all-NULL
        # case is (None, None, None, None) — a truthy tuple handled directly
        # below. The former `if not row` early return was dead code.
        row = result.fetchone()

        return NumericStats(
            min_value=row[0],
            max_value=row[1],
            mean_value=row[2],
            std_dev=row[3],
        )

    def get_datetime_stats(self, column_name: str) -> DateTimeStats:
        """Collect datetime statistics for a column."""
        col_q = quote_tsql_identifier(column_name)
        # Time component detection varies by dialect
        if self._dialect and self._dialect.name in ("databricks", "generic"):
            time_check = (
                f"HOUR({col_q}) <> 0 "
                f"OR MINUTE({col_q}) <> 0 "
                f"OR SECOND({col_q}) <> 0"
            )
        else:
            time_check = f"CAST({col_q} AS TIME) <> '00:00:00'"

        sql = f"""
            SELECT
                MIN({col_q}) as min_date,
                MAX({col_q}) as max_date,
                DATEDIFF(day, MIN({col_q}), MAX({col_q})) as date_range_days,
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
            WHERE {col_q} IS NOT NULL
        """
        query = text(transpile_query(sql, self._dialect))

        result = self.connection.execute(query)
        # WR-02: full-width single-row aggregate. The meaningful guard is
        # `row[0] is None` (all-NULL column → no min/max date); the former
        # `not row` disjunct was dead (a no-GROUP-BY aggregate never returns
        # an empty result).
        row = result.fetchone()

        if row[0] is None:
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
        col_q = quote_tsql_identifier(column_name)
        # Get length statistics
        length_sql = f"""
            SELECT
                MIN(LEN({col_q})) as min_length,
                MAX(LEN({col_q})) as max_length,
                AVG(CAST(LEN({col_q}) AS FLOAT)) as avg_length
            FROM {self._qualified_table}
            WHERE {col_q} IS NOT NULL
        """
        length_query = text(transpile_query(length_sql, self._dialect))

        length_result = self.connection.execute(length_query)
        # WR-02: full-width single-row aggregate; all-NULL column yields
        # (None, None, None). Index directly, drop the misleading guards.
        length_row = length_result.fetchone()
        min_length, max_length, avg_length = (
            length_row[0],
            length_row[1],
            length_row[2],
        )

        # Get top frequent values
        sample_sql = f"""
            SELECT TOP {sample_size}
                {col_q} as value,
                COUNT(*) as frequency
            FROM {self._qualified_table}
            WHERE {col_q} IS NOT NULL
            GROUP BY {col_q}
            ORDER BY COUNT(*) DESC, {col_q}
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
        # Pitfall 5: this fast path is native Databricks SQL (NOT transpiled), so
        # the 3-part name must be built here when a catalog is set — mirroring
        # get_sample_data (src/db/query.py). Every segment is quoted via
        # quote_identifier (T-15.1-09 injection control).
        if self._catalog:
            qualified_table = (
                f"{qi(self._catalog)}.{qi(self.schema_name)}.{qi(self.table_name)}"
            )
        else:
            qualified_table = f"{qi(self.schema_name)}.{qi(self.table_name)}"
        sql = f"DESCRIBE EXTENDED {qualified_table} {qi(column_name)}"

        try:
            result = self.connection.execute(text(sql))
            rows = result.fetchall()
        except SQLAlchemyError:
            # WR-01: narrow from bare `except Exception`. "DESCRIBE EXTENDED
            # unsupported / no stats" surfaces as a SQLAlchemyError subclass
            # (e.g. ProgrammingError) and legitimately degrades to Tier-2.
            # Non-SQLAlchemy errors (auth/network/injection-induced) now
            # propagate instead of being silently masked.
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

        null_count = safe_int(desc_stats.get("num_nulls"))
        if null_count is None:
            null_count = 0
        distinct_count = safe_int(desc_stats.get("distinct_count"))
        if distinct_count is None:
            distinct_count = 0

        numeric_stats = None
        if type_category == "numeric":
            numeric_stats = NumericStats(
                min_value=safe_float(desc_stats.get("min")),
                max_value=safe_float(desc_stats.get("max")),
                # mean/stddev are intrinsically absent from columnar metadata:
                # Parquet/Delta footers store min/max/null_count/numRecords but
                # never Σx or Σx², so a mean cannot be derived (ANALYZE COMPUTE
                # STATISTICS doesn't compute them either). Tier-2 would, but that
                # requires a full aggregate scan — out of scope for the fast path.
                mean_value=None,
                std_dev=None,
            )

        # TD-11: DESCRIBE EXTENDED is column-scoped and carries no table row
        # count, so issue one COUNT(*) — on Delta this is answered from the
        # transaction-log metadata (not a data scan), preserving the fast path's
        # value. Derive null_percentage honestly instead of hardcoding 0.0
        # alongside a populated null_count.
        total_rows = self._fast_path_row_count()
        null_percentage = (
            (null_count / total_rows * 100.0) if total_rows > 0 else 0.0
        )

        return ColumnStatistics(
            column_name=column_name,
            table_name=self.table_name,
            schema_name=self.schema_name,
            data_type=str(type_obj),
            total_rows=total_rows,
            distinct_count=distinct_count,
            # DESCRIBE EXTENDED's distinct_count is an HLL approximation, not an
            # exact count (UE-03) — a unique key can report fewer distinct values
            # than rows. Flag it so the caller doesn't read a phantom-duplicate
            # signal as real.
            distinct_count_approximate=True,
            null_count=null_count,
            null_percentage=null_percentage,
            numeric_stats=numeric_stats,
        )

    def _fast_path_row_count(self) -> int:
        """Row count for the Databricks fast path via one COUNT(*).

        Metadata-cheap on Delta (answered from the transaction log, not a data
        scan). Mirrors the COUNT(*) in :meth:`get_basic_stats`.
        """
        sql = f"SELECT COUNT(*) AS total_rows FROM {self._qualified_table}"
        query = text(transpile_query(sql, self._dialect))
        row = self.connection.execute(query).fetchone()
        return row[0]

    def get_column_statistics(
        self, column_name: str, sample_size: int = 10
    ) -> ColumnStatistics:
        """Collect complete statistical profile for a single column.

        On Databricks the DESCRIBE EXTENDED fast path fires for BOTH the
        default-catalog and the cross-catalog branch (WR-05): the type resolves
        to a ``TypeEngine`` in both cases, so the ``isinstance`` gate passes and
        precomputed stats are used instead of Tier-2 aggregates. On the
        cross-catalog path the ``data_type`` response field is ``str(TypeEngine)``
        (e.g. ``"INTEGER"``), converged onto the default-catalog format (FR-014).

        Fast-path contract (TD-11): ``total_rows`` is populated via one
        COUNT(*) (metadata-cheap on Delta) and ``null_percentage`` is derived
        from it, so they agree with ``null_count``. ``numeric_stats.mean_value``
        and ``std_dev`` are ``None`` on the fast path by design — they are
        intrinsically absent from columnar metadata and only the Tier-2 path
        (MSSQL, or Databricks tables without precomputed stats) computes them.
        """
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
            # Tier-2 uses exact COUNT(DISTINCT) (UE-03) — explicitly not
            # approximate (default is False; pinned here and under test).
            distinct_count_approximate=False,
            null_count=basic_stats["null_count"],
            null_percentage=basic_stats["null_percentage"],
            numeric_stats=numeric_stats,
            datetime_stats=datetime_stats,
            string_stats=string_stats,
        )

    def _resolve_columns_to_analyze(
        self,
        columns: list[str] | None,
        column_pattern: str | None,
    ) -> list[str]:
        """Resolve which columns to analyze.

        Precedence: explicit ``columns`` > ``column_pattern`` > all columns
        (via SQLAlchemy inspector, falling back to INFORMATION_SCHEMA).
        """
        if columns is not None:
            return columns
        if column_pattern is not None:
            pattern_results = self.get_columns_by_pattern(column_pattern)
            return [col_name for col_name, _type_info in pattern_results]

        if self._is_cross_catalog_databricks:
            return [c["name"] for c in self._reflect_catalog_columns()]

        if self._inspector is not None:
            inspector_cols = self._inspector.get_columns(
                self.table_name, schema=self.schema_name
            )
            return [c["name"] for c in inspector_cols]

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
        return [row[0] for row in result.fetchall()]

    def get_columns_info(
        self,
        columns: list[str] | None = None,
        column_pattern: str | None = None,
        sample_size: int = 10,
    ) -> list[ColumnStatistics]:
        """Collect statistics for multiple columns with optional filtering.

        The Databricks DESCRIBE EXTENDED fast path fires for both default-catalog
        and cross-catalog columns (WR-05): ``get_column_data_type`` returns a
        ``TypeEngine`` on both branches, so the per-column ``isinstance`` gate
        below passes cross-catalog and precomputed stats are used.
        """
        columns_to_analyze = self._resolve_columns_to_analyze(columns, column_pattern)

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
