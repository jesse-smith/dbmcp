"""Unit tests for asyncio.to_thread wrapping in MCP tools.

Verifies that all 9 MCP tools use asyncio.to_thread for DB operations,
preventing the async event loop from blocking.

Imports go through src.mcp_server.server to resolve circular imports.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.db.dialects.databricks import DatabricksDialect
from src.db.dialects.mssql import MssqlDialect

# Import through server to resolve circular imports
from src.mcp_server.server import (
    connect_database,
    execute_query,
    find_fk_candidates,
    find_pk_candidates,
    get_column_info,
    get_sample_data,
    get_table_schema,
    list_schemas,
    list_tables,
)

# ---------------------------------------------------------------------------
# Schema Tools: asyncio.to_thread tests
# ---------------------------------------------------------------------------

class TestSchemaToolsAsyncWrapping:
    """Verify schema tools wrap sync DB work in asyncio.to_thread."""

    async def test_connect_database_uses_to_thread(self):
        """connect_database wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "connection_id": "abc123",
                "message": "Connected",
                "dialect": "generic",
                "schema_count": 1,
                "has_cached_docs": False,
            }

            await connect_database(sqlalchemy_url="sqlite:///test.db")
            mock_to_thread.assert_called_once()

    async def test_list_schemas_uses_to_thread(self):
        """list_schemas wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "schemas": [],
                "total_schemas": 0,
            }

            await list_schemas(connection_id="test-conn")
            mock_to_thread.assert_called_once()

    async def test_list_tables_uses_to_thread(self):
        """list_tables wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "tables": [],
                "returned_count": 0,
                "total_count": 0,
                "offset": 0,
                "limit": 100,
                "has_more": False,
            }

            await list_tables(connection_id="test-conn")
            mock_to_thread.assert_called_once()

    async def test_get_table_schema_uses_to_thread(self):
        """get_table_schema wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "table": {"table_name": "test", "schema_name": "dbo", "columns": []},
            }

            await get_table_schema(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# Query Tools: asyncio.to_thread tests
# ---------------------------------------------------------------------------

class TestQueryToolsAsyncWrapping:
    """Verify query tools wrap sync DB work in asyncio.to_thread."""

    async def test_get_sample_data_uses_to_thread(self):
        """get_sample_data wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "sample_id": "s1",
                "table_id": "t1",
                "sample_size": 5,
                "actual_rows_returned": 0,
                "sampling_method": "top",
                "rows": [],
                "truncated_columns": [],
                "sampled_at": "2026-01-01T00:00:00",
            }

            await get_sample_data(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()

    async def test_get_sample_data_threads_dialect_into_metadata_and_query_services(self):
        """WIRING-02 regression: both MetadataService and QueryService receive the
        connection's registered dialect — prevents silent degradation to tsql on
        Databricks/generic connections for the get_sample_data path."""
        from datetime import datetime
        from unittest.mock import MagicMock

        from src.mcp_server import query_tools

        fake_dialect = MagicMock(name="registered_dialect")
        fake_dialect.name = "databricks"
        # Resolver-compatible dialect facts so resolve_identifier (now called in
        # _sync_work) parses cleanly instead of raising on MagicMock attributes.
        fake_dialect.sqlglot_dialect = "databricks"
        fake_dialect.max_identifier_depth = 3
        fake_dialect.default_schema = None
        fake_engine = MagicMock(name="engine")

        fake_sample = MagicMock()
        fake_sample.sample_id = "sid"
        fake_sample.table_id = "tid"
        fake_sample.sample_size = 5
        fake_sample.rows = []
        fake_sample.sampling_method = query_tools.SamplingMethod.TOP
        fake_sample.truncated_columns = []
        fake_sample.sampled_at = datetime.now()

        with (
            patch.object(query_tools, "get_connection_manager") as mock_cm_factory,
            patch.object(query_tools, "MetadataService") as MockMS,
            patch.object(query_tools, "QueryService") as MockQS,
            patch.object(query_tools, "get_config") as mock_cfg,
        ):
            mock_cm = MagicMock()
            mock_cm.get_engine.return_value = fake_engine
            mock_cm.get_dialect.return_value = fake_dialect
            mock_cm_factory.return_value = mock_cm
            mock_cfg.return_value.defaults.sample_size = 5
            MockQS.return_value.get_sample_data.return_value = fake_sample

            await query_tools.get_sample_data(
                connection_id="cid-1",
                table_name="t",
                schema_name="s",
                sample_size=5,
            )

            MockMS.assert_called_once_with(fake_engine, dialect=fake_dialect)
            MockQS.assert_called_once_with(
                fake_engine,
                dialect=fake_dialect,
                metadata_service=MockMS.return_value,
            )

    async def test_execute_query_uses_to_thread(self):
        """execute_query wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "query_id": "q1",
                "query_type": "SELECT",
                "columns": [],
                "rows": [],
                "rows_returned": 0,
                "rows_available": 0,
                "limited": False,
                "execution_time_ms": 1.0,
            }

            await execute_query(connection_id="test-conn", query_text="SELECT 1")
            mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# Analysis Tools: asyncio.to_thread tests
# ---------------------------------------------------------------------------

class TestAnalysisToolsAsyncWrapping:
    """Verify analysis tools wrap sync DB work in asyncio.to_thread."""

    async def test_get_column_info_uses_to_thread(self):
        """get_column_info wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "table_name": "test",
                "schema_name": "dbo",
                "total_columns_analyzed": 0,
                "columns": [],
            }

            await get_column_info(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()

    async def test_find_pk_candidates_uses_to_thread(self):
        """find_pk_candidates wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "table_name": "test",
                "schema_name": "dbo",
                "candidates": [],
            }

            await find_pk_candidates(connection_id="test-conn", table_name="test")
            mock_to_thread.assert_called_once()

    async def test_find_fk_candidates_uses_to_thread(self):
        """find_fk_candidates wraps sync DB work in asyncio.to_thread."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.return_value = {
                "status": "success",
                "source": {"column_name": "id", "table_name": "test", "schema_name": "dbo", "data_type": "int"},
                "candidates": [],
                "total_found": 0,
                "was_limited": False,
                "search_scope": "dbo",
            }

            await find_fk_candidates(
                connection_id="test-conn",
                table_name="test",
                column_name="id",
            )
            mock_to_thread.assert_called_once()


