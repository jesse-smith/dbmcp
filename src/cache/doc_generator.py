"""Markdown documentation generation for database schema cache.

Generates overview, schema, table, and relationships markdown files
from database metadata.
"""

from datetime import datetime

from src.models.relationship import DeclaredFK, InferredFK
from src.models.schema import Column, Index, Schema, Table


class DocumentationGenerator:
    """Generates markdown documentation from database metadata."""

    def generate_overview(
        self,
        database_name: str,
        schemas: list[Schema],
        tables: dict[str, list[Table]],
        declared_fks: list[DeclaredFK],
        inferred_fks: list[InferredFK],
    ) -> str:
        """Generate overview.md content."""
        lines = [
            f"# Database: {database_name}",
            "",
            f"**Generated**: {datetime.now().isoformat()}",
            "",
            "## Summary",
            "",
            f"- **Schemas**: {len(schemas)}",
            f"- **Tables**: {sum(len(t) for t in tables.values())}",
            f"- **Declared Foreign Keys**: {len(declared_fks)}",
            f"- **Inferred Relationships**: {len(inferred_fks)}",
            "",
            "## Schemas",
            "",
            "| Schema | Tables | Views |",
            "|--------|--------|-------|",
        ]

        for schema in sorted(schemas, key=lambda s: -s.table_count):
            lines.append(
                f"| [{schema.schema_name}](schemas/{schema.schema_name}.md) | {schema.table_count} | {schema.view_count} |"
            )

        lines.extend([
            "",
            "## Quick Navigation",
            "",
            "- [Relationships](relationships.md) - All foreign key relationships",
        ])

        return "\n".join(lines)

    def generate_schema_doc(
        self, schema: Schema, tables: list[Table]
    ) -> str:
        """Generate schema markdown file."""
        lines = [
            f"# Schema: {schema.schema_name}",
            "",
            f"**Tables**: {schema.table_count} | **Views**: {schema.view_count}",
            "",
            "## Tables",
            "",
            "| Table | Rows | Primary Key | Last Modified |",
            "|-------|------|-------------|---------------|",
        ]

        for table in sorted(tables, key=lambda t: -(t.row_count or 0)):
            pk_status = "Yes" if table.has_primary_key else "No"
            modified = table.last_modified.isoformat() if table.last_modified else "N/A"
            row_count = f"{table.row_count:,}" if table.row_count is not None else "N/A"
            table_link = f"[{table.table_name}](../tables/{schema.schema_name}.{table.table_name}.md)"
            lines.append(f"| {table_link} | {row_count} | {pk_status} | {modified} |")

        return "\n".join(lines)

    def generate_table_doc(
        self,
        table: Table,
        columns: list[Column],
        indexes: list[Index],
        declared_fks: list[DeclaredFK],
        inferred_fks: list[InferredFK],
        sample_data: list[dict],
    ) -> str:
        """Generate table markdown file."""
        schema_name = table.schema_id
        lines = [
            f"# Table: {schema_name}.{table.table_name}",
            "",
            f"**Type**: {table.table_type.value.title()}",
            f"**Row Count**: {table.row_count:,}" if table.row_count is not None else "**Row Count**: Unknown",
            f"**Primary Key**: {'Yes' if table.has_primary_key else 'No'}",
            "",
            "## Columns",
            "",
            "| # | Column | Type | Nullable | PK | FK | Default |",
            "|---|--------|------|----------|----|----|---------|",
        ]

        for col in sorted(columns, key=lambda c: c.ordinal_position):
            nullable = "Yes" if col.is_nullable else "No"
            pk = "Yes" if col.is_primary_key else ""
            fk = "Yes" if col.is_foreign_key else ""
            default = col.default_value or ""
            lines.append(
                f"| {col.ordinal_position} | `{col.column_name}` | {col.data_type} | {nullable} | {pk} | {fk} | {default} |"
            )

        if indexes:
            lines.extend([
                "",
                "## Indexes",
                "",
                "| Index | Columns | Unique | Clustered |",
                "|-------|---------|--------|-----------|",
            ])
            for idx in indexes:
                unique = "Yes" if idx.is_unique else "No"
                clustered = "Yes" if idx.is_clustered else "No"
                cols = ", ".join(idx.columns)
                lines.append(f"| `{idx.index_name}` | {cols} | {unique} | {clustered} |")

        if declared_fks or inferred_fks:
            lines.extend([
                "",
                "## Relationships",
                "",
            ])

            if declared_fks:
                lines.extend([
                    "### Declared Foreign Keys",
                    "",
                    "| Column | References |",
                    "|--------|------------|",
                ])
                for fk in declared_fks:
                    lines.append(
                        f"| `{fk.source_column}` | {fk.target_table_id}.{fk.target_column} |"
                    )

            if inferred_fks:
                lines.extend([
                    "",
                    "### Inferred Relationships",
                    "",
                    "| Column | Likely References | Confidence | Reasoning |",
                    "|--------|-------------------|------------|-----------|",
                ])
                for fk in inferred_fks:
                    lines.append(
                        f"| `{fk.source_column}` | {fk.target_table_id}.{fk.target_column} | {fk.confidence_score:.0%} | {fk.reasoning} |"
                    )

        if sample_data:
            lines.extend([
                "",
                "## Sample Data",
                "",
            ])

            if sample_data:
                col_names = list(sample_data[0].keys())
                lines.append("| " + " | ".join(col_names) + " |")
                lines.append("|" + "|".join(["---"] * len(col_names)) + "|")

                for row in sample_data[:5]:
                    values = [str(row.get(col, "")) for col in col_names]
                    values = [v.replace("|", "\\|") for v in values]
                    lines.append("| " + " | ".join(values) + " |")

        return "\n".join(lines)

    def generate_relationships_doc(
        self,
        declared_fks: list[DeclaredFK],
        inferred_fks: list[InferredFK],
    ) -> str:
        """Generate relationships.md content."""
        lines = [
            "# Database Relationships",
            "",
            f"**Generated**: {datetime.now().isoformat()}",
            "",
            "## Summary",
            "",
            f"- **Declared Foreign Keys**: {len(declared_fks)}",
            f"- **Inferred Relationships**: {len(inferred_fks)}",
            "",
        ]

        if declared_fks:
            lines.extend([
                "## Declared Foreign Keys",
                "",
                "| Source Table | Source Column | Target Table | Target Column | On Delete |",
                "|--------------|---------------|--------------|---------------|-----------|",
            ])
            for fk in sorted(declared_fks, key=lambda f: f.source_table_id):
                on_delete = fk.on_delete or "NO ACTION"
                lines.append(
                    f"| {fk.source_table_id} | `{fk.source_column}` | {fk.target_table_id} | `{fk.target_column}` | {on_delete} |"
                )

        if inferred_fks:
            lines.extend([
                "",
                "## Inferred Relationships",
                "",
                "These relationships are not declared in the schema but inferred from naming patterns, type compatibility, and structural hints.",
                "",
                "| Source Table | Source Column | Target Table | Target Column | Confidence | Reasoning |",
                "|--------------|---------------|--------------|---------------|------------|-----------|",
            ])
            for fk in sorted(inferred_fks, key=lambda f: -f.confidence_score):
                lines.append(
                    f"| {fk.source_table_id} | `{fk.source_column}` | {fk.target_table_id} | `{fk.target_column}` | {fk.confidence_score:.0%} | {fk.reasoning} |"
                )

        return "\n".join(lines)
