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
        # Get connection from connection manager
        conn_manager = get_connection_manager()
        if connection_id not in conn_manager.connections:
            return json.dumps({
                "status": "error",
                "error_message": f"Connection '{connection_id}' not found",
            })

        connection_info = conn_manager.connections[connection_id]
        connection = connection_info["connection"]

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

        return json.dumps(response, default=str)  # default=str handles datetime serialization

    except ValueError as e:
        # Column not found error from collector
        return json.dumps({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        # Unexpected error
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
        if connection_id not in conn_manager.connections:
            return json.dumps({
                "status": "error",
                "error_message": f"Connection '{connection_id}' not found",
            })

        connection_info = conn_manager.connections[connection_id]
        connection = connection_info["connection"]

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

    except Exception as e:
        return json.dumps({
            "status": "error",
            "error_message": f"Unexpected error: {str(e)}",
        })