# ---------------------------------------------------------------------------
# Error handling still works through to_thread
# ---------------------------------------------------------------------------

class TestAsyncErrorHandling:
    """Verify error handling works correctly through asyncio.to_thread wrapping."""

    async def test_list_schemas_value_error_returns_error_response(self):
        """ValueError in sync work is caught and returns error TOON response."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = ValueError("Connection 'bad' not found")

            result = await list_schemas(connection_id="bad")
            assert "error" in result
            assert "not found" in result

    async def test_execute_query_exception_returns_error_response(self):
        """General Exception in sync work is caught and returns error TOON response."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = RuntimeError("DB connection lost")

            result = await execute_query(connection_id="test-conn", query_text="SELECT 1")
            assert "error" in result
            assert "DB connection lost" in result

    async def test_get_column_info_exception_returns_error_response(self):
        """Exception in analysis tool sync work returns error response."""
        with patch("asyncio.to_thread") as mock_to_thread:
            mock_to_thread.side_effect = Exception("Timeout expired")

            result = await get_column_info(connection_id="test-conn", table_name="test")
            assert "error" in result
            assert "Timeout expired" in result


# ---------------------------------------------------------------------------
# Error classification wiring tests
# ---------------------------------------------------------------------------


# All 9 MCP tools with their module path (for patching _classify_db_error)
# and minimal kwargs needed to invoke them past parameter validation into
# the try/except safety net (where asyncio.to_thread is called).
_TOOL_PARAMS = [
    pytest.param(
        connect_database,
        "src.mcp_server.schema_tools",
        {"sqlalchemy_url": "sqlite:///test.db"},
        id="connect_database",
    ),
    pytest.param(
        list_schemas,
        "src.mcp_server.schema_tools",
        {"connection_id": "test-conn"},
        id="list_schemas",
    ),
    pytest.param(
        list_tables,
        "src.mcp_server.schema_tools",
        {"connection_id": "test-conn"},
        id="list_tables",
    ),
    pytest.param(
        get_table_schema,
        "src.mcp_server.schema_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="get_table_schema",
    ),
    pytest.param(
        get_sample_data,
        "src.mcp_server.query_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="get_sample_data",
    ),
    pytest.param(
        execute_query,
        "src.mcp_server.query_tools",
        {"connection_id": "test-conn", "query_text": "SELECT 1"},
        id="execute_query",
    ),
    pytest.param(
        get_column_info,
        "src.mcp_server.analysis_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="get_column_info",
    ),
    pytest.param(
        find_pk_candidates,
        "src.mcp_server.analysis_tools",
        {"connection_id": "test-conn", "table_name": "test"},
        id="find_pk_candidates",
    ),
    pytest.param(
        find_fk_candidates,
        "src.mcp_server.analysis_tools",
        {"connection_id": "test-conn", "table_name": "test", "column_name": "id"},
        id="find_fk_candidates",
    ),
]


