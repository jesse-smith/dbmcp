"""Per-tool mock setup and invocation to get real response dicts.

Provides TOOL_CONFIGS (list of tool config dicts) and invoke_tool() that
calls each MCP tool with appropriate mocks to capture success and error
response shapes for staleness guard testing.
"""

from contextlib import contextmanager
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from src.mcp_server.server import (
    connect_database,
    execute_query,
    find_fk_candidates,
    find_pk_candidates,
    get_column_info,
    get_connection_manager,
    get_sample_data,
    get_table_schema,
    list_schemas,
    list_tables,
)
from src.models.schema import (
    AuthenticationMethod,
    Column,
    Connection,
    Schema,
    SamplingMethod,
    Table,
    TableType,
)


# =============================================================================
# Mock helpers
# =============================================================================


def _mock_schema():
    """Create a sample Schema object."""
    return Schema(
        schema_id="test:dbo",
        schema_name="dbo",
        connection_id="test123",
        table_count=5,
        view_count=1,
    )


def _mock_table():
    """Create a sample Table object."""
    return Table(
        table_id="dbo.TestTable",
        schema_id="dbo",
        table_name="TestTable",
        table_type=TableType.TABLE,
        row_count=100,
        has_primary_key=True,
        access_denied=False,
    )


def _mock_column():
    """Create a sample Column object."""
    return Column(
        column_id="dbo.TestTable.id",
        table_id="dbo.TestTable",
        column_name="id",
        ordinal_position=1,
        data_type="INT",
        is_nullable=False,
        is_primary_key=True,
        is_foreign_key=False,
    )


def _mock_connection():
    """Create a sample Connection object."""
    return Connection(
        connection_id="test123",
        server="testserver",
        database="testdb",
        port=1433,
        authentication_method=AuthenticationMethod.SQL,
        username="testuser",
    )


# =============================================================================
# Mock context managers for each tool
# =============================================================================


@contextmanager
def _connect_database_success_mocks():
    """Mocks for connect_database success path."""
    conn = _mock_connection()
    schemas = [_mock_schema()]

    with (
        patch.object(get_connection_manager(), "connect", return_value=conn),
        patch.object(get_connection_manager(), "get_engine") as mock_engine,
    ):
        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = schemas

        with (
            patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_cache_dir = MagicMock()
            mock_cache_dir.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache_dir)
            yield


@contextmanager
def _connect_database_error_mocks():
    """Mocks for connect_database error path."""
    from src.db.connection import ConnectionError

    with patch.object(
        get_connection_manager(),
        "connect",
        side_effect=ConnectionError("Test connection error"),
    ):
        yield


@contextmanager
def _list_schemas_success_mocks():
    """Mocks for list_schemas success path."""
    schemas = [_mock_schema()]
    mock_metadata_svc = MagicMock()
    mock_metadata_svc.list_schemas.return_value = schemas

    with (
        patch.object(get_connection_manager(), "get_engine"),
        patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
    ):
        yield


@contextmanager
def _list_schemas_error_mocks():
    """Mocks for list_schemas error path."""
    with patch.object(
        get_connection_manager(),
        "get_engine",
        side_effect=ValueError("Unknown connection_id"),
    ):
        yield


@contextmanager
def _list_tables_success_mocks():
    """Mocks for list_tables success path."""
    tables = [_mock_table()]
    mock_metadata_svc = MagicMock()
    mock_metadata_svc.list_tables.return_value = (tables, {"total_count": 1})

    with (
        patch.object(get_connection_manager(), "get_engine"),
        patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
    ):
        yield


@contextmanager
def _list_tables_error_mocks():
    """Mocks for list_tables error path -- invalid limit triggers validation error."""
    # No mocks needed; passing limit=0 triggers validation error
    yield


