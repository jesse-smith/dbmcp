"""Meta-tests for the docstring field parser.

Verifies that extract_fields() correctly parses TOON structural outline
format from tool docstrings, handling top-level fields, nesting, and
conditional annotations.
"""

import pytest

from tests.staleness.docstring_parser import extract_fields


# ---------------------------------------------------------------------------
# Fixtures: real docstrings copied from the codebase
# ---------------------------------------------------------------------------

CONNECT_DATABASE_DOCSTRING = """\
Connect to a SQL Server database.

Establishes a pooled connection to a SQL Server database. Required before
any other database operations. Returns a connection_id for subsequent calls.

Args:
    server: SQL Server host (hostname or IP address)
    database: Database name

Returns:
    TOON-encoded string with connection details:

        status: "success" | "error"
        connection_id: string              // on success only
        message: string                    // on success only
        schema_count: int                  // on success only
        has_cached_docs: bool              // on success only
        error_message: string              // on error only
"""

LIST_SCHEMAS_DOCSTRING = """\
List all schemas in the connected database.

Returns schemas with table and view counts, sorted by table count descending.
Excludes system schemas (sys, INFORMATION_SCHEMA, guest).

Args:
    connection_id: Connection ID from connect_database

Returns:
    TOON-encoded string with schema list:

        status: "success" | "error"
        total_schemas: int
        schemas: list
            schema_name: string
            table_count: int
            view_count: int
        error_message: string              // on error only

Error conditions:
    - Invalid connection_id: returns status "error" with error_message
"""

LIST_TABLES_DOCSTRING = """\
List tables in specified schema(s) with row counts and metadata.

Efficiently retrieves table metadata using SQL Server DMVs.

Args:
    connection_id: Connection ID from connect_database

Returns:
    TOON-encoded string with table list and pagination metadata:

        status: "success" | "error"
        returned_count: int
        total_count: int
        offset: int
        limit: int
        has_more: bool
        tables: list
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

GET_COLUMN_INFO_DOCSTRING = """\
Retrieve per-column statistical profiles for a table.

**EXPERIMENTAL** -- Statistics are based on common practices.

Args:
    connection_id: Connection ID from connect_database