class TestSafetyNetErrorClassification:
    """Verify all 9 MCP tool safety nets wire _classify_db_error for SQLAlchemy errors."""

    @pytest.mark.parametrize("tool_fn,module_path,kwargs", _TOOL_PARAMS)
    async def test_safety_net_classifies_sqlalchemy_errors(
        self, tool_fn, module_path, kwargs
    ):
        """SQLAlchemyError in a tool triggers _classify_db_error and includes guidance."""
        fake_guidance = "Check your credentials (username/password) and verify the account has access to the database."
        raw_error_text = "Login failed for user 'bob'"

        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch(
                f"{module_path}._classify_db_error",
                return_value=("auth_failure", fake_guidance),
                create=True,
            ) as mock_classify,
        ):
            mock_to_thread.side_effect = SQLAlchemyError(raw_error_text)
            result = await tool_fn(**kwargs)

            mock_classify.assert_called_once()
            # Guidance text should appear in the response
            assert fake_guidance in result
            # Raw error should also appear (in parens)
            assert raw_error_text in result

    @pytest.mark.parametrize("tool_fn,module_path,kwargs", _TOOL_PARAMS)
    async def test_safety_net_generic_error_fallback(
        self, tool_fn, module_path, kwargs
    ):
        """Non-SQLAlchemy error uses generic fallback, does NOT call _classify_db_error."""
        with (
            patch("asyncio.to_thread") as mock_to_thread,
            patch(
                f"{module_path}._classify_db_error",
                create=True,
            ) as mock_classify,
        ):
            mock_to_thread.side_effect = ValueError("something broke")
            result = await tool_fn(**kwargs)

            mock_classify.assert_not_called()
            # Generic fallback should contain the error text
            assert "something broke" in result


# ---------------------------------------------------------------------------
# Catalog gate + resolver routing boundary tests (IDENT-05 / IDENT-06)
# ---------------------------------------------------------------------------


def _patch_cm(module, dialect, engine=None):
    """Patch a tool module's get_connection_manager to return the given dialect."""
    mock_cm = MagicMock()
    mock_cm.get_engine.return_value = engine if engine is not None else MagicMock()
    mock_cm.get_dialect.return_value = dialect
    factory = patch.object(module, "get_connection_manager", return_value=mock_cm)
    return factory, mock_cm


