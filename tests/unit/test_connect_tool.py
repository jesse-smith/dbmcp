"""Unit tests for rewritten connect_database tool routing.

Tests the two-param interface (connection_name | sqlalchemy_url) and
verifies correct routing to connect_with_config / connect_with_url.
"""

from unittest.mock import MagicMock, patch

import toon_format

from src.mcp_server.server import connect_database


def _decode(toon_str: str) -> dict:
    """Decode a TOON-encoded tool response to a dict."""
    return toon_format.decode(toon_str)


# ---------------------------------------------------------------------------
# Validation: both / neither params
# ---------------------------------------------------------------------------


class TestConnectDatabaseParamValidation:
    """Tests for parameter mutual exclusivity."""

    async def test_both_params_error(self):
        """Passing both connection_name and sqlalchemy_url returns error."""
        result = await connect_database(
            connection_name="mydb",
            sqlalchemy_url="sqlite:///test.db",
        )
        data = _decode(result)
        assert data["status"] == "error"
        assert "Provide either connection_name or sqlalchemy_url, not both" in data["error_message"]

    async def test_no_params_error(self):
        """Passing neither connection_name nor sqlalchemy_url returns error."""
        result = await connect_database()
        data = _decode(result)
        assert data["status"] == "error"
        assert "Provide connection_name or sqlalchemy_url" in data["error_message"]


# ---------------------------------------------------------------------------
# connection_name path
# ---------------------------------------------------------------------------


class TestConnectDatabaseByName:
    """Tests for the connection_name path."""

    async def test_connection_name_not_found(self):
        """Unknown connection_name returns error with 'not found in config'."""
        from src.config import AppConfig

        mock_config = AppConfig(connections={})
        with patch("src.mcp_server.schema_tools.get_config", return_value=mock_config):
            result = await connect_database(connection_name="missing")

        data = _decode(result)
        assert data["status"] == "error"
        assert "not found in config" in data["error_message"]

    async def test_connection_name_valid_calls_connect_with_config(self):
        """Valid connection_name routes through connect_with_config."""
        from src.config import AppConfig, MssqlConnectionConfig
        from src.models.schema import Connection

        mock_config = AppConfig(
            connections={"mydb": MssqlConnectionConfig(server="host", database="db")}
        )
        mock_conn = Connection(connection_id="abc123", server="host", database="db")
        mock_engine = MagicMock()
        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = []

        with (
            patch("src.mcp_server.schema_tools.get_config", return_value=mock_config),
            patch("src.mcp_server.schema_tools.get_dialect") as mock_get_dialect,
            patch.object(
                __import__("src.mcp_server.server", fromlist=["_connection_manager"]),
                "_connection_manager",
            ) as _,
            patch("src.mcp_server.schema_tools.get_connection_manager") as mock_gcm,
            patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_dialect_cls = MagicMock()
            mock_dialect_instance = MagicMock()
            mock_dialect_cls.return_value = mock_dialect_instance
            mock_get_dialect.return_value = mock_dialect_cls

            mock_cm = MagicMock()
            mock_cm.connect_with_config.return_value = mock_conn
            mock_cm.get_engine.return_value = mock_engine
            mock_gcm.return_value = mock_cm

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache)

            result = await connect_database(connection_name="mydb")

        data = _decode(result)
        assert data["status"] == "success"
        assert data["connection_id"] == "abc123"
        mock_cm.connect_with_config.assert_called_once()


# ---------------------------------------------------------------------------
# sqlalchemy_url path
# ---------------------------------------------------------------------------


