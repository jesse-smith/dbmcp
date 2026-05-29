"""Foreign key candidate search for data-exposure analysis.

Discovers potential FK relationships for a source column by:
1. Resolving target tables (with schema/table/pattern filters)
2. Collecting candidate columns (all or PK-only via PKDiscovery)
3. Gathering structural metadata (constraints, indexes, nullability)
4. Optional value overlap via SQL INTERSECT
5. Applying result limit

Returns FKCandidateResult with raw metadata only -- no scoring or interpretation.
"""

import fnmatch
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import Connection

from src.analysis._sql import CatalogAwareReflector, transpile_query
from src.analysis.pk_discovery import PKDiscovery
from src.models.analysis import FKCandidateData, FKCandidateResult

if TYPE_CHECKING:
    from sqlalchemy.engine import Inspector

    from src.db.dialects.protocol import DialectStrategy


class FKCandidateSearch:
    """Search for FK candidates for a source column.

    Supports:
    - Target table filtering by schema, table list, or LIKE pattern
    - PK-only or all-column candidate matching
    - Structural metadata collection per candidate
    - Optional value overlap via SQL INTERSECT
    - Result limiting with was_limited flag
    - Dialect-aware: Inspector for generic/Databricks, INFORMATION_SCHEMA for MSSQL
    """

    def __init__(
        self,
        connection: Connection,
        source_schema: str,
        source_table: str,
        source_column: str,
        source_data_type: str,
        dialect: "DialectStrategy | None" = None,
        inspector: "Inspector | None" = None,
        catalog: "str | None" = None,
    ):
        self.connection = connection
        self.source_schema = source_schema
        self.source_table = source_table
        self.source_column = source_column
        self.source_data_type = source_data_type
        self._dialect = dialect
        self._inspector = inspector
        self._catalog = catalog
        # Cross-catalog reads only apply to Databricks with an explicit catalog.
        # Other dialects reject catalog upstream (resolver), so this stays False.
        self._cross_catalog = (
            bool(catalog) and dialect is not None and dialect.name == "databricks"
        )

    def _use_inspector(self) -> bool:
        """Whether to use Inspector-based paths instead of MSSQL SQL."""
        return (
            self._inspector is not None
            and self._dialect is not None
            and self._dialect.name != "mssql"
        )

    def get_target_tables(
        self,
        target_schema: str | None = None,
        target_tables: list[str] | None = None,
        target_table_pattern: str | None = None,
    ) -> list[tuple[str, str]]:
        """Resolve which target tables to search.

        Uses Inspector for non-MSSQL dialects, INFORMATION_SCHEMA for MSSQL/None.

        Args:
            target_schema: Filter to this schema. Defaults to source schema.
            target_tables: Explicit list of table names.
            target_table_pattern: SQL LIKE pattern for table names.

        Returns:
            List of (schema_name, table_name) tuples, excluding source table.
        """
        schema = target_schema or self.source_schema

        if self._cross_catalog:
            return self._get_target_tables_cross_catalog(
                schema, target_tables, target_table_pattern
            )
        if self._use_inspector():
            return self._get_target_tables_inspector(
                schema, target_tables, target_table_pattern
            )
        return self._get_target_tables_mssql(
            schema, target_tables, target_table_pattern
        )

    def _get_target_tables_mssql(
        self,
        schema: str,
        target_tables: list[str] | None,
        target_table_pattern: str | None,
    ) -> list[tuple[str, str]]:
        """Use INFORMATION_SCHEMA for table listing (MSSQL/default)."""
        if target_tables is not None:
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

    def _get_target_tables_inspector(
        self,
        schema: str,
        target_tables: list[str] | None,
        target_table_pattern: str | None,
    ) -> list[tuple[str, str]]:
        """Use Inspector for table listing (generic/Databricks)."""
        all_table_names = self._inspector.get_table_names(schema=schema)

        if target_tables is not None:
            target_set = set(target_tables)
            table_names = [t for t in all_table_names if t in target_set]
        elif target_table_pattern is not None:
            # Convert SQL LIKE pattern to fnmatch glob pattern
            glob_pattern = target_table_pattern.replace("%", "*").replace("_", "?")
            table_names = [
                t for t in all_table_names if fnmatch.fnmatch(t, glob_pattern)
            ]
        else:
            table_names = all_table_names

        tables = [(schema, t) for t in sorted(table_names)]

        # Exclude source table
        tables = [
            (s, t) for s, t in tables
            if not (s == self.source_schema and t == self.source_table)
        ]

        return tables

    def _get_target_tables_cross_catalog(
        self,
        schema: str,
        target_tables: list[str] | None,
        target_table_pattern: str | None,
    ) -> list[tuple[str, str]]:
        """Enumerate target tables scoped to the resolved catalog (Pitfall 3).

        Open Q1 (KISS): cross-catalog FK targets are searched within the
        requested catalog ONLY -- never the connection default catalog. Table
        names come from a catalog-scoped ``SHOW TABLES IN catalog.schema`` via
        :class:`CatalogAwareReflector` (stateless; no catalog-switching statement
        is emitted). Client filtering (explicit list / LIKE pattern) mirrors the
        Inspector path.
        """
        reflector = CatalogAwareReflector(self.connection, self._dialect)
        all_table_names = reflector.list_tables(self._catalog, schema)

        if target_tables is not None:
            target_set = set(target_tables)
            table_names = [t for t in all_table_names if t in target_set]
        elif target_table_pattern is not None:
            # Convert SQL LIKE pattern to fnmatch glob pattern.
            glob_pattern = target_table_pattern.replace("%", "*").replace("_", "?")
            table_names = [
                t for t in all_table_names if fnmatch.fnmatch(t, glob_pattern)
            ]
        else:
            table_names = all_table_names

        tables = [(schema, t) for t in sorted(table_names)]

        # Exclude source table.
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
                dialect=self._dialect,
                inspector=self._inspector,
                catalog=self._catalog,
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

        # All columns: catalog-aware reflector on the cross-catalog branch.
        if self._cross_catalog:
            reflector = CatalogAwareReflector(self.connection, self._dialect)
            columns = reflector.reflect_columns(
                self._catalog, target_schema, target_table
            )
            # DESCRIBE TABLE does not expose nullability; treat as nullable so
            # no candidate is falsely excluded (mirrors PKDiscovery's contract).
            return [
                {
                    "column_name": c["name"],
                    "data_type": c["data_type"],
                    "is_nullable": True,
                }
                for c in columns
            ]

        # All columns: use Inspector for non-MSSQL, INFORMATION_SCHEMA for MSSQL
        if self._use_inspector():
            columns = self._inspector.get_columns(
                target_table, schema=target_schema
            )
            return [
                {
                    "column_name": c["name"],
                    "data_type": str(c["type"]),
                    "is_nullable": c.get("nullable", True),
                }
                for c in columns
            ]

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
        # Constraints: catalog-scoped information_schema on the cross-catalog
        # branch; Inspector for non-MSSQL; INFORMATION_SCHEMA for MSSQL.
        if self._cross_catalog:
            is_primary_key, is_unique = self._get_constraints_cross_catalog(
                target_schema, target_table, target_column
            )
        elif self._use_inspector():
            is_primary_key, is_unique = self._get_constraints_inspector(
                target_schema, target_table, target_column
            )
        else:
            is_primary_key, is_unique = self._get_constraints_mssql(
                target_schema, target_table, target_column
            )

        # Index check: gated by supports_indexes (D-13)
        has_index: bool | None = None
        if self._dialect is None or self._dialect.supports_indexes:
            if self._use_inspector():
                # Generic: Inspector.get_indexes()
                indexes = self._inspector.get_indexes(
                    target_table, schema=target_schema
                )
                has_index = any(
                    target_column in idx.get("column_names", [])
                    for idx in indexes
                )
            else:
                # MSSQL: sys.indexes DMV (existing query)
                has_index = self._check_index_mssql(
                    target_schema, target_table, target_column
                )
        # When supports_indexes=False (Databricks), has_index stays None

        return {
            "target_is_primary_key": is_primary_key,
            "target_is_unique": is_unique,
            "target_is_nullable": target_is_nullable,
            "target_has_index": has_index,
        }

    def _get_constraints_mssql(
        self, schema: str, table: str, column: str
    ) -> tuple[bool, bool]:
        """Use INFORMATION_SCHEMA for constraint checks (MSSQL/default)."""
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
                "schema_name": schema,
                "table_name": table,
                "column_name": column,
            },
        )
        constraint_rows = constraint_result.fetchall()

        is_primary_key = any(r[0] == "PRIMARY KEY" for r in constraint_rows)
        is_unique = any(
            r[0] in ("PRIMARY KEY", "UNIQUE") for r in constraint_rows
        )
        return is_primary_key, is_unique

    def _get_constraints_inspector(
        self, schema: str, table: str, column: str
    ) -> tuple[bool, bool]:
        """Use Inspector for constraint checks (generic/Databricks)."""
        pk_info = self._inspector.get_pk_constraint(table, schema=schema)
        is_primary_key = column in (pk_info.get("constrained_columns") or [])

        unique_constraints = self._inspector.get_unique_constraints(
            table, schema=schema
        )
        is_unique = is_primary_key or any(
            column in uc.get("column_names", [])
            for uc in unique_constraints
        )
        return is_primary_key, is_unique

    def _get_constraints_cross_catalog(
        self, schema: str, table: str, column: str
    ) -> tuple[bool, bool]:
        """Catalog-scoped PK/UNIQUE check via the requested catalog's
        ``information_schema`` (cross-catalog Databricks).

        The catalog segment is backtick-quoted via ``dialect.quote_identifier``
        (identifiers cannot be parameter-bound); schema/table/column are bound
        parameters. No catalog-switching statement is emitted -- the query is
        fully qualified and stateless over the pooled connection (T-15.1-07). Mirrors
        ``PKDiscovery._get_constraint_candidates_cross_catalog``.
        """
        qi = self._dialect.quote_identifier
        info_schema = f"{qi(self._catalog)}.information_schema"

        constraint_query = text(f"""
            SELECT tc.constraint_type
            FROM {info_schema}.table_constraints tc
            JOIN {info_schema}.key_column_usage kcu
                ON tc.constraint_name = kcu.constraint_name
                AND tc.table_schema = kcu.table_schema
                AND tc.table_name = kcu.table_name
            WHERE tc.table_schema = :schema_name
                AND tc.table_name = :table_name
                AND kcu.column_name = :column_name
                AND tc.constraint_type IN ('PRIMARY KEY', 'UNIQUE')
        """)
        result = self.connection.execute(
            constraint_query,
            {
                "schema_name": schema,
                "table_name": table,
                "column_name": column,
            },
        )
        rows = result.fetchall()

        is_primary_key = any(r[0] == "PRIMARY KEY" for r in rows)
        is_unique = any(r[0] in ("PRIMARY KEY", "UNIQUE") for r in rows)
        return is_primary_key, is_unique

    def _check_index_mssql(
        self, schema: str, table: str, column: str
    ) -> bool:
        """Use sys.indexes DMV for index check (MSSQL)."""
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
                "schema_name": schema,
                "table_name": table,
                "column_name": column,
            },
        )
        return len(index_result.fetchall()) > 0

    def compute_overlap(
        self,
        target_schema: str,
        target_table: str,
        target_column: str,
    ) -> dict:
        """Compute value overlap between source and target columns.

        Uses SQL INTERSECT for exact count. SQL is transpiled for non-MSSQL.

        Args:
            target_schema: Target schema name.
            target_table: Target table name.
            target_column: Target column name.

        Returns:
            Dict with overlap_count and overlap_percentage (None if
            source has zero distinct values).
        """
        # On the cross-catalog branch, both source and target references carry
        # the resolved catalog (3-part TSQL brackets -> `cat`.`sch`.`tbl` after
        # transpile_query). Never pre-quote with backticks (Pitfall 4); no
        # catalog-switching statement is emitted -- the names are stateless.
        if self._catalog:
            source_table = (
                f"[{self._catalog}].[{self.source_schema}].[{self.source_table}]"
            )
            target_table_q = (
                f"[{self._catalog}].[{target_schema}].[{target_table}]"
            )
        else:
            source_table = f"[{self.source_schema}].[{self.source_table}]"
            target_table_q = f"[{target_schema}].[{target_table}]"

        # Get source distinct count
        src_count_sql = f"""
            SELECT COUNT(DISTINCT [{self.source_column}])
            FROM {source_table}
            WHERE [{self.source_column}] IS NOT NULL
        """
        src_count_query = text(transpile_query(src_count_sql, self._dialect))
        src_result = self.connection.execute(src_count_query)
        src_row = src_result.fetchone()
        src_distinct = src_row[0] if src_row else 0

        if src_distinct == 0:
            return {"overlap_count": None, "overlap_percentage": None}

        # Count intersection via INTERSECT
        overlap_sql = f"""
            SELECT COUNT(*) FROM (
                SELECT [{self.source_column}] FROM {source_table}
                    WHERE [{self.source_column}] IS NOT NULL
                INTERSECT
                SELECT [{target_column}] FROM {target_table_q}
                    WHERE [{target_column}] IS NOT NULL
            ) AS overlap
        """
        overlap_query = text(transpile_query(overlap_sql, self._dialect))
        overlap_result = self.connection.execute(overlap_query)
        overlap_row = overlap_result.fetchone()
        overlap_count = overlap_row[0] if overlap_row else 0

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
