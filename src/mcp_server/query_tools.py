"""Query and data sampling MCP tools.

Tools: get_sample_data, execute_query
"""

import asyncio

from src.db.metadata import MetadataService
from src.db.query import QueryService
from src.mcp_server.server import get_connection_manager, logger, mcp
from src.models.schema import SamplingMethod
from src.serialization import encode_response

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
        TOON-encoded string with sample rows and metadata:

            status: "success" | "error"
            sample_id: string                  // on success only
            table_id: string                   // on success only
            sample_size: int                   // on success only
            actual_rows_returned: int          // on success only
            sampling_method: "top" | "tablesample" | "modulo"  // on success only
            rows: list of object               // on success only
            truncated_columns: list of string  // on success only
            sampled_at: ISO 8601 string        // on success only
            error_message: string              // on error only
    """
    # Validate parameters (fast, no I/O)
    if sample_size < 1 or sample_size > 1000:
        return encode_response({
            "status": "error",
            "error_message": "sample_size must be between 1 and 1000",
        })

    valid_methods = ["top", "tablesample", "modulo"]
    if sampling_method not in valid_methods:
        return encode_response({
            "status": "error",
            "error_message": f"sampling_method must be one of: {valid_methods}",
        })

    try:
        method_enum = SamplingMethod(sampling_method.lower())
    except ValueError:
        return encode_response({
            "status": "error",
            "error_message": f"Invalid sampling_method '{sampling_method}'. Use 'top', 'tablesample', or 'modulo'.",
        })

    def _sync_work():
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        metadata_svc = MetadataService(engine)
        query_svc = QueryService(engine, metadata_service=metadata_svc)

        sample = query_svc.get_sample_data(
            table_name=table_name,
            schema_name=schema_name,
            sample_size=sample_size,
            sampling_method=method_enum,
            columns=columns,
        )

        return {
            "status": "success",
            "sample_id": sample.sample_id,
            "table_id": sample.table_id,
            "sample_size": sample.sample_size,
            "actual_rows_returned": len(sample.rows),
            "sampling_method": sample.sampling_method.value,
            "rows": sample.rows,
            "truncated_columns": sample.truncated_columns,
            "sampled_at": sample.sampled_at.isoformat(),
        }

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({"status": "error", "error_message": str(e)})
    except Exception as e:
        logger.exception("Error in get_sample_data")
        return encode_response({"status": "error", "error_message": f"Failed to get sample data: {str(e)}"})


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
    Write operations (INSERT, UPDATE, DELETE) are blocked.
    Results are returned as a structured JSON with columns and rows.

    Large text values (>1000 chars) and binary data are automatically truncated
    to keep responses token-efficient.

    Args:
        connection_id: Connection ID from connect_database
        query_text: SQL query to execute (SELECT only)
        row_limit: Maximum rows to return, 1-10000 (default: 1000)

    Returns:
        TOON-encoded string with query results:

            status: "success" | "blocked" | "error"
            query_id: string                   // on success only
            query_type: string                 // on success only
            columns: list of string            // on success only
            rows: list of object               // on success only
            rows_returned: int                 // on success only
            rows_available: int                // on success only
            limited: bool                      // on success only
            execution_time_ms: float           // on success only
            error_message: string              // on error/blocked only
    """
    # Validate parameters (fast, no I/O)
    if row_limit < 1:
        return encode_response({
            "status": "error",
            "error_message": "row_limit must be at least 1",
        })
    if row_limit > 10000:
        return encode_response({
            "status": "error",
            "error_message": "row_limit cannot exceed 10000",
        })

    if not query_text or not query_text.strip():
        return encode_response({
            "status": "error",
            "error_message": "query_text is required and cannot be empty",
        })

    def _sync_work():
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        query_svc = QueryService(engine)

        query = query_svc.execute_query(
            connection_id=connection_id,
            query_text=query_text,
            row_limit=row_limit,
            allow_write=False,
        )

        return query_svc.get_query_results(query)

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        logger.exception("Error in execute_query")
        return encode_response({
            "status": "error",
            "error_message": f"Query execution failed: {type(e).__name__}: {str(e)}",
        })
