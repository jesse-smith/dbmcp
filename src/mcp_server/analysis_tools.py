"""MCP tools for data-exposure analysis.

Provides three analysis tools:
- get_column_info: Per-column statistical profiles
- find_pk_candidates: Primary key candidate discovery
- find_fk_candidates: Foreign key candidate search

All tools expose raw statistics and structural metadata only — no interpretation.
"""

import asyncio

from sqlalchemy import inspect
from sqlalchemy.exc import SQLAlchemyError

from src.analysis._sql import CatalogAwareReflector
from src.analysis.column_stats import ColumnStatsCollector
from src.analysis.fk_candidates import FKCandidateSearch
from src.analysis.pk_discovery import PKDiscovery
from src.db.connection import _classify_db_error
from src.db.identifiers import resolve_identifier
from src.mcp_server._errors import format_unexpected_error
from src.mcp_server.server import get_connection_manager, mcp
from src.serialization import encode_response


@mcp.tool()
async def get_column_info(
    connection_id: str,
    table_name: str,
    schema_name: str | None = None,
    columns: list[str] | None = None,
    column_pattern: str | None = None,
    sample_size: int = 10,
    catalog: str | None = None,
) -> str:
    """Retrieve per-column statistical profiles for a table.

    **EXPERIMENTAL** — Statistics are based on common practices but have not been
    battle-tested for utility. Use as a starting point for investigation, not as
    definitive answers.

    Computes row counts, distinct counts, null counts/percentages, and type-specific
    statistics for each column. Numeric columns get min/max/mean/stddev. Datetime
    columns get min/max dates, range in days, and whether a time component is present.
    String columns get min/max/avg length and a sample of top frequent values.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Name of the table. May be dotted (e.g. 'schema.table' or
            'catalog.schema.table') and is resolved against the dialect.
        schema_name: Schema name. Defaults to the dialect's default schema
            (e.g. 'dbo' on MSSQL) when omitted.
        columns: Explicit list of column names to analyze (takes precedence over pattern)
        column_pattern: SQL LIKE pattern to filter column names (e.g., '%_id')
        sample_size: Number of top frequent value samples for string columns (default: 10)
        catalog: Optional Databricks catalog name. Rejected on non-Databricks
            dialects (returns an error response). On Databricks the catalog is
            threaded end-to-end: the existence check and column statistics are
            computed against the requested catalog (cross-catalog supported via
            catalog-scoped reflection — IDENT-08).

    Returns:
        TOON-encoded string with status, table/schema metadata, and column statistics:

            status: "success" | "error"
            table_name: string                 // on success only
            schema_name: string                // on success only
            total_columns_analyzed: int        // on success only
            columns: list                      // on success only
                column_name: string
                data_type: string
                total_rows: int
                distinct_count: int
                null_count: int
                null_percentage: float
                numeric_stats: object          // numeric columns only
                    min_value: float | null
                    max_value: float | null
                    mean_value: float | null
                    std_dev: float | null
                datetime_stats: object         // datetime columns only
                    min_date: ISO 8601 string | null
                    max_date: ISO 8601 string | null
                    date_range_days: int | null
                    has_time_component: bool
                string_stats: object           // string columns only
                    min_length: int | null
                    max_length: int | null
                    avg_length: float | null
                    sample_values: list of [string, int] pairs
            error_message: string              // on error only

    Error conditions:
        - Invalid connection_id: returns status "error" with error_message
        - Table not found: returns status "error" with error_message
        - Column not found (explicit list): returns status "error" with error_message
        - No columns match pattern: returns status "success" with empty columns list
    """
    def _sync_work():
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        dialect = conn_manager.get_dialect(connection_id)
        # Resolve + validate the identifier at the boundary (D-03). The resolver
        # GATES catalog (D-07): a catalog supplied on MSSQL/generic raises
        # ValueError -> error response below. On Databricks the resolved catalog
        # is threaded end-to-end (IDENT-08): cross-catalog existence check +
        # catalog-scoped column statistics, no default-catalog binding required.
        resolved = resolve_identifier(table_name, schema_name, catalog, dialect)
        resolved_table = resolved.table
        resolved_schema = resolved.schema
        cross_catalog = (
            bool(resolved.catalog)
            and dialect is not None
            and dialect.name == "databricks"
        )

        with engine.connect() as connection:
            inspector = inspect(engine)

            # Table existence check. For Databricks cross-catalog access use the
            # catalog-aware MetadataService path (mirrors metadata.py:table_exists,
            # SHOW TABLES IN catalog.schema); otherwise the dialect-agnostic
            # Inspector path bound to the default catalog.
            if cross_catalog:
                from src.db.metadata import MetadataService

                metadata_svc = MetadataService(engine, dialect=dialect)
                if not metadata_svc.table_exists(
                    resolved_table, resolved_schema, catalog=resolved.catalog
                ):
                    return {
                        "status": "error",
                        "error_message": (
                            f"Table '{resolved_schema}.{resolved_table}' not found"
                        ),
                    }
            else:
                table_names = inspector.get_table_names(schema=resolved_schema)
                if resolved_table not in table_names:
                    # Also check views
                    view_names = inspector.get_view_names(schema=resolved_schema)
                    if resolved_table not in view_names:
                        return {
                            "status": "error",
                            "error_message": f"Table '{resolved_table}' not found in schema '{resolved_schema}'",
                        }

            collector = ColumnStatsCollector(
                connection=connection,
                schema_name=resolved_schema,
                table_name=resolved_table,
                dialect=dialect,
                inspector=inspector,
                catalog=resolved.catalog if cross_catalog else None,
            )

            column_stats = collector.get_columns_info(
                columns=columns,
                column_pattern=column_pattern,
                sample_size=sample_size,
            )

            return {
                "status": "success",
                "table_name": resolved_table,
                "schema_name": resolved_schema,
                "total_columns_analyzed": len(column_stats),
                "columns": [stat.to_dict() for stat in column_stats],
            }

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = format_unexpected_error(e, include_type=False)
        return encode_response({
            "status": "error",
            "error_message": error_msg,
        })


