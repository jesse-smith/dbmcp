"""Schema discovery and table structure MCP tools.

Tools: connect_database, list_schemas, list_tables, get_table_schema
"""

import json
from pathlib import Path

from src.db.connection import ConnectionError
from src.db.metadata import MetadataService
from src.mcp_server.server import get_connection_manager, logger, mcp
from src.models.schema import AuthenticationMethod


def _validate_list_tables_params(
    limit: int,
    offset: int,
    object_type: str | None,
    sort_by: str,
) -> str | None:
    """Validate list_tables parameters, returning an error message or None."""
    if limit < 1:
        return "limit must be at least 1"
    if limit > 1000:
        return "limit cannot exceed 1000"
    if offset < 0:
        return "offset cannot be negative"
    valid_object_types = [None, "table", "view"]
    if object_type not in valid_object_types:
        return f"object_type must be one of: {valid_object_types}"
    valid_sort_by = ["name", "row_count", "last_modified"]
    if sort_by not in valid_sort_by:
        return f"sort_by must be one of: {valid_sort_by}"
    return None


def _build_table_entry(
    t,
    output_mode: str,
    metadata_svc: MetadataService,
) -> dict:
    """Build a response dict for a single table entry."""
    entry = {
        "schema_name": t.schema_id,
        "table_name": t.table_name,
        "table_type": t.table_type.value,
        "row_count": t.row_count,
        "has_primary_key": t.has_primary_key,
        "last_modified": t.last_modified.isoformat() if t.last_modified else None,
        "access_denied": t.access_denied,
    }
    if output_mode == "detailed":
        entry["columns"] = [
            {
                "column_name": c.column_name,
                "data_type": c.data_type,
                "is_nullable": c.is_nullable,
                "is_primary_key": c.is_primary_key,
            }
            for c in metadata_svc.get_columns(t.table_name, t.schema_id)
        ]
    return entry


def _get_metadata_service(connection_id: str) -> MetadataService:
    """Get a MetadataService for the given connection."""
    conn_manager = get_connection_manager()
    engine = conn_manager.get_engine(connection_id)
    return MetadataService(engine)


# =============================================================================
# Connection Tools
# =============================================================================