class TestCatalogGateBoundary:
    """D-07 catalog gate: passing catalog on MSSQL/generic returns status=error."""

    async def test_get_sample_data_catalog_on_mssql_errors(self):
        from src.mcp_server import query_tools

        factory, _ = _patch_cm(query_tools, MssqlDialect())
        with factory, patch.object(query_tools, "get_config") as cfg:
            cfg.return_value.defaults.sample_size = 5
            result = await query_tools.get_sample_data(
                connection_id="c", table_name="t", catalog="x"
            )
        assert "error" in result
        assert "catalog" in result.lower()

    async def test_get_column_info_catalog_on_mssql_errors(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            result = await analysis_tools.get_column_info(
                connection_id="c", table_name="t", catalog="x"
            )
        assert "error" in result
        assert "catalog" in result.lower()

    async def test_find_pk_candidates_catalog_on_mssql_errors(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            result = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="t", catalog="x"
            )
        assert "error" in result
        assert "catalog" in result.lower()

    async def test_find_fk_candidates_catalog_on_mssql_errors(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            result = await analysis_tools.find_fk_candidates(
                connection_id="c", table_name="t", column_name="id", catalog="x"
            )
        assert "error" in result
        assert "catalog" in result.lower()

    async def test_list_schemas_catalog_on_mssql_errors(self):
        from src.mcp_server import schema_tools

        factory, _ = _patch_cm(schema_tools, MssqlDialect())
        with factory:
            result = await schema_tools.list_schemas(connection_id="c", catalog="x")
        assert "error" in result
        assert "catalog" in result.lower()

    async def test_list_tables_catalog_on_mssql_errors(self):
        from src.mcp_server import schema_tools

        factory, _ = _patch_cm(schema_tools, MssqlDialect())
        with factory:
            result = await schema_tools.list_tables(connection_id="c", catalog="x")
        assert "error" in result
        assert "catalog" in result.lower()


class TestResolverConflictBoundary:
    """D-04 conflict: table_name segment vs explicit schema_name disagreement."""

    async def test_get_sample_data_conflict_errors(self):
        from src.mcp_server import query_tools

        factory, _ = _patch_cm(query_tools, MssqlDialect())
        with factory, patch.object(query_tools, "get_config") as cfg:
            cfg.return_value.defaults.sample_size = 5
            result = await query_tools.get_sample_data(
                connection_id="c", table_name="sales.orders", schema_name="hr"
            )
        assert "error" in result
        assert "conflict" in result.lower()

    async def test_get_column_info_conflict_errors(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            result = await analysis_tools.get_column_info(
                connection_id="c", table_name="sales.orders", schema_name="hr"
            )
        assert "error" in result
        assert "conflict" in result.lower()

    async def test_find_pk_candidates_conflict_errors(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            result = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="sales.orders", schema_name="hr"
            )
        assert "error" in result
        assert "conflict" in result.lower()

    async def test_find_fk_candidates_conflict_errors(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            result = await analysis_tools.find_fk_candidates(
                connection_id="c",
                table_name="sales.orders",
                column_name="id",
                schema_name="hr",
            )
        assert "error" in result
        assert "conflict" in result.lower()


class TestDatabricksThreePartHappyPath:
    """SC3: a 3-part table_name resolves and reaches the deeper layer with
    catalog/schema/table split apart."""

    async def test_get_sample_data_three_part_routes_catalog(self):
        from src.mcp_server import query_tools

        fake_engine = MagicMock(name="engine")
        factory, _ = _patch_cm(query_tools, DatabricksDialect(), engine=fake_engine)

        fake_sample = MagicMock()
        fake_sample.sample_id = "sid"
        fake_sample.table_id = "tid"
        fake_sample.sample_size = 0
        fake_sample.rows = []
        fake_sample.sampling_method = query_tools.SamplingMethod.TOP
        fake_sample.truncated_columns = []
        fake_sample.sampled_at = datetime.now()

        with (
            factory,
            patch.object(query_tools, "MetadataService"),
            patch.object(query_tools, "QueryService") as MockQS,
            patch.object(query_tools, "get_config") as cfg,
        ):
            cfg.return_value.defaults.sample_size = 5
            MockQS.return_value.get_sample_data.return_value = fake_sample

            await query_tools.get_sample_data(
                connection_id="c", table_name="cat.sch.tbl"
            )

            kwargs = MockQS.return_value.get_sample_data.call_args.kwargs
            assert kwargs["catalog"] == "cat"
            assert kwargs["schema_name"] == "sch"
            assert kwargs["table_name"] == "tbl"

    async def test_get_column_info_three_part_routes_to_metadata(self):
        from src.mcp_server import analysis_tools

        fake_engine = MagicMock(name="engine")
        # Context-manager engine.connect() for the `with engine.connect()` block
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        fake_engine.connect.return_value.__exit__.return_value = False
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "ColumnStatsCollector") as MockCSC,
        ):
            MockMS.return_value.table_exists.return_value = True
            MockCSC.return_value.get_columns_info.return_value = []
            mock_inspect.return_value = MagicMock()

            result = await analysis_tools.get_column_info(
                connection_id="c", table_name="cat.sch.tbl"
            )

            # Cross-catalog existence check routed through MetadataService with
            # the split catalog/schema/table.
            MockMS.return_value.table_exists.assert_called_once_with(
                "tbl", "sch", catalog="cat"
            )
            # Stats collector receives the resolved schema/table.
            csc_kwargs = MockCSC.call_args.kwargs
            assert csc_kwargs["schema_name"] == "sch"
            assert csc_kwargs["table_name"] == "tbl"
            assert "success" in result

    async def test_find_pk_candidates_three_part_routes_resolved(self):
        from src.mcp_server import analysis_tools

        fake_engine = MagicMock(name="engine")
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        fake_engine.connect.return_value.__exit__.return_value = False
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "PKDiscovery") as MockPK,
        ):
            mock_inspector = MagicMock()
            mock_inspect.return_value = mock_inspector
            # Cross-catalog 3-part name -> catalog-aware existence check.
            MockMS.return_value.table_exists.return_value = True
            MockPK.return_value.find_candidates.return_value = []

            result = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="cat.sch.tbl"
            )

            MockMS.return_value.table_exists.assert_called_once_with(
                "tbl", "sch", catalog="cat"
            )
            pk_kwargs = MockPK.call_args.kwargs
            assert pk_kwargs["schema_name"] == "sch"
            assert pk_kwargs["table_name"] == "tbl"
            assert pk_kwargs["catalog"] == "cat"
            assert "success" in result

    async def test_find_fk_candidates_three_part_routes_resolved(self):
        from src.mcp_server import analysis_tools

        fake_engine = MagicMock(name="engine")
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        fake_engine.connect.return_value.__exit__.return_value = False
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        fake_fk_result = MagicMock()
        fake_fk_result.candidates = []
        fake_fk_result.total_found = 0
        fake_fk_result.was_limited = False
        fake_fk_result.search_scope = "scope"

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "CatalogAwareReflector") as MockReflector,
            patch.object(analysis_tools, "FKCandidateSearch") as MockFK,
        ):
            mock_inspector = MagicMock()
            mock_inspect.return_value = mock_inspector
            # Cross-catalog 3-part name -> catalog-aware existence + reflection.
            MockMS.return_value.table_exists.return_value = True
            MockReflector.return_value.reflect_columns.return_value = [
                {"name": "id", "data_type": "INT"}
            ]
            MockFK.return_value.find_candidates.return_value = fake_fk_result

            result = await analysis_tools.find_fk_candidates(
                connection_id="c", table_name="cat.sch.tbl", column_name="id"
            )

            MockMS.return_value.table_exists.assert_called_once_with(
                "tbl", "sch", catalog="cat"
            )
            MockReflector.return_value.reflect_columns.assert_called_once_with(
                "cat", "sch", "tbl"
            )
            fk_kwargs = MockFK.call_args.kwargs
            assert fk_kwargs["source_schema"] == "sch"
            assert fk_kwargs["source_table"] == "tbl"
            assert fk_kwargs["catalog"] == "cat"
            assert "success" in result


