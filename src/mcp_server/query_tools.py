"""Query and data sampling MCP tools.

Tools: get_sample_data, execute_query
Hidden: analyze_column
"""

import json

from src.db.query import QueryService
from src.mcp_server.server import get_connection_manager, logger, mcp
from src.models.schema import SamplingMethod

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


# @mcp.tool()  # Hidden: not useful in current form, kept for future refactoring
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
