"""Unit tests for query timeout configuration.

Tests that pyodbc connection.timeout is set via SQLAlchemy pool event
for both standard and Azure AD Integrated auth paths.
"""

from unittest.mock import MagicMock, patch

import pytest

from src.db.connection import ConnectionManager, PoolConfig
from src.models.schema import AuthenticationMethod


class TestPoolConfigQueryTimeout:
    """Tests for PoolConfig.query_timeout field."""

    def test_pool_config_has_query_timeout_default_30(self):
        """PoolConfig has query_timeout field with default 30."""
        config = PoolConfig()
        assert config.query_timeout == 30

    def test_pool_config_query_timeout_custom(self):
        """PoolConfig accepts custom query_timeout."""
        config = PoolConfig(query_timeout=60)
        assert config.query_timeout == 60


class TestConnectQueryTimeoutParam:
    """Tests for ConnectionManager.connect() query_timeout parameter."""

    def test_connect_accepts_query_timeout(self):
        """connect() accepts query_timeout parameter."""
        manager = ConnectionManager()

        with (
            patch("src.db.connection.create_engine") as mock_engine,
            patch("src.db.connection.event"),
        ):
            mock_connection = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = MagicMock(
                version="SQL Server 2019",
                database_name="testdb",
            )
            mock_connection.execute.return_value = mock_result
            mock_engine_instance = MagicMock()
            mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
            mock_engine.return_value = mock_engine_instance

            conn = manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=60,
            )
            assert conn.connection_id is not None

    def test_connect_invalid_query_timeout_negative(self):
        """query_timeout < 0 raises ValueError."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Query timeout must be 0 .* or between 5 and 300"):
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=-1,
            )

    def test_connect_invalid_query_timeout_too_low(self):
        """query_timeout between 1 and 4 raises ValueError."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Query timeout must be 0 .* or between 5 and 300"):
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=3,
            )

    def test_connect_invalid_query_timeout_too_high(self):
        """query_timeout > 300 raises ValueError."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Query timeout must be 0 .* or between 5 and 300"):
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=301,
            )

    def test_connect_query_timeout_zero_means_no_timeout(self):
        """query_timeout=0 means no timeout (valid)."""
        manager = ConnectionManager()

        with (
            patch("src.db.connection.create_engine") as mock_engine,
            patch("src.db.connection.event"),
        ):
            mock_connection = MagicMock()
            mock_result = MagicMock()
            mock_result.fetchone.return_value = MagicMock(
                version="SQL Server 2019",
                database_name="testdb",
            )
            mock_connection.execute.return_value = mock_result
            mock_engine_instance = MagicMock()
            mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
            mock_engine.return_value = mock_engine_instance

            conn = manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=0,
            )
            assert conn.connection_id is not None


class TestEngineQueryTimeoutEventListener:
    """Tests that query timeout is set via SQLAlchemy pool event on the raw pyodbc connection."""

    @patch("src.db.connection.create_engine")
    def test_standard_auth_registers_connect_event_for_timeout(self, mock_create_engine):
        """Standard auth registers a 'connect' event listener when query_timeout > 0."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            version="SQL Server 2019",
            database_name="testdb",
        )
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        with patch("src.db.connection.event") as mock_event:
            manager = ConnectionManager()
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=45,
            )

            # Verify event.listens_for was used on the engine for "connect"
            mock_event.listens_for.assert_called_once_with(mock_engine_instance, "connect")

    @patch("src.db.connection.create_engine")
    def test_no_event_listener_when_timeout_zero(self, mock_create_engine):
        """No connect event registered when query_timeout=0."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            version="SQL Server 2019",
            database_name="testdb",
        )
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        with patch("src.db.connection.event") as mock_event:
            manager = ConnectionManager()
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=0,
            )

            mock_event.listens_for.assert_not_called()

    @patch("src.db.connection.create_engine")
    def test_standard_auth_no_connect_args_for_timeout(self, mock_create_engine):
        """Standard auth does NOT pass query timeout via connect_args attrs_before."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            version="SQL Server 2019",
            database_name="testdb",
        )
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        with patch("src.db.connection.event"):
            manager = ConnectionManager()
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                query_timeout=30,
            )

            call_kwargs = mock_create_engine.call_args.kwargs
            # No connect_args should be passed — timeout is via event listener
            assert "connect_args" not in call_kwargs

    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_azure_ad_no_query_timeout_in_attrs_before(
        self, mock_create_engine, mock_provider_cls
    ):
        """Azure AD Integrated does NOT put query timeout in attrs_before (only token)."""
        mock_provider = MagicMock()
        mock_provider.get_token.return_value = "fake-token"
        mock_provider.pack_token_for_pyodbc.return_value = b"\x00\x00\x00\x00"
        mock_provider_cls.return_value = mock_provider

        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(
            version="SQL Server 2019",
            database_name="testdb",
        )
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        with patch("src.db.connection.event"):
            manager = ConnectionManager()
            manager.connect(
                server="myserver.database.windows.net",
                database="testdb",
                authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
                query_timeout=60,
            )

            # Extract the creator callable and invoke it
            creator = mock_create_engine.call_args.kwargs["creator"]
            with patch("src.db.connection.pyodbc") as mock_pyodbc:
                mock_pyodbc.connect.return_value = MagicMock()
                creator()

                # attrs_before should only contain the access token, not query timeout
                call_kwargs = mock_pyodbc.connect.call_args
                attrs_before = call_kwargs.kwargs.get("attrs_before") or call_kwargs[1].get("attrs_before")
                from src.db.azure_auth import SQL_COPT_SS_ACCESS_TOKEN
                assert SQL_COPT_SS_ACCESS_TOKEN in attrs_before
                # SQL_ATTR_QUERY_TIMEOUT should NOT be in attrs_before anymore
                assert 1005 not in attrs_before


class TestTimeoutEventCallbackBehavior:
    """Tests that the event callback correctly sets dbapi_connection.timeout."""

    def test_event_callback_sets_timeout_on_dbapi_connection(self):
        """The connect event callback sets .timeout on the raw pyodbc connection."""
        from src.db.connection import ConnectionManager

        manager = ConnectionManager()
        query_timeout = 45

        # Directly test _create_engine and capture the event listener
        captured_listeners = []

        def capture_listens_for(target, identifier):
            def decorator(fn):
                captured_listeners.append((identifier, fn))
                return fn
            return decorator

        with (
            patch("src.db.connection.create_engine") as mock_create_engine,
            patch("src.db.connection.event") as mock_event,
        ):
            mock_engine_instance = MagicMock()
            mock_create_engine.return_value = mock_engine_instance
            mock_event.listens_for.side_effect = capture_listens_for

            manager._create_engine(
                "DRIVER={ODBC Driver 18 for SQL Server};Server=localhost;Database=testdb",
                AuthenticationMethod.SQL,
                None,
                query_timeout,
            )

        # There should be one captured listener for "connect"
        assert len(captured_listeners) == 1
        identifier, callback = captured_listeners[0]
        assert identifier == "connect"

        # Call the callback with a mock dbapi connection
        mock_dbapi_conn = MagicMock()
        mock_conn_record = MagicMock()
        callback(mock_dbapi_conn, mock_conn_record)

        # Verify it set .timeout on the raw connection
        assert mock_dbapi_conn.timeout == query_timeout