# ---------------------------------------------------------------------------
# Cross-catalog wiring boundary tests (IDENT-08, Plan 15.1-05)
#
# Assert that the resolved catalog threads end-to-end through the three
# analysis tools on the Databricks cross-catalog branch, and that pk/fk use
# the catalog-aware MetadataService.table_exists existence check (mirroring
# get_column_info) rather than the catalog-blind Inspector path.
# ---------------------------------------------------------------------------


class TestCrossCatalogWiring:
    """IDENT-08: catalog reaches each analysis class; pk/fk use catalog-aware
    existence check on the cross-catalog Databricks branch."""

    @staticmethod
    def _databricks_engine():
        fake_engine = MagicMock(name="engine")
        fake_engine.connect.return_value.__enter__.return_value = MagicMock()
        fake_engine.connect.return_value.__exit__.return_value = False
        return fake_engine

    async def test_get_column_info_threads_catalog(self):
        from src.mcp_server import analysis_tools

        fake_engine = self._databricks_engine()
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "ColumnStatsCollector") as MockCSC,
        ):
            MockMS.return_value.table_exists.return_value = True
            MockCSC.return_value.get_columns_info.return_value = []
            mock_inspect.return_value = MagicMock()

            result = await analysis_tools.get_column_info(
                connection_id="c", table_name="tbl", schema_name="sch",
                catalog="cerner_src",
            )

            # Catalog-aware existence check used (not Inspector path).
            MockMS.return_value.table_exists.assert_called_once_with(
                "tbl", "sch", catalog="cerner_src"
            )
            assert MockCSC.call_args.kwargs["catalog"] == "cerner_src"
            assert "success" in result

    async def test_find_pk_candidates_threads_catalog(self):
        from src.mcp_server import analysis_tools

        fake_engine = self._databricks_engine()
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "PKDiscovery") as MockPK,
        ):
            MockMS.return_value.table_exists.return_value = True
            MockPK.return_value.find_candidates.return_value = []
            mock_inspector = MagicMock()
            mock_inspect.return_value = mock_inspector

            result = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="tbl", schema_name="sch",
                catalog="cerner_src",
            )

            # Cross-catalog existence check routed through MetadataService.
            MockMS.return_value.table_exists.assert_called_once_with(
                "tbl", "sch", catalog="cerner_src"
            )
            # Inspector existence path NOT used on the cross-catalog branch.
            mock_inspector.get_table_names.assert_not_called()
            assert MockPK.call_args.kwargs["catalog"] == "cerner_src"
            assert "success" in result

    async def test_find_fk_candidates_threads_catalog(self):
        from src.mcp_server import analysis_tools

        fake_engine = self._databricks_engine()
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        fake_fk_result = MagicMock()
        fake_fk_result.candidates = []
        fake_fk_result.total_found = 0
        fake_fk_result.was_limited = False
        fake_fk_result.search_scope = "scope"

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "CatalogAwareReflector") as MockReflector,
            patch.object(analysis_tools, "FKCandidateSearch") as MockFK,
        ):
            MockMS.return_value.table_exists.return_value = True
            MockReflector.return_value.reflect_columns.return_value = [
                {"name": "id", "data_type": "INT"}
            ]
            MockFK.return_value.find_candidates.return_value = fake_fk_result
            mock_inspector = MagicMock()
            mock_inspect.return_value = mock_inspector

            result = await analysis_tools.find_fk_candidates(
                connection_id="c", table_name="tbl", column_name="id",
                schema_name="sch", catalog="cerner_src",
            )

            # Cross-catalog existence check routed through MetadataService.
            MockMS.return_value.table_exists.assert_called_once_with(
                "tbl", "sch", catalog="cerner_src"
            )
            # Source-column type read uses catalog-aware reflection, not Inspector.
            MockReflector.return_value.reflect_columns.assert_called_once_with(
                "cerner_src", "sch", "tbl"
            )
            mock_inspector.get_columns.assert_not_called()
            assert MockFK.call_args.kwargs["catalog"] == "cerner_src"
            assert MockFK.call_args.kwargs["source_data_type"] == "INT"
            assert "success" in result

    async def test_default_path_no_catalog_get_column_info(self):
        from src.mcp_server import analysis_tools

        fake_engine = self._databricks_engine()
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "ColumnStatsCollector") as MockCSC,
        ):
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ["tbl"]
            mock_inspect.return_value = mock_inspector
            MockCSC.return_value.get_columns_info.return_value = []

            result = await analysis_tools.get_column_info(
                connection_id="c", table_name="tbl", schema_name="sch",
            )

            # No catalog -> Inspector existence path; no MetadataService.table_exists.
            MockMS.return_value.table_exists.assert_not_called()
            mock_inspector.get_table_names.assert_called_once_with(schema="sch")
            assert MockCSC.call_args.kwargs["catalog"] is None
            assert "success" in result

    async def test_default_path_no_catalog_find_pk_candidates(self):
        from src.mcp_server import analysis_tools

        fake_engine = self._databricks_engine()
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "PKDiscovery") as MockPK,
        ):
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ["tbl"]
            mock_inspect.return_value = mock_inspector
            MockPK.return_value.find_candidates.return_value = []

            result = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="tbl", schema_name="sch",
            )

            MockMS.return_value.table_exists.assert_not_called()
            mock_inspector.get_table_names.assert_called_once_with(schema="sch")
            assert MockPK.call_args.kwargs["catalog"] is None
            assert "success" in result

    async def test_default_path_no_catalog_find_fk_candidates(self):
        from src.mcp_server import analysis_tools

        fake_engine = self._databricks_engine()
        factory, _ = _patch_cm(analysis_tools, DatabricksDialect(), engine=fake_engine)

        fake_fk_result = MagicMock()
        fake_fk_result.candidates = []
        fake_fk_result.total_found = 0
        fake_fk_result.was_limited = False
        fake_fk_result.search_scope = "scope"

        with (
            factory,
            patch.object(analysis_tools, "inspect") as mock_inspect,
            patch("src.db.metadata.MetadataService") as MockMS,
            patch.object(analysis_tools, "FKCandidateSearch") as MockFK,
        ):
            mock_inspector = MagicMock()
            mock_inspector.get_table_names.return_value = ["tbl"]
            mock_inspector.get_columns.return_value = [{"name": "id", "type": "INT"}]
            mock_inspect.return_value = mock_inspector
            MockFK.return_value.find_candidates.return_value = fake_fk_result

            result = await analysis_tools.find_fk_candidates(
                connection_id="c", table_name="tbl", column_name="id",
                schema_name="sch",
            )

            MockMS.return_value.table_exists.assert_not_called()
            mock_inspector.get_table_names.assert_called_once_with(schema="sch")
            mock_inspector.get_columns.assert_called_once_with("tbl", schema="sch")
            assert MockFK.call_args.kwargs["catalog"] is None
            assert "success" in result

    async def test_mssql_catalog_rejected_unchanged_all_three(self):
        from src.mcp_server import analysis_tools

        # get_column_info
        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            r1 = await analysis_tools.get_column_info(
                connection_id="c", table_name="t", catalog="x"
            )
        assert "error" in r1 and "catalog" in r1.lower()

        # find_pk_candidates
        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            r2 = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="t", catalog="x"
            )
        assert "error" in r2 and "catalog" in r2.lower()

        # find_fk_candidates
        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory:
            r3 = await analysis_tools.find_fk_candidates(
                connection_id="c", table_name="t", column_name="id", catalog="x"
            )
        assert "error" in r3 and "catalog" in r3.lower()


