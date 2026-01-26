"""Schema drift detection module.

Compares cached documentation with current database state to detect changes.
Identifies added, removed, and modified tables/columns.
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.cache.storage import DocumentationStorage
from src.models.schema import Schema, Table


@dataclass
class DriftResult:
    """Result of schema drift detection.

    Attributes:
        drift_detected: Whether any drift was detected
        cached_hash: Hash from cached documentation
        current_hash: Hash computed from current schema
        added_tables: Tables present in current but not cached
        removed_tables: Tables present in cached but not current
        modified_tables: Tables with structural changes
        summary: Human-readable summary of changes
        checked_at: When drift check was performed
    """

    drift_detected: bool
    cached_hash: str
    current_hash: str
    added_tables: list[str] = field(default_factory=list)
    removed_tables: list[str] = field(default_factory=list)
    modified_tables: list[dict[str, Any]] = field(default_factory=list)
    summary: str = ""
    checked_at: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict[str, Any]:
        """Convert to dictionary for JSON serialization."""
        return {
            "drift_detected": self.drift_detected,
            "cached_hash": self.cached_hash,
            "current_hash": self.current_hash,
            "added_tables": self.added_tables,
            "removed_tables": self.removed_tables,
            "modified_tables": self.modified_tables,
            "summary": self.summary,
            "checked_at": self.checked_at.isoformat(),
        }


class DriftDetector:
    """Detects schema drift between cached docs and current database state."""

    def __init__(self, storage: DocumentationStorage | None = None):
        """Initialize drift detector.

        Args:
            storage: DocumentationStorage instance. If None, creates default.
        """
        self.storage = storage or DocumentationStorage()

    def check_drift(
        self,
        connection_id: str,
        current_schemas: list[Schema],
        current_tables: dict[str, list[Table]],
    ) -> DriftResult:
        """Check for schema drift between cache and current state.

        Args:
            connection_id: Connection ID to check cache for
            current_schemas: Current list of Schema objects
            current_tables: Current dict mapping schema_name to Table objects

        Returns:
            DriftResult with details of any detected changes
        """
        # Check if cache exists
        if not self.storage.cache_exists(connection_id):
            return DriftResult(
                drift_detected=True,
                cached_hash="",
                current_hash=self.storage.compute_schema_hash(current_schemas, current_tables),
                summary="No cached documentation exists",
            )

        # Load cached metadata
        cached_metadata = self.storage.get_cache_metadata(connection_id)
        if not cached_metadata:
            return DriftResult(
                drift_detected=True,
                cached_hash="",
                current_hash=self.storage.compute_schema_hash(current_schemas, current_tables),
                summary="Cache metadata missing",
            )

        cached_hash = cached_metadata.get("schema_hash", "")
        current_hash = self.storage.compute_schema_hash(current_schemas, current_tables)

        # Quick check: if hashes match, no drift
        if cached_hash == current_hash:
            return DriftResult(
                drift_detected=False,
                cached_hash=cached_hash,
                current_hash=current_hash,
                summary="No changes detected",
            )

        # Load cached documentation for detailed comparison
        cached_docs = self.storage.load_cached_docs(connection_id)

        # Build sets of table names for comparison
        cached_table_names = set()
        for schema_data in cached_docs.get("schemas", []):
            schema_name = schema_data.get("schema_name")
            for table_data in schema_data.get("tables", []):
                table_name = table_data.get("table_name")
                if schema_name and table_name:
                    cached_table_names.add(f"{schema_name}.{table_name}")

        current_table_names = set()
        for schema in current_schemas:
            schema_tables = current_tables.get(schema.schema_name, [])
            for table in schema_tables:
                current_table_names.add(f"{schema.schema_name}.{table.table_name}")

        # Identify changes
        added_tables = list(current_table_names - cached_table_names)
        removed_tables = list(cached_table_names - current_table_names)

        # Build summary
        summary_parts = []
        if added_tables:
            summary_parts.append(f"Added tables: {', '.join(sorted(added_tables))}")
        if removed_tables:
            summary_parts.append(f"Removed tables: {', '.join(sorted(removed_tables))}")

        if not summary_parts:
            # Hash changed but no table add/remove - must be structural changes
            summary_parts.append("Structural changes detected in existing tables")

        return DriftResult(
            drift_detected=True,
            cached_hash=cached_hash,
            current_hash=current_hash,
            added_tables=sorted(added_tables),
            removed_tables=sorted(removed_tables),
            summary="; ".join(summary_parts),
        )

    def generate_drift_report(self, drift_result: DriftResult) -> str:
        """Generate a human-readable drift report.

        Args:
            drift_result: Result from check_drift

        Returns:
            Formatted markdown report
        """
        lines = [
            "# Schema Drift Report",
            "",
            f"**Checked**: {drift_result.checked_at.isoformat()}",
            f"**Drift Detected**: {'Yes' if drift_result.drift_detected else 'No'}",
            "",
        ]

        if not drift_result.drift_detected:
            lines.extend([
                "## Status",
                "",
                "No changes detected between cached documentation and current database schema.",
            ])
            return "\n".join(lines)

        lines.extend([
            "## Summary",
            "",
            drift_result.summary,
            "",
        ])

        if drift_result.added_tables:
            lines.extend([
                "## Added Tables",
                "",
            ])
            for table in drift_result.added_tables:
                lines.append(f"- `{table}`")
            lines.append("")

        if drift_result.removed_tables:
            lines.extend([
                "## Removed Tables",
                "",
            ])
            for table in drift_result.removed_tables:
                lines.append(f"- `{table}`")
            lines.append("")

        if drift_result.modified_tables:
            lines.extend([
                "## Modified Tables",
                "",
            ])
            for mod in drift_result.modified_tables:
                table_name = mod.get("table_name", "Unknown")
                changes = mod.get("changes", [])
                lines.append(f"### `{table_name}`")
                lines.append("")
                for change in changes:
                    lines.append(f"- {change}")
                lines.append("")

        lines.extend([
            "## Recommendation",
            "",
            "Run `export_documentation` to update the cached documentation.",
        ])

        return "\n".join(lines)
