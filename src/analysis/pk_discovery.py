"""Primary key candidate discovery for data-exposure analysis.

Identifies PK candidates via two approaches:
1. Constraint-backed: Columns with PK or UNIQUE constraints
2. Structural: Columns that are unique, non-null, and match a configurable type set

Returns PKCandidate model instances with raw metadata only — no scoring or interpretation.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.models.analysis import PKCandidate

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
    """

    def __init__(
        self,
        connection: Connection,
        schema_name: str,
        table_name: str,
    ):
        self.connection = connection
        self.schema_name = schema_name
        self.table_name = table_name
        self._qualified_table = f"[{schema_name}].[{table_name}]"

    def get_constraint_candidates(
        self,
        type_filter: list[str],
    ) -> list[PKCandidate]:
        """Find columns backed by PK or UNIQUE constraints.

        Args:
            type_filter: SQL types to evaluate is_pk_type against.
                Empty list means all types qualify.

        Returns:
            List of PKCandidate instances for constraint-backed columns.
        """
        type_filter_lower = {t.lower() for t in type_filter}
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

    def get_structural_candidates(
        self,
        type_filter: list[str],
        exclude_columns: set[str],
    ) -> list[PKCandidate]:
        """Find structural PK candidates (unique + non-null + type match).

        Args:
            type_filter: SQL types to consider. Empty list disables type filtering.
            exclude_columns: Column names to skip (already found via constraints).

        Returns:
            List of PKCandidate instances for structural candidates.
        """
        # Get all columns with metadata
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
        all_columns = cols_result.fetchall()

        type_filter_lower = {t.lower() for t in type_filter}
        candidates = []

        for col_name, data_type, is_nullable in all_columns:
            # Skip already-found constraint columns
            if col_name in exclude_columns:
                continue

            # Must be non-null
            if is_nullable == "YES":
                continue

            # Type filter check (empty filter = all types pass)
            if type_filter_lower and data_type.lower() not in type_filter_lower:
                continue

            # Check uniqueness: COUNT(DISTINCT col) vs COUNT(*) WHERE col IS NOT NULL
            uniq_query = text(f"""
                SELECT
                    COUNT(DISTINCT [{col_name}]) AS distinct_count,
                    COUNT(*) AS total_non_null
                FROM {self._qualified_table}
                WHERE [{col_name}] IS NOT NULL
            """)

            uniq_result = self.connection.execute(uniq_query)
            row = uniq_result.fetchall()
            if not row:
                continue

            distinct_count = row[0][0]
            total_non_null = row[0][1]

            is_unique = distinct_count == total_non_null and total_non_null > 0

            if not is_unique:
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
