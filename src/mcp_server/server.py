"""FastMCP server for Database Schema Explorer.

This module implements the MCP server entry point and all MCP tools
for database exploration. Uses FastMCP for clean decorator-based tool definition.

CRITICAL: Never use print() or stdout - it corrupts JSON-RPC messages.
All logging goes to file and stderr only.
"""

import json
from pathlib import Path

from mcp.server.fastmcp import FastMCP

from src.db.connection import ConnectionError, ConnectionManager
from src.db.metadata import MetadataService
from src.db.query import QueryService
from src.logging_config import CredentialFilter, setup_logging
from src.models.schema import AuthenticationMethod, SamplingMethod

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
    username: str | None = None,
    password: str | None = None,
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
    Supports pagination via offset parameter (T132).
    Supports filtering by object type to include/exclude views (T133).

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
        JSON string with table list and pagination metadata
    """
    try:
        # Validate limit
        if limit < 1:
            return json.dumps({"error": "limit must be at least 1"})
        if limit > 1000:
            return json.dumps({"error": "limit cannot exceed 1000"})

        # Validate offset (T132)
        if offset < 0:
            return json.dumps({"error": "offset cannot be negative"})

        # Validate object_type (T133)
        valid_object_types = [None, "table", "view"]
        if object_type not in valid_object_types:
            return json.dumps({"error": f"object_type must be one of: {valid_object_types}"})

        # Validate sort_by
        valid_sort_by = ["name", "row_count", "last_modified"]
        if sort_by not in valid_sort_by:
            return json.dumps({"error": f"sort_by must be one of: {valid_sort_by}"})

        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)

        all_tables = []
        total_count = 0

        # If schema_filter provided, query each schema
        if schema_filter:
            for schema_name in schema_filter:
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
                total_count += pagination.get("total_count", 0)
        else:
            # Query all schemas
            all_tables, pagination = metadata_svc.list_tables(
                schema_name=None,
                name_pattern=name_pattern,
                min_row_count=min_row_count,
                sort_by=sort_by,
                sort_order=sort_order,
                limit=limit,
                offset=offset,
                object_type=object_type,
                connection_id=connection_id,
            )
            total_count = pagination.get("total_count", len(all_tables))

        # Apply limit after combining schemas (for schema_filter case)
        all_tables = all_tables[:limit]

        # Build response based on output_mode
        if output_mode == "detailed":
            table_list = [
                {
                    "schema_name": t.schema_id,
                    "table_name": t.table_name,
                    "table_type": t.table_type.value,
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
                    "table_type": t.table_type.value,
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
            "timed_out": metadata.get("timed_out", False),
            "tables_analyzed": metadata.get("tables_analyzed", 0),
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in infer_relationships")
        return json.dumps({"error": f"Failed to infer relationships: {str(e)}"})


# =============================================================================
# Sample Data Tools (User Story 4)
# =============================================================================


@mcp.tool()
async def get_sample_data(
    connection_id: str,
    table_name: str,
    schema_name: str = "dbo",
    sample_size: int = 5,
    sampling_method: str = "top",
    columns: list[str] | None = None,
) -> str:
    """Retrieve sample data from a table.

    Returns representative sample rows from a table with support for multiple
    sampling strategies. Automatically truncates large text (>1000 chars) and
    binary data (shows first 32 bytes as hex) to keep responses token-efficient.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Table name to sample from
        schema_name: Schema name (default: 'dbo')
        sample_size: Number of rows to return, 1-1000 (default: 5)
        sampling_method: Sampling strategy - 'top', 'tablesample', or 'modulo' (default: 'top')
            - 'top': Fast SELECT TOP N (not representative, just first N rows)
            - 'tablesample': SQL Server statistical sampling (more representative)
            - 'modulo': Deterministic sampling using modulo on row number (repeatable)
        columns: Optional list of column names to include (default: all columns)

    Returns:
        JSON string with sample rows and metadata
    """
    try:
        # Validate sample_size
        if sample_size < 1 or sample_size > 1000:
            return json.dumps({
                "error": "sample_size must be between 1 and 1000",
            })

        # Validate sampling_method
        valid_methods = ["top", "tablesample", "modulo"]
        if sampling_method not in valid_methods:
            return json.dumps({
                "error": f"sampling_method must be one of: {valid_methods}",
            })

        # Parse sampling method enum
        try:
            method_enum = SamplingMethod(sampling_method.lower())
        except ValueError:
            return json.dumps({
                "error": f"Invalid sampling_method '{sampling_method}'. Use 'top', 'tablesample', or 'modulo'.",
            })

        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        query_svc = QueryService(engine)

        # Get sample data
        sample = query_svc.get_sample_data(
            table_name=table_name,
            schema_name=schema_name,
            sample_size=sample_size,
            sampling_method=method_enum,
            columns=columns,
        )

        return json.dumps({
            "sample_id": sample.sample_id,
            "table_id": sample.table_id,
            "sample_size": sample.sample_size,
            "actual_rows_returned": len(sample.rows),
            "sampling_method": sample.sampling_method.value,
            "rows": sample.rows,
            "truncated_columns": sample.truncated_columns,
            "sampled_at": sample.sampled_at.isoformat(),
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in get_sample_data")
        return json.dumps({"error": f"Failed to get sample data: {str(e)}"})


# =============================================================================
# Column Analysis Tools (User Story 5)
# =============================================================================


@mcp.tool()
async def analyze_column(
    connection_id: str,
    column_name: str,
    table_name: str,
    schema_name: str = "dbo",
) -> str:
    """Analyze a column to infer its purpose and characteristics.

    Performs statistical analysis on a column to determine its likely purpose
    (e.g., ID, enum, status, flag, amount, quantity, percentage, timestamp).
    Returns type-specific statistics and a confidence score for the inference.

    Useful for understanding cryptic column names like FLG_1, STATUS_CD, or AMT_3.

    Args:
        connection_id: Connection ID from connect_database
        column_name: Name of the column to analyze
        table_name: Table containing the column
        schema_name: Schema name (default: 'dbo')

    Returns:
        JSON string with column analysis results including:
        - inferred_purpose: The detected purpose (id, enum, status, flag, amount, quantity, percentage, timestamp, unknown)
        - confidence: Confidence score (0.0-1.0)
        - reasoning: Explanation of why this purpose was inferred
        - is_enum: Whether the column appears to be an enumeration
        - statistics: Type-specific statistics (numeric, datetime, or string)
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)

        # Import here to avoid circular imports
        from src.inference.columns import ColumnAnalyzer

        analyzer = ColumnAnalyzer(engine)
        analysis = analyzer.analyze_column(
            column_name=column_name,
            table_name=table_name,
            schema_name=schema_name,
        )

        # Build response with type-specific statistics
        result = {
            "column_name": analysis.column_name,
            "table_name": analysis.table_name,
            "schema_name": analysis.schema_name,
            "data_type": analysis.data_type,
            "inferred_purpose": analysis.inferred_purpose.value,
            "confidence": analysis.confidence,
            "reasoning": analysis.reasoning,
            "is_enum": analysis.is_enum,
            "distinct_count": analysis.distinct_count,
            "null_count": analysis.null_count,
            "null_percentage": analysis.null_percentage,
            "total_rows": analysis.total_rows,
            "analyzed_at": analysis.analyzed_at.isoformat(),
        }

        # Add type-specific statistics
        if analysis.numeric_stats:
            result["numeric_statistics"] = {
                "min": analysis.numeric_stats.min_value,
                "max": analysis.numeric_stats.max_value,
                "mean": analysis.numeric_stats.mean_value,
                "median": analysis.numeric_stats.median_value,
                "std_dev": analysis.numeric_stats.std_dev,
                "is_integer": analysis.numeric_stats.is_integer,
            }

        if analysis.datetime_stats:
            result["datetime_statistics"] = {
                "min_date": analysis.datetime_stats.min_date.isoformat() if analysis.datetime_stats.min_date else None,
                "max_date": analysis.datetime_stats.max_date.isoformat() if analysis.datetime_stats.max_date else None,
                "date_range_days": analysis.datetime_stats.date_range_days,
                "has_time_component": analysis.datetime_stats.has_time_component,
                "business_hours_percentage": analysis.datetime_stats.business_hours_percentage,
            }

        if analysis.string_stats:
            result["string_statistics"] = {
                "top_values": [
                    {"value": v, "frequency": f}
                    for v, f in analysis.string_stats.top_values
                ],
                "avg_length": analysis.string_stats.avg_length,
                "min_length": analysis.string_stats.min_length,
                "max_length": analysis.string_stats.max_length,
                "all_uppercase": analysis.string_stats.all_uppercase,
                "contains_numbers": analysis.string_stats.contains_numbers,
            }

        return json.dumps(result)

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in analyze_column")
        return json.dumps({"error": f"Failed to analyze column: {str(e)}"})


