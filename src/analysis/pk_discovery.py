"""Primary key candidate discovery for data-exposure analysis.

Identifies PK candidates via two approaches:
1. Constraint-backed: Columns with PK or UNIQUE constraints
2. Structural: Columns that are unique, non-null, and match a configurable type set

Returns PKCandidate model instances with raw metadata only -- no scoring or interpretation.
"""

from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.analysis._sql import (
    CatalogAwareReflector,
    quote_tsql_identifier,
    transpile_query,
)
from src.models.analysis import PKCandidate

if TYPE_CHECKING:
    from sqlalchemy.engine import Inspector

    from src.db.dialects.protocol import DialectStrategy

# Default types considered for structural PK candidacy
DEFAULT_PK_TYPE_FILTER = [
    "int", "bigint", "smallint", "tinyint", "uniqueidentifier",
]


class PKDiscovery:
    """Discover primary key candidates for a table.

    Supports:
    - Constraint-backed detection (PK and UNIQUE constraints)
    - Structural candidacy (unique values + non-null + type match)
    - Configurable type filter for structural candidates
    - Dialect-aware: Inspector for generic/Databricks, INFORMATION_SCHEMA for MSSQL
    """

    def __init__(
        self,
        connection: Connection,
        schema_name: str,
        table_name: str,
        dialect: "DialectStrategy | None" = None,
        inspector: "Inspector | None" = None,
        catalog: "str | None" = None,
    ):
        self.connection = connection
        self.schema_name = schema_name
        self.table_name = table_name
        self._dialect = dialect
        self._inspector = inspector
        self._catalog = catalog
        # Cross-catalog reads only apply to Databricks with an explicit catalog.
        # Other dialects reject catalog upstream (resolver), so this stays False.
        self._cross_catalog = (
            bool(catalog) and dialect is not None and dialect.name == "databricks"
        )
        # 3-part TSQL brackets when cross-catalog (sqlglot transpiles to
        # `cat`.`sch`.`tbl`); 2-part otherwise. Never pre-quote with backticks
        # -- this string is fed through transpile_query(read="tsql") (Pitfall 4).
        q = quote_tsql_identifier
        if catalog:
            self._qualified_table = (
                f"{q(catalog)}.{q(schema_name)}.{q(table_name)}"
            )
        else:
            self._qualified_table = f"{q(schema_name)}.{q(table_name)}"

    def get_constraint_candidates(
        self,
        type_filter: list[str],
    ) -> list[PKCandidate]:
        """Find columns backed by PK or UNIQUE constraints.

        Uses Inspector for non-MSSQL dialects, INFORMATION_SCHEMA for MSSQL/None.

        Args:
            type_filter: SQL types to evaluate is_pk_type against.
                Empty list means all types qualify.

        Returns:
            List of PKCandidate instances for constraint-backed columns.
        """
        type_filter_lower = {t.lower() for t in type_filter}

        if self._cross_catalog:
            return self._get_constraint_candidates_cross_catalog(type_filter_lower)
        if (
            self._dialect is not None
            and self._dialect.name != "mssql"
            and self._inspector is not None
        ):
            return self._get_constraint_candidates_inspector(type_filter_lower)
        return self._get_constraint_candidates_mssql(type_filter_lower)

    def _get_constraint_candidates_mssql(
        self, type_filter_lower: set[str]
    ) -> list[PKCandidate]:
        """Use INFORMATION_SCHEMA for constraint discovery (MSSQL/default)."""
        candidates = []

        # Get PRIMARY KEY columns
        pk_query = text("""
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE,
                'PRIMARY KEY' AS constraint_type
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
                ON tc.CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
                AND tc.TABLE_SCHEMA = ccu.TABLE_SCHEMA
            JOIN INFORMATION_SCHEMA.COLUMNS c
                ON ccu.COLUMN_NAME = c.COLUMN_NAME
                AND ccu.TABLE_SCHEMA = c.TABLE_SCHEMA
                AND ccu.TABLE_NAME = c.TABLE_NAME
            WHERE tc.TABLE_SCHEMA = :schema_name
                AND tc.TABLE_NAME = :table_name
                AND tc.CONSTRAINT_TYPE = 'PRIMARY KEY'
        """)

        pk_result = self.connection.execute(
            pk_query,
            {"schema_name": self.schema_name, "table_name": self.table_name},
        )
        pk_columns = set()
        for row in pk_result.fetchall():
            pk_columns.add(row[0])
            candidates.append(PKCandidate(
                column_name=row[0],
                data_type=row[1],
                is_constraint_backed=True,
                constraint_type=row[2],
                is_unique=True,
                is_non_null=True,
                is_pk_type=not type_filter_lower or row[1].lower() in type_filter_lower,
            ))

        # Get UNIQUE constraint columns (excluding those already found as PK)
        uq_query = text("""
            SELECT
                c.COLUMN_NAME,
                c.DATA_TYPE
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
                ON tc.CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
                AND tc.TABLE_SCHEMA = ccu.TABLE_SCHEMA
            JOIN INFORMATION_SCHEMA.COLUMNS c
                ON ccu.COLUMN_NAME = c.COLUMN_NAME
                AND ccu.TABLE_SCHEMA = c.TABLE_SCHEMA
                AND ccu.TABLE_NAME = c.TABLE_NAME
            WHERE tc.TABLE_SCHEMA = :schema_name
                AND tc.TABLE_NAME = :table_name
                AND tc.CONSTRAINT_TYPE = 'UNIQUE'
        """)

        uq_result = self.connection.execute(
            uq_query,
            {"schema_name": self.schema_name, "table_name": self.table_name},
        )
        for row in uq_result.fetchall():
            if row[0] not in pk_columns:
                candidates.append(PKCandidate(
                    column_name=row[0],
                    data_type=row[1],
                    is_constraint_backed=True,
                    constraint_type="UNIQUE",
                    is_unique=True,
                    is_non_null=False,  # UNIQUE doesn't imply non-null
                    is_pk_type=not type_filter_lower or row[1].lower() in type_filter_lower,
                ))

        return candidates

    def _get_constraint_candidates_inspector(
        self, type_filter_lower: set[str]
    ) -> list[PKCandidate]:
        """Use Inspector for constraint discovery (generic/Databricks)."""
        candidates = []
        pk_columns: set[str] = set()

        # Determine if constraints are informational (Databricks)
        is_informational = self._dialect.name == "databricks"

        # Build column type map from Inspector
        columns = self._inspector.get_columns(
            self.table_name, schema=self.schema_name
        )
        col_type_map = {c["name"]: str(c["type"]) for c in columns}

        # Get PK constraint
        pk_info = self._inspector.get_pk_constraint(
            self.table_name, schema=self.schema_name
        )
        if pk_info and pk_info.get("constrained_columns"):
            for col_name in pk_info["constrained_columns"]:
                pk_columns.add(col_name)
                data_type = col_type_map.get(col_name, "unknown")
                candidates.append(PKCandidate(
                    column_name=col_name,
                    data_type=data_type,
                    is_constraint_backed=True,
                    constraint_type="PRIMARY KEY",
                    is_unique=True,
                    is_non_null=True,
                    is_pk_type=not type_filter_lower or data_type.lower() in type_filter_lower,
                    constraint_enforced=not is_informational,
                ))

        # Get UNIQUE constraints
        unique_constraints = self._inspector.get_unique_constraints(
            self.table_name, schema=self.schema_name
        )
        for uc in unique_constraints:
            for col_name in uc.get("column_names", []):
                if col_name not in pk_columns:
                    data_type = col_type_map.get(col_name, "unknown")
                    candidates.append(PKCandidate(
                        column_name=col_name,
                        data_type=data_type,
                        is_constraint_backed=True,
                        constraint_type="UNIQUE",
                        is_unique=True,
                        is_non_null=False,
                        is_pk_type=not type_filter_lower or data_type.lower() in type_filter_lower,
                        constraint_enforced=not is_informational,
                    ))

        return candidates

    def _get_constraint_candidates_cross_catalog(
        self, type_filter_lower: set[str]
    ) -> list[PKCandidate]:
        """Catalog-scoped PK/UNIQUE discovery for cross-catalog Databricks.

        Columns are reflected via :class:`CatalogAwareReflector` (DESCRIBE TABLE
        on the explicit 3-part name). PK/UNIQUE constraints are read from the
        requested catalog's ``information_schema`` -- every identifier segment is
        backtick-quoted (no parameter binding, since identifiers cannot be bound).
        No catalog-switching statement is emitted; the queries are fully
        qualified and stateless over the pooled connection (T-15.1-04).
        """
        candidates: list[PKCandidate] = []
        pk_columns: set[str] = set()

        # Column type map via catalog-aware DESCRIBE TABLE (reflector returns
        # {"name", "data_type"} dicts over the analysis class's live connection).
        reflector = CatalogAwareReflector(self.connection, self._dialect)
        columns = reflector.reflect_columns(
            self._catalog, self.schema_name, self.table_name
        )
        col_type_map = {c["name"]: c["data_type"] for c in columns}

        qi = self._dialect.quote_identifier
        info_schema = f"{qi(self._catalog)}.information_schema"

        # PRIMARY KEY columns from the catalog's information_schema.
        pk_query = text(f"""
            SELECT kcu.column_name, tc.constraint_type
            FROM {info_schema}.table_constraints tc
            JOIN {info_schema}.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = :schema_name
                AND tc.table_name = :table_name
                AND tc.constraint_type = 'PRIMARY KEY'
        """)
        pk_result = self.connection.execute(
            pk_query,
            {"schema_name": self.schema_name, "table_name": self.table_name},
        )
        for row in pk_result.fetchall():
            col_name = row[0]
            pk_columns.add(col_name)
            data_type = col_type_map.get(col_name, "unknown")
            candidates.append(PKCandidate(
                column_name=col_name,
                data_type=data_type,
                is_constraint_backed=True,
                constraint_type="PRIMARY KEY",
                is_unique=True,
                is_non_null=True,
                is_pk_type=not type_filter_lower or data_type.lower() in type_filter_lower,
                constraint_enforced=False,  # Databricks constraints are informational
            ))

        # UNIQUE constraint columns (excluding those already found as PK).
        uq_query = text(f"""
            SELECT kcu.column_name
            FROM {info_schema}.table_constraints tc
            JOIN {info_schema}.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = :schema_name
                AND tc.table_name = :table_name
                AND tc.constraint_type = 'UNIQUE'
        """)
        uq_result = self.connection.execute(
            uq_query,
            {"schema_name": self.schema_name, "table_name": self.table_name},
        )
        for row in uq_result.fetchall():
            col_name = row[0]
            if col_name not in pk_columns:
                data_type = col_type_map.get(col_name, "unknown")
                candidates.append(PKCandidate(
                    column_name=col_name,
                    data_type=data_type,
                    is_constraint_backed=True,
                    constraint_type="UNIQUE",
                    is_unique=True,
                    is_non_null=False,
                    is_pk_type=not type_filter_lower or data_type.lower() in type_filter_lower,
                    constraint_enforced=False,
                ))

        return candidates

    def get_structural_candidates(
        self,
        type_filter: list[str],
        exclude_columns: set[str],
    ) -> list[PKCandidate]:
        """Find structural PK candidates (unique + non-null + type match).

        Uses Inspector for column listing when available, INFORMATION_SCHEMA otherwise.

        Args:
            type_filter: SQL types to consider. Empty list disables type filtering.
            exclude_columns: Column names to skip (already found via constraints).

        Returns:
            List of PKCandidate instances for structural candidates.
        """
        type_filter_lower = {t.lower() for t in type_filter}
        all_columns = self._list_all_columns()

        candidates = []
        for col_name, data_type, is_nullable in all_columns:
            # Skip already-found constraint columns / nullable / wrong-type
            if col_name in exclude_columns or is_nullable:
                continue
            if type_filter_lower and data_type.lower() not in type_filter_lower:
                continue

            if not self._column_is_unique(col_name):
                continue

            is_pk_type = (
                not type_filter_lower
                or data_type.lower() in type_filter_lower
            )
            candidates.append(PKCandidate(
                column_name=col_name,
                data_type=data_type,
                is_constraint_backed=False,
                constraint_type=None,
                is_unique=True,
                is_non_null=True,
                is_pk_type=is_pk_type,
            ))

        return candidates

    def _list_all_columns(self) -> list[tuple[str, str, bool]]:
        """List all (name, data_type, is_nullable) columns for the target table.

        Uses the catalog-aware reflector on the cross-catalog Databricks branch,
        SQLAlchemy Inspector when available, else INFORMATION_SCHEMA.
        """
        if self._cross_catalog:
            # DESCRIBE TABLE does not expose nullability; treat reflected columns
            # as non-nullable so the uniqueness probe (over the 3-part qualified
            # table) is the sole structural gate. col_type_map keys are names.
            reflector = CatalogAwareReflector(self.connection, self._dialect)
            columns = reflector.reflect_columns(
                self._catalog, self.schema_name, self.table_name
            )
            return [(c["name"], c["data_type"], False) for c in columns]

        if self._inspector is not None:
            columns = self._inspector.get_columns(
                self.table_name, schema=self.schema_name
            )
            return [
                (c["name"], str(c["type"]), c.get("nullable", True))
                for c in columns
            ]

        cols_query = text("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :schema_name
                AND TABLE_NAME = :table_name
            ORDER BY ORDINAL_POSITION
        """)
        cols_result = self.connection.execute(
            cols_query,
            {"schema_name": self.schema_name, "table_name": self.table_name},
        )
        return [
            (row[0], row[1], row[2] == "YES")
            for row in cols_result.fetchall()
        ]

    def _column_is_unique(self, col_name: str) -> bool:
        """Check uniqueness of ``col_name`` over its non-null domain.

        Unique iff COUNT(DISTINCT col) == COUNT(*) over non-null rows AND
        at least one non-null row exists.
        """
        col_q = quote_tsql_identifier(col_name)
        uniq_sql = f"""
            SELECT
                COUNT(DISTINCT {col_q}) AS distinct_count,
                COUNT(*) AS total_non_null
            FROM {self._qualified_table}
            WHERE {col_q} IS NOT NULL
        """
        uniq_query = text(transpile_query(uniq_sql, self._dialect))
        uniq_result = self.connection.execute(uniq_query)
        row = uniq_result.fetchall()
        if not row:
            return False
        distinct_count = row[0][0]
        total_non_null = row[0][1]
        return distinct_count == total_non_null and total_non_null > 0

    def find_candidates(
        self,
        type_filter: list[str] | None = None,
    ) -> list[PKCandidate]:
        """Find all PK candidates (constraint-backed + structural).

        Args:
            type_filter: SQL types for structural candidacy. None uses defaults.
                Empty list disables type filtering.

        Returns:
            List of PKCandidate instances, constraint-backed first.
        """
        if type_filter is None:
            type_filter = DEFAULT_PK_TYPE_FILTER

        # Step 1: Find constraint-backed candidates
        constraint_candidates = self.get_constraint_candidates(type_filter=type_filter)
        constraint_column_names = {c.column_name for c in constraint_candidates}

        # Step 2: Find structural candidates (excluding constraint columns)
        structural_candidates = self.get_structural_candidates(
            type_filter=type_filter,
            exclude_columns=constraint_column_names,
        )

        return constraint_candidates + structural_candidates
