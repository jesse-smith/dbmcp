"""FastMCP server for Database Schema Explorer.

This module implements the MCP server entry point and all MCP tools
for database exploration. Uses FastMCP for clean decorator-based tool definition.

CRITICAL: Never use print() or stdout - it corrupts JSON-RPC messages.
All logging goes to file and stderr only.
"""

import json
from pathlib import Path
from typing import Optional

from mcp.server.fastmcp import FastMCP

from src.db.connection import ConnectionError, ConnectionManager
from src.db.metadata import MetadataService
from src.logging_config import CredentialFilter, setup_logging
from src.models.schema import AuthenticationMethod

# Configure logging (file + stderr, never stdout)
logger = setup_logging(log_file=Path("dbmcp.log"), log_to_stderr=True)
logger.addFilter(CredentialFilter())

# Create MCP server instance
mcp = FastMCP("dbmcp")

# Global connection manager (singleton for the server lifetime)
_connection_manager = ConnectionManager()


def get_connection_manager() -> ConnectionManager:
    """Get the global connection manager instance."""
    return _connection_manager


# =============================================================================
# Connection Tools
# =============================================================================


@mcp.tool()
async def connect_database(
    server: str,
    database: str,
    username: Optional[str] = None,
    password: Optional[str] = None,
    port: int = 1433,
    authentication_method: str = "sql",
    trust_server_cert: bool = False,
    connection_timeout: int = 30,
) -> str:
    """Connect to a SQL Server database.

    Establishes a pooled connection to a SQL Server database. Required before
    any other database operations. Returns a connection_id for subsequent calls.

    Args:
        server: SQL Server host (hostname or IP address)
        database: Database name
        username: Username for SQL/Azure AD authentication (optional for Windows auth)
        password: Password for SQL/Azure AD authentication (optional for Windows auth)
        port: SQL Server port (default: 1433)
        authentication_method: Auth method - 'sql', 'windows', or 'azure_ad' (default: 'sql')
        trust_server_cert: Trust server certificate without validation (default: False)
        connection_timeout: Connection timeout in seconds, 5-300 (default: 30)

    Returns:
        JSON string with connection details including connection_id
    """
    try:
        # Parse authentication method
        try:
            auth_method = AuthenticationMethod(authentication_method.lower())
        except ValueError:
            return json.dumps({
                "status": "failed",
                "message": f"Invalid authentication_method '{authentication_method}'. Use 'sql', 'windows', or 'azure_ad'.",
            })

        # Attempt connection
        conn_manager = get_connection_manager()
        connection = conn_manager.connect(
            server=server,
            database=database,
            username=username,
            password=password,
            port=port,
            authentication_method=auth_method,
            trust_server_cert=trust_server_cert,
            connection_timeout=connection_timeout,
        )

        # Get schema count for response
        engine = conn_manager.get_engine(connection.connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas(connection_id=connection.connection_id)

        # Check for cached documentation
        cache_dir = Path("docs") / connection.connection_id
        has_cached_docs = cache_dir.exists() and any(cache_dir.iterdir()) if cache_dir.exists() else False

        logger.info(f"Connected to {database} on {server}:{port}")

        return json.dumps({
            "connection_id": connection.connection_id,
            "status": "connected",
            "message": f"Successfully connected to {database}",
            "schema_count": len(schemas),
            "has_cached_docs": has_cached_docs,
        })

    except ConnectionError as e:
        logger.error(f"Connection failed: {type(e).__name__}")
        return json.dumps({
            "status": "failed",
            "message": str(e),
        })
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return json.dumps({
            "status": "failed",
            "message": str(e),
        })
    except Exception as e:
        logger.exception("Unexpected error in connect_database")
        return json.dumps({
            "status": "failed",
            "message": f"Unexpected error: {type(e).__name__}: {str(e)}",
        })


# =============================================================================
# Schema Discovery Tools (User Story 1)
# =============================================================================


@mcp.tool()
async def list_schemas(connection_id: str) -> str:
    """List all schemas in the connected database.

    Returns schemas with table and view counts, sorted by table count descending.
    Excludes system schemas (sys, INFORMATION_SCHEMA, guest).

    Args:
        connection_id: Connection ID from connect_database

    Returns:
        JSON string with schema list
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas(connection_id=connection_id)

        return json.dumps({
            "schemas": [
                {
                    "schema_name": s.schema_name,
                    "table_count": s.table_count,
                    "view_count": s.view_count,
                }
                for s in schemas
            ],
            "total_schemas": len(schemas),
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in list_schemas")
        return json.dumps({"error": f"Failed to list schemas: {str(e)}"})


@mcp.tool()
async def list_tables(
    connection_id: str,
    schema_filter: Optional[list[str]] = None,
    name_pattern: Optional[str] = None,
    min_row_count: Optional[int] = None,
    sort_by: str = "row_count",
    sort_order: str = "desc",
    limit: int = 100,
    output_mode: str = "summary",
) -> str:
    """List tables in specified schema(s) with row counts and metadata.

    Efficiently retrieves table metadata using SQL Server DMVs.
    Supports filtering by schema, name pattern, and minimum row count.

    Args:
        connection_id: Connection ID from connect_database
        schema_filter: List of schema names to include (empty = all schemas)
        name_pattern: Table name filter using SQL LIKE pattern (e.g., 'Customer%')
        min_row_count: Minimum row count threshold to filter tables
        sort_by: Sort criterion - 'name', 'row_count', or 'last_modified' (default: 'row_count')
        sort_order: Sort order - 'asc' or 'desc' (default: 'desc')
        limit: Maximum tables to return, 1-1000 (default: 100)
        output_mode: 'summary' (names+row counts) or 'detailed' (includes columns) (default: 'summary')

    Returns:
        JSON string with table list
    """
    try:
        # Validate limit
        if limit < 1:
            return json.dumps({"error": "limit must be at least 1"})
        if limit > 1000:
            return json.dumps({"error": "limit cannot exceed 1000"})

        # Validate sort_by
        valid_sort_by = ["name", "row_count", "last_modified"]
        if sort_by not in valid_sort_by:
            return json.dumps({"error": f"sort_by must be one of: {valid_sort_by}"})

        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)

        all_tables = []

        # If schema_filter provided, query each schema
        if schema_filter:
            for schema_name in schema_filter:
                tables = metadata_svc.list_tables(
                    schema_name=schema_name,
                    name_pattern=name_pattern,
                    min_row_count=min_row_count,
                    sort_by=sort_by,
                    sort_order=sort_order,
                    limit=limit,
                    connection_id=connection_id,
                )
                all_tables.extend(tables)
        else:
            # Query all schemas
            all_tables = metadata_svc.list_tables(
                schema_name=None,
                name_pattern=name_pattern,
                min_row_count=min_row_count,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                connection_id=connection_id,
            )

        # Apply limit after combining schemas
        all_tables = all_tables[:limit]

        # Build response based on output_mode
        if output_mode == "detailed":
            table_list = [
                {
                    "schema_name": t.schema_id,
                    "table_name": t.table_name,
                    "row_count": t.row_count,
                    "has_primary_key": t.has_primary_key,
                    "last_modified": t.last_modified.isoformat() if t.last_modified else None,
                    "access_denied": t.access_denied,
                    "columns": [
                        {
                            "column_name": c.column_name,
                            "data_type": c.data_type,
                            "is_nullable": c.is_nullable,
                            "is_primary_key": c.is_primary_key,
                        }
                        for c in metadata_svc.get_columns(t.table_name, t.schema_id)
                    ],
                }
                for t in all_tables
            ]
        else:
            # Summary mode - more token-efficient
            table_list = [
                {
                    "schema_name": t.schema_id,
                    "table_name": t.table_name,
                    "row_count": t.row_count,
                    "has_primary_key": t.has_primary_key,
                    "last_modified": t.last_modified.isoformat() if t.last_modified else None,
                    "access_denied": t.access_denied,
                }
                for t in all_tables
            ]

        return json.dumps({
            "tables": table_list,
            "total_tables": len(all_tables),
            "filtered_count": len(all_tables),
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in list_tables")
        return json.dumps({"error": f"Failed to list tables: {str(e)}"})


# =============================================================================
# Table Structure Tools (User Story 2)
# =============================================================================


@mcp.tool()
async def get_table_schema(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo",
    include_indexes: bool = True,
    include_relationships: bool = True,
) -> str:
    """Get detailed schema for a specific table.

    Returns complete table metadata including columns, data types, constraints,
    indexes, and declared foreign key relationships.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Name of the table
        schema_name: Schema name (default: 'dbo')
        include_indexes: Include index information (default: True)
        include_relationships: Include declared foreign keys (default: True)

    Returns:
        JSON string with table schema details
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)

        # Check if table exists
        if not metadata_svc.table_exists(table_name, schema_name):
            return json.dumps({
                "error": f"Table '{schema_name}.{table_name}' not found",
            })

        schema = metadata_svc.get_table_schema(
            table_name=table_name,
            schema_name=schema_name,
            include_indexes=include_indexes,
            include_relationships=include_relationships,
        )

        return json.dumps({"table": schema})

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in get_table_schema")
        return json.dumps({"error": f"Failed to get table schema: {str(e)}"})