# =============================================================================
# Documentation Cache Tools (User Story 6)
# =============================================================================


@mcp.tool()
async def export_documentation(
    connection_id: str,
    output_dir: str | None = None,
    include_sample_data: bool = False,
    include_inferred_relationships: bool = True,
) -> str:
    """Export database documentation to local markdown files.

    Generates a complete documentation cache including database overview,
    schema descriptions, table details, and relationship information.
    This cache can be loaded in future sessions to reduce discovery queries.

    Args:
        connection_id: Connection ID from connect_database
        output_dir: Custom output directory (default: docs/[connection_id])
        include_sample_data: Include sample data in table docs (default: False)
        include_inferred_relationships: Include inferred FKs (default: True)

    Returns:
        JSON string with export results including files_created and total_size_bytes
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)

        # Import here to avoid circular imports
        from src.cache.storage import DocumentationStorage
        from src.inference.relationships import ForeignKeyInferencer
        from src.models.relationship import DeclaredFK

        storage = DocumentationStorage()

        # Get database name from connection
        connection = conn_manager.get_connection(connection_id)
        database_name = connection.database

        # Gather all metadata
        schemas = metadata_svc.list_schemas(connection_id=connection_id)

        # Build tables dict by schema
        tables_dict: dict[str, list] = {}
        columns_dict: dict[str, list] = {}
        indexes_dict: dict[str, list] = {}

        for schema in schemas:
            schema_tables, _ = metadata_svc.list_tables(
                schema_name=schema.schema_name,
                connection_id=connection_id,
            )
            tables_dict[schema.schema_name] = schema_tables

            for table in schema_tables:
                table_id = table.table_id
                columns_dict[table_id] = metadata_svc.get_columns(
                    table.table_name, schema.schema_name
                )
                indexes_dict[table_id] = metadata_svc.get_indexes(
                    table.table_name, schema.schema_name
                )

        # Get declared foreign keys
        declared_fks: list[DeclaredFK] = []
        for schema in schemas:
            for table in tables_dict.get(schema.schema_name, []):
                fks = metadata_svc.get_foreign_keys(table.table_name, schema.schema_name)
                declared_fks.extend(fks)

        # Get inferred relationships if requested
        inferred_fks = []
        if include_inferred_relationships:
            inferencer = ForeignKeyInferencer(engine, threshold=0.50)
            for schema in schemas:
                for table in tables_dict.get(schema.schema_name, []):
                    try:
                        inferred, _ = inferencer.infer_relationships(
                            table_name=table.table_name,
                            schema_name=schema.schema_name,
                            max_candidates=10,
                        )
                        inferred_fks.extend(inferred)
                    except Exception as e:
                        logger.warning(f"Failed to infer relationships for {schema.schema_name}.{table.table_name}: {e}")

        # Get sample data if requested
        sample_data_dict: dict[str, list] = {}
        if include_sample_data:
            from src.db.query import QueryService
            query_svc = QueryService(engine)
            for schema in schemas:
                for table in tables_dict.get(schema.schema_name, []):
                    try:
                        sample = query_svc.get_sample_data(
                            table_name=table.table_name,
                            schema_name=schema.schema_name,
                            sample_size=3,
                        )
                        sample_data_dict[table.table_id] = sample.rows
                    except Exception as e:
                        logger.warning(f"Failed to get sample for {schema.schema_name}.{table.table_name}: {e}")

        # Export documentation
        cache = storage.export_documentation(
            connection_id=connection_id,
            database_name=database_name,
            schemas=schemas,
            tables=tables_dict,
            columns=columns_dict,
            indexes=indexes_dict,
            declared_fks=declared_fks,
            inferred_fks=inferred_fks,
            include_sample_data=include_sample_data,
            sample_data=sample_data_dict if include_sample_data else None,
            include_inferred_relationships=include_inferred_relationships,
            output_dir=output_dir,
        )

        # Get file list from metadata
        metadata = storage.get_cache_metadata(connection_id)
        files_created = metadata.get("files_created", []) if metadata else []
        total_size = metadata.get("total_size_bytes", 0) if metadata else 0
        nfr_003_warning = metadata.get("nfr_003_warning") if metadata else None

        logger.info(f"Exported documentation for {database_name}: {len(files_created)} files, {total_size} bytes")

        response = {
            "status": "success",
            "cache_dir": cache.cache_dir,
            "files_created": files_created,
            "total_size_bytes": total_size,
            "schema_hash": cache.schema_hash,
            "entity_counts": {
                "schemas": len(schemas),
                "tables": sum(len(t) for t in tables_dict.values()),
                "declared_fks": len(declared_fks),
                "inferred_fks": len(inferred_fks),
            },
        }

        # T135: Include NFR-003 warning if size limit exceeded
        if nfr_003_warning:
            response["warning"] = nfr_003_warning

        return json.dumps(response)

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in export_documentation")
        return json.dumps({"error": f"Failed to export documentation: {str(e)}"})


@mcp.tool()
async def load_cached_docs(connection_id: str) -> str:
    """Load previously cached database documentation.

    Retrieves cached documentation from markdown files generated by
    export_documentation. Returns entity counts and cache age for
    quick validation without querying the database.

    Args:
        connection_id: Connection ID to load cache for

    Returns:
        JSON string with cached documentation summary including:
        - database_name: Name of the cached database
        - schemas: List of schema summaries
        - entity_counts: Counts of schemas, tables, and relationships
        - cache_age_days: Days since cache was created
        - schema_hash: Hash for drift detection
    """
    try:
        from src.cache.storage import DocumentationStorage

        storage = DocumentationStorage()

        if not storage.cache_exists(connection_id):
            return json.dumps({
                "error": f"No cached documentation found for connection: {connection_id}",
                "hint": "Use export_documentation to create a cache first",
            })

        cached = storage.load_cached_docs(connection_id)

        return json.dumps({
            "status": "loaded",
            "connection_id": connection_id,
            "database_name": cached.get("database_name"),
            "schemas": [
                {
                    "schema_name": s.get("schema_name"),
                    "table_count": s.get("table_count"),
                    "view_count": s.get("view_count"),
                }
                for s in cached.get("schemas", [])
            ],
            "entity_counts": cached.get("entity_counts"),
            "cache_age_days": cached.get("cache_age_days"),
            "schema_hash": cached.get("schema_hash"),
        })

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in load_cached_docs")
        return json.dumps({"error": f"Failed to load cached docs: {str(e)}"})


@mcp.tool()
async def check_drift(
    connection_id: str,
    auto_refresh: bool = False,
) -> str:
    """Check for schema drift between cached docs and current database.

    Compares the cached documentation hash with the current database schema
    to detect added, removed, or modified tables.

    Args:
        connection_id: Connection ID from connect_database
        auto_refresh: If True and drift detected, automatically export new docs (default: False)

    Returns:
        JSON string with drift detection results including:
        - drift_detected: Whether changes were found
        - added_tables: Tables present now but not in cache
        - removed_tables: Tables in cache but not present now
        - summary: Human-readable summary of changes
    """
    try:
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)

        from src.cache.drift import DriftDetector
        from src.cache.storage import DocumentationStorage

        storage = DocumentationStorage()
        detector = DriftDetector(storage)

        # Get current schema state
        schemas = metadata_svc.list_schemas(connection_id=connection_id)
        tables_dict: dict[str, list] = {}
        for schema in schemas:
            tables, _ = metadata_svc.list_tables(
                schema_name=schema.schema_name,
                connection_id=connection_id,
            )
            tables_dict[schema.schema_name] = tables

        # Check for drift
        result = detector.check_drift(
            connection_id=connection_id,
            current_schemas=schemas,
            current_tables=tables_dict,
        )

        response = result.to_dict()

        # Auto-refresh if requested and drift detected
        if auto_refresh and result.drift_detected:
            # Call export_documentation internally
            export_result = await export_documentation(
                connection_id=connection_id,
                include_inferred_relationships=True,
            )
            export_data = json.loads(export_result)
            response["auto_refreshed"] = export_data.get("status") == "success"
            response["new_cache_dir"] = export_data.get("cache_dir")

        return json.dumps(response)

    except ValueError as e:
        return json.dumps({"error": str(e)})
    except Exception as e:
        logger.exception("Error in check_drift")
        return json.dumps({"error": f"Failed to check drift: {str(e)}"})


# =============================================================================
# Query Execution Tools (User Story 7)
# =============================================================================


@mcp.tool()
async def execute_query(
    connection_id: str,
    query_text: str,
    row_limit: int = 1000,
) -> str:
    """Execute a SQL SELECT query and return results.

    Executes ad-hoc SELECT queries with automatic row limiting for safety.
    Write operations (INSERT, UPDATE, DELETE) are blocked by default.
    Results are returned as a structured JSON with columns and rows.

    Large text values (>1000 chars) and binary data are automatically truncated
    to keep responses token-efficient.

    Args:
        connection_id: Connection ID from connect_database
        query_text: SQL query to execute (SELECT only by default)
        row_limit: Maximum rows to return, 1-10000 (default: 1000)

    Returns:
        JSON string with query results including:
        - status: 'success', 'blocked', or 'error'
        - query_id: Unique identifier for this execution
        - query_type: Detected query type (select, insert, update, delete, other)
        - columns: List of column names (for SELECT)
        - rows: Array of row objects (for SELECT)
        - rows_returned: Number of rows in the response
        - rows_available: Total rows available (if limit was applied)
        - limited: Whether results were truncated due to row_limit
        - execution_time_ms: Query execution time in milliseconds
        - error_message: Error details if status is 'error' or 'blocked'
    """
    try:
        # Validate row_limit
        if row_limit < 1:
            return json.dumps({
                "status": "error",
                "error_message": "row_limit must be at least 1",
            })
        if row_limit > 10000:
            return json.dumps({
                "status": "error",
                "error_message": "row_limit cannot exceed 10000",
            })

        # Validate query_text
        if not query_text or not query_text.strip():
            return json.dumps({
                "status": "error",
                "error_message": "query_text is required and cannot be empty",
            })

        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        query_svc = QueryService(engine)

        # Execute query
        query = query_svc.execute_query(
            connection_id=connection_id,
            query_text=query_text,
            row_limit=row_limit,
            allow_write=False,  # Always block write operations
        )

        # Get formatted results
        result = query_svc.get_query_results(query)

        return json.dumps(result)

    except ValueError as e:
        return json.dumps({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        logger.exception("Error in execute_query")
        return json.dumps({
            "status": "error",
            "error_message": f"Query execution failed: {type(e).__name__}: {str(e)}",
        })


# =============================================================================
# Server Entry Point
# =============================================================================


def main():
    """Run the MCP server on stdio transport."""
    logger.info("Starting dbmcp MCP server")
    mcp.run(transport="stdio")


if __name__ == "__main__":
    main()
