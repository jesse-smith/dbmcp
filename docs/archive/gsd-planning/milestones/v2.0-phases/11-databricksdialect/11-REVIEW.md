---
phase: 11-databricksdialect
reviewed: 2026-04-15T00:00:00Z
depth: standard
files_reviewed: 12
files_reviewed_list:
  - pyproject.toml
  - src/db/connection.py
  - src/db/dialects/__init__.py
  - src/db/dialects/databricks.py
  - src/db/metadata.py
  - src/mcp_server/schema_tools.py
  - tests/integration/test_discovery.py
  - tests/staleness/tool_invoker.py
  - tests/unit/test_connect_tool.py
  - tests/unit/test_connection_manager.py
  - tests/unit/test_databricks_dialect.py
  - tests/unit/test_metadata.py
findings:
  critical: 0
  warning: 2
  info: 3
  total: 5
status: issues_found
---

# Phase 11: Code Review Report

**Reviewed:** 2026-04-15T00:00:00Z
**Depth:** standard
**Files Reviewed:** 12
**Status:** issues_found

## Summary

Reviewed 12 files implementing Databricks dialect support. The implementation follows the dialect strategy pattern established in the codebase and includes comprehensive test coverage. Found 2 warnings related to error handling and edge cases, plus 3 informational items for code clarity improvements.

The Databricks dialect correctly implements token-based authentication, backtick identifier quoting, and capability flags. The integration with connection management and metadata service is sound. Test coverage is strong with both unit and integration tests.

## Warnings

### WR-01: Missing validation for required parameters in DatabricksDialect.create_engine

**File:** `src/db/dialects/databricks.py:88-92`
**Issue:** The `create_engine` method accesses required kwargs without validation, which could raise KeyError if host or http_path are missing. While the method is called internally from ConnectionManager.connect_with_config (which does construct these params), the method signature accepts **kwargs without enforcing required parameters at the interface level.

**Fix:**
```python
def create_engine(self, **kwargs) -> Engine:
    """Create a SQLAlchemy Engine with Databricks token auth.

    Args:
        **kwargs: Connection parameters:
            host (str): Databricks workspace hostname. (required)
            http_path (str): SQL warehouse HTTP path. (required)
            token (str): Personal access token or OAuth token. (optional)
            catalog (str): Unity Catalog name (default "main"). (optional)
            schema (str): Schema name (default "default"). (optional)

    Returns:
        Configured SQLAlchemy Engine.

    Raises:
        ImportError: If databricks-sqlalchemy is not installed.
        ValueError: If required parameters are missing.
    """
    if _databricks_import_error is not None:
        raise ImportError(
            "Databricks support requires databricks-sqlalchemy. "
            "Install with: pip install dbmcp[databricks]"
        ) from _databricks_import_error

    # Validate required parameters
    try:
        host: str = kwargs["host"]
        http_path: str = kwargs["http_path"]
    except KeyError as e:
        raise ValueError(f"Missing required parameter: {e.args[0]}") from e

    token: str = kwargs.get("token", "")
    catalog: str = kwargs.get("catalog", "main")
    schema: str = kwargs.get("schema", "default")
    # ... rest of implementation
```

### WR-02: Silent empty result on DESCRIBE TABLE EXTENDED failure

**File:** `src/db/metadata.py:918-925`
**Issue:** The `_parse_databricks_table_properties` method catches all exceptions and returns an empty dict with only a warning log. This means if DESCRIBE TABLE EXTENDED fails (e.g., due to insufficient permissions or table not found), the caller in `get_table_schema` will silently return no Databricks-specific properties without any indication to the end user that the query failed. While the docstring mentions "Empty dict on failure," callers cannot distinguish between "no properties exist" vs "query failed."

**Fix:** Consider adding a status indicator or raising the exception for critical failures:
```python
def _parse_databricks_table_properties(
    self, table_name: str, schema_name: str, catalog: str
) -> dict:
    """Parse DESCRIBE TABLE EXTENDED for Databricks-specific properties.

    Returns dict with optional keys: owner, storage_format, table_type_detail,
    created_time, location, partition_columns. On failure, returns dict with
    'error' key containing error message.

    Args:
        table_name: Table name
        schema_name: Schema name
        catalog: Catalog name

    Returns:
        Dictionary of parsed properties. Dict with 'error' key on failure.
    """
    try:
        # ... existing implementation ...
        return props

    except Exception as e:
        # T-11-06: Never let DTE parsing failure break get_table_schema
        error_msg = f"{type(e).__name__}: {e}"
        logger.warning(
            f"Failed to parse DESCRIBE EXTENDED for {catalog}.{schema_name}.{table_name}: {error_msg}"
        )
        # Return error indicator so caller can optionally surface it
        return {"_describe_extended_error": error_msg}
```