class TestAnalysisToolsNotFoundEarlyExit:
    """Drive each analysis tool to its in-tool not-found early-exit.

    These cover the ``return missing`` / ``return col_error`` branches that the
    tools take when ``_check_table_exists`` / ``_reflect_source_column`` report
    an absent table or column. The non-cross-catalog path runs synchronously via
    a mocked SQLAlchemy Inspector (no DB, no catalog gate). Equivalent to the
    integration ``test_table_not_found`` cases, but inside the CI selection.
    """

    def _empty_inspector(self):
        """Inspector reporting no tables, views, or columns."""
        inspector = MagicMock()
        inspector.get_table_names.return_value = []
        inspector.get_view_names.return_value = []
        inspector.get_columns.return_value = []
        return inspector

    async def test_get_column_info_table_not_found(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory, patch.object(
            analysis_tools, "inspect", return_value=self._empty_inspector()
        ):
            result = await analysis_tools.get_column_info(
                connection_id="c", table_name="ghost", schema_name="dbo"
            )
        assert "error" in result and "not found" in result.lower()
        assert "ghost" in result

    async def test_find_pk_candidates_table_not_found(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory, patch.object(
            analysis_tools, "inspect", return_value=self._empty_inspector()
        ):
            result = await analysis_tools.find_pk_candidates(
                connection_id="c", table_name="ghost", schema_name="dbo"
            )
        assert "error" in result and "not found" in result.lower()
        assert "ghost" in result

    async def test_find_fk_candidates_table_not_found(self):
        from src.mcp_server import analysis_tools

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory, patch.object(
            analysis_tools, "inspect", return_value=self._empty_inspector()
        ):
            result = await analysis_tools.find_fk_candidates(
                connection_id="c",
                table_name="ghost",
                column_name="id",
                schema_name="dbo",
            )
        assert "error" in result and "not found" in result.lower()
        assert "ghost" in result

    async def test_find_fk_candidates_column_not_found(self):
        """Table present but the source column is absent -> column not-found exit."""
        from src.mcp_server import analysis_tools

        inspector = MagicMock()
        inspector.get_table_names.return_value = ["orders"]
        inspector.get_view_names.return_value = []
        inspector.get_columns.return_value = [{"name": "order_id", "type": "INTEGER"}]

        factory, _ = _patch_cm(analysis_tools, MssqlDialect())
        with factory, patch.object(
            analysis_tools, "inspect", return_value=inspector
        ):
            result = await analysis_tools.find_fk_candidates(
                connection_id="c",
                table_name="orders",
                column_name="ghost_col",
                schema_name="dbo",
            )
        assert "error" in result and "not found" in result.lower()
        assert "ghost_col" in result
