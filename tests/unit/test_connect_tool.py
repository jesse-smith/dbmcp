"""Unit tests for rewritten connect_database tool routing.

Tests the two-param interface (connection_name | sqlalchemy_url) and
verifies correct routing to connect_with_config / connect_with_url.
"""

from unittest.mock import MagicMock, patch

import pytest

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

    def test_databricks_config_routes_to_connect_with_url(self):
        """DatabricksConnectionConfig routes to connect_with_url with correct URL."""
        from src.config import DatabricksConnectionConfig
        from src.db.connection import ConnectionManager

        config = DatabricksConnectionConfig(
            host="workspace.cloud.databricks.com",
            http_path="/sql/1.0/warehouses/abc123",
            token="dapi_test_token",
            catalog="analytics",
            schema_name="production",
        )
        dialect = MagicMock()
        cm = ConnectionManager()

        with patch.object(cm, "connect_with_url") as mock_connect_url:
            mock_connect_url.return_value = MagicMock()
            cm.connect_with_config(config, dialect, query_timeout=30)

            mock_connect_url.assert_called_once()
            url_arg = mock_connect_url.call_args[0][0]

            assert url_arg.startswith("databricks://token:")
            assert "dapi_test_token" in url_arg
            assert "workspace.cloud.databricks.com" in url_arg
            assert "http_path" in url_arg
            assert "catalog=analytics" in url_arg
            assert "schema=production" in url_arg

    def test_databricks_config_resolves_env_var_token(self):
        """Token with env var reference is resolved via resolve_env_vars."""
        import os

        from src.config import DatabricksConnectionConfig
        from src.db.connection import ConnectionManager

        config = DatabricksConnectionConfig(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token="${DATABRICKS_TOKEN}",
        )
        dialect = MagicMock()
        cm = ConnectionManager()

        with (
            patch.dict(os.environ, {"DATABRICKS_TOKEN": "resolved_secret"}),
            patch.object(cm, "connect_with_url") as mock_connect_url,
        ):
            mock_connect_url.return_value = MagicMock()
            cm.connect_with_config(config, dialect)

            url_arg = mock_connect_url.call_args[0][0]
            assert "resolved_secret" in url_arg
            assert "${DATABRICKS_TOKEN}" not in url_arg

    def test_databricks_config_defaults_catalog_and_schema(self):
        """Default catalog 'main' and schema 'default' are included in URL."""
        from src.config import DatabricksConnectionConfig
        from src.db.connection import ConnectionManager

        config = DatabricksConnectionConfig(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token="tok",
        )
        dialect = MagicMock()
        cm = ConnectionManager()

        with patch.object(cm, "connect_with_url") as mock_connect_url:
            mock_connect_url.return_value = MagicMock()
            cm.connect_with_config(config, dialect)

            url_arg = mock_connect_url.call_args[0][0]
            assert "catalog=main" in url_arg
            assert "schema=default" in url_arg

    def test_databricks_config_none_token_uses_empty_string(self):
        """None token results in empty string in URL password position."""
        from src.config import DatabricksConnectionConfig
        from src.db.connection import ConnectionManager

        config = DatabricksConnectionConfig(
            host="test.databricks.com",
            http_path="/sql/1.0/warehouses/abc",
            token=None,
        )
        dialect = MagicMock()
        cm = ConnectionManager()

        with patch.object(cm, "connect_with_url") as mock_connect_url:
            mock_connect_url.return_value = MagicMock()
            cm.connect_with_config(config, dialect)

            url_arg = mock_connect_url.call_args[0][0]
            assert "databricks://token:@" in url_arg