Returns:
    TOON-encoded string with status, table/schema metadata, and column statistics:

        status: "success" | "error"
        table_name: string
        schema_name: string
        total_columns_analyzed: int
        columns: list
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
"""


class TestExtractFieldsEdgeCases:
    """Edge cases and empty inputs."""

    def test_empty_docstring_returns_empty(self):
        result = extract_fields("")
        assert result["top_level"] == set()
        assert result["nested"] == {}
        assert result["conditional"] == {}

    def test_none_docstring_returns_empty(self):
        result = extract_fields(None)
        assert result["top_level"] == set()
        assert result["nested"] == {}
        assert result["conditional"] == {}

    def test_no_returns_section(self):
        docstring = "Does something.\n\nArgs:\n    x: int\n"
        result = extract_fields(docstring)
        assert result["top_level"] == set()


class TestExtractFieldsTopLevel:
    """Top-level field extraction from simple Returns sections."""

    def test_simple_fields(self):
        result = extract_fields(CONNECT_DATABASE_DOCSTRING)
        expected = {"status", "connection_id", "message", "schema_count",
                    "has_cached_docs", "error_message"}
        assert result["top_level"] == expected

    def test_conditional_annotations_preserved(self):
        result = extract_fields(CONNECT_DATABASE_DOCSTRING)
        assert result["conditional"]["connection_id"] == "on success only"
        assert result["conditional"]["message"] == "on success only"
        assert result["conditional"]["schema_count"] == "on success only"
        assert result["conditional"]["has_cached_docs"] == "on success only"
        assert result["conditional"]["error_message"] == "on error only"
        # status has no annotation
        assert "status" not in result["conditional"]

    def test_stops_at_section_header(self):
        """Parser should stop at 'Error conditions:' section."""
        result = extract_fields(LIST_SCHEMAS_DOCSTRING)
        # Should NOT include anything from Error conditions section
        expected_top = {"status", "total_schemas", "schemas", "error_message"}
        assert result["top_level"] == expected_top


class TestExtractFieldsNested:
    """Nested field extraction (one level deep under list/object parents)."""

    def test_list_children_extracted(self):
        result = extract_fields(LIST_SCHEMAS_DOCSTRING)
        assert "schemas" in result["nested"]
        assert result["nested"]["schemas"] == {
            "schema_name", "table_count", "view_count"
        }

    def test_list_tables_nested_fields(self):
        result = extract_fields(LIST_TABLES_DOCSTRING)
        assert "tables" in result["nested"]
        expected_children = {
            "schema_name", "table_name", "table_type", "row_count",
            "has_primary_key", "last_modified", "access_denied", "columns",
        }
        assert result["nested"]["tables"] == expected_children

    def test_columns_annotation_in_nested(self):
        """columns under tables has '// detailed mode only' annotation."""
        result = extract_fields(LIST_TABLES_DOCSTRING)
        assert result["conditional"]["columns"] == "detailed mode only"


class TestExtractFieldsDeepNesting:
    """get_column_info has 2-level nesting (columns -> numeric_stats -> children)."""

    def test_column_info_top_level(self):
        result = extract_fields(GET_COLUMN_INFO_DOCSTRING)
        expected_top = {
            "status", "table_name", "schema_name",
            "total_columns_analyzed", "columns", "error_message",
        }
        assert result["top_level"] == expected_top

    def test_column_info_columns_children(self):
        result = extract_fields(GET_COLUMN_INFO_DOCSTRING)
        assert "columns" in result["nested"]
        children = result["nested"]["columns"]
        # Should include direct children of columns list
        assert "column_name" in children
        assert "data_type" in children
        assert "total_rows" in children
        assert "distinct_count" in children
        assert "null_count" in children
        assert "null_percentage" in children
        assert "numeric_stats" in children
        assert "datetime_stats" in children
        assert "string_stats" in children

    def test_column_info_conditional_nested_objects(self):
        """numeric_stats, datetime_stats, string_stats have conditional annotations."""
        result = extract_fields(GET_COLUMN_INFO_DOCSTRING)
        assert result["conditional"]["numeric_stats"] == "numeric columns only"
        assert result["conditional"]["datetime_stats"] == "datetime columns only"
        assert result["conditional"]["string_stats"] == "string columns only"


def _get_function_docstring(filepath: str, func_name: str) -> str:
    """Extract a function's docstring from source without importing the module.

    Uses the ast module to avoid circular import issues with the MCP server modules.
    """
    import ast
    from pathlib import Path

    source = Path(filepath).read_text()
    tree = ast.parse(source)

    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.name == func_name:
                return ast.get_docstring(node)
    raise ValueError(f"Function {func_name!r} not found in {filepath}")


class TestExtractFieldsRealDocstrings:
    """Integration-style tests using actual tool docstrings from source files."""

    def test_connect_database(self):
        doc = _get_function_docstring("src/mcp_server/schema_tools.py", "connect_database")
        result = extract_fields(doc)
        assert "status" in result["top_level"]
        assert "connection_id" in result["top_level"]
        assert result["conditional"]["error_message"] == "on error only"

    def test_list_tables(self):
        doc = _get_function_docstring("src/mcp_server/schema_tools.py", "list_tables")
        result = extract_fields(doc)
        assert "tables" in result["top_level"]
        assert "tables" in result["nested"]
        assert "schema_name" in result["nested"]["tables"]

    def test_get_column_info(self):
        doc = _get_function_docstring("src/mcp_server/analysis_tools.py", "get_column_info")
        result = extract_fields(doc)
        assert "columns" in result["top_level"]
        assert "columns" in result["nested"]
        assert "column_name" in result["nested"]["columns"]
