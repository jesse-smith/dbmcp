"""Foreign key candidate search for data-exposure analysis.

Discovers potential FK relationships for a source column by:
1. Resolving target tables (with schema/table/pattern filters)
2. Collecting candidate columns (all or PK-only via PKDiscovery)
3. Gathering structural metadata (constraints, indexes, nullability)
4. Optional value overlap via SQL INTERSECT
5. Applying result limit

Returns FKCandidateResult with raw metadata only — no scoring or interpretation.
"""

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.analysis.pk_discovery import PKDiscovery
from src.models.analysis import FKCandidateData, FKCandidateResult


class FKCandidateSearch:
    """Search for FK candidates for a source column.

    Supports:
    - Target table filtering by schema, table list, or LIKE pattern
    - PK-only or all-column candidate matching
    - Structural metadata collection per candidate
    - Optional value overlap via SQL INTERSECT
    - Result limiting with was_limited flag
    """

    def __init__(
        self,
        connection: Connection,
        source_schema: str,
        source_table: str,
        source_column: str,
        source_data_type: str,
    ):
        self.connection = connection
        self.source_schema = source_schema
        self.source_table = source_table
        self.source_column = source_column
        self.source_data_type = source_data_type

    def get_target_tables(
        self,
        target_schema: str | None = None,
        target_tables: list[str] | None = None,
        target_table_pattern: str | None = None,
    ) -> list[tuple[str, str]]:
        """Resolve which target tables to search.

        Args:
            target_schema: Filter to this schema. Defaults to source schema.
            target_tables: Explicit list of table names.
            target_table_pattern: SQL LIKE pattern for table names.

        Returns:
            List of (schema_name, table_name) tuples, excluding source table.
        """
        schema = target_schema or self.source_schema

        if target_tables is not None:
            # Filter by explicit list
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME IN (SELECT value FROM STRING_SPLIT(:table_list, ','))
                    AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            params = {
                "schema_name": schema,
                "table_list": ",".join(target_tables),
            }
        elif target_table_pattern is not None:
            # Filter by LIKE pattern
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME LIKE :table_pattern
                    AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            params = {
                "schema_name": schema,
                "table_pattern": target_table_pattern,
            }
        else:
            # All tables in schema
            query = text("""
                SELECT TABLE_SCHEMA, TABLE_NAME
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_TYPE = 'BASE TABLE'
                ORDER BY TABLE_NAME
            """)
            params = {"schema_name": schema}

        result = self.connection.execute(query, params)
        tables = [(row[0], row[1]) for row in result.fetchall()]

        # Exclude source table
        tables = [
            (s, t) for s, t in tables
            if not (s == self.source_schema and t == self.source_table)
        ]

        return tables

    def get_candidate_columns(
        self,
        target_schema: str,
        target_table: str,
        pk_candidates_only: bool = True,
    ) -> list[dict]:
        """Get candidate columns from a target table.

        Args:
            target_schema: Target table schema.
            target_table: Target table name.
            pk_candidates_only: If True, only PK candidates. If False, all.

        Returns:
            List of dicts with column_name, data_type, is_nullable keys.
        """
        if pk_candidates_only:
            discovery = PKDiscovery(
                connection=self.connection,
                schema_name=target_schema,
                table_name=target_table,
            )
            pk_candidates = discovery.find_candidates()
            return [
                {
                    "column_name": c.column_name,
                    "data_type": c.data_type,
                    "is_nullable": not c.is_non_null,
                }
                for c in pk_candidates
            ]

        # All columns
        query = text("""
            SELECT COLUMN_NAME, DATA_TYPE, IS_NULLABLE
            FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = :schema_name
                AND TABLE_NAME = :table_name
            ORDER BY ORDINAL_POSITION
        """)
        result = self.connection.execute(
            query,
            {"schema_name": target_schema, "table_name": target_table},
        )
        return [
            {
                "column_name": row[0],
                "data_type": row[1],
                "is_nullable": row[2] == "YES",
            }
            for row in result.fetchall()
        ]

    def get_column_metadata(
        self,
        target_schema: str,
        target_table: str,
        target_column: str,
        target_data_type: str,
        target_is_nullable: bool,
    ) -> dict:
        """Collect structural metadata for a target column.

        Args:
            target_schema: Target schema name.
            target_table: Target table name.
            target_column: Target column name.
            target_data_type: Target column data type.
            target_is_nullable: Whether target column allows nulls.

        Returns:
            Dict with target_is_primary_key, target_is_unique,
            target_is_nullable, target_has_index.
        """
        # Check constraints (PK and UNIQUE)
        constraint_query = text("""
            SELECT tc.CONSTRAINT_TYPE
            FROM INFORMATION_SCHEMA.TABLE_CONSTRAINTS tc
            JOIN INFORMATION_SCHEMA.CONSTRAINT_COLUMN_USAGE ccu
                ON tc.CONSTRAINT_NAME = ccu.CONSTRAINT_NAME
                AND tc.TABLE_SCHEMA = ccu.TABLE_SCHEMA
            WHERE tc.TABLE_SCHEMA = :schema_name
                AND tc.TABLE_NAME = :table_name
                AND ccu.COLUMN_NAME = :column_name
                AND tc.CONSTRAINT_TYPE IN ('PRIMARY KEY', 'UNIQUE')
        """)
        constraint_result = self.connection.execute(
            constraint_query,
            {
                "schema_name": target_schema,
                "table_name": target_table,
                "column_name": target_column,
            },
        )
        constraint_rows = constraint_result.fetchall()

        is_primary_key = any(r[0] == "PRIMARY KEY" for r in constraint_rows)
        is_unique = any(
            r[0] in ("PRIMARY KEY", "UNIQUE") for r in constraint_rows
        )

        # Check indexes
        index_query = text("""
            SELECT i.name
            FROM sys.indexes i
            JOIN sys.index_columns ic ON i.object_id = ic.object_id
                AND i.index_id = ic.index_id
            JOIN sys.columns c ON ic.object_id = c.object_id
                AND ic.column_id = c.column_id
            JOIN sys.tables t ON i.object_id = t.object_id
            JOIN sys.schemas s ON t.schema_id = s.schema_id
            WHERE s.name = :schema_name
                AND t.name = :table_name
                AND c.name = :column_name
        """)
        index_result = self.connection.execute(
            index_query,
            {
                "schema_name": target_schema,
                "table_name": target_table,
                "column_name": target_column,
            },
        )
        has_index = len(index_result.fetchall()) > 0

        return {
            "target_is_primary_key": is_primary_key,
            "target_is_unique": is_unique,
            "target_is_nullable": target_is_nullable,
            "target_has_index": has_index,
        }

    def compute_overlap(
        self,
        target_schema: str,
        target_table: str,
        target_column: str,
    ) -> dict:
        """Compute value overlap between source and target columns.

        Uses SQL INTERSECT for exact count.

        Args:
            target_schema: Target schema name.
            target_table: Target table name.
            target_column: Target column name.

        Returns:
            Dict with overlap_count and overlap_percentage (None if
            source has zero distinct values).
        """
        source_table = f"[{self.source_schema}].[{self.source_table}]"
        target_table_q = f"[{target_schema}].[{target_table}]"

        # Get source distinct count
        src_count_query = text(f"""
            SELECT COUNT(DISTINCT [{self.source_column}])
            FROM {source_table}
            WHERE [{self.source_column}] IS NOT NULL
        """)
        src_result = self.connection.execute(src_count_query)
        src_distinct = src_result.fetchall()[0][0]

        if src_distinct == 0:
            return {"overlap_count": None, "overlap_percentage": None}

        # Count intersection via INTERSECT
        overlap_query = text(f"""
            SELECT COUNT(*) FROM (
                SELECT [{self.source_column}] FROM {source_table}
                    WHERE [{self.source_column}] IS NOT NULL
                INTERSECT
                SELECT [{target_column}] FROM {target_table_q}
                    WHERE [{target_column}] IS NOT NULL
            ) AS overlap
        """)
        overlap_result = self.connection.execute(overlap_query)
        overlap_count = overlap_result.fetchall()[0][0]

        overlap_percentage = (overlap_count / src_distinct) * 100.0

        return {
            "overlap_count": overlap_count,
            "overlap_percentage": round(overlap_percentage, 2),
        }

    def apply_limit(
        self,
        candidates: list[FKCandidateData],
        limit: int = 100,
    ) -> FKCandidateResult:
        """Apply limit to candidate list and build result wrapper.

        Args:
            candidates: Full list of candidates.
            limit: Max candidates to return. 0 = no limit.

        Returns:
            FKCandidateResult with limiting metadata.
        """
        total_found = len(candidates)

        if limit > 0 and total_found > limit:
            limited_candidates = candidates[:limit]
            was_limited = True
        else:
            limited_candidates = candidates
            was_limited = False

        return FKCandidateResult(
            candidates=limited_candidates,
            total_found=total_found,
            was_limited=was_limited,
            search_scope="",  # Set by caller
        )

    def build_search_scope(
        self,
        target_schema: str | None,
        target_tables: list[str] | None,
        target_table_pattern: str | None,
        pk_candidates_only: bool,
    ) -> str:
        """Build a human-readable search scope description.

        Args:
            target_schema: Target schema filter.
            target_tables: Target table list filter.
            target_table_pattern: Target table LIKE pattern.
            pk_candidates_only: Whether PK filter is active.

        Returns:
            Search scope description string.
        """
        parts = []
        schema = target_schema or self.source_schema
        parts.append(f"schema: {schema}")

        if target_tables:
            parts.append(f"tables: {', '.join(target_tables)}")
        if target_table_pattern:
            parts.append(f"pattern: {target_table_pattern}")

        parts.append(f"pk_candidates_only: {str(pk_candidates_only).lower()}")

        return ", ".join(parts)

    def find_candidates(
        self,
        target_schema: str | None = None,
        target_tables: list[str] | None = None,
        target_table_pattern: str | None = None,
        pk_candidates_only: bool = True,
        include_overlap: bool = False,
        limit: int = 100,
    ) -> FKCandidateResult:
        """Run full FK candidate search.

        Args:
            target_schema: Filter targets to this schema.
            target_tables: Explicit list of target table names.
            target_table_pattern: SQL LIKE pattern for target table names.
            pk_candidates_only: Only compare against PK-candidate columns.
            include_overlap: Compute value overlap metrics.
            limit: Maximum candidates to return (0 = no limit).

        Returns:
            FKCandidateResult with candidates and metadata.
        """
        # Step 1: Resolve target tables
        tables = self.get_target_tables(
            target_schema=target_schema,
            target_tables=target_tables,
            target_table_pattern=target_table_pattern,
        )

        # Step 2-4: For each target table, find candidates
        all_candidates: list[FKCandidateData] = []

        for tgt_schema, tgt_table in tables:
            columns = self.get_candidate_columns(
                target_schema=tgt_schema,
                target_table=tgt_table,
                pk_candidates_only=pk_candidates_only,
            )

            for col_info in columns:
                # Gather structural metadata
                metadata = self.get_column_metadata(
                    target_schema=tgt_schema,
                    target_table=tgt_table,
                    target_column=col_info["column_name"],
                    target_data_type=col_info["data_type"],
                    target_is_nullable=col_info["is_nullable"],
                )

                # Optional overlap
                overlap_count = None
                overlap_percentage = None
                if include_overlap:
                    overlap = self.compute_overlap(
                        target_schema=tgt_schema,
                        target_table=tgt_table,
                        target_column=col_info["column_name"],
                    )
                    overlap_count = overlap["overlap_count"]
                    overlap_percentage = overlap["overlap_percentage"]

                all_candidates.append(FKCandidateData(
                    source_column=self.source_column,
                    source_table=self.source_table,
                    source_schema=self.source_schema,
                    source_data_type=self.source_data_type,
                    target_column=col_info["column_name"],
                    target_table=tgt_table,
                    target_schema=tgt_schema,
                    target_data_type=col_info["data_type"],
                    target_is_primary_key=metadata["target_is_primary_key"],
                    target_is_unique=metadata["target_is_unique"],
                    target_is_nullable=metadata["target_is_nullable"],
                    target_has_index=metadata["target_has_index"],
                    overlap_count=overlap_count,
                    overlap_percentage=overlap_percentage,
                ))

        # Step 5: Apply limit
        result = self.apply_limit(all_candidates, limit=limit)

        # Set search scope
        result.search_scope = self.build_search_scope(
            target_schema=target_schema,
            target_tables=target_tables,
            target_table_pattern=target_table_pattern,
            pk_candidates_only=pk_candidates_only,
        )

        return result