class TestConnectDatabaseByUrl:
    """Tests for the sqlalchemy_url path."""

    async def test_sqlalchemy_url_calls_connect_with_url(self):
        """sqlalchemy_url auto-detects dialect and connects via connect_with_url."""
        from src.config import AppConfig
        from src.models.schema import Connection

        mock_config = AppConfig()
        mock_conn = Connection(
            connection_id="url123",
            server="localhost",
            database="testdb",
            dialect_name="generic",
        )
        mock_engine = MagicMock()
        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = []
        mock_dialect = MagicMock()

        with (
            patch("src.mcp_server.schema_tools.get_config", return_value=mock_config),
            patch("src.mcp_server.schema_tools.resolve_dialect_from_url", return_value=mock_dialect),
            patch("src.mcp_server.schema_tools.get_connection_manager") as mock_gcm,
            patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_cm = MagicMock()
            mock_cm.connect_with_url.return_value = mock_conn
            mock_cm.get_engine.return_value = mock_engine
            mock_gcm.return_value = mock_cm

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache)

            result = await connect_database(sqlalchemy_url="sqlite:///test.db")

        data = _decode(result)
        assert data["status"] == "success"
        assert data["connection_id"] == "url123"
        assert data["dialect"] == "generic"
        mock_cm.connect_with_url.assert_called_once()

    async def test_databricks_connection_name_routes_through_connect_with_config(self):
        """DatabricksConnectionConfig via connection_name routes to connect_with_url."""
        from src.config import AppConfig, DatabricksConnectionConfig
        from src.models.schema import Connection

        mock_config = AppConfig(
            connections={
                "mydb": DatabricksConnectionConfig(
                    host="workspace.cloud.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="dapi_test",
                    catalog="analytics",
                    schema_name="prod",
                )
            }
        )
        mock_conn = Connection(
            connection_id="dbr123",
            server="workspace.cloud.databricks.com",
            database="analytics",
            dialect_name="databricks",
        )
        mock_engine = MagicMock()
        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = []

        with (
            patch("src.mcp_server.schema_tools.get_config", return_value=mock_config),
            patch("src.mcp_server.schema_tools.get_dialect") as mock_get_dialect,
            patch("src.mcp_server.schema_tools.get_connection_manager") as mock_gcm,
            patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_dialect_cls = MagicMock()
            mock_dialect_instance = MagicMock()
            mock_dialect_cls.return_value = mock_dialect_instance
            mock_get_dialect.return_value = mock_dialect_cls

            mock_cm = MagicMock()
            mock_cm.connect_with_config.return_value = mock_conn
            mock_cm.get_engine.return_value = mock_engine
            mock_gcm.return_value = mock_cm

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache)

            result = await connect_database(connection_name="mydb")

        data = _decode(result)
        assert data["status"] == "success"
        assert data["connection_id"] == "dbr123"
        mock_cm.connect_with_config.assert_called_once()

    async def test_url_credentials_not_in_response(self):
        """URL credentials must not appear in success response."""
        from src.config import AppConfig
        from src.models.schema import Connection

        mock_config = AppConfig()
        mock_conn = Connection(
            connection_id="url123",
            server="myhost",
            database="mydb",
            dialect_name="generic",
        )
        mock_engine = MagicMock()
        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = []

        with (
            patch("src.mcp_server.schema_tools.get_config", return_value=mock_config),
            patch("src.mcp_server.schema_tools.resolve_dialect_from_url", return_value=MagicMock()),
            patch("src.mcp_server.schema_tools.get_connection_manager") as mock_gcm,
            patch("src.mcp_server.schema_tools.MetadataService", return_value=mock_metadata_svc),
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_cm = MagicMock()
            mock_cm.connect_with_url.return_value = mock_conn
            mock_cm.get_engine.return_value = mock_engine
            mock_gcm.return_value = mock_cm

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache)

            result = await connect_database(
                sqlalchemy_url="postgresql://user:supersecret@myhost/mydb"
            )

        # The raw URL with credentials must NOT be in the response
        assert "supersecret" not in result
        assert "user:supersecret" not in result


# ---------------------------------------------------------------------------
# DatabricksConnectionConfig routing in connect_with_config
# ---------------------------------------------------------------------------


