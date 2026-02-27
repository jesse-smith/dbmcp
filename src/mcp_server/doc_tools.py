"""Documentation cache MCP tools.

Hidden: export_documentation, load_cached_docs, check_drift
"""

import json
from pathlib import Path

from src.db.metadata import MetadataService
from src.mcp_server.server import get_connection_manager, logger

# =============================================================================
# Documentation Cache Tools (User Story 6)
# =============================================================================


# @mcp.tool()  # Hidden: not useful in current form, kept for future refactoring
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
        from src.models.relationship import DeclaredFK, create_relationship_id

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
            # Paginate to collect ALL tables (default limit=100 would truncate)
            all_schema_tables: list = []
            offset = 0
            page_size = 1000
            while True:
                page_tables, pagination = metadata_svc.list_tables(
                    schema_name=schema.schema_name,
                    connection_id=connection_id,
                    limit=page_size,
                    offset=offset,
                )
                all_schema_tables.extend(page_tables)
                if not pagination.get("has_more", False):
                    break
                offset += page_size
            tables_dict[schema.schema_name] = all_schema_tables

            for table in all_schema_tables:
                table_id = table.table_id
                columns_dict[table_id] = metadata_svc.get_columns(
                    table.table_name, schema.schema_name
                )
                indexes_dict[table_id] = metadata_svc.get_indexes(
                    table.table_name, schema.schema_name
                )

        # Get declared foreign keys (convert raw dicts from SQLAlchemy to DeclaredFK objects)
        declared_fks: list[DeclaredFK] = []
        for schema in schemas:
            for table in tables_dict.get(schema.schema_name, []):
                raw_fks = metadata_svc.get_foreign_keys(table.table_name, schema.schema_name)
                for fk_dict in raw_fks:
                    # SQLAlchemy returns multi-column FKs as lists; create one DeclaredFK per column pair
                    source_cols = fk_dict.get("constrained_columns", [])
                    target_cols = fk_dict.get("referred_columns", [])
                    referred_schema = fk_dict.get("referred_schema") or schema.schema_name
                    referred_table = fk_dict.get("referred_table", "")
                    constraint_name = fk_dict.get("name", "")

                    for src_col, tgt_col in zip(source_cols, target_cols, strict=False):
                        rel_id = create_relationship_id(
                            table.table_id, src_col,
                            f"{referred_schema}.{referred_table}", tgt_col,
                        )
                        declared_fks.append(DeclaredFK(
                            relationship_id=rel_id,
                            source_table_id=table.table_id,
                            source_column=src_col,
                            target_table_id=f"{referred_schema}.{referred_table}",
                            target_column=tgt_col,
                            constraint_name=constraint_name,
                        ))

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

        # Get file list from metadata — read from the actual output directory
        if output_dir:
            metadata_path = Path(output_dir) / ".cache_metadata.json"
            if metadata_path.exists():
                metadata = json.loads(metadata_path.read_text())
            else:
                metadata = None
        else:
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


# @mcp.tool()  # Hidden: not useful in current form, kept for future refactoring
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


# @mcp.tool()  # Hidden: not useful in current form, kept for future refactoring
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
            # Preserve prior export settings from cache metadata
            prior_metadata = storage.get_cache_metadata(connection_id)
            prior_include_sample = prior_metadata.get("include_sample_data", False) if prior_metadata else False
            prior_include_inferred = prior_metadata.get("include_inferred_relationships", True) if prior_metadata else True

            # Call export_documentation internally with preserved settings
            export_result = await export_documentation(
                connection_id=connection_id,
                include_sample_data=prior_include_sample,
                include_inferred_relationships=prior_include_inferred,
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
