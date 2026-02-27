"""Documentation cache storage module.

Handles reading and writing cached database documentation as markdown files.
Cache structure:
    docs/[connection_id]/
    ├── overview.md           # Database summary, schema list
    ├── schemas/
    │   ├── dbo.md           # Tables in dbo schema
    │   └── sales.md
    ├── tables/
    │   ├── Customers.md     # Full table metadata
    │   └── Orders.md
    └── relationships.md      # All inferred and declared relationships

T135: Includes NFR-003 compliance check (warn if >1MB for 500 tables).
"""

import hashlib
import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from src.cache.doc_generator import DocumentationGenerator
from src.models.relationship import DeclaredFK, InferredFK
from src.models.schema import (
    Column,
    DocumentationCache,
    Index,
    Schema,
    Table,
)

logger = logging.getLogger(__name__)

# Shared generator instance
_doc_generator = DocumentationGenerator()

# NFR-003: Documentation should be <1MB for 500 tables
NFR_003_SIZE_LIMIT_BYTES = 1_000_000  # 1MB
NFR_003_TABLE_THRESHOLD = 500


class DocumentationStorage:
    """Handles reading and writing documentation cache as markdown files."""

    # Default base directory for cache
    DEFAULT_BASE_DIR = Path("docs")

    def __init__(self, base_dir: Path | str | None = None):
        """Initialize storage with base directory.

        Args:
            base_dir: Base directory for documentation cache.
                     Defaults to 'docs/' in current directory.
        """
        self.base_dir = Path(base_dir) if base_dir else self.DEFAULT_BASE_DIR

    def get_cache_dir(self, connection_id: str) -> Path:
        """Get the cache directory for a connection."""
        return self.base_dir / connection_id

    def cache_exists(self, connection_id: str) -> bool:
        """Check if documentation cache exists for a connection."""
        cache_dir = self.get_cache_dir(connection_id)
        return cache_dir.exists() and (cache_dir / "overview.md").exists()

    # =========================================================================
    # Hash Computation
    # =========================================================================

    def compute_schema_hash(
        self, schemas: list[Schema], tables: dict[str, list[Table]]
    ) -> str:
        """Compute a hash of the database schema for drift detection.

        Args:
            schemas: List of Schema objects
            tables: Dict mapping schema_name to list of Table objects

        Returns:
            SHA-256 hash of sorted table.column names
        """
        # Build sorted list of "schema.table" names
        items = []
        for schema in sorted(schemas, key=lambda s: s.schema_name):
            schema_tables = tables.get(schema.schema_name, [])
            for table in sorted(schema_tables, key=lambda t: t.table_name):
                items.append(f"{schema.schema_name}.{table.table_name}")

        # Compute hash
        content = "\n".join(items)
        return hashlib.sha256(content.encode()).hexdigest()

    # =========================================================================
    # Writing Documentation
    # =========================================================================

    def export_documentation(
        self,
        connection_id: str,
        database_name: str,
        schemas: list[Schema],
        tables: dict[str, list[Table]],
        columns: dict[str, list[Column]],
        indexes: dict[str, list[Index]],
        declared_fks: list[DeclaredFK],
        inferred_fks: list[InferredFK],
        include_sample_data: bool = False,
        sample_data: dict[str, list[dict]] | None = None,
        include_inferred_relationships: bool = True,
        output_dir: Path | str | None = None,
    ) -> DocumentationCache:
        """Export database documentation to markdown files.

        Args:
            connection_id: Unique connection identifier
            database_name: Name of the database
            schemas: List of Schema objects
            tables: Dict mapping schema_name to list of Table objects
            columns: Dict mapping table_id to list of Column objects
            indexes: Dict mapping table_id to list of Index objects
            declared_fks: List of declared foreign keys
            inferred_fks: List of inferred foreign keys
            include_sample_data: Whether to include sample data in tables
            sample_data: Dict mapping table_id to sample rows
            include_inferred_relationships: Whether to include inferred FKs
            output_dir: Custom output directory (default: docs/[connection_id])

        Returns:
            DocumentationCache entity with metadata about exported files
        """
        # Determine output directory
        cache_dir = Path(output_dir) if output_dir else self.get_cache_dir(connection_id)
        cache_dir = cache_dir.resolve()
        cache_dir.mkdir(parents=True, exist_ok=True)

        # Track files created and total size
        files_created: list[str] = []
        total_size = 0

        # Determine the base for relative path computation
        # Use project root (base_dir.parent) if cache_dir is inside it, else use cache_dir's parent
        project_root = self.base_dir.parent.resolve()
        try:
            cache_dir.relative_to(project_root)
            rel_base = project_root
        except ValueError:
            rel_base = cache_dir.parent

        # Create subdirectories
        (cache_dir / "schemas").mkdir(exist_ok=True)
        (cache_dir / "tables").mkdir(exist_ok=True)

        # Compute schema hash
        schema_hash = self.compute_schema_hash(schemas, tables)

        # Generate overview.md
        overview_content = _doc_generator.generate_overview(
            database_name, schemas, tables, declared_fks, inferred_fks
        )
        overview_path = cache_dir / "overview.md"
        overview_path.write_text(overview_content)
        files_created.append(str(overview_path.relative_to(rel_base)))
        total_size += overview_path.stat().st_size

        # Generate schema markdown files
        for schema in schemas:
            schema_tables = tables.get(schema.schema_name, [])
            schema_content = _doc_generator.generate_schema_doc(schema, schema_tables)
            schema_path = cache_dir / "schemas" / f"{schema.schema_name}.md"
            schema_path.write_text(schema_content)
            files_created.append(str(schema_path.relative_to(rel_base)))
            total_size += schema_path.stat().st_size

        # Generate table markdown files
        for schema in schemas:
            schema_tables = tables.get(schema.schema_name, [])
            for table in schema_tables:
                table_columns = columns.get(table.table_id, [])
                table_indexes = indexes.get(table.table_id, [])
                table_sample = (
                    sample_data.get(table.table_id, [])
                    if include_sample_data and sample_data
                    else []
                )

                # Get relationships for this table
                table_declared = [
                    fk for fk in declared_fks if fk.source_table_id == table.table_id
                ]
                table_inferred = (
                    [fk for fk in inferred_fks if fk.source_table_id == table.table_id]
                    if include_inferred_relationships
                    else []
                )

                table_content = _doc_generator.generate_table_doc(
                    table,
                    table_columns,
                    table_indexes,
                    table_declared,
                    table_inferred,
                    table_sample,
                )
                table_path = cache_dir / "tables" / f"{schema.schema_name}.{table.table_name}.md"
                table_path.write_text(table_content)
                files_created.append(str(table_path.relative_to(rel_base)))
                total_size += table_path.stat().st_size

        # Generate relationships.md
        relationships_content = _doc_generator.generate_relationships_doc(
            declared_fks,
            inferred_fks if include_inferred_relationships else [],
        )
        relationships_path = cache_dir / "relationships.md"
        relationships_path.write_text(relationships_content)
        files_created.append(str(relationships_path.relative_to(rel_base)))
        total_size += relationships_path.stat().st_size

        # T135: NFR-003 compliance check
        total_table_count = sum(len(t) for t in tables.values())
        nfr_003_warning = None
        if total_table_count >= NFR_003_TABLE_THRESHOLD and total_size > NFR_003_SIZE_LIMIT_BYTES:
            nfr_003_warning = (
                f"NFR-003 WARNING: Documentation size ({total_size:,} bytes) exceeds "
                f"{NFR_003_SIZE_LIMIT_BYTES:,} byte limit for {total_table_count} tables. "
                f"Consider using summary mode or excluding sample data."
            )
            logger.warning(nfr_003_warning)
        elif total_size > NFR_003_SIZE_LIMIT_BYTES:
            # Still warn if size is large even for fewer tables
            nfr_003_warning = (
                f"Documentation size ({total_size:,} bytes) exceeds "
                f"{NFR_003_SIZE_LIMIT_BYTES:,} byte limit for {total_table_count} tables."
            )
            logger.info(nfr_003_warning)

        # Write metadata file for cache parsing
        metadata = {
            "connection_id": connection_id,
            "database_name": database_name,
            "schema_hash": schema_hash,
            "created_at": datetime.now().isoformat(),
            "files_created": files_created,
            "total_size_bytes": total_size,
            "include_sample_data": include_sample_data,
            "include_inferred_relationships": include_inferred_relationships,
            "nfr_003_warning": nfr_003_warning,
            "table_count": total_table_count,
        }
        metadata_path = cache_dir / ".cache_metadata.json"
        metadata_path.write_text(json.dumps(metadata, indent=2))

        # Return DocumentationCache entity
        return DocumentationCache(
            cache_id=connection_id,
            connection_id=connection_id,
            cache_dir=str(cache_dir),
            created_at=datetime.now(),
            last_updated=datetime.now(),
            schema_hash=schema_hash,
            drift_detected=False,
            drift_summary=None,
        )

    # =========================================================================
    # Reading Documentation
    # =========================================================================

    def load_cached_docs(
        self, connection_id: str
    ) -> dict[str, Any]:
        """Load cached documentation from markdown files.

        Args:
            connection_id: Connection ID to load cache for

        Returns:
            Dictionary with parsed cache data including:
            - schemas: List of Schema-like dicts
            - tables: List of Table-like dicts
            - relationships: Dict with declared and inferred FKs
            - cache_age_days: Days since cache was created
            - metadata: Cache metadata
        """
        cache_dir = self.get_cache_dir(connection_id)

        if not self.cache_exists(connection_id):
            raise ValueError(f"No cached documentation found for connection: {connection_id}")

        # Load metadata
        metadata_path = cache_dir / ".cache_metadata.json"
        if metadata_path.exists():
            metadata = json.loads(metadata_path.read_text())
        else:
            metadata = {}

        # Parse created_at for cache age
        created_at = metadata.get("created_at")
        if created_at:
            cache_date = datetime.fromisoformat(created_at)
            cache_age_days = (datetime.now() - cache_date).days
        else:
            cache_age_days = None

        # Verify overview file exists (used for cache validation)
        overview_path = cache_dir / "overview.md"
        _ = self._parse_overview(overview_path.read_text())

        # Parse schemas
        schemas = []
        schemas_dir = cache_dir / "schemas"
        if schemas_dir.exists():
            for schema_file in schemas_dir.glob("*.md"):
                schema_data = self._parse_schema_doc(schema_file.read_text())
                schemas.append(schema_data)

        # Parse tables
        tables = []
        tables_dir = cache_dir / "tables"
        if tables_dir.exists():
            for table_file in tables_dir.glob("*.md"):
                table_data = self._parse_table_doc(table_file.read_text())
                tables.append(table_data)

        # Parse relationships
        relationships_path = cache_dir / "relationships.md"
        relationships = {"declared": [], "inferred": []}
        if relationships_path.exists():
            relationships = self._parse_relationships_doc(relationships_path.read_text())

        return {
            "connection_id": connection_id,
            "database_name": metadata.get("database_name", "Unknown"),
            "schemas": schemas,
            "tables": tables,
            "relationships": relationships,
            "cache_age_days": cache_age_days,
            "schema_hash": metadata.get("schema_hash"),
            "entity_counts": {
                "schemas": len(schemas),
                "tables": len(tables),
                "declared_fks": len(relationships.get("declared", [])),
                "inferred_fks": len(relationships.get("inferred", [])),
            },
            "metadata": metadata,
        }

    def _parse_overview(self, content: str) -> dict[str, Any]:
        """Parse overview.md to extract high-level data."""
        data = {
            "database_name": None,
            "schema_count": 0,
            "table_count": 0,
        }

        # Extract database name from title
        title_match = re.search(r"^# Database: (.+)$", content, re.MULTILINE)
        if title_match:
            data["database_name"] = title_match.group(1)

        # Extract counts from summary
        schemas_match = re.search(r"\*\*Schemas\*\*: (\d+)", content)
        if schemas_match:
            data["schema_count"] = int(schemas_match.group(1))

        tables_match = re.search(r"\*\*Tables\*\*: (\d+)", content)
        if tables_match:
            data["table_count"] = int(tables_match.group(1))

        return data

    def _parse_schema_doc(self, content: str) -> dict[str, Any]:
        """Parse a schema markdown file."""
        data: dict[str, Any] = {
            "schema_name": None,
            "table_count": 0,
            "view_count": 0,
            "tables": [],
        }

        # Extract schema name from title
        title_match = re.search(r"^# Schema: (.+)$", content, re.MULTILINE)
        if title_match:
            data["schema_name"] = title_match.group(1)

        # Extract table/view counts
        counts_match = re.search(r"\*\*Tables\*\*: (\d+) \| \*\*Views\*\*: (\d+)", content)
        if counts_match:
            data["table_count"] = int(counts_match.group(1))
            data["view_count"] = int(counts_match.group(2))

        # Parse table rows from the table
        table_pattern = r"\| \[([^\]]+)\]\([^\)]+\) \| ([^|]+) \| ([^|]+) \| ([^|]+) \|"
        for match in re.finditer(table_pattern, content):
            table_name = match.group(1)
            row_count_str = match.group(2).strip().replace(",", "")
            has_pk = match.group(3).strip() == "Yes"

            row_count = int(row_count_str) if row_count_str != "N/A" else None

            data["tables"].append({
                "table_name": table_name,
                "row_count": row_count,
                "has_primary_key": has_pk,
            })

        return data

    def _parse_table_doc(self, content: str) -> dict[str, Any]:
        """Parse a table markdown file."""
        data: dict[str, Any] = {
            "schema_name": None,
            "table_name": None,
            "table_type": "table",
            "row_count": None,
            "has_primary_key": False,
            "columns": [],
            "indexes": [],
        }

        # Extract table name from title (format: schema.table)
        title_match = re.search(r"^# Table: ([^.]+)\.(.+)$", content, re.MULTILINE)
        if title_match:
            data["schema_name"] = title_match.group(1)
            data["table_name"] = title_match.group(2)

        # Extract table type
        type_match = re.search(r"\*\*Type\*\*: (Table|View)", content, re.IGNORECASE)
        if type_match:
            data["table_type"] = type_match.group(1).lower()

        # Extract row count
        row_match = re.search(r"\*\*Row Count\*\*: ([\d,]+|Unknown)", content)
        if row_match:
            count_str = row_match.group(1).replace(",", "")
            data["row_count"] = int(count_str) if count_str != "Unknown" else None

        # Extract primary key
        pk_match = re.search(r"\*\*Primary Key\*\*: (Yes|No)", content)
        if pk_match:
            data["has_primary_key"] = pk_match.group(1) == "Yes"

        # Parse columns section
        col_pattern = r"\| (\d+) \| `([^`]+)` \| ([^|]+) \| (Yes|No) \| (Yes)? \| (Yes)? \| ([^|]*) \|"
        for match in re.finditer(col_pattern, content):
            col_data = {
                "ordinal_position": int(match.group(1)),
                "column_name": match.group(2),
                "data_type": match.group(3).strip(),
                "is_nullable": match.group(4) == "Yes",
                "is_primary_key": match.group(5) == "Yes" if match.group(5) else False,
                "is_foreign_key": match.group(6) == "Yes" if match.group(6) else False,
                "default_value": match.group(7).strip() or None,
            }
            data["columns"].append(col_data)

        # Parse indexes section
        idx_pattern = r"\| `([^`]+)` \| ([^|]+) \| (Yes|No) \| (Yes|No) \|"
        in_indexes = False
        for line in content.split("\n"):
            if "## Indexes" in line:
                in_indexes = True
            elif line.startswith("## ") and in_indexes:
                in_indexes = False

            if in_indexes:
                idx_match = re.match(idx_pattern, line.strip())
                if idx_match:
                    data["indexes"].append({
                        "index_name": idx_match.group(1),
                        "columns": [c.strip() for c in idx_match.group(2).split(",")],
                        "is_unique": idx_match.group(3) == "Yes",
                        "is_clustered": idx_match.group(4) == "Yes",
                    })

        return data

    def _parse_relationships_doc(self, content: str) -> dict[str, list[dict]]:
        """Parse relationships.md to extract FK data."""
        result: dict[str, list[dict]] = {
            "declared": [],
            "inferred": [],
        }

        # Parse declared FKs
        decl_pattern = r"\| ([^|]+) \| `([^`]+)` \| ([^|]+) \| `([^`]+)` \| ([^|]+) \|"
        in_declared = False
        in_inferred = False

        for line in content.split("\n"):
            if "## Declared Foreign Keys" in line:
                in_declared = True
                in_inferred = False
            elif "## Inferred Relationships" in line:
                in_declared = False
                in_inferred = True

            match = re.match(decl_pattern, line.strip())
            if match and not line.strip().startswith("|---"):
                if in_declared:
                    result["declared"].append({
                        "source_table": match.group(1).strip(),
                        "source_column": match.group(2),
                        "target_table": match.group(3).strip(),
                        "target_column": match.group(4),
                        "on_delete": match.group(5).strip(),
                    })

        # Parse inferred FKs (different column count)
        inf_pattern = r"\| ([^|]+) \| `([^`]+)` \| ([^|]+) \| `([^`]+)` \| ([\d.]+%) \| ([^|]+) \|"
        in_inferred = False
        for line in content.split("\n"):
            if "## Inferred Relationships" in line:
                in_inferred = True
            elif line.startswith("## ") and in_inferred and "Inferred" not in line:
                in_inferred = False

            if in_inferred:
                match = re.match(inf_pattern, line.strip())
                if match:
                    confidence_str = match.group(5).rstrip("%")
                    confidence = float(confidence_str) / 100

                    result["inferred"].append({
                        "source_table": match.group(1).strip(),
                        "source_column": match.group(2),
                        "target_table": match.group(3).strip(),
                        "target_column": match.group(4),
                        "confidence_score": confidence,
                        "reasoning": match.group(6).strip(),
                    })

        return result

    def get_cache_metadata(self, connection_id: str) -> dict[str, Any] | None:
        """Get cache metadata without loading full documentation.

        Args:
            connection_id: Connection ID

        Returns:
            Cache metadata dict or None if cache doesn't exist
        """
        cache_dir = self.get_cache_dir(connection_id)
        metadata_path = cache_dir / ".cache_metadata.json"

        if not metadata_path.exists():
            return None

        return json.loads(metadata_path.read_text())