@contextmanager
def _get_table_schema_success_mocks():
    """Mocks for get_table_schema success path."""
    table_schema = {
        "table_name": "TestTable",
        "schema_name": "dbo",
        "columns": [
            {
                "column_name": "id",
                "ordinal_position": 1,
                "data_type": "INT",
                "max_length": None,
                "is_nullable": False,
                "default_value": None,
                "is_identity": True,
                "is_computed": False,
                "is_primary_key": True,
                "is_foreign_key": False,
            }
        ],
        "indexes": [
            {
                "index_name": "PK_TestTable",
                "is_unique": True,
                "is_primary_key": True,
                "is_clustered": True,
                "columns": ["id"],
                "included_columns": [],
            }
        ],
        "foreign_keys": [
            {
                "constraint_name": "FK_Test",
                "source_columns": ["other_id"],
                "target_schema": "dbo",
                "target_table": "OtherTable",
                "target_columns": ["id"],
            }
        ],
    }

    mock_metadata_svc = MagicMock()
    mock_metadata_svc.table_exists.return_value = True
    mock_metadata_svc.get_table_schema.return_value = table_schema

    with (
        patch.object(get_connection_manager(), "get_engine"),
        patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
    ):
        yield


@contextmanager
def _get_table_schema_error_mocks():
    """Mocks for get_table_schema error path -- table not found."""
    mock_metadata_svc = MagicMock()
    mock_metadata_svc.table_exists.return_value = False

    with (
        patch.object(get_connection_manager(), "get_engine"),
        patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
    ):
        yield


@contextmanager
def _get_sample_data_success_mocks():
    """Mocks for get_sample_data success path."""
    from src.models.schema import SampleData

    sample = SampleData(
        sample_id="dbo.TestTable:123",
        table_id="dbo.TestTable",
        sample_size=5,
        sampling_method=SamplingMethod.TOP,
        rows=[{"id": 1, "name": "test"}],
        truncated_columns=[],
        sampled_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
    )

    mock_query_svc = MagicMock()
    mock_query_svc.get_sample_data.return_value = sample

    with (
        patch.object(get_connection_manager(), "get_engine"),
        patch("src.mcp_server.query_tools.QueryService", return_value=mock_query_svc),
    ):
        yield


@contextmanager
def _get_sample_data_error_mocks():
    """Mocks for get_sample_data error path -- invalid connection_id."""
    with patch.object(
        get_connection_manager(),
        "get_engine",
        side_effect=ValueError("Unknown connection_id"),
    ):
        yield


@contextmanager
def _execute_query_success_mocks():
    """Mocks for execute_query success path."""
    mock_query_svc = MagicMock()

    # Mock execute_query to return a query object
    mock_query = MagicMock()

    # Mock get_query_results to return what the docstring describes
    mock_query_svc.get_query_results.return_value = {
        "status": "success",
        "query_id": "q123",
        "query_type": "select",
        "columns": ["id", "name"],
        "rows": [{"id": 1, "name": "test"}],
        "rows_returned": 1,
        "rows_available": 1,
        "limited": False,
        "execution_time_ms": 10.5,
    }
    mock_query_svc.execute_query.return_value = mock_query

    with (
        patch.object(get_connection_manager(), "get_engine"),
        patch("src.mcp_server.query_tools.QueryService", return_value=mock_query_svc),
    ):
        yield


@contextmanager
def _execute_query_error_mocks():
    """Mocks for execute_query error path -- empty query triggers validation error."""
    # No mocks needed; empty query_text triggers validation error
    yield


@contextmanager
def _get_column_info_success_mocks():
    """Mocks for get_column_info success path."""
    mock_collector = MagicMock()
    mock_stat = MagicMock()
    mock_stat.to_dict.return_value = {
        "column_name": "id",
        "data_type": "INT",
        "total_rows": 100,
        "distinct_count": 100,
        "null_count": 0,
        "null_percentage": 0.0,
        "numeric_stats": {
            "min_value": 1.0,
            "max_value": 100.0,
            "mean_value": 50.5,
            "std_dev": 28.87,
        },
        "datetime_stats": {
            "min_date": "2026-01-01T00:00:00",
            "max_date": "2026-12-31T00:00:00",
            "date_range_days": 365,
            "has_time_component": False,
        },
        "string_stats": {
            "min_length": 1,
            "max_length": 50,
            "avg_length": 10.5,
            "sample_values": [["test", 5]],
        },
    }
    mock_collector.get_columns_info.return_value = [mock_stat]

    # Mock engine and connection context manager
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=None)

    # Mock table existence check
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_conn.execute.return_value = mock_result

    with (
        patch.object(get_connection_manager(), "get_engine", return_value=mock_engine),
        patch("src.mcp_server.analysis_tools.ColumnStatsCollector", return_value=mock_collector),
    ):
        yield


