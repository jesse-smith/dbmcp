"""Schema discovery and table structure MCP tools.

Tools: connect_database, list_schemas, list_tables, get_table_schema
"""

import asyncio
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from src.config import get_config
from src.db.connection import ConnectionError, _classify_db_error
from src.db.dialects.registry import get_dialect, resolve_dialect_from_url
from src.db.metadata import MetadataService
from src.mcp_server._errors import format_unexpected_error
from src.mcp_server.server import get_connection_manager, logger, mcp
from src.serialization import encode_response


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
    dialect = conn_manager.get_dialect(connection_id)
    return MetadataService(engine, dialect=dialect)


# =============================================================================
# Connection Tools
# =============================================================================


@mcp.tool()
async def connect_database(
    connection_name: str | None = None,
    sqlalchemy_url: str | None = None,
) -> str:
    """Connect to a database.

    Establishes a pooled connection to a database. Required before any other
    database operations. Returns a connection_id for subsequent calls.

    Two connection methods:
    - connection_name: Use a named connection from dbmcp.toml config file
    - sqlalchemy_url: Connect directly with a SQLAlchemy URL (e.g., 'postgresql://user:pass@host/db')

    Provide exactly one of connection_name or sqlalchemy_url.

    MSSQL URL query parameters (mssql+pyodbc://...):
    - authentication_method: sql | windows | azure_ad | azure_ad_integrated
      (default: sql when credentials are present, else windows)
    - trust_server_cert: true | false (default: false)
    - tenant_id: Azure AD tenant (optional)

    Example (MSSQL):
        mssql+pyodbc://user:pass@host/db?authentication_method=sql&trust_server_cert=true

    Args:
        connection_name: Named connection from config file (optional)
        sqlalchemy_url: SQLAlchemy connection URL (optional)

    Returns:
        TOON-encoded string with connection details:

            status: "success" | "error"
            connection_id: string              // on success only
            message: string                    // on success only
            dialect: string                    // on success only
            schema_count: int                  // on success only
            has_cached_docs: bool              // on success only
            error_message: string              // on error only
    """
    # Validate exactly one path
    if connection_name is not None and sqlalchemy_url is not None:
        return encode_response({
            "status": "error",
            "error_message": "Provide either connection_name or sqlalchemy_url, not both.",
        })
    if connection_name is None and sqlalchemy_url is None:
        return encode_response({
            "status": "error",
            "error_message": "Provide connection_name or sqlalchemy_url.",
        })

    def _sync_connect():
        conn_manager = get_connection_manager()

        if connection_name is not None:
            config = get_config()
            if config.load_error:
                return {
                    "status": "error",
                    "error_message": f"config parse error: {config.load_error}",
                }
            if connection_name not in config.connections:
                return {
                    "status": "error",
                    "error_message": f"Named connection '{connection_name}' not found in config. "
                    f"Available: {sorted(config.connections.keys()) or 'none'}",
                }
            conn_cfg = config.connections[connection_name]
            dialect_cls = get_dialect(conn_cfg.dialect)
            dialect = dialect_cls()
            connection = conn_manager.connect_with_config(
                config=conn_cfg,
                dialect=dialect,
                query_timeout=config.defaults.query_timeout,
            )
        else:
            # sqlalchemy_url path
            assert sqlalchemy_url is not None
            dialect = resolve_dialect_from_url(sqlalchemy_url)
            connection = conn_manager.connect_with_url(
                sqlalchemy_url=sqlalchemy_url,
                dialect=dialect,
                query_timeout=get_config().defaults.query_timeout,
            )

        engine = conn_manager.get_engine(connection.connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas(connection_id=connection.connection_id)

        cache_dir = Path("docs") / connection.connection_id
        has_cached_docs = cache_dir.exists() and any(cache_dir.iterdir())

        return {
            "connection_id": connection.connection_id,
            "status": "success",
            "message": f"Successfully connected to {connection.database or connection.server or 'database'}",
            "dialect": connection.dialect_name,
            "schema_count": len(schemas),
            "has_cached_docs": has_cached_docs,
        }

    try:
        result = await asyncio.to_thread(_sync_connect)
        return encode_response(result)
    except ConnectionError as e:
        logger.error(f"Connection failed: {type(e).__name__}")
        return encode_response({
            "status": "error",
            "error_message": str(e),
        })
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        return encode_response({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        logger.exception("Unexpected error in connect_database")
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = format_unexpected_error(e, include_type=True)
        return encode_response({
            "status": "error",
            "error_message": error_msg,
        })


# =============================================================================
# Schema Discovery Tools (User Story 1)
# =============================================================================


@mcp.tool()
async def list_schemas(connection_id: str, catalog: str | None = None) -> str:
    """List all schemas in the connected database.

    Returns schemas with table and view counts, sorted by table count descending.
    Excludes system schemas (sys, INFORMATION_SCHEMA, guest).

    Args:
        connection_id: Connection ID from connect_database
        catalog: Optional Databricks catalog name. Overrides the connection's
            default catalog. If omitted on a Databricks connection, the
            connection's configured default catalog is used (SHOW SCHEMAS IN).
            Ignored for non-Databricks dialects.

    Returns:
        TOON-encoded string with schema list:

            status: "success" | "error"
            total_schemas: int                 // on success only
            schemas: list                      // on success only
                schema_name: string
                table_count: int
                view_count: int
            error_message: string              // on error only

    Error conditions:
        - Invalid connection_id: returns status "error" with error_message
    """
    def _sync_work():
        metadata_svc = _get_metadata_service(connection_id)
        schemas = metadata_svc.list_schemas(connection_id=connection_id, catalog=catalog)
        return {
            "status": "success",
            "schemas": [
                {
                    "schema_name": s.schema_name,
                    "table_count": s.table_count,
                    "view_count": s.view_count,
                }
                for s in schemas
            ],
            "total_schemas": len(schemas),
        }

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({"status": "error", "error_message": str(e)})
    except Exception as e:
        logger.exception("Error in list_schemas")
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = f"Failed to list schemas: {str(e)}"
        return encode_response({"status": "error", "error_message": error_msg})


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
    catalog: str | None = None,
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
        catalog: Optional Databricks catalog name. Overrides the connection's
            default catalog. Ignored for non-Databricks dialects.

    Returns:
        TOON-encoded string with table list and pagination metadata:

            status: "success" | "error"
            returned_count: int                // on success only
            total_count: int                   // on success only
            offset: int                        // on success only
            limit: int                         // on success only
            has_more: bool                     // on success only
            tables: list                       // on success only
                schema_name: string
                table_name: string
                table_type: "table" | "view"
                row_count: int
                has_primary_key: bool
                last_modified: ISO 8601 string | null
                access_denied: bool
                columns: list              // detailed mode only
            error_message: string          // on error only
    """
    # Validate parameters with early return (fast, no I/O)
    validation_error = _validate_list_tables_params(limit, offset, object_type, sort_by)
    if validation_error is not None:
        return encode_response({"status": "error", "error_message": validation_error})

    def _sync_work():
        metadata_svc = _get_metadata_service(connection_id)

        all_tables = []
        total_count = 0

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
                catalog=catalog,
            )
            all_tables.extend(tables)
            total_count += pagination.get("total_count", len(tables))

        all_tables = all_tables[:limit]

        table_list = [
            _build_table_entry(t, output_mode, metadata_svc) for t in all_tables
        ]

        return {
            "status": "success",
            "tables": table_list,
            "returned_count": len(all_tables),
            "total_count": total_count,
            "offset": offset,
            "limit": limit,
            "has_more": (offset + len(all_tables)) < total_count,
        }

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({"status": "error", "error_message": str(e)})
    except Exception as e:
        logger.exception("Error in list_tables")
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = f"Failed to list tables: {str(e)}"
        return encode_response({"status": "error", "error_message": error_msg})


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
    catalog: str | None = None,
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
        catalog: Optional Databricks catalog name. Overrides the connection's
            default catalog. Ignored for non-Databricks dialects.

    Returns:
        TOON-encoded string with table schema details:

            status: "success" | "error"
            table: object                          // on success only
                table_name: string
                schema_name: string
                columns: list
                    column_name: string
                    ordinal_position: int
                    data_type: string
                    max_length: int | null
                    is_nullable: bool
                    default_value: string | null
                    is_identity: bool
                    is_computed: bool
                    is_primary_key: bool
                    is_foreign_key: bool
                indexes: list                      // if include_indexes=True
                    index_name: string
                    is_unique: bool
                    is_primary_key: bool
                    is_clustered: bool
                    columns: list of string
                    included_columns: list of string
                foreign_keys: list                 // if include_relationships=True
                    constraint_name: string | null
                    source_columns: list of string
                    target_schema: string
                    target_table: string
                    target_columns: list of string
            error_message: string                  // on error only
    """
    def _sync_work():
        metadata_svc = _get_metadata_service(connection_id)

        if not metadata_svc.table_exists(table_name, schema_name, catalog=catalog):
            return {
                "status": "error",
                "error_message": f"Table '{schema_name}.{table_name}' not found",
            }

        schema = metadata_svc.get_table_schema(
            table_name=table_name,
            schema_name=schema_name,
            include_indexes=include_indexes,
            include_relationships=include_relationships,
            catalog=catalog,
        )

        return {"status": "success", "table": schema}

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({"status": "error", "error_message": str(e)})
    except Exception as e:
        logger.exception("Error in get_table_schema")
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = f"Failed to get table schema: {str(e)}"
        return encode_response({"status": "error", "error_message": error_msg})
