"""Unit tests for query timeout configuration.

Tests that SQL_ATTR_QUERY_TIMEOUT is passed to pyodbc for both standard
and Azure AD Integrated auth paths.
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

        with patch("src.db.connection.create_engine") as mock_engine:
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

        with patch("src.db.connection.create_engine") as mock_engine:
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


class TestEngineQueryTimeoutStandardAuth:
    """Tests that SQL_ATTR_QUERY_TIMEOUT is passed via connect_args for standard auth."""

    @patch("src.db.connection.create_engine")
    def test_standard_auth_passes_query_timeout_in_connect_args(self, mock_create_engine):
        """Standard auth passes SQL_ATTR_QUERY_TIMEOUT via connect_args attrs_before."""
        from src.db.connection import SQL_ATTR_QUERY_TIMEOUT

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

        manager = ConnectionManager()
        manager.connect(
            server="localhost",
            database="testdb",
            username="user",
            password="pass",
            query_timeout=45,
        )

        call_kwargs = mock_create_engine.call_args.kwargs
        assert "connect_args" in call_kwargs
        assert "attrs_before" in call_kwargs["connect_args"]
        assert call_kwargs["connect_args"]["attrs_before"][SQL_ATTR_QUERY_TIMEOUT] == 45

    @patch("src.db.connection.create_engine")
    def test_standard_auth_default_timeout_30(self, mock_create_engine):
        """Standard auth uses default query_timeout of 30."""
        from src.db.connection import SQL_ATTR_QUERY_TIMEOUT

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

        manager = ConnectionManager()
        manager.connect(
            server="localhost",
            database="testdb",
            username="user",
            password="pass",
        )

        call_kwargs = mock_create_engine.call_args.kwargs
        assert call_kwargs["connect_args"]["attrs_before"][SQL_ATTR_QUERY_TIMEOUT] == 30


class TestEngineQueryTimeoutAzureAdIntegrated:
    """Tests that SQL_ATTR_QUERY_TIMEOUT is passed via attrs_before for Azure AD Integrated."""

    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_azure_ad_integrated_passes_query_timeout_in_attrs_before(
        self, mock_create_engine, mock_provider_cls
    ):
        """Azure AD Integrated adds SQL_ATTR_QUERY_TIMEOUT to attrs_before alongside token."""
        from src.db.connection import SQL_ATTR_QUERY_TIMEOUT

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

            # Verify attrs_before contains both token and query timeout
            call_kwargs = mock_pyodbc.connect.call_args
            attrs_before = call_kwargs.kwargs.get("attrs_before") or call_kwargs[1].get("attrs_before")
            from src.db.azure_auth import SQL_COPT_SS_ACCESS_TOKEN
            assert SQL_COPT_SS_ACCESS_TOKEN in attrs_before
            assert SQL_ATTR_QUERY_TIMEOUT in attrs_before
            assert attrs_before[SQL_ATTR_QUERY_TIMEOUT] == 60
