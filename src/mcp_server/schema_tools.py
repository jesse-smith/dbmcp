"""Schema discovery and table structure MCP tools.

Tools: connect_database, list_schemas, list_tables, get_table_schema
"""

import asyncio
from pathlib import Path

from sqlalchemy.exc import SQLAlchemyError

from src.config import get_config, resolve_env_vars
from src.db.connection import ConnectionError, _classify_db_error
from src.db.metadata import MetadataService
from src.mcp_server.server import get_connection_manager, logger, mcp
from src.models.schema import AuthenticationMethod, ResolvedConnectionParams
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
    return MetadataService(engine)


# =============================================================================
# Connection resolution helpers
# =============================================================================


def _pick(explicit, config_val):
    """Return explicit arg if provided, else config value."""
    return explicit if explicit is not None else config_val


def _resolve_env_field(explicit: str | None, config_val: str | None) -> tuple[str | None, dict | None]:
    """Resolve a credential field that may contain env var references.

    Returns:
        (resolved_value, error_dict_or_none) — if error_dict is not None, return it.
    """
    if explicit is not None:
        return explicit, None
    if config_val is not None:
        try:
            return resolve_env_vars(config_val), None
        except ValueError as e:
            return None, {"status": "error", "error_message": str(e)}
    return None, None


def _merge_with_config(
    server: str | None,
    database: str | None,
    port: int | None,
    authentication_method: str | None,
    trust_server_cert: bool | None,
    connection_timeout: int | None,
    username: str | None,
    password: str | None,
    tenant_id: str | None,
    conn_cfg,
) -> tuple[dict | None, dict | None]:
    """Merge explicit args with a named ConnectionConfig.

    Returns:
        (merged_dict, error_dict_or_none) — merged_dict has all effective values,
        or error_dict if env var resolution failed.
    """
    eff_password, err = _resolve_env_field(password, conn_cfg.password)
    if err is not None:
        return None, err

    eff_tenant_id, err = _resolve_env_field(tenant_id, conn_cfg.tenant_id)
    if err is not None:
        return None, err

    return {
        "server": _pick(server, conn_cfg.server),
        "database": _pick(database, conn_cfg.database),
        "port": _pick(port, conn_cfg.port),
        "authentication_method": _pick(authentication_method, conn_cfg.authentication_method),
        "trust_server_cert": _pick(trust_server_cert, conn_cfg.trust_server_cert),
        "connection_timeout": _pick(connection_timeout, conn_cfg.connection_timeout),
        "username": _pick(username, conn_cfg.username),
        "password": eff_password,
        "tenant_id": eff_tenant_id,
    }, None


def _defaults_only(
    server: str | None,
    database: str | None,
    port: int | None,
    authentication_method: str | None,
    trust_server_cert: bool | None,
    connection_timeout: int | None,
    username: str | None,
    password: str | None,
    tenant_id: str | None,
) -> dict:
    """Build effective params from explicit args + hardcoded defaults (no named connection)."""
    return {
        "server": server,
        "database": database,
        "port": port if port is not None else 1433,
        "authentication_method": authentication_method if authentication_method is not None else "sql",
        "trust_server_cert": trust_server_cert if trust_server_cert is not None else False,
        "connection_timeout": connection_timeout if connection_timeout is not None else 30,
        "username": username,
        "password": password,
        "tenant_id": tenant_id,
    }