# =============================================================================
# Relationship Inference Tools (User Story 3)
# =============================================================================


@mcp.tool()
async def infer_relationships(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo",
    confidence_threshold: float = 0.50,
    max_candidates: int = 20,
    include_value_overlap: bool = False,
) -> str:
    """Infer potential foreign key relationships for a table.

    Analyzes column names, data types, and structural hints to infer likely
    foreign key relationships in legacy databases with undeclared FKs.
    Uses three-factor weighted scoring: name similarity (40%), type compatibility (15%),
    and structural hints (45%).

    Args:
        connection_id: Connection ID from connect_database
        table_name: Source table to analyze
        schema_name: Schema name (default: 'dbo')
        confidence_threshold: Minimum confidence score 0.0-1.0 (default: 0.50)
        max_candidates: Maximum relationships to return, 1-1000 (default: 20)
        include_value_overlap: Enable value overlap analysis (Phase 2 feature, raises NotImplementedError)

    Returns:
        JSON string with inferred relationships and analysis metadata
    """
    try:
        # Parameter validation
        if confidence_threshold < 0.0 or confidence_threshold > 1.0:
            return json.dumps({
                "error": "confidence_threshold must be between 0.0 and 1.0"
            })

        if max_candidates < 1 or max_candidates > 1000:
            return json.dumps({
                "error": "max_candidates must be between 1 and 1000"
            })

        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)

        # Import here to avoid circular imports
        from src.inference.relationships import ForeignKeyInferencer

        inferencer = ForeignKeyInferencer(engine, threshold=confidence_threshold)

        try:
            inferred, metadata = inferencer.infer_relationships(
                table_name=table_name,
                schema_name=schema_name,
                max_candidates=max_candidates,
                include_value_overlap=include_value_overlap,
            )
        except NotImplementedError as e:
            return json.dumps({
                "error": str(e),
                "hint": "Set include_value_overlap=false for Phase 1 inference"
            })

        return json.dumps({
            "inferred_relationships": [
                {
                    "source_table": rel.source_table_id,
                    "source_column": rel.source_column,
                    "target_table": rel.target_table_id,
                    "target_column": rel.target_column,
                    "confidence_score": rel.confidence_score,
                    "reasoning": rel.reasoning,
                    "factors": rel.inference_factors.to_dict(),
                }
                for rel in inferred
            ],
            "analysis_time_ms": metadata["analysis_time_ms"],
            "total_candidates_evaluated": metadata["total_candidates_evaluated"],
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in infer_relationships")
        return json.dumps({"error": f"Failed to infer relationships: {str(e)}"})


# =============================================================================
# Server Entry Point
# =============================================================================


def main():
    """Run the MCP server on stdio transport."""
    logger.info("Starting dbmcp MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
