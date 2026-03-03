"""MCP tools for data-exposure analysis.

Provides three analysis tools:
- get_column_info: Per-column statistical profiles
- find_pk_candidates: Primary key candidate discovery
- find_fk_candidates: Foreign key candidate search

All tools expose raw statistics and structural metadata only — no interpretation.
"""

import json

from sqlalchemy import text

from src.analysis.column_stats import ColumnStatsCollector
from src.analysis.fk_candidates import FKCandidateSearch
from src.analysis.pk_discovery import PKDiscovery
from src.mcp_server.server import get_connection_manager, mcp


@mcp.tool()
async def get_column_info(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo",
    columns: list[str] | None = None,
    column_pattern: str | None = None,
    sample_size: int = 10,
) -> str:
    """Retrieve per-column statistical profiles for a table.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Table name to analyze
        schema_name: Schema name (default: 'dbo')
        columns: Explicit list of column names to analyze (takes precedence over pattern)
        column_pattern: SQL LIKE pattern to filter column names (e.g., '%_id')
        sample_size: Number of top frequent value samples for string columns (default: 10)

    Returns:
        JSON string with status, table/schema metadata, and column statistics

    Error conditions:
        - Invalid connection_id: {"status": "error", "error_message": "Connection '...' not found"}
        - Table not found: {"status": "error", "error_message": "Table '...' not found in schema '...'"}
        - Column not found (explicit list): {"status": "error", "error_message": "Column(s) not found: ..."}
        - No columns match pattern: {"status": "success", "columns": [], "total_columns_analyzed": 0}
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)

        with engine.connect() as connection:
            # Verify table exists
            table_exists_query = text("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME = :table_name
            """)
            result = connection.execute(
                table_exists_query,
                {"schema_name": schema_name, "table_name": table_name}
            )
            if result.scalar() == 0:
                return json.dumps({
                    "status": "error",
                    "error_message": f"Table '{table_name}' not found in schema '{schema_name}'",
                })

            # Create collector and gather statistics
            collector = ColumnStatsCollector(
                connection=connection,
                schema_name=schema_name,
                table_name=table_name,
            )

            column_stats = collector.get_columns_info(
                columns=columns,
                column_pattern=column_pattern,
                sample_size=sample_size,
            )

            # Build response
            response = {
                "status": "success",
                "table_name": table_name,
                "schema_name": schema_name,
                "total_columns_analyzed": len(column_stats),
                "columns": [stat.to_dict() for stat in column_stats],
            }

            return json.dumps(response, default=str)

    except ValueError as e:
        return json.dumps({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error_message": f"Unexpected error: {str(e)}",
        })


@mcp.tool()
async def find_pk_candidates(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo",
    type_filter: list[str] | None = None,
) -> str:
    """Identify columns that meet primary key candidacy criteria.

    Discovers PK candidates via two approaches:
    1. Constraint-backed: Columns with PK or UNIQUE constraints
    2. Structural: Columns that are unique, non-null, and match the type filter

    Args:
        connection_id: Connection ID from connect_database
        table_name: Table to search for PK candidates
        schema_name: Schema name (default: 'dbo')
        type_filter: SQL types considered for structural PK candidacy.
            Default: ["int", "bigint", "smallint", "tinyint", "uniqueidentifier"].
            Set to empty list to disable type filtering.

    Returns:
        JSON string with status, table/schema metadata, and candidates list

    Error conditions:
        - Invalid connection_id: {"status": "error", "error_message": "Connection '...' not found"}
        - Table not found: {"status": "error", "error_message": "Table '...' not found in schema '...'"}
        - No candidates found: {"status": "success", "candidates": []} (not an error)
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)

        with engine.connect() as connection:
            # Verify table exists
            table_exists_query = text("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME = :table_name
            """)
            result = connection.execute(
                table_exists_query,
                {"schema_name": schema_name, "table_name": table_name},
            )
            if result.scalar() == 0:
                return json.dumps({
                    "status": "error",
                    "error_message": f"Table '{table_name}' not found in schema '{schema_name}'",
                })

            discovery = PKDiscovery(
                connection=connection,
                schema_name=schema_name,
                table_name=table_name,
            )

            candidates = discovery.find_candidates(type_filter=type_filter)

            response = {
                "status": "success",
                "table_name": table_name,
                "schema_name": schema_name,
                "candidates": [c.to_dict() for c in candidates],
            }

            return json.dumps(response)

    except ValueError as e:
        return json.dumps({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error_message": f"Unexpected error: {str(e)}",
        })