@contextmanager
def _get_column_info_error_mocks():
    """Mocks for get_column_info error path -- invalid connection."""
    with patch.object(
        get_connection_manager(),
        "get_engine",
        side_effect=ValueError("Unknown connection_id"),
    ):
        yield


@contextmanager
def _find_pk_candidates_success_mocks():
    """Mocks for find_pk_candidates success path."""
    mock_discovery = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.to_dict.return_value = {
        "column_name": "id",
        "data_type": "INT",
        "is_constraint_backed": True,
        "constraint_type": "PRIMARY KEY",
        "is_unique": True,
        "is_non_null": True,
        "is_pk_type": True,
    }
    mock_discovery.find_candidates.return_value = [mock_candidate]

    # Mock engine and connection context manager
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=None)

    # Mock table existence check
    mock_result = MagicMock()
    mock_result.scalar.return_value = 1
    mock_conn.execute.return_value = mock_result

    with (
        patch.object(get_connection_manager(), "get_engine", return_value=mock_engine),
        patch("src.mcp_server.analysis_tools.PKDiscovery", return_value=mock_discovery),
    ):
        yield


@contextmanager
def _find_pk_candidates_error_mocks():
    """Mocks for find_pk_candidates error path -- invalid connection."""
    with patch.object(
        get_connection_manager(),
        "get_engine",
        side_effect=ValueError("Unknown connection_id"),
    ):
        yield


@contextmanager
def _find_fk_candidates_success_mocks():
    """Mocks for find_fk_candidates success path."""
    mock_search = MagicMock()
    mock_fk_result = MagicMock()
    mock_candidate = MagicMock()
    mock_candidate.to_dict.return_value = {
        "source_column": "customer_id",
        "source_table": "orders",
        "source_schema": "dbo",
        "source_data_type": "INT",
        "target_column": "id",
        "target_table": "customers",
        "target_schema": "dbo",
        "target_data_type": "INT",
        "target_is_primary_key": True,
        "target_is_unique": True,
        "target_is_nullable": False,
        "target_has_index": True,
    }
    mock_fk_result.candidates = [mock_candidate]
    mock_fk_result.total_found = 1
    mock_fk_result.was_limited = False
    mock_fk_result.search_scope = "dbo schema, PK candidates only"
    mock_search.find_candidates.return_value = mock_fk_result

    # Mock engine and connection context manager
    mock_engine = MagicMock()
    mock_conn = MagicMock()
    mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
    mock_engine.connect.return_value.__exit__ = MagicMock(return_value=None)

    # Mock table existence check (scalar returns 1)
    mock_table_result = MagicMock()
    mock_table_result.scalar.return_value = 1

    # Mock column existence check (fetchone returns a row with data_type)
    mock_col_row = MagicMock()
    mock_col_row.__getitem__ = MagicMock(return_value="INT")
    mock_col_result = MagicMock()
    mock_col_result.fetchone.return_value = mock_col_row

    # Return different results for different queries
    call_count = {"n": 0}

    def mock_execute(query, params=None):
        call_count["n"] += 1
        if call_count["n"] == 1:
            return mock_table_result  # Table existence check
        return mock_col_result  # Column existence check

    mock_conn.execute = mock_execute

    with (
        patch.object(get_connection_manager(), "get_engine", return_value=mock_engine),
        patch("src.mcp_server.analysis_tools.FKCandidateSearch", return_value=mock_search),
    ):
        yield