class TestConnectWithConfigDatabricks:
    """Direct tests for ConnectionManager.connect_with_config with DatabricksConnectionConfig."""

    def _patched_cm_and_dialect(self, dialect_name="databricks"):
        """Build a ConnectionManager with _test_connection neutralized and a
        dialect mock whose create_engine returns a MagicMock Engine."""
        from src.db.connection import ConnectionManager

        cm = ConnectionManager()
        # _test_connection runs SELECT 1 against a real engine; neutralize it.
        cm._test_connection = lambda engine, start_time, dialect_name: None
        dialect = MagicMock()
        dialect.name = dialect_name
        dialect.create_engine.return_value = MagicMock(name="Engine")
        return cm, dialect

    def test_databricks_config_calls_dialect_with_resolved_kwargs(self):
        """DatabricksConnectionConfig invokes dialect.create_engine with kwargs
        (host, http_path, token, catalog, schema) — NOT sqlalchemy_url."""
        from src.config import DatabricksConnectionConfig

        config = DatabricksConnectionConfig(
            host="workspace.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/abc123",
            token="dapi_test_token",
            catalog="analytics",
            schema_name="production",
        )
        cm, dialect = self._patched_cm_and_dialect()

        cm.connect_with_config(config, dialect, query_timeout=30)

        dialect.create_engine.assert_called_once()
        kwargs = dialect.create_engine.call_args.kwargs
        assert kwargs == {
            "host": "workspace.cloud.databricks.com",
            "http_path": "/sql/1.0/warehouses/abc123",
            "token": "dapi_test_token",
            "catalog": "analytics",
            "schema": "production",
        }
        assert "sqlalchemy_url" not in kwargs

    def test_databricks_config_resolves_env_var_token(self):
        """Token with env var reference is resolved via resolve_env_vars."""
        import os

        from src.config import DatabricksConnectionConfig

        config = DatabricksConnectionConfig(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token="${DATABRICKS_TOKEN}",
        )
        cm, dialect = self._patched_cm_and_dialect()

        with patch.dict(os.environ, {"DATABRICKS_TOKEN": "resolved_secret"}):
            cm.connect_with_config(config, dialect)

        kwargs = dialect.create_engine.call_args.kwargs
        assert kwargs["token"] == "resolved_secret"
        assert "${DATABRICKS_TOKEN}" not in kwargs["token"]

    def test_databricks_config_resolves_env_var_host_and_http_path(self):
        """host and http_path env var references are resolved (Bug A regression)."""
        import os

        from src.config import DatabricksConnectionConfig

        config = DatabricksConnectionConfig(
            host="${DBX_HOST}",
            http_path="${DBX_PATH}",
            token="tok",
        )
        cm, dialect = self._patched_cm_and_dialect()

        with patch.dict(
            os.environ,
            {"DBX_HOST": "real.databricks.com", "DBX_PATH": "/sql/1.0/warehouses/xyz"},
        ):
            cm.connect_with_config(config, dialect)

        kwargs = dialect.create_engine.call_args.kwargs
        assert kwargs["host"] == "real.databricks.com"
        assert kwargs["http_path"] == "/sql/1.0/warehouses/xyz"

    def test_databricks_config_defaults_catalog_and_schema(self):
        """Default catalog 'main' and schema 'default' are passed when unset."""
        from src.config import DatabricksConnectionConfig

        config = DatabricksConnectionConfig(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token="tok",
        )
        cm, dialect = self._patched_cm_and_dialect()

        cm.connect_with_config(config, dialect)

        kwargs = dialect.create_engine.call_args.kwargs
        assert kwargs["catalog"] == "main"
        assert kwargs["schema"] == "default"

    def test_databricks_config_none_token_uses_empty_string(self):
        """None token becomes empty string in the token kwarg."""
        from src.config import DatabricksConnectionConfig

        config = DatabricksConnectionConfig(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token=None,
        )
        cm, dialect = self._patched_cm_and_dialect()

        cm.connect_with_config(config, dialect)

        kwargs = dialect.create_engine.call_args.kwargs
        assert kwargs["token"] == ""


# ---------------------------------------------------------------------------
# WIRING-01 regression: dialect threaded into one-shot MetadataService
# ---------------------------------------------------------------------------