@mcp.tool()
async def connect_database(
    server: str,
    database: str,
    username: str | None = None,
    password: str | None = None,
    port: int = 1433,
    authentication_method: str = "sql",
    trust_server_cert: bool = False,
    connection_timeout: int = 30,
    tenant_id: str | None = None,
) -> str:
    """Connect to a SQL Server database.

    Establishes a pooled connection to a SQL Server database. Required before
    any other database operations. Returns a connection_id for subsequent calls.

    Args:
        server: SQL Server host (hostname or IP address)
        database: Database name
        username: Username for SQL/Azure AD authentication (optional for Windows/azure_ad_integrated auth)
        password: Password for SQL/Azure AD authentication (optional for Windows/azure_ad_integrated auth)
        port: SQL Server port (default: 1433)
        authentication_method: Auth method - 'sql', 'windows', 'azure_ad', or 'azure_ad_integrated' (default: 'sql')
        trust_server_cert: Trust server certificate without validation (default: False)
        connection_timeout: Connection timeout in seconds, 5-300 (default: 30)
        tenant_id: Azure AD tenant ID for azure_ad_integrated auth (optional, default: None)

    Returns:
        JSON string with connection details::

            {
                "connection_id": <string>,       // on success only
                "status": <"connected" | "failed">,
                "message": <string>,
                "schema_count": <int>,           // on success only
                "has_cached_docs": <bool>         // on success only
            }
    """
    try:
        # Parse authentication method
        try:
            auth_method = AuthenticationMethod(authentication_method.lower())
        except ValueError:
            return json.dumps({
                "status": "failed",
                "message": f"Invalid authentication_method '{authentication_method}'. Use 'sql', 'windows', 'azure_ad', or 'azure_ad_integrated'.",
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
            tenant_id=tenant_id,
        )

        # Get schema count for response
        engine = conn_manager.get_engine(connection.connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas(connection_id=connection.connection_id)

        # Check for cached documentation
        cache_dir = Path("docs") / connection.connection_id
        has_cached_docs = cache_dir.exists() and any(cache_dir.iterdir())

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
        JSON string with schema list::

            {
                "schemas": [
                    {
                        "schema_name": <string>,
                        "table_count": <int>,
                        "view_count": <int>
                    }
                ],
                "total_schemas": <int>
            }

    Error conditions:
        - Invalid connection_id: {"error": "Connection '...' not found"}
    """
    try:
        metadata_svc = _get_metadata_service(connection_id)
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
    schema_filter: list[str] | None = None,
    name_pattern: str | None = None,
    min_row_count: int | None = None,
    sort_by: str = "row_count",
    sort_order: str = "desc",
    limit: int = 100,
    offset: int = 0,
    object_type: str | None = None,
    output_mode: str = "summary",
) -> str:
    """List tables in specified schema(s) with row counts and metadata.

    Efficiently retrieves table metadata using SQL Server DMVs.
    Supports filtering by schema, name pattern, and minimum row count.
    Supports pagination via offset parameter.
    Supports filtering by object type to include/exclude views.

    Args:
        connection_id: Connection ID from connect_database
        schema_filter: List of schema names to include (empty = all schemas)
        name_pattern: Table name filter using SQL LIKE pattern (e.g., 'Customer%')
        min_row_count: Minimum row count threshold to filter tables
        sort_by: Sort criterion - 'name', 'row_count', or 'last_modified' (default: 'row_count')
        sort_order: Sort order - 'asc' or 'desc' (default: 'desc')
        limit: Maximum tables to return, 1-1000 (default: 100)
        offset: Number of results to skip for pagination (default: 0)
        object_type: Filter by type - 'table', 'view', or None for all (default: None)
        output_mode: 'summary' (names+row counts) or 'detailed' (includes columns) (default: 'summary')

    Returns:
        JSON string with table list and pagination metadata::

            {
                "tables": [
                    {
                        "schema_name": <string>,
                        "table_name": <string>,
                        "table_type": <"table" | "view">,
                        "row_count": <int>,
                        "has_primary_key": <bool>,
                        "last_modified": <ISO 8601 string | null>,
                        "access_denied": <bool>,
                        "columns": [...]             // detailed mode only
                    }
                ],
                "returned_count": <int>,
                "total_count": <int>,
                "offset": <int>,
                "limit": <int>,
                "has_more": <bool>
            }

    Error conditions:
        - Invalid connection_id: {"error": "Connection '...' not found"}
        - Invalid parameters: {"error": "<validation message>"}
    """
    # Validate parameters with early return
    validation_error = _validate_list_tables_params(limit, offset, object_type, sort_by)
    if validation_error is not None:
        return json.dumps({"error": validation_error})

    try:
        metadata_svc = _get_metadata_service(connection_id)

        all_tables = []
        total_count = 0

        # Query each specified schema, or all schemas if no filter
        schemas_to_query = schema_filter or [None]
        for schema_name in schemas_to_query:
            tables, pagination = metadata_svc.list_tables(
                schema_name=schema_name,
                name_pattern=name_pattern,
                min_row_count=min_row_count,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset,
                object_type=object_type,
                connection_id=connection_id,
            )
            all_tables.extend(tables)
            total_count += pagination.get("total_count", len(tables))

        # Apply limit after combining schemas (for schema_filter case)
        all_tables = all_tables[:limit]

        table_list = [
            _build_table_entry(t, output_mode, metadata_svc) for t in all_tables
        ]

        return json.dumps({
            "tables": table_list,
            "returned_count": len(all_tables),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(all_tables)) < total_count,
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
        JSON string with table schema details::

            {
                "table": {
                    "table_name": <string>,
                    "schema_name": <string>,
                    "columns": [
                        {
                            "column_name": <string>,
                            "ordinal_position": <int>,
                            "data_type": <string>,
                            "max_length": <int | null>,
                            "is_nullable": <bool>,
                            "default_value": <string | null>,
                            "is_identity": <bool>,
                            "is_computed": <bool>,
                            "is_primary_key": <bool>,
                            "is_foreign_key": <bool>
                        }
                    ],
                    "indexes": [                     // if include_indexes=True
                        {
                            "index_name": <string>,
                            "is_unique": <bool>,
                            "is_primary_key": <bool>,
                            "is_clustered": <bool>,
                            "columns": [<string>],
                            "included_columns": [<string>]
                        }
                    ],
                    "foreign_keys": [                // if include_relationships=True
                        {
                            "constraint_name": <string | null>,
                            "source_columns": [<string>],
                            "target_schema": <string>,
                            "target_table": <string>,
                            "target_columns": [<string>]
                        }
                    ]
                }
            }

    Error conditions:
        - Table not found: {"error": "Table '...' not found"}
        - Invalid connection_id: {"error": "Connection '...' not found"}
    """
    try:
        metadata_svc = _get_metadata_service(connection_id)

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