@contextmanager
def _find_fk_candidates_error_mocks():
    """Mocks for find_fk_candidates error path -- invalid connection."""
    with patch.object(
        get_connection_manager(),
        "get_engine",
        side_effect=ValueError("Unknown connection_id"),
    ):
        yield


# =============================================================================
# Tool configurations
# =============================================================================


TOOL_CONFIGS = [
    {
        "name": "connect_database",
        "fn": connect_database,
        "success_args": {"server": "testserver", "database": "testdb"},
        "error_args": {"server": "testserver", "database": "testdb"},
        "success_mocks": _connect_database_success_mocks,
        "error_mocks": _connect_database_error_mocks,
    },
    {
        "name": "list_schemas",
        "fn": list_schemas,
        "success_args": {"connection_id": "test123"},
        "error_args": {"connection_id": "nonexistent"},
        "success_mocks": _list_schemas_success_mocks,
        "error_mocks": _list_schemas_error_mocks,
    },
    {
        "name": "list_tables",
        "fn": list_tables,
        "success_args": {"connection_id": "test123"},
        "error_args": {"connection_id": "test123", "limit": 0},
        "success_mocks": _list_tables_success_mocks,
        "error_mocks": _list_tables_error_mocks,
    },
    {
        "name": "get_table_schema",
        "fn": get_table_schema,
        "success_args": {"connection_id": "test123", "table_name": "TestTable"},
        "error_args": {"connection_id": "test123", "table_name": "NonExistent"},
        "success_mocks": _get_table_schema_success_mocks,
        "error_mocks": _get_table_schema_error_mocks,
    },
    {
        "name": "get_sample_data",
        "fn": get_sample_data,
        "success_args": {"connection_id": "test123", "table_name": "TestTable"},
        "error_args": {"connection_id": "nonexistent", "table_name": "TestTable"},
        "success_mocks": _get_sample_data_success_mocks,
        "error_mocks": _get_sample_data_error_mocks,
    },
    {
        "name": "execute_query",
        "fn": execute_query,
        "success_args": {"connection_id": "test123", "query_text": "SELECT 1"},
        "error_args": {"connection_id": "test123", "query_text": ""},
        "success_mocks": _execute_query_success_mocks,
        "error_mocks": _execute_query_error_mocks,
    },
    {
        "name": "get_column_info",
        "fn": get_column_info,
        "success_args": {"connection_id": "test123", "table_name": "TestTable"},
        "error_args": {"connection_id": "nonexistent", "table_name": "TestTable"},
        "success_mocks": _get_column_info_success_mocks,
        "error_mocks": _get_column_info_error_mocks,
    },
    {
        "name": "find_pk_candidates",
        "fn": find_pk_candidates,
        "success_args": {"connection_id": "test123", "table_name": "TestTable"},
        "error_args": {"connection_id": "nonexistent", "table_name": "TestTable"},
        "success_mocks": _find_pk_candidates_success_mocks,
        "error_mocks": _find_pk_candidates_error_mocks,
    },
    {
        "name": "find_fk_candidates",
        "fn": find_fk_candidates,
        "success_args": {
            "connection_id": "test123",
            "table_name": "orders",
            "column_name": "customer_id",
        },
        "error_args": {
            "connection_id": "nonexistent",
            "table_name": "orders",
            "column_name": "customer_id",
        },
        "success_mocks": _find_fk_candidates_success_mocks,
        "error_mocks": _find_fk_candidates_error_mocks,
    },
]


# =============================================================================
# Invocation function
# =============================================================================


async def invoke_tool(tool_config: dict, path: str = "success") -> str:
    """Invoke an MCP tool with mocks for the given path (success or error).

    Args:
        tool_config: Tool configuration dict from TOOL_CONFIGS.
        path: "success" or "error" -- determines which mock set and args to use.

    Returns:
        TOON-encoded response string from the tool.
    """
    fn = tool_config["fn"]
    args = tool_config[f"{path}_args"]
    mock_ctx = tool_config[f"{path}_mocks"]

    with mock_ctx():
        result = await fn(**args)

    return result