@mcp.tool()
async def find_pk_candidates(
    connection_id: str,
    table_name: str,
    schema_name: str | None = None,
    type_filter: list[str] | None = None,
    catalog: str | None = None,
) -> str:
    """Identify columns that meet primary key candidacy criteria.

    **EXPERIMENTAL** — Results are based on common heuristics but have not been
    battle-tested for utility. They may contain false positives or exclude valid
    candidates. Use as a starting point for investigation, not as definitive answers.

    Discovers PK candidates via two approaches:
    1. Constraint-backed: Columns with declared PK or UNIQUE constraints
    2. Structural: Columns that are unique, non-null, and match the type filter

    Does not detect composite keys. Structural uniqueness checks query the full table
    and may be slow on very large tables.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Table to search for PK candidates. May be dotted (e.g.
            'schema.table' or 'catalog.schema.table') and is resolved against
            the dialect.
        schema_name: Schema name. Defaults to the dialect's default schema
            (e.g. 'dbo' on MSSQL) when omitted.
        type_filter: SQL types considered for structural PK candidacy.
            Default: ["int", "bigint", "smallint", "tinyint", "uniqueidentifier"].
            Set to empty list to disable type filtering.
        catalog: Optional Databricks catalog name. Rejected on non-Databricks
            dialects (returns an error response). On Databricks the catalog is
            threaded end-to-end (IDENT-08): the existence check and PK discovery
            run against the requested catalog via catalog-scoped reflection
            (cross-catalog supported — no default-catalog binding required).

    Returns:
        TOON-encoded string with status, table/schema metadata, and candidates list:

            status: "success" | "error"
            table_name: string                 // on success only
            schema_name: string                // on success only
            candidates: list                   // on success only
                column_name: string
                data_type: string
                is_constraint_backed: bool
                constraint_type: "PRIMARY KEY" | "UNIQUE" | null
                is_unique: bool                // all values distinct
                is_non_null: bool              // no nulls
                is_pk_type: bool               // data_type matches type_filter
            error_message: string              // on error only

    Error conditions:
        - Invalid connection_id: returns status "error" with error_message
        - Table not found: returns status "error" with error_message
        - No candidates found: returns status "success" with empty candidates list
    """
    def _sync_work():
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        dialect = conn_manager.get_dialect(connection_id)
        # Resolve + validate the identifier at the boundary (D-03/D-14). The
        # resolver GATES catalog (D-07): a catalog supplied on MSSQL/generic
        # raises ValueError -> error response below. On Databricks the resolved
        # catalog is threaded end-to-end (IDENT-08): cross-catalog existence
        # check + catalog-scoped PK discovery, no default-catalog binding.
        resolved = resolve_identifier(table_name, schema_name, catalog, dialect)
        resolved_table = resolved.table
        resolved_schema = resolved.schema
        cross_catalog = (
            bool(resolved.catalog)
            and dialect is not None
            and dialect.name == "databricks"
        )

        with engine.connect() as connection:
            inspector = inspect(engine)

            # Table existence check. Cross-catalog Databricks uses the
            # catalog-aware MetadataService path (SHOW TABLES IN catalog.schema,
            # mirrors get_column_info); otherwise the dialect-agnostic Inspector.
            if cross_catalog:
                from src.db.metadata import MetadataService

                metadata_svc = MetadataService(engine, dialect=dialect)
                if not metadata_svc.table_exists(
                    resolved_table, resolved_schema, catalog=resolved.catalog
                ):
                    return {
                        "status": "error",
                        "error_message": (
                            f"Table '{resolved_schema}.{resolved_table}' not found"
                        ),
                    }
            else:
                table_names = inspector.get_table_names(schema=resolved_schema)
                if resolved_table not in table_names:
                    view_names = inspector.get_view_names(schema=resolved_schema)
                    if resolved_table not in view_names:
                        return {
                            "status": "error",
                            "error_message": f"Table '{resolved_table}' not found in schema '{resolved_schema}'",
                        }

            discovery = PKDiscovery(
                connection=connection,
                schema_name=resolved_schema,
                table_name=resolved_table,
                dialect=dialect,
                inspector=inspector,
                catalog=resolved.catalog if cross_catalog else None,
            )

            candidates = discovery.find_candidates(type_filter=type_filter)

            return {
                "status": "success",
                "table_name": resolved_table,
                "schema_name": resolved_schema,
                "candidates": [c.to_dict() for c in candidates],
            }

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = format_unexpected_error(e, include_type=False)
        return encode_response({
            "status": "error",
            "error_message": error_msg,
        })