class TestConnectDatabaseThreadsDialectIntoMetadataService:
    """Regression tests for WIRING-01 (META-01 integration boundary).

    Before the fix, connect_database's one-shot MetadataService was constructed
    as `MetadataService(engine)` — without the resolved dialect. For generic
    SQLAlchemy URLs (e.g., postgresql://...), engine.dialect.name differs from
    the "generic" registry key, so auto-infer yielded None and schema_count
    was degraded.
    """

    async def test_url_path_threads_dialect_kwarg_into_metadata_service(self):
        """One-shot MetadataService receives dialect= from resolve_dialect_from_url."""
        from src.config import AppConfig
        from src.models.schema import Connection

        mock_config = AppConfig()
        mock_conn = Connection(
            connection_id="cid-wiring01",
            server="h",
            database="db",
            dialect_name="generic",
        )
        mock_engine = MagicMock(name="engine")
        # Simulate engine.dialect.name NOT matching the registry key for "generic"
        mock_engine.dialect.name = "postgresql"

        fake_dialect = MagicMock(name="resolved_dialect")
        fake_dialect.name = "generic"

        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = ["s1", "s2"]

        with (
            patch("src.mcp_server.schema_tools.get_config", return_value=mock_config),
            patch(
                "src.mcp_server.schema_tools.resolve_dialect_from_url",
                return_value=fake_dialect,
            ),
            patch("src.mcp_server.schema_tools.get_connection_manager") as mock_gcm,
            patch(
                "src.mcp_server.schema_tools.MetadataService",
                return_value=mock_metadata_svc,
            ) as MockMS,
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_cm = MagicMock()
            mock_cm.connect_with_url.return_value = mock_conn
            mock_cm.get_engine.return_value = mock_engine
            mock_gcm.return_value = mock_cm

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache)

            await connect_database(sqlalchemy_url="postgresql://u:p@h/db")

        # Assert: MetadataService was constructed with dialect=fake_dialect
        MockMS.assert_called_once_with(mock_engine, dialect=fake_dialect)

    async def test_schema_count_correct_for_generic_url_with_mismatched_engine_dialect(self):
        """schema_count reflects list_schemas count when dialect is threaded explicitly.

        Even when engine.dialect.name ("postgresql") does not match the "generic"
        registry key, the response surfaces the real schema count because the
        resolved dialect is passed into MetadataService (not auto-inferred).
        """
        from src.config import AppConfig
        from src.models.schema import Connection

        mock_config = AppConfig()
        mock_conn = Connection(
            connection_id="cid-wiring01b",
            server="h",
            database="db",
            dialect_name="generic",
        )
        mock_engine = MagicMock(name="engine")
        mock_engine.dialect.name = "postgresql"

        fake_dialect = MagicMock(name="resolved_dialect")
        fake_dialect.name = "generic"

        mock_metadata_svc = MagicMock()
        mock_metadata_svc.list_schemas.return_value = ["s1", "s2", "s3"]

        with (
            patch("src.mcp_server.schema_tools.get_config", return_value=mock_config),
            patch(
                "src.mcp_server.schema_tools.resolve_dialect_from_url",
                return_value=fake_dialect,
            ),
            patch("src.mcp_server.schema_tools.get_connection_manager") as mock_gcm,
            patch(
                "src.mcp_server.schema_tools.MetadataService",
                return_value=mock_metadata_svc,
            ) as MockMS,
            patch("src.mcp_server.schema_tools.Path") as mock_path,
        ):
            mock_cm = MagicMock()
            mock_cm.connect_with_url.return_value = mock_conn
            mock_cm.get_engine.return_value = mock_engine
            mock_gcm.return_value = mock_cm

            mock_cache = MagicMock()
            mock_cache.exists.return_value = False
            mock_path.return_value.__truediv__ = MagicMock(return_value=mock_cache)

            result = await connect_database(sqlalchemy_url="postgresql://u:p@h/db")

        # Construction: dialect was threaded through explicitly
        MockMS.assert_called_once_with(mock_engine, dialect=fake_dialect)
        # Behavior: schema_count equals len(list_schemas) — not degraded
        data = _decode(result)
        assert data["status"] == "success"
        assert data["schema_count"] == 3
