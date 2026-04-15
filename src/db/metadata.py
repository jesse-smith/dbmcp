"""Metadata service for database schema introspection.

This module provides methods for querying database metadata including
schemas, tables, columns, indexes, and foreign keys using SQLAlchemy inspector
and SQL Server system views (DMVs).

Performance logging (T105) tracks query times against NFR-001 (<30s for 1000 tables).
"""

import time
from datetime import datetime

# Avoid circular import at module level; use TYPE_CHECKING for annotations only.
from typing import TYPE_CHECKING

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError

from src.logging_config import get_logger
from src.models.schema import Column, Index, Schema, Table, TableType

if TYPE_CHECKING:
    from src.db.dialects.protocol import DialectStrategy

logger = get_logger(__name__)

# NFR-001: Metadata queries should complete within 30 seconds
NFR_001_THRESHOLD_MS = 30000


class MetadataService:
    """Service for querying database metadata.

    Uses SQLAlchemy inspector for cross-database compatibility, with
    optimized SQL Server DMV queries when available for performance
    with large databases (1000+ tables per NFR-001).

    Attributes:
        engine: SQLAlchemy engine for database connection
        inspector: SQLAlchemy inspector for metadata introspection
        dialect_name: Database dialect (e.g., 'mssql', 'sqlite', 'postgresql')
    """

    def __init__(self, engine: Engine, dialect: "DialectStrategy | None" = None):
        """Initialize metadata service.

        Args:
            engine: SQLAlchemy engine
            dialect: Optional dialect strategy. Auto-inferred from engine if None.
        """
        self.engine = engine
        self._inspector = None
        self.dialect_name = engine.dialect.name

        self._dialect: DialectStrategy | None
        if dialect is not None:
            self._dialect = dialect
        else:
            from src.db.dialects.registry import get_dialect
            try:
                dialect_cls = get_dialect(self.dialect_name)
                self._dialect = dialect_cls()
            except ValueError:
                self._dialect = None

    @property
    def inspector(self):
        """Lazily create inspector to avoid connection issues."""
        if self._inspector is None:
            self._inspector = inspect(self.engine)
        return self._inspector

    @property
    def is_mssql(self) -> bool:
        """Check if connected to SQL Server."""
        return self.dialect_name == "mssql"

    def list_schemas(self, connection_id: str = "", catalog: str | None = None) -> list[Schema]:
        """List all schemas with table and view counts.

        Uses SQL Server DMVs for efficiency when available, falls back to
        SQLAlchemy inspector for other databases.

        Args:
            connection_id: Optional connection ID for schema_id generation
            catalog: Optional Databricks catalog name. Overrides the connection's
                default catalog. Ignored for non-Databricks dialects.

        Returns:
            List of Schema objects sorted by table count descending
        """
        start_time = time.time()

        # Databricks with explicit catalog: use raw SQL for cross-catalog query
        if catalog and self._dialect and self._dialect.name == "databricks":
            result = self._list_schemas_databricks(connection_id, catalog)
        elif self._dialect and self._dialect.has_fast_row_counts:
            result = self._list_schemas_mssql(connection_id)
        else:
            result = self._list_schemas_generic(connection_id)

        # T105: Performance logging
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.debug(f"list_schemas completed in {elapsed_ms}ms, returned {len(result)} schemas")
        if elapsed_ms > NFR_001_THRESHOLD_MS:
            logger.warning(f"list_schemas exceeded NFR-001 threshold: {elapsed_ms}ms (>{NFR_001_THRESHOLD_MS}ms)")

        return result

    def _list_schemas_mssql(self, connection_id: str = "") -> list[Schema]:
        """SQL Server optimized schema listing using DMVs."""
        schemas = []

        with self.engine.connect() as conn:
            result = conn.execute(text("""
                SELECT
                    s.name AS schema_name,
                    COUNT(DISTINCT CASE WHEN t.type = 'U' THEN t.name END) AS table_count,
                    COUNT(DISTINCT CASE WHEN t.type = 'V' THEN t.name END) AS view_count
                FROM sys.schemas s
                LEFT JOIN sys.objects t ON s.schema_id = t.schema_id
                    AND t.type IN ('U', 'V')
                WHERE s.name NOT IN ('sys', 'INFORMATION_SCHEMA', 'guest')
                GROUP BY s.name
                HAVING COUNT(DISTINCT CASE WHEN t.type = 'U' THEN t.name END) > 0
                    OR COUNT(DISTINCT CASE WHEN t.type = 'V' THEN t.name END) > 0
                    OR s.name = 'dbo'
                ORDER BY table_count DESC, schema_name
            """))

            for row in result:
                schema_id = f"{connection_id}_{row.schema_name}" if connection_id else row.schema_name
                schemas.append(Schema(
                    schema_id=schema_id,
                    connection_id=connection_id,
                    schema_name=row.schema_name,
                    table_count=row.table_count or 0,
                    view_count=row.view_count or 0,
                    last_scanned=datetime.now(),
                ))

        logger.debug(f"Found {len(schemas)} schemas (SQL Server)")
        return schemas

    def _list_schemas_databricks(self, connection_id: str, catalog: str) -> list[Schema]:
        """Databricks schema listing using SHOW SCHEMAS IN for cross-catalog queries.

        All identifiers are backtick-quoted via dialect.quote_identifier() to prevent
        SQL injection (per T-11-04 security requirement).
        """
        schemas = []
        quoted_catalog = self._dialect.quote_identifier(catalog)

        with self.engine.connect() as conn:
            result = conn.execute(text(f"SHOW SCHEMAS IN {quoted_catalog}"))
            for row in result.fetchall():
                schema_name = row[0]
                schema_id = f"{connection_id}_{schema_name}" if connection_id else schema_name
                schemas.append(Schema(
                    schema_id=schema_id,
                    connection_id=connection_id,
                    schema_name=schema_name,
                    table_count=0,  # Not available from SHOW SCHEMAS
                    view_count=0,
                    last_scanned=datetime.now(),
                ))

        logger.debug(f"Found {len(schemas)} schemas (Databricks catalog={catalog})")
        return schemas

    def _list_schemas_generic(self, connection_id: str = "") -> list[Schema]:
        """Generic schema listing using SQLAlchemy inspector."""
        schemas = []
        schema_data: dict[str, dict] = {}

        # Get schema names from inspector
        try:
            schema_names = self.inspector.get_schema_names()
        except SQLAlchemyError:
            # Some databases don't support schema introspection
            schema_names = [None]  # Use default schema

        for schema_name in schema_names:
            # Skip system schemas
            if schema_name in ("information_schema", "pg_catalog", "pg_toast"):
                continue

            # For SQLite, schema_name is None or 'main'
            display_name = schema_name or "main"

            try:
                tables = self.inspector.get_table_names(schema=schema_name)
                views = self.inspector.get_view_names(schema=schema_name)
            except SQLAlchemyError:
                tables = []
                views = []

            if tables or views or display_name in ("main", "dbo", "public"):
                schema_data[display_name] = {
                    "table_count": len(tables),
                    "view_count": len(views),
                }

        # Sort by table count descending
        for schema_name in sorted(schema_data.keys(), key=lambda k: -schema_data[k]["table_count"]):
            data = schema_data[schema_name]
            schema_id = f"{connection_id}_{schema_name}" if connection_id else schema_name
            schemas.append(Schema(
                schema_id=schema_id,
                connection_id=connection_id,
                schema_name=schema_name,
                table_count=data["table_count"],
                view_count=data["view_count"],
                last_scanned=datetime.now(),
            ))

        logger.debug(f"Found {len(schemas)} schemas (generic)")
        return schemas

    def list_tables(
        self,
        schema_name: str | None = None,
        name_pattern: str | None = None,
        min_row_count: int | None = None,
        sort_by: str = "row_count",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        object_type: str | None = None,
        connection_id: str = "",
        catalog: str | None = None,
    ) -> tuple[list[Table], dict]:
        """List tables with row counts and metadata.

        Uses SQL Server DMVs for efficiency when available, falls back to
        SQLAlchemy inspector for other databases.

        Args:
            schema_name: Filter by schema (None = all schemas)
            name_pattern: SQL LIKE pattern for table name filter
            min_row_count: Minimum row count threshold
            sort_by: Sort criterion ('name', 'row_count', 'last_modified')
            sort_order: Sort order ('asc', 'desc')
            limit: Maximum tables to return (1-1000)
            offset: Number of tables to skip for pagination (T132)
            object_type: Filter by type - 'table', 'view', or None for all (T133)
            connection_id: Connection ID for table_id generation
            catalog: Optional Databricks catalog name. Overrides the connection's
                default catalog. Ignored for non-Databricks dialects.

        Returns:
            Tuple of (List of Table objects, pagination metadata dict)
            Pagination metadata includes: total_count, offset, limit, has_more
        """
        start_time = time.time()

        # Databricks with explicit catalog: use raw SQL for cross-catalog query
        if catalog and self._dialect and self._dialect.name == "databricks":
            result, pagination = self._list_tables_databricks(
                schema_name or "default", catalog, name_pattern,
                sort_by, sort_order, limit, offset, connection_id
            )
        elif self._dialect and self._dialect.has_fast_row_counts:
            result, pagination = self._list_tables_mssql(
                schema_name, name_pattern, min_row_count,
                sort_by, sort_order, limit, offset, object_type, connection_id
            )
        else:
            result, pagination = self._list_tables_generic(
                schema_name, name_pattern, min_row_count,
                sort_by, sort_order, limit, offset, object_type, connection_id
            )

        # T105: Performance logging
        elapsed_ms = int((time.time() - start_time) * 1000)
        logger.debug(f"list_tables completed in {elapsed_ms}ms, returned {len(result)} tables")
        if elapsed_ms > NFR_001_THRESHOLD_MS:
            logger.warning(f"list_tables exceeded NFR-001 threshold: {elapsed_ms}ms (>{NFR_001_THRESHOLD_MS}ms)")

        return result, pagination

    @staticmethod
    def _matches_name_pattern(name: str, name_pattern: str | None) -> bool:
        """Check if a name matches a SQL LIKE pattern (converted to fnmatch)."""
        if not name_pattern:
            return True
        import fnmatch
        pattern = name_pattern.replace("%", "*").replace("_", "?")
        return fnmatch.fnmatch(name, pattern)

    def _list_tables_databricks(
        self,
        schema_name: str,
        catalog: str,
        name_pattern: str | None,
        sort_by: str,
        sort_order: str,
        limit: int,
        offset: int,
        connection_id: str,
    ) -> tuple[list[Table], dict]:
        """Databricks table listing using SHOW TABLES IN for cross-catalog queries.

        All identifiers are backtick-quoted via dialect.quote_identifier() to prevent
        SQL injection (per T-11-04 security requirement).
        """
        tables: list[Table] = []
        quoted_catalog = self._dialect.quote_identifier(catalog)
        quoted_schema = self._dialect.quote_identifier(schema_name)

        with self.engine.connect() as conn:
            result = conn.execute(
                text(f"SHOW TABLES IN {quoted_catalog}.{quoted_schema}")
            )
            for row in result.fetchall():
                # SHOW TABLES returns (database, tableName, isTemporary)
                table_name = row[1] if len(row) > 1 else row[0]

                if not self._matches_name_pattern(table_name, name_pattern):
                    continue

                table_id = f"{catalog}.{schema_name}.{table_name}"
                tables.append(Table(
                    table_id=table_id,
                    schema_id=schema_name,
                    table_name=table_name,
                    table_type=TableType.TABLE,
                    row_count=None,  # Not available from SHOW TABLES
                    row_count_updated=datetime.now(),
                    has_primary_key=False,
                    last_modified=None,
                    access_denied=False,
                ))

        # Sort
        reverse = sort_order.lower() == "desc"
        if sort_by == "name":
            tables.sort(key=lambda t: t.table_name, reverse=reverse)

        # Pagination
        total_count = len(tables)
        effective_limit = min(max(limit, 1), 1000)
        effective_offset = max(offset, 0)
        tables = tables[effective_offset:effective_offset + effective_limit]

        pagination = {
            "total_count": total_count,
            "offset": effective_offset,
            "limit": effective_limit,
            "has_more": (effective_offset + len(tables)) < total_count,
        }

        logger.debug(f"Found {len(tables)} tables (Databricks catalog={catalog}.{schema_name})")
        return tables, pagination

    def _collect_objects_from_schema(
        self,
        schema: str | None,
        table_type: TableType,
        name_pattern: str | None,
        min_row_count: int | None,
        catalog: str | None = None,
    ) -> list[Table]:
        """Collect tables or views from a single schema.

        Args:
            schema: Schema name (None for default schema)
            table_type: TABLE or VIEW
            name_pattern: SQL LIKE pattern for name filtering
            min_row_count: Minimum row count threshold (tables only)
            catalog: Optional catalog for three-level Databricks table IDs (D-11)

        Returns:
            List of matching Table objects
        """
        display_schema = schema or "main"
        is_table = table_type == TableType.TABLE

        if is_table:
            names = self.inspector.get_table_names(schema=schema)
        else:
            names = self.inspector.get_view_names(schema=schema)

        # Determine table_id format: three-level for Databricks, two-level otherwise
        use_three_level = (
            catalog is not None
            and self._dialect is not None
            and self._dialect.name == "databricks"
        )

        results: list[Table] = []
        for name in names:
            if not self._matches_name_pattern(name, name_pattern):
                continue

            row_count = self._get_row_count_generic(name, schema) if is_table else None

            if min_row_count is not None and (row_count or 0) < min_row_count:
                continue

            has_pk = self._has_primary_key(name, schema) if is_table else False

            if use_three_level:
                table_id = f"{catalog}.{display_schema}.{name}"
            else:
                table_id = f"{display_schema}.{name}"

            results.append(Table(
                table_id=table_id,
                schema_id=display_schema,
                table_name=name,
                table_type=table_type,
                row_count=row_count,
                row_count_updated=datetime.now(),
                has_primary_key=has_pk,
                last_modified=None,
                access_denied=False,
            ))

        return results

    def _has_primary_key(self, table_name: str, schema: str | None) -> bool:
        """Check if a table has a primary key constraint."""
        try:
            pk = self.inspector.get_pk_constraint(table_name, schema=schema)
            return bool(pk.get("constrained_columns"))
        except SQLAlchemyError:
            return False

    def _list_tables_generic(
        self,
        schema_name: str | None = None,
        name_pattern: str | None = None,
        min_row_count: int | None = None,
        sort_by: str = "row_count",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        object_type: str | None = None,
        connection_id: str = "",
    ) -> tuple[list[Table], dict]:
        """Generic table listing using SQLAlchemy inspector."""
        tables: list[Table] = []

        # Determine schema to query
        if schema_name:
            schemas_to_check = [schema_name if schema_name != "main" else None]
        else:
            try:
                schemas_to_check = self.inspector.get_schema_names()
            except SQLAlchemyError:
                schemas_to_check = [None]

        # T133: Determine which object types to collect
        types_to_collect: list[TableType] = []
        if object_type is None or object_type == "table":
            types_to_collect.append(TableType.TABLE)
        if object_type is None or object_type == "view":
            types_to_collect.append(TableType.VIEW)

        for schema in schemas_to_check:
            for table_type in types_to_collect:
                try:
                    tables.extend(self._collect_objects_from_schema(
                        schema, table_type, name_pattern, min_row_count,
                    ))
                except SQLAlchemyError:
                    pass

        # Sort tables
        reverse = sort_order.lower() == "desc"
        if sort_by == "name":
            tables.sort(key=lambda t: t.table_name, reverse=reverse)
        elif sort_by == "row_count":
            tables.sort(key=lambda t: t.row_count or 0, reverse=reverse)
        # last_modified not available in generic mode

        # T132: Pagination support
        total_count = len(tables)
        effective_limit = min(max(limit, 1), 1000)
        effective_offset = max(offset, 0)

        # Apply offset and limit
        tables = tables[effective_offset:effective_offset + effective_limit]

        pagination = {
            "total_count": total_count,
            "offset": effective_offset,
            "limit": effective_limit,
            "has_more": (effective_offset + len(tables)) < total_count,
        }

        logger.debug(f"Found {len(tables)} tables (generic), total: {total_count}")
        return tables, pagination

    def _get_row_count_generic(self, table_name: str, schema: str | None) -> int | None:
        """Get row count for a table using COUNT(*)."""
        try:
            # Build qualified table name
            if schema and schema != "main":
                qualified_name = f'"{schema}"."{table_name}"'
            else:
                qualified_name = f'"{table_name}"'

            with self.engine.connect() as conn:
                result = conn.execute(text(f"SELECT COUNT(*) FROM {qualified_name}"))
                row = result.fetchone()
                return row[0] if row else None
        except SQLAlchemyError as e:
            logger.debug(f"Could not get row count for {table_name}: {type(e).__name__}: {e}")
            return None

    def _list_tables_mssql(
        self,
        schema_name: str | None = None,
        name_pattern: str | None = None,
        min_row_count: int | None = None,
        sort_by: str = "row_count",
        sort_order: str = "desc",
        limit: int = 100,
        offset: int = 0,
        object_type: str | None = None,
        connection_id: str = "",
    ) -> tuple[list[Table], dict]:
        """SQL Server optimized table listing using DMVs."""
        tables = []

        # T133: Object type filtering - 'U' = user table, 'V' = view
        type_filter_map = {"table": ["'U'"], "view": ["'V'"]}
        type_filter = type_filter_map.get(object_type, ["'U'", "'V'"])

        # Build dynamic SQL for filtering
        where_clauses = [f"t.type IN ({', '.join(type_filter)})"]
        params: dict = {}

        if schema_name:
            where_clauses.append("s.name = :schema_name")
            params["schema_name"] = schema_name

        if name_pattern:
            where_clauses.append("t.name LIKE :name_pattern")
            params["name_pattern"] = name_pattern

        where_sql = " AND ".join(where_clauses)

        # Build ORDER BY clause
        sort_column_map = {
            "name": "t.name",
            "row_count": "ISNULL(row_counts.row_count, 0)",
            "last_modified": "t.modify_date",
        }
        sort_column = sort_column_map.get(sort_by, "ISNULL(row_counts.row_count, 0)")
        order_direction = "DESC" if sort_order.lower() == "desc" else "ASC"

        # T132: First get total count for pagination
        # Must include row_counts join and min_row_count filter to match the data query
        count_query = text(f"""
            WITH row_counts AS (
                SELECT
                    object_id,
                    SUM(CASE WHEN index_id IN (0, 1) THEN row_count ELSE 0 END) AS row_count
                FROM sys.dm_db_partition_stats
                GROUP BY object_id
            )
            SELECT COUNT(*) AS total_count
            FROM sys.objects t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            LEFT JOIN row_counts ON t.object_id = row_counts.object_id
            WHERE {where_sql}
            {"AND ISNULL(row_counts.row_count, 0) >= :min_row_count" if min_row_count else ""}
        """)

        effective_limit = min(max(limit, 1), 1000)
        effective_offset = max(offset, 0)

        # T132: Use OFFSET/FETCH for pagination (SQL Server 2012+)
        query = text(f"""
            WITH row_counts AS (
                SELECT
                    object_id,
                    SUM(CASE WHEN index_id IN (0, 1) THEN row_count ELSE 0 END) AS row_count
                FROM sys.dm_db_partition_stats
                GROUP BY object_id
            )
            SELECT
                s.name AS schema_name,
                t.name AS table_name,
                t.type AS object_type,
                ISNULL(row_counts.row_count, 0) AS row_count,
                t.modify_date AS last_modified,
                CASE WHEN pk.object_id IS NOT NULL THEN 1 ELSE 0 END AS has_primary_key
            FROM sys.objects t
            INNER JOIN sys.schemas s ON t.schema_id = s.schema_id
            LEFT JOIN row_counts ON t.object_id = row_counts.object_id
            LEFT JOIN (
                SELECT DISTINCT parent_object_id AS object_id
                FROM sys.key_constraints
                WHERE type = 'PK'
            ) pk ON t.object_id = pk.object_id
            WHERE {where_sql}
            {"AND ISNULL(row_counts.row_count, 0) >= :min_row_count" if min_row_count else ""}
            ORDER BY {sort_column} {order_direction}
            OFFSET :offset ROWS FETCH NEXT :limit ROWS ONLY
        """)

        params["limit"] = effective_limit
        params["offset"] = effective_offset
        if min_row_count:
            params["min_row_count"] = min_row_count

        with self.engine.connect() as conn:
            # Get total count
            count_result = conn.execute(count_query, params)
            total_count = count_result.fetchone()[0]

            # Get paginated results
            result = conn.execute(query, params)

            for row in result:
                table_id = f"{row.schema_name}.{row.table_name}"
                # T133: Determine table type from object type
                table_type = TableType.VIEW if row.object_type == "V " else TableType.TABLE

                tables.append(Table(
                    table_id=table_id,
                    schema_id=row.schema_name,
                    table_name=row.table_name,
                    table_type=table_type,
                    row_count=row.row_count if table_type == TableType.TABLE else None,
                    row_count_updated=datetime.now(),
                    has_primary_key=bool(row.has_primary_key),
                    last_modified=row.last_modified,
                    access_denied=False,
                ))

        # T132: Build pagination metadata
        pagination = {
            "total_count": total_count,
            "offset": effective_offset,
            "limit": effective_limit,
            "has_more": (effective_offset + len(tables)) < total_count,
        }

        logger.debug(f"Found {len(tables)} tables, total: {total_count}")
        return tables, pagination

    def get_columns(self, table_name: str, schema_name: str = "dbo") -> list[Column]:
        """Get column metadata for a table.

        Uses SQLAlchemy inspector for portable column introspection.

        Args:
            table_name: Table name
            schema_name: Schema name (default: 'dbo')

        Returns:
            List of Column objects
        """
        columns = []
        table_id = f"{schema_name}.{table_name}"

        try:
            inspector_columns = self.inspector.get_columns(table_name, schema=schema_name)
            pk_constraint = self.inspector.get_pk_constraint(table_name, schema=schema_name)
            pk_columns = set(pk_constraint.get("constrained_columns", []))

            # Get FK columns
            fks = self.inspector.get_foreign_keys(table_name, schema=schema_name)
            fk_columns = set()
            for fk in fks:
                fk_columns.update(fk.get("constrained_columns", []))

            for idx, col in enumerate(inspector_columns, start=1):
                column_id = f"{table_id}.{col['name']}"
                data_type = str(col["type"])

                columns.append(Column(
                    column_id=column_id,
                    table_id=table_id,
                    column_name=col["name"],
                    ordinal_position=idx,
                    data_type=data_type,
                    max_length=getattr(col["type"], "length", None),
                    is_nullable=col.get("nullable", True),
                    default_value=str(col.get("default")) if col.get("default") else None,
                    is_identity=col.get("autoincrement", False),
                    is_computed=col.get("computed", False),
                    is_primary_key=col["name"] in pk_columns,
                    is_foreign_key=col["name"] in fk_columns,
                ))

        except SQLAlchemyError as e:
            logger.warning(f"Error getting columns for {schema_name}.{table_name}: {type(e).__name__}: {e}")

        return columns

    def get_indexes(self, table_name: str, schema_name: str = "dbo") -> list[Index]:
        """Get index metadata for a table.

        Args:
            table_name: Table name
            schema_name: Schema name (default: 'dbo')

        Returns:
            List of Index objects
        """
        indexes = []
        table_id = f"{schema_name}.{table_name}"

        try:
            inspector_indexes = self.inspector.get_indexes(table_name, schema=schema_name)
            pk_constraint = self.inspector.get_pk_constraint(table_name, schema=schema_name)
            pk_name = pk_constraint.get("name")

            for idx in inspector_indexes:
                index_id = f"{table_id}.{idx['name']}"
                indexes.append(Index(
                    index_id=index_id,
                    table_id=table_id,
                    index_name=idx["name"],
                    is_unique=idx.get("unique", False),
                    is_primary_key=idx["name"] == pk_name if pk_name else False,
                    is_clustered=idx.get("clustered", False),
                    columns=idx.get("column_names", []),
                    included_columns=idx.get("include_columns", []) or [],
                ))

        except SQLAlchemyError as e:
            logger.warning(f"Error getting indexes for {schema_name}.{table_name}: {type(e).__name__}: {e}")

        return indexes

    def get_foreign_keys(self, table_name: str, schema_name: str = "dbo") -> list[dict]:
        """Get declared foreign key relationships for a table.

        Args:
            table_name: Table name
            schema_name: Schema name (default: 'dbo')

        Returns:
            List of foreign key dictionaries
        """
        try:
            return self.inspector.get_foreign_keys(table_name, schema=schema_name)
        except SQLAlchemyError as e:
            logger.warning(f"Error getting foreign keys for {schema_name}.{table_name}: {type(e).__name__}: {e}")
            return []

    def get_primary_key(self, table_name: str, schema_name: str = "dbo") -> dict:
        """Get primary key constraint for a table.

        Args:
            table_name: Table name
            schema_name: Schema name (default: 'dbo')

        Returns:
            Primary key constraint dictionary
        """
        try:
            return self.inspector.get_pk_constraint(table_name, schema=schema_name)
        except SQLAlchemyError as e:
            logger.warning(f"Error getting primary key for {schema_name}.{table_name}: {type(e).__name__}: {e}")
            return {}

    def get_table_schema(
        self,
        table_name: str,
        schema_name: str = "dbo",
        include_indexes: bool = True,
        include_relationships: bool = True,
        catalog: str | None = None,
    ) -> dict:
        """Get complete table schema including columns, indexes, and FKs.

        Combines metadata into a structured response for the MCP tool.

        Args:
            table_name: Table name
            schema_name: Schema name (default: 'dbo')
            include_indexes: Include index information
            include_relationships: Include declared foreign keys
            catalog: Optional Databricks catalog name. Overrides the connection's
                default catalog. Ignored for non-Databricks dialects.

        Returns:
            Dictionary with complete table metadata
        """
        columns = self.get_columns(table_name, schema_name)

        result = {
            "table_name": table_name,
            "schema_name": schema_name,
            "columns": [
                {
                    "column_name": col.column_name,
                    "ordinal_position": col.ordinal_position,
                    "data_type": col.data_type,
                    "max_length": col.max_length,
                    "is_nullable": col.is_nullable,
                    "default_value": col.default_value,
                    "is_identity": col.is_identity,
                    "is_computed": col.is_computed,
                    "is_primary_key": col.is_primary_key,
                    "is_foreign_key": col.is_foreign_key,
                }
                for col in columns
            ],
        }

        # D-13: Gate index section on dialect.supports_indexes
        # When supports_indexes is False, "indexes" key is absent entirely
        if include_indexes and (not self._dialect or self._dialect.supports_indexes):
            indexes = self.get_indexes(table_name, schema_name)
            result["indexes"] = [
                {
                    "index_name": idx.index_name,
                    "is_unique": idx.is_unique,
                    "is_primary_key": idx.is_primary_key,
                    "is_clustered": idx.is_clustered,
                    "columns": idx.columns,
                    "included_columns": idx.included_columns,
                }
                for idx in indexes
            ]

        if include_relationships:
            fks = self.get_foreign_keys(table_name, schema_name)
            result["foreign_keys"] = [
                {
                    "constraint_name": fk.get("name"),
                    "source_columns": fk.get("constrained_columns", []),
                    "target_schema": fk.get("referred_schema", "dbo"),
                    "target_table": fk.get("referred_table"),
                    "target_columns": fk.get("referred_columns", []),
                }
                for fk in fks
            ]

        # Databricks-specific table properties via DESCRIBE EXTENDED (D-07)
        if self._dialect and self._dialect.name == "databricks":
            dte_catalog = catalog or "main"  # Fall back to default catalog
            dte_props = self._parse_databricks_table_properties(
                table_name, schema_name, dte_catalog
            )
            # Optionally log or surface error to user
            if "_describe_extended_error" in dte_props:
                logger.debug(f"Could not retrieve extended properties: {dte_props['_describe_extended_error']}")
                dte_props.pop("_describe_extended_error")  # Don't include in response
            # Merge DTE properties into result (only present keys)
            result.update(dte_props)
            # Add catalog to response for Databricks (D-11)
            if catalog:
                result["catalog"] = catalog

        return result

    def _parse_databricks_table_properties(
        self, table_name: str, schema_name: str, catalog: str
    ) -> dict:
        """Parse DESCRIBE TABLE EXTENDED for Databricks-specific properties.

        Returns dict with optional keys: owner, storage_format, table_type_detail,
        created_time, location, partition_columns. On failure, returns dict with
        '_describe_extended_error' key containing error message.

        All identifiers are backtick-quoted via dialect.quote_identifier() to
        prevent SQL injection (T-11-04).

        Args:
            table_name: Table name
            schema_name: Schema name
            catalog: Catalog name

        Returns:
            Dictionary of parsed properties. Dict with '_describe_extended_error' key on failure.
        """
        try:
            quoted_catalog = self._dialect.quote_identifier(catalog)
            quoted_schema = self._dialect.quote_identifier(schema_name)
            quoted_table = self._dialect.quote_identifier(table_name)
            qualified = f"{quoted_catalog}.{quoted_schema}.{quoted_table}"

            with self.engine.connect() as conn:
                result = conn.execute(text(f"DESCRIBE TABLE EXTENDED {qualified}"))
                rows = result.fetchall()

            props: dict = {}
            partition_cols: list[str] = []
            in_partition_section = False
            in_detail_section = False

            for row in rows:
                col_name = (row[0] or "").strip()
                data_type = (row[1] or "").strip() if len(row) > 1 else ""

                # Section markers
                if col_name.startswith("# Partition Information"):
                    in_partition_section = True
                    in_detail_section = False
                    continue
                elif col_name.startswith("# Detailed Table Information"):
                    in_partition_section = False
                    in_detail_section = True
                    continue
                elif col_name.startswith("#"):
                    continue  # Skip header rows
                elif not col_name and not data_type:
                    in_partition_section = False
                    # Don't reset detail section -- it continues to end
                    continue

                if in_partition_section and col_name:
                    partition_cols.append(col_name)

                if in_detail_section:
                    key_map = {
                        "Owner": "owner",
                        "Provider": "storage_format",
                        "Type": "table_type_detail",
                        "Created Time": "created_time",
                        "Location": "location",
                    }
                    if col_name in key_map:
                        props[key_map[col_name]] = data_type

            if partition_cols:
                props["partition_columns"] = partition_cols

            return props

        except Exception as e:
            # T-11-06: Never let DTE parsing failure break get_table_schema
            error_msg = f"{type(e).__name__}: {e}"
            logger.warning(
                f"Failed to parse DESCRIBE EXTENDED for {catalog}.{schema_name}.{table_name}: {error_msg}"
            )
            # Return error indicator so caller can optionally surface it
            return {"_describe_extended_error": error_msg}

    def table_exists(self, table_name: str, schema_name: str = "dbo") -> bool:
        """Check if a table exists.

        Args:
            table_name: Table name
            schema_name: Schema name

        Returns:
            True if table exists
        """
        try:
            tables = self.inspector.get_table_names(schema=schema_name)
            return table_name in tables
        except SQLAlchemyError:
            return False