@mcp.tool()
async def find_fk_candidates(
    connection_id: str,
    table_name: str,
    column_name: str,
    schema_name: str | None = None,
    target_schema: str | None = None,
    target_tables: list[str] | None = None,
    target_table_pattern: str | None = None,
    pk_candidates_only: bool = True,
    include_overlap: bool = False,
    limit: int = 100,
    catalog: str | None = None,
) -> str:
    """Discover potential foreign key relationships for a source column.

    **EXPERIMENTAL** — Results are based on common heuristics but have not been
    battle-tested for utility. They may contain false positives or exclude valid
    candidates. Use as a starting point for investigation, not as definitive answers.

    Searches for target columns that could be the referenced side of a foreign key
    relationship. Matches by compatible data type. By default only considers target
    columns that are PK candidates (constraint-backed or structurally unique);
    set pk_candidates_only=False to broaden the search to all type-compatible columns.
    Optionally computes value overlap between source and target via SQL INTERSECT.

    Args:
        connection_id: Connection ID from connect_database
        table_name: Source table name. May be dotted (e.g. 'schema.table' or
            'catalog.schema.table') and is resolved against the dialect.
        column_name: Source column name
        schema_name: Source schema name. Defaults to the dialect's default
            schema (e.g. 'dbo' on MSSQL) when omitted.
        target_schema: Filter targets to this schema. Defaults to source schema.
        target_tables: Explicit list of target table names
        target_table_pattern: SQL LIKE pattern for target table names
        pk_candidates_only: Only compare against PK-candidate columns (default: True)
        include_overlap: Compute value overlap metrics (default: False)
        limit: Maximum candidates to return, 0 = no limit (default: 100)
        catalog: Optional Databricks catalog name. Rejected on non-Databricks
            dialects (returns an error response). On Databricks the catalog is
            threaded end-to-end (IDENT-08): the existence check, source-column
            type reflection, and FK search run against the requested catalog via
            catalog-scoped reflection (cross-catalog supported — no
            default-catalog binding required).

    Returns:
        TOON-encoded string with status, source metadata, candidates list, and search info:

            status: "success" | "error"
            source: object                     // on success only
                column_name: string
                table_name: string
                schema_name: string
                data_type: string
            candidates: list                   // on success only
                source_column: string
                source_table: string
                source_schema: string
                source_data_type: string
                target_column: string
                target_table: string
                target_schema: string
                target_data_type: string
                target_is_primary_key: bool
                target_is_unique: bool
                target_is_nullable: bool
                target_has_index: bool
                overlap_count: int             // only when include_overlap=True
                overlap_percentage: float      // only when include_overlap=True
            total_found: int                   // on success only
            was_limited: bool                  // on success only
            search_scope: string               // on success only
            error_message: string              // on error only

    Error conditions:
        - Invalid connection_id: returns status "error" with error_message
        - Table not found: returns status "error" with error_message
        - Column not found: returns status "error" with error_message
        - No candidates: returns status "success" with empty candidates list
    """
    def _sync_work():
        conn_manager = get_connection_manager()
        engine = conn_manager.get_engine(connection_id)
        dialect = conn_manager.get_dialect(connection_id)
        # Resolve + validate the identifier at the boundary (D-03/D-14). The
        # resolver GATES catalog (D-07): a catalog supplied on MSSQL/generic
        # raises ValueError -> error response below. On Databricks the resolved
        # catalog is threaded end-to-end (IDENT-08): cross-catalog existence
        # check, catalog-scoped source-column reflection, and catalog-scoped FK
        # search — no default-catalog binding required.
        resolved = resolve_identifier(table_name, schema_name, catalog, dialect)
        resolved_table = resolved.table
        resolved_schema = resolved.schema
        cross_catalog = (
            bool(resolved.catalog)
            and dialect is not None
            and dialect.name == "databricks"
        )

        with engine.connect() as connection:
            inspector = inspect(engine)

            # Table existence check. Cross-catalog Databricks uses the
            # catalog-aware MetadataService path (mirrors get_column_info);
            # otherwise the dialect-agnostic Inspector.
            if cross_catalog:
                from src.db.metadata import MetadataService

                metadata_svc = MetadataService(engine, dialect=dialect)
                if not metadata_svc.table_exists(
                    resolved_table, resolved_schema, catalog=resolved.catalog
                ):
                    return {
                        "status": "error",
                        "error_message": (
                            f"Table '{resolved_schema}.{resolved_table}' not found"
                        ),
                    }
            else:
                table_names = inspector.get_table_names(schema=resolved_schema)
                if resolved_table not in table_names:
                    view_names = inspector.get_view_names(schema=resolved_schema)
                    if resolved_table not in view_names:
                        return {
                            "status": "error",
                            "error_message": f"Table '{resolved_table}' not found in schema '{resolved_schema}'",
                        }

            # Source-column existence and type. Cross-catalog Databricks reads
            # the type via catalog-scoped DESCRIBE TABLE (CatalogAwareReflector,
            # data_type already a string); otherwise the dialect-agnostic
            # Inspector path bound to the default catalog.
            if cross_catalog:
                reflector = CatalogAwareReflector(connection, dialect)
                columns = reflector.reflect_columns(
                    resolved.catalog, resolved_schema, resolved_table
                )
                col_info = next(
                    (c for c in columns if c["name"] == column_name), None
                )
                if col_info is None:
                    return {
                        "status": "error",
                        "error_message": f"Column '{column_name}' not found in table '{resolved_schema}.{resolved_table}'",
                    }
                source_data_type = col_info["data_type"]
            else:
                columns = inspector.get_columns(resolved_table, schema=resolved_schema)
                col_info = next(
                    (c for c in columns if c["name"] == column_name), None
                )
                if col_info is None:
                    return {
                        "status": "error",
                        "error_message": f"Column '{column_name}' not found in table '{resolved_schema}.{resolved_table}'",
                    }
                source_data_type = str(col_info["type"])

            search = FKCandidateSearch(
                connection=connection,
                source_schema=resolved_schema,
                source_table=resolved_table,
                source_column=column_name,
                source_data_type=source_data_type,
                dialect=dialect,
                inspector=inspector,
                catalog=resolved.catalog if cross_catalog else None,
            )

            fk_result = search.find_candidates(
                target_schema=target_schema,
                target_tables=target_tables,
                target_table_pattern=target_table_pattern,
                pk_candidates_only=pk_candidates_only,
                include_overlap=include_overlap,
                limit=limit,
            )

            return {
                "status": "success",
                "source": {
                    "column_name": column_name,
                    "table_name": resolved_table,
                    "schema_name": resolved_schema,
                    "data_type": source_data_type,
                },
                "candidates": [c.to_dict() for c in fk_result.candidates],
                "total_found": fk_result.total_found,
                "was_limited": fk_result.was_limited,
                "search_scope": fk_result.search_scope,
            }

    try:
        result = await asyncio.to_thread(_sync_work)
        return encode_response(result)
    except ValueError as e:
        return encode_response({
            "status": "error",
            "error_message": str(e),
        })
    except Exception as e:
        if isinstance(e, SQLAlchemyError):
            _cat, guidance = _classify_db_error(e)
            error_msg = f"{guidance} ({e})"
        else:
            error_msg = format_unexpected_error(e, include_type=False)
        return encode_response({
            "status": "error",
            "error_message": error_msg,
        })