Then in `get_table_schema` (line 837-842), optionally filter out or handle the error key:
```python
dte_props = self._parse_databricks_table_properties(
    table_name, schema_name, dte_catalog
)
# Optionally log or surface error to user
if "_describe_extended_error" in dte_props:
    logger.debug(f"Could not retrieve extended properties: {dte_props['_describe_extended_error']}")
    dte_props.pop("_describe_extended_error")  # Don't include in response
result.update(dte_props)
```

## Info

### IN-01: Inconsistent quote_identifier usage in metadata queries

**File:** `src/db/metadata.py:149-152`
**Issue:** In `_list_schemas_databricks`, the code uses `self._dialect.quote_identifier(catalog)` to safely quote the catalog name, which is good for SQL injection prevention. However, other Databricks query paths (like `_list_tables_databricks` at line 301-302 and line 306) also quote identifiers. This is correct, but the pattern could be more consistently documented.

**Fix:** Add a comment at the top of each Databricks query method noting the SQL injection prevention strategy:
```python
def _list_schemas_databricks(self, connection_id: str, catalog: str) -> list[Schema]:
    """Databricks schema listing using SHOW SCHEMAS IN for cross-catalog queries.
    
    All identifiers are backtick-quoted via dialect.quote_identifier() to prevent
    SQL injection (per T-11-04 security requirement).
    """
    schemas = []
    quoted_catalog = self._dialect.quote_identifier(catalog)
    # ...
```

### IN-02: Test coverage for URL encoding edge cases

**File:** `tests/unit/test_databricks_dialect.py:142-163`
**Issue:** The test `test_create_engine_url_encodes_token_special_chars` validates URL encoding of special characters in tokens. This is good, but there's no test for the edge case where token is empty string or None (which would result in `databricks://token:@host`). While the code handles this (line 90 uses `kwargs.get("token", "")`), explicit test coverage would document this behavior.

**Fix:** Add a test case:
```python
@patch("src.db.dialects.databricks.sa_create_engine")
def test_create_engine_empty_token(self, mock_sa_create_engine):
    """Empty token results in databricks://token:@host URL."""
    from src.db.dialects import databricks as databricks_mod

    original_error = databricks_mod._databricks_import_error
    try:
        databricks_mod._databricks_import_error = None
        dialect = databricks_mod.DatabricksDialect()
        mock_sa_create_engine.return_value = MagicMock()

        dialect.create_engine(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token="",
        )

        url = mock_sa_create_engine.call_args[0][0]
        assert "databricks://token:@test.databricks.com" in url
    finally:
        databricks_mod._databricks_import_error = original_error
```

### IN-03: Potential for clearer separation of three-level vs two-level table IDs

**File:** `src/db/metadata.py:377-399`
**Issue:** The `_collect_objects_from_schema` method uses a boolean `use_three_level` to determine table_id format (lines 377-382). The logic is correct, but the conditional logic for when to use three-level IDs (`catalog is not None and self._dialect is not None and self._dialect.name == "databricks"`) is scattered. This could be extracted to a helper method for clarity.

**Fix:**
```python
def _should_use_three_level_table_ids(self, catalog: str | None) -> bool:
    """Determine if table IDs should use three-level format (catalog.schema.table).
    
    Three-level IDs are used for Databricks when a catalog is explicitly provided.
    
    Args:
        catalog: Optional catalog name
        
    Returns:
        True if three-level IDs should be used
    """
    return (
        catalog is not None
        and self._dialect is not None
        and self._dialect.name == "databricks"
    )

def _collect_objects_from_schema(
    self,
    schema: str | None,
    table_type: TableType,
    name_pattern: str | None,
    min_row_count: int | None,
    catalog: str | None = None,
) -> list[Table]:
    """Collect tables or views from a single schema.
    
    Args:
        schema: Schema name (None for default schema)
        table_type: TABLE or VIEW
        name_pattern: SQL LIKE pattern for name filtering
        min_row_count: Minimum row count threshold (tables only)
        catalog: Optional catalog for three-level Databricks table IDs (D-11)
        
    Returns:
        List of matching Table objects
    """
    display_schema = schema or "main"
    is_table = table_type == TableType.TABLE

    if is_table:
        names = self.inspector.get_table_names(schema=schema)
    else:
        names = self.inspector.get_view_names(schema=schema)

    use_three_level = self._should_use_three_level_table_ids(catalog)

    results: list[Table] = []
    for name in names:
        # ... rest of method unchanged
```

---

_Reviewed: 2026-04-15T00:00:00Z_
_Reviewer: Claude (gsd-code-reviewer)_
_Depth: standard_