def _resolve_connection_params(
    server: str | None,
    database: str | None,
    username: str | None,
    password: str | None,
    port: int | None,
    authentication_method: str | None,
    trust_server_cert: bool | None,
    connection_timeout: int | None,
    tenant_id: str | None,
    connection_name: str | None,
) -> tuple[ResolvedConnectionParams | None, dict | None]:
    """Resolve all connect_database parameters into a ResolvedConnectionParams.

    Returns:
        (params, None) on success, or (None, error_dict) on failure.
    """
    if connection_name is not None:
        config = get_config()
        if connection_name not in config.connections:
            return None, {
                "status": "error",
                "error_message": f"Named connection '{connection_name}' not found in config. "
                f"Available: {sorted(config.connections.keys()) or 'none'}",
            }
        merged, err = _merge_with_config(
            server, database, port, authentication_method,
            trust_server_cert, connection_timeout, username, password,
            tenant_id, config.connections[connection_name],
        )
        if err is not None:
            return None, err
        eff = merged
    else:
        eff = _defaults_only(
            server, database, port, authentication_method,
            trust_server_cert, connection_timeout, username, password, tenant_id,
        )

    # Validate required fields
    if not eff["server"]:
        return None, {
            "status": "error",
            "error_message": "server is required (provide directly or via connection_name)",
        }
    if not eff["database"]:
        return None, {
            "status": "error",
            "error_message": "database is required (provide directly or via connection_name)",
        }

    # Parse authentication method
    try:
        AuthenticationMethod(eff["authentication_method"].lower())
    except ValueError:
        return None, {
            "status": "error",
            "error_message": f"Invalid authentication_method '{eff['authentication_method']}'. "
            "Use 'sql', 'windows', 'azure_ad', or 'azure_ad_integrated'.",
        }

    return ResolvedConnectionParams(
        server=eff["server"],
        database=eff["database"],
        port=eff["port"],
        authentication_method=eff["authentication_method"],
        trust_server_cert=eff["trust_server_cert"],
        connection_timeout=eff["connection_timeout"],
        username=eff["username"],
        password=eff["password"],
        tenant_id=eff["tenant_id"],
    ), None


# =============================================================================
# Connection Tools
# =============================================================================


@mcp.tool()
async def connect_database(
    server: str | None = None,
    database: str | None = None,
    username: str | None = None,
    password: str | None = None,
    port: int | None = None,
    authentication_method: str | None = None,
    trust_server_cert: bool | None = None,
    connection_timeout: int | None = None,
    tenant_id: str | None = None,
    connection_name: str | None = None,
) -> str:
    """Connect to a SQL Server database.

    Establishes a pooled connection to a SQL Server database. Required before
    any other database operations. Returns a connection_id for subsequent calls.

    Can use a named connection from dbmcp.toml config file via connection_name.
    Explicit arguments override config values.

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
        connection_name: Named connection from config file (optional)

    Returns:
        TOON-encoded string with connection details:

            status: "success" | "error"
            connection_id: string              // on success only
            message: string                    // on success only
            schema_count: int                  // on success only
            has_cached_docs: bool              // on success only
            error_message: string              // on error only
    """
    params, err = _resolve_connection_params(
        server, database, username, password, port,
        authentication_method, trust_server_cert, connection_timeout,
        tenant_id, connection_name,
    )
    if err is not None:
        return encode_response(err)

    auth_method = AuthenticationMethod(params.authentication_method.lower())

    def _sync_connect():
        conn_manager = get_connection_manager()
        connection = conn_manager.connect(
            server=params.server,
            database=params.database,
            username=params.username,
            password=params.password,
            port=params.port,
            authentication_method=auth_method,
            trust_server_cert=params.trust_server_cert,
            connection_timeout=params.connection_timeout,
            tenant_id=params.tenant_id,
        )

        engine = conn_manager.get_engine(connection.connection_id)
        metadata_svc = MetadataService(engine)
        schemas = metadata_svc.list_schemas(connection_id=connection.connection_id)

        cache_dir = Path("docs") / connection.connection_id
        has_cached_docs = cache_dir.exists() and any(cache_dir.iterdir())

        logger.info(f"Connected to {params.database} on {params.server}:{params.port}")

        return {
            "connection_id": connection.connection_id,
            "status": "success",
            "message": f"Successfully connected to {params.database}",
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
            error_msg = f"Unexpected error: {type(e).__name__}: {str(e)}"
        return encode_response({
            "status": "error",
            "error_message": error_msg,
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
        schemas = metadata_svc.list_schemas(connection_id=connection_id)
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

        if not metadata_svc.table_exists(table_name, schema_name):
            return {
                "status": "error",
                "error_message": f"Table '{schema_name}.{table_name}' not found",
            }

        schema = metadata_svc.get_table_schema(
            table_name=table_name,
            schema_name=schema_name,
            include_indexes=include_indexes,
            include_relationships=include_relationships,
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
