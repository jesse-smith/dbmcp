"""Unit tests for generalized ConnectionManager methods.

Tests connect_with_url, connect_with_config, _generate_url_connection_id,
and generalized Connection model with optional MSSQL-specific fields.
"""

from datetime import datetime
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.db.connection import ConnectionError, ConnectionManager
from src.models.schema import AuthenticationMethod, Connection


# ---------------------------------------------------------------------------
# Connection model generalization
# ---------------------------------------------------------------------------


class TestConnectionModelDefaults:
    """Connection dataclass accepts minimal fields for generic connections."""

    def test_connection_minimal_creation(self):
        """Connection can be created with only connection_id (all others have defaults)."""
        conn = Connection(connection_id="abc")
        assert conn.connection_id == "abc"
        assert conn.server == ""
        assert conn.database == ""
        assert conn.port == 0
        assert conn.dialect_name == "mssql"
        assert conn.username is None
        assert isinstance(conn.created_at, datetime)

    def test_connection_backward_compat(self):
        """Connection(connection_id, server, database) still works (backward compat)."""
        conn = Connection(
            connection_id="abc",
            server="myhost",
            database="mydb",
        )
        assert conn.server == "myhost"
        assert conn.database == "mydb"
        assert conn.port == 0
        assert conn.authentication_method == AuthenticationMethod.SQL

    def test_connection_dialect_name_field(self):
        """Connection can store a dialect_name for display purposes."""
        conn = Connection(connection_id="abc", dialect_name="postgresql")
        assert conn.dialect_name == "postgresql"


# ---------------------------------------------------------------------------
# connect_with_url
# ---------------------------------------------------------------------------


class TestConnectWithUrl:
    """Tests for ConnectionManager.connect_with_url."""

    def _make_mock_dialect(self, name="generic"):
        dialect = MagicMock()
        dialect.name = name
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        dialect.create_engine.return_value = mock_engine
        return dialect, mock_engine

    def test_connect_with_url_returns_connection(self):
        """connect_with_url creates engine via dialect and returns Connection."""
        dialect, mock_engine = self._make_mock_dialect()
        manager = ConnectionManager()

        conn = manager.connect_with_url(
            sqlalchemy_url="sqlite:///test.db",
            dialect=dialect,
        )

        assert isinstance(conn, Connection)
        assert conn.dialect_name == "generic"
        dialect.create_engine.assert_called_once()
        call_kwargs = dialect.create_engine.call_args.kwargs
        assert call_kwargs["sqlalchemy_url"] == "sqlite:///test.db"

    def test_connect_with_url_populates_host_and_database(self):
        """connect_with_url extracts host and database from URL into Connection."""
        dialect, _ = self._make_mock_dialect()
        manager = ConnectionManager()

        conn = manager.connect_with_url(
            sqlalchemy_url="postgresql://myhost:5432/mydb",
            dialect=dialect,
        )

        assert conn.server == "myhost"
        assert conn.database == "mydb"
        assert conn.port == 5432

    def test_connect_with_url_stores_dialect(self):
        """connect_with_url stores dialect in _dialects dict."""
        dialect, _ = self._make_mock_dialect()
        manager = ConnectionManager()

        conn = manager.connect_with_url(
            sqlalchemy_url="sqlite:///test.db",
            dialect=dialect,
        )

        assert manager._dialects[conn.connection_id] is dialect

    def test_connect_with_url_reuses_existing(self):
        """connect_with_url returns existing connection for same URL."""
        dialect, _ = self._make_mock_dialect()
        manager = ConnectionManager()

        conn1 = manager.connect_with_url("sqlite:///test.db", dialect)
        conn2 = manager.connect_with_url("sqlite:///test.db", dialect)

        assert conn1.connection_id == conn2.connection_id
        # create_engine only called once (reuse)
        assert dialect.create_engine.call_count == 1

    def test_connect_with_url_hides_password_on_error(self):
        """connect_with_url uses render_as_string(hide_password=True) in error messages."""
        dialect = MagicMock()
        dialect.name = "generic"
        dialect.create_engine.side_effect = SQLAlchemyError("Connection refused")
        manager = ConnectionManager()

        with pytest.raises(ConnectionError) as exc_info:
            manager.connect_with_url(
                sqlalchemy_url="postgresql://user:secret@host/db",
                dialect=dialect,
            )

        error_msg = str(exc_info.value)
        assert "secret" not in error_msg
        assert "***" in error_msg or "user:***@host" in error_msg


# ---------------------------------------------------------------------------
# _test_connection uses SELECT 1
# ---------------------------------------------------------------------------


class TestTestConnectionDialectNeutral:
    """_test_connection uses dialect-neutral SELECT 1 probe."""

    def test_test_connection_uses_select_1(self):
        """_test_connection executes SELECT 1 (not @@VERSION)."""
        manager = ConnectionManager()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        manager._test_connection(mock_engine, 0.0, "generic")

        # Verify the executed SQL is SELECT 1
        mock_conn.execute.assert_called_once()
        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "SELECT 1" in executed_sql
        assert "@@VERSION" not in executed_sql


# ---------------------------------------------------------------------------
# connect_with_config
# ---------------------------------------------------------------------------


class TestConnectWithConfig:
    """Tests for ConnectionManager.connect_with_config routing."""

    def test_connect_with_config_mssql_routes_to_connect(self):
        """connect_with_config for MssqlConnectionConfig calls existing connect() logic."""
        from src.config import MssqlConnectionConfig

        config = MssqlConnectionConfig(
            server="myserver",
            database="mydb",
            port=1433,
            authentication_method="windows",
        )
        dialect = MagicMock()
        manager = ConnectionManager()

        with patch.object(manager, "connect") as mock_connect:
            mock_connect.return_value = Connection(connection_id="test123")
            result = manager.connect_with_config(config, dialect)

        mock_connect.assert_called_once()
        call_kwargs = mock_connect.call_args.kwargs
        assert call_kwargs["server"] == "myserver"
        assert call_kwargs["database"] == "mydb"
        assert result.connection_id == "test123"

    def test_connect_with_config_generic_routes_to_connect_with_url(self):
        """connect_with_config for GenericConnectionConfig calls connect_with_url."""
        from src.config import GenericConnectionConfig

        config = GenericConnectionConfig(sqlalchemy_url="sqlite:///test.db")
        dialect = MagicMock()
        manager = ConnectionManager()

        with patch.object(manager, "connect_with_url") as mock_url:
            mock_url.return_value = Connection(connection_id="url123")
            result = manager.connect_with_config(config, dialect)

        mock_url.assert_called_once()
        assert mock_url.call_args.args[0] == "sqlite:///test.db"
        assert result.connection_id == "url123"

    def test_connect_with_config_unsupported_raises(self):
        """connect_with_config for unknown config type raises ValueError."""
        config = MagicMock()
        config.__class__.__name__ = "UnknownConfig"
        dialect = MagicMock()
        manager = ConnectionManager()

        with pytest.raises(ValueError, match="Unsupported config type"):
            manager.connect_with_config(config, dialect)