@mcp.tool()
async def find_fk_candidates(
    connection_id: str,
    table_name: str,
    column_name: str,
    schema_name: str = "dbo",
    target_schema: str | None = None,
    target_tables: list[str] | None = None,
    target_table_pattern: str | None = None,
    pk_candidates_only: bool = True,
    include_overlap: bool = False,
    limit: int = 100,
) -> str:
    """Discover potential foreign key relationships for a source column.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Source table name
        column_name: Source column name
        schema_name: Source schema name (default: 'dbo')
        target_schema: Filter targets to this schema. Defaults to source schema.
        target_tables: Explicit list of target table names
        target_table_pattern: SQL LIKE pattern for target table names
        pk_candidates_only: Only compare against PK-candidate columns (default: True)
        include_overlap: Compute value overlap metrics (default: False)
        limit: Maximum candidates to return, 0 = no limit (default: 100)

    Returns:
        JSON string with status, source metadata, candidates list, and search info

    Error conditions:
        - Invalid connection_id: {"status": "error", "error_message": "Connection '...' not found"}
        - Table not found: {"status": "error", "error_message": "Table '...' not found in schema '...'"}
        - Column not found: {"status": "error", "error_message": "Column '...' not found in table '...'"}
        - No candidates: {"status": "success", "candidates": [], "total_found": 0} (not an error)
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)

        with engine.connect() as connection:
            # Verify table exists
            table_exists_query = text("""
                SELECT COUNT(*)
                FROM INFORMATION_SCHEMA.TABLES
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME = :table_name
            """)
            result = connection.execute(
                table_exists_query,
                {"schema_name": schema_name, "table_name": table_name},
            )
            if result.scalar() == 0:
                return json.dumps({
                    "status": "error",
                    "error_message": f"Table '{table_name}' not found in schema '{schema_name}'",
                })

            # Verify column exists and get data type
            col_query = text("""
                SELECT DATA_TYPE
                FROM INFORMATION_SCHEMA.COLUMNS
                WHERE TABLE_SCHEMA = :schema_name
                    AND TABLE_NAME = :table_name
                    AND COLUMN_NAME = :column_name
            """)
            col_result = connection.execute(
                col_query,
                {
                    "schema_name": schema_name,
                    "table_name": table_name,
                    "column_name": column_name,
                },
            )
            col_row = col_result.fetchone()
            if col_row is None:
                return json.dumps({
                    "status": "error",
                    "error_message": f"Column '{column_name}' not found in table '{schema_name}.{table_name}'",
                })

            source_data_type = col_row[0]

            search = FKCandidateSearch(
                connection=connection,
                source_schema=schema_name,
                source_table=table_name,
                source_column=column_name,
                source_data_type=source_data_type,
            )

            fk_result = search.find_candidates(
                target_schema=target_schema,
                target_tables=target_tables,
                target_table_pattern=target_table_pattern,
                pk_candidates_only=pk_candidates_only,
                include_overlap=include_overlap,
                limit=limit,
            )

            response = {
                "status": "success",
                "source": {
                    "column_name": column_name,
                    "table_name": table_name,
                    "schema_name": schema_name,
                    "data_type": source_data_type,
                },
                "candidates": [c.to_dict() for c in fk_result.candidates],
                "total_found": fk_result.total_found,
                "was_limited": fk_result.was_limited,
                "search_scope": fk_result.search_scope,
            }

            return json.dumps(response)

    except ValueError as e:
        return json.dumps({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        return json.dumps({
            "status": "error",
            "error_message": f"Unexpected error: {str(e)}",
        })
