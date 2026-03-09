"""Unit tests for connection management.

Tests for ConnectionManager and NFR-005 compliance (credentials never logged) - T137.
"""

import logging
import re
from unittest.mock import MagicMock, patch

import pytest
from sqlalchemy.exc import SQLAlchemyError

from src.db.connection import ConnectionError, ConnectionManager
from src.models.schema import AuthenticationMethod


class TestConnectionValidation:
    """Tests for connection parameter validation."""

    def test_connect_requires_server(self):
        """Server parameter is required."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Server and database are required"):
            manager.connect(server="", database="testdb")

    def test_connect_requires_database(self):
        """Database parameter is required."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Server and database are required"):
            manager.connect(server="localhost", database="")

    def test_connect_requires_credentials_for_sql_auth(self):
        """Username and password required for SQL authentication."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Username and password required"):
            manager.connect(
                server="localhost",
                database="testdb",
                authentication_method=AuthenticationMethod.SQL,
            )

    def test_connect_requires_credentials_for_azure_ad(self):
        """Username and password required for Azure AD authentication."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Username and password required"):
            manager.connect(
                server="localhost",
                database="testdb",
                authentication_method=AuthenticationMethod.AZURE_AD,
            )

    def test_connection_timeout_min_boundary(self):
        """Connection timeout cannot be less than 5 seconds."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Connection timeout must be between"):
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                connection_timeout=4,
            )

    def test_connection_timeout_max_boundary(self):
        """Connection timeout cannot exceed 300 seconds."""
        manager = ConnectionManager()
        with pytest.raises(ValueError, match="Connection timeout must be between"):
            manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="pass",
                connection_timeout=301,
            )


class TestNFR005CredentialSafety:
    """Tests for NFR-005 compliance - credentials never logged.

    NFR-005: No credentials are ever logged to console, file, or external services.
    This test suite verifies that password values never appear in log output.
    """

    @pytest.fixture
    def log_capture(self):
        """Capture log output for analysis."""
        # Create string handler to capture logs
        log_output = []

        class ListHandler(logging.Handler):
            def emit(self, record):
                log_output.append(self.format(record))

        handler = ListHandler()
        handler.setLevel(logging.DEBUG)
        handler.setFormatter(logging.Formatter('%(message)s'))

        # Attach to connection module logger
        conn_logger = logging.getLogger("src.db.connection")
        conn_logger.addHandler(handler)
        original_level = conn_logger.level
        conn_logger.setLevel(logging.DEBUG)

        yield log_output

        # Cleanup
        conn_logger.removeHandler(handler)
        conn_logger.setLevel(original_level)

    def test_password_not_in_connect_logs(self, log_capture):
        """T137: Verify password is not logged during connection attempt."""
        manager = ConnectionManager()
        secret_password = "SuperSecretP@ssw0rd!123"

        with patch("src.db.connection.create_engine") as mock_engine:
            # Simulate connection failure to trigger error logging
            mock_engine.side_effect = SQLAlchemyError("Connection refused")

            with pytest.raises(ConnectionError):
                manager.connect(
                    server="localhost",
                    database="testdb",
                    username="testuser",
                    password=secret_password,
                )

        # Scan all log output for password
        all_logs = " ".join(log_capture)
        assert secret_password not in all_logs, "Password found in log output!"

    def test_password_not_in_successful_connect_logs(self, log_capture):
        """T137: Verify password is not logged during successful connection."""
        manager = ConnectionManager()
        secret_password = "AnotherSecret!456"

        with (
            patch("src.db.connection.create_engine") as mock_engine,
            patch("src.db.connection.event"),
        ):
            # Setup mock for successful connection
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

            manager.connect(
                server="localhost",
                database="testdb",
                username="testuser",
                password=secret_password,
            )

        # Scan all log output for password
        all_logs = " ".join(log_capture)
        assert secret_password not in all_logs, "Password found in successful connection logs!"

    def test_odbc_connection_string_not_fully_logged(self, log_capture):
        """T137: Verify full ODBC connection string (with password) not logged."""
        manager = ConnectionManager()
        secret_password = "ODbc_Passw0rd#789"

        with patch("src.db.connection.create_engine") as mock_engine:
            mock_engine.side_effect = SQLAlchemyError("Test error")

            with pytest.raises(ConnectionError):
                manager.connect(
                    server="testserver",
                    database="testdb",
                    username="testuser",
                    password=secret_password,
                )

        # Check logs don't contain PWD= pattern with actual password
        all_logs = " ".join(log_capture)
        assert f"PWD={secret_password}" not in all_logs
        assert f"Password={secret_password}" not in all_logs

    def test_credential_patterns_absent_from_logs(self, log_capture):
        """T137: Verify common credential patterns not in logs."""
        manager = ConnectionManager()
        secret_password = "Pattern_Test_Pass!000"

        with patch("src.db.connection.create_engine") as mock_engine:
            mock_engine.side_effect = SQLAlchemyError("Test error")

            with pytest.raises(ConnectionError):
                manager.connect(
                    server="testserver",
                    database="testdb",
                    username="testuser",
                    password=secret_password,
                )

        all_logs = " ".join(log_capture)

        # Check for common credential patterns
        credential_patterns = [
            secret_password,  # Raw password
            re.escape(f"PWD={secret_password}"),
            re.escape(f"password={secret_password}"),
            re.escape(f"Password={secret_password}"),
        ]

        for pattern in credential_patterns:
            assert not re.search(pattern, all_logs, re.IGNORECASE), \
                f"Credential pattern '{pattern}' found in logs!"


class TestConnectionIdGeneration:
    """Tests for connection ID generation."""

    def test_connection_id_excludes_password(self):
        """Connection ID hash should not include password."""
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

            # Connect with two different passwords
            conn1 = manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="password1",
            )

            # Reset engines to force new connection
            manager._engines.clear()
            manager._connections.clear()

            conn2 = manager.connect(
                server="localhost",
                database="testdb",
                username="user",
                password="password2",
            )

            # Same server/db/user should produce same connection_id
            # (password excluded from hash)
            assert conn1.connection_id == conn2.connection_id

    def test_connection_id_includes_server(self):
        """Connection ID should differ for different servers."""
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

            conn1 = manager.connect(
                server="server1",
                database="testdb",
                username="user",
                password="pass",
            )

            conn2 = manager.connect(
                server="server2",
                database="testdb",
                username="user",
                password="pass",
            )

            # Different servers should produce different connection_ids
            assert conn1.connection_id != conn2.connection_id


class TestODBCConnectionString:
    """Tests for ODBC connection string building."""

    def test_sql_auth_includes_uid_and_pwd(self):
        """SQL authentication should include UID and PWD in connection string."""
        manager = ConnectionManager()

        conn_str = manager._build_odbc_connection_string(
            server="localhost",
            database="testdb",
            username="testuser",
            password="testpass",
            port=1433,
            authentication_method=AuthenticationMethod.SQL,
            trust_server_cert=False,
            connection_timeout=30,
        )

        assert "UID=testuser" in conn_str
        assert "PWD=testpass" in conn_str
        assert "Trusted_Connection" not in conn_str

    def test_windows_auth_uses_trusted_connection(self):
        """Windows authentication should use Trusted_Connection."""
        manager = ConnectionManager()

        conn_str = manager._build_odbc_connection_string(
            server="localhost",
            database="testdb",
            username=None,
            password=None,
            port=1433,
            authentication_method=AuthenticationMethod.WINDOWS,
            trust_server_cert=False,
            connection_timeout=30,
        )

        assert "Trusted_Connection=yes" in conn_str
        assert "UID=" not in conn_str
        assert "PWD=" not in conn_str

    def test_azure_ad_auth_includes_authentication_param(self):
        """Azure AD authentication should include Authentication parameter."""
        manager = ConnectionManager()

        conn_str = manager._build_odbc_connection_string(
            server="myserver.database.windows.net",
            database="testdb",
            username="user@domain.com",
            password="azurepass",
            port=1433,
            authentication_method=AuthenticationMethod.AZURE_AD,
            trust_server_cert=False,
            connection_timeout=30,
        )

        assert "UID=user@domain.com" in conn_str
        assert "PWD=azurepass" in conn_str
        assert "Authentication=ActiveDirectoryPassword" in conn_str

    def test_azure_ad_integrated_excludes_uid_pwd_authentication(self):
        """T009: azure_ad_integrated ODBC string must NOT contain UID, PWD, or Authentication."""
        manager = ConnectionManager()

        conn_str = manager._build_odbc_connection_string(
            server="myserver.database.windows.net",
            database="testdb",
            username=None,
            password=None,
            port=1433,
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
            trust_server_cert=False,
            connection_timeout=30,
        )

        assert "UID=" not in conn_str
        assert "PWD=" not in conn_str
        assert "Authentication=" not in conn_str
        assert "Driver={ODBC Driver 18 for SQL Server}" in conn_str
        assert "Server=myserver.database.windows.net,1433" in conn_str
        assert "Database=testdb" in conn_str
        assert "TrustServerCertificate=" in conn_str
        assert "Connection Timeout=30" in conn_str


class TestAzureAdIntegratedValidation:
    """T008: Tests for azure_ad_integrated auth validation."""

    def test_azure_ad_integrated_does_not_require_username_password(self):
        """azure_ad_integrated auth method does NOT require username/password."""
        manager = ConnectionManager()

        # Should NOT raise ValueError about missing credentials
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

            with patch("src.db.connection.AzureTokenProvider") as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider.get_token.return_value = "fake-token"
                mock_provider.pack_token_for_pyodbc.return_value = b"\x00\x00\x00\x00"
                mock_provider_cls.return_value = mock_provider

                conn = manager.connect(
                    server="myserver.database.windows.net",
                    database="testdb",
                    authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
                )
                assert conn.connection_id is not None

    def test_azure_ad_integrated_ignores_provided_username_password(self):
        """Providing username/password with azure_ad_integrated is silently ignored (no error)."""
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

            with patch("src.db.connection.AzureTokenProvider") as mock_provider_cls:
                mock_provider = MagicMock()
                mock_provider.get_token.return_value = "fake-token"
                mock_provider.pack_token_for_pyodbc.return_value = b"\x00\x00\x00\x00"
                mock_provider_cls.return_value = mock_provider

                # Should not raise even with username/password provided
                conn = manager.connect(
                    server="myserver.database.windows.net",
                    database="testdb",
                    username="ignored@domain.com",
                    password="ignored-password",
                    authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
                )
                assert conn.connection_id is not None


class TestAzureAdIntegratedCreatorPattern:
    """T010: Tests for creator function pattern with azure_ad_integrated."""

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_uses_creator_instead_of_url(self, mock_create_engine, mock_provider_cls, mock_event):
        """azure_ad_integrated uses create_engine(creator=...) instead of URL-based connection."""
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
        )

        # Verify create_engine was called with creator= keyword, not a URL containing odbc_connect
        call_args = mock_create_engine.call_args
        assert "creator" in call_args.kwargs or (len(call_args.args) == 0 and "creator" in call_args.kwargs)
        # Should NOT have a URL as first positional arg
        if call_args.args:
            assert "odbc_connect" not in call_args.args[0]


class TestAzureAdIntegratedConnectionIdHash:
    """T011: Tests for connection ID hash with azure_ad_integrated."""

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_connection_id_uses_azure_ad_marker(self, mock_create_engine, mock_provider_cls, mock_event):
        """Connection ID hash uses 'azure_ad' (not username) for azure_ad_integrated."""
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

        # Connect with azure_ad_integrated (no username)
        conn = manager.connect(
            server="myserver.database.windows.net",
            database="testdb",
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
        )

        # The connection hash should be based on 'azure_ad', not 'windows' (the fallback when username is None)
        import hashlib
        expected_hash_input = "myserver.database.windows.net:1433/testdb/azure_ad"
        expected_id = hashlib.sha256(expected_hash_input.encode()).hexdigest()[:12]
        assert conn.connection_id == expected_id

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_azure_ad_integrated_id_differs_from_windows(self, mock_create_engine, mock_provider_cls, mock_event):
        """azure_ad_integrated connection ID differs from windows auth (same server/db, no username)."""
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

        # Azure AD integrated
        conn_azure = manager.connect(
            server="myserver.database.windows.net",
            database="testdb",
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
        )

        # Clear to allow re-connect
        manager._engines.clear()
        manager._connections.clear()

        # Windows auth (same server/db, also no username)
        conn_windows = manager.connect(
            server="myserver.database.windows.net",
            database="testdb",
            authentication_method=AuthenticationMethod.WINDOWS,
        )

        # They should have different IDs because the hash input differs
        assert conn_azure.connection_id != conn_windows.connection_id


class TestAzureAdIntegratedTokenRefresh:
    """T019-T020: Tests for token refresh behavior with azure_ad_integrated."""

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_creator_calls_get_token_on_every_invocation(self, mock_create_engine, mock_provider_cls, mock_event):
        """T019: The creator callable calls get_token() on every invocation (not cached)."""
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
        )

        # Extract the creator callable from create_engine call
        creator = mock_create_engine.call_args.kwargs["creator"]

        # Reset the mock to track new calls
        mock_provider.get_token.reset_mock()

        # Call creator multiple times (simulating pool creating new connections)
        with patch("src.db.connection.pyodbc") as mock_pyodbc:
            mock_pyodbc.connect.return_value = MagicMock()
            creator()
            creator()
            creator()

        # get_token should be called once per creator invocation
        assert mock_provider.get_token.call_count == 3

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_pool_pre_ping_and_recycle_set_for_azure_ad_integrated(self, mock_create_engine, mock_provider_cls, mock_event):
        """T020: pool_pre_ping=True and pool_recycle=2700 set on azure_ad_integrated engine."""
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
        )

        call_kwargs = mock_create_engine.call_args.kwargs
        assert call_kwargs["pool_pre_ping"] is True
        assert call_kwargs["pool_recycle"] == 2700


class TestAuthAwarePoolRecycle:
    """Tests for auth-aware pool_recycle behavior."""

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_azure_ad_integrated_sets_pool_recycle_2700(self, mock_create_engine, mock_provider_cls, mock_event):
        """Azure AD Integrated auth sets pool_recycle=2700 on engine (default)."""
        mock_provider = MagicMock()
        mock_provider.get_token.return_value = "fake-token"
        mock_provider.pack_token_for_pyodbc.return_value = b"\x00\x00\x00\x00"
        mock_provider_cls.return_value = mock_provider

        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019", database_name="testdb")
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        manager = ConnectionManager()
        manager.connect(
            server="myserver.database.windows.net",
            database="testdb",
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
        )

        assert mock_create_engine.call_args.kwargs["pool_recycle"] == 2700

    @patch("src.db.connection.event")
    @patch("src.db.connection.create_engine")
    def test_azure_ad_password_sets_pool_recycle_2700(self, mock_create_engine, mock_event):
        """Azure AD (password) auth sets pool_recycle=2700 on engine (default)."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019", database_name="testdb")
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        manager = ConnectionManager()
        manager.connect(
            server="myserver.database.windows.net",
            database="testdb",
            username="user@domain.com",
            password="password",
            authentication_method=AuthenticationMethod.AZURE_AD,
        )

        assert mock_create_engine.call_args.kwargs["pool_recycle"] == 2700

    @patch("src.db.connection.event")
    @patch("src.db.connection.create_engine")
    def test_sql_auth_keeps_pool_recycle_3600(self, mock_create_engine, mock_event):
        """SQL auth keeps pool_recycle=3600 on engine."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019", database_name="testdb")
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
            authentication_method=AuthenticationMethod.SQL,
        )

        assert mock_create_engine.call_args.kwargs["pool_recycle"] == 3600

    @patch("src.db.connection.event")
    @patch("src.db.connection.create_engine")
    def test_windows_auth_keeps_pool_recycle_3600(self, mock_create_engine, mock_event):
        """Windows auth keeps pool_recycle=3600 on engine."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019", database_name="testdb")
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        manager = ConnectionManager()
        manager.connect(
            server="localhost",
            database="testdb",
            authentication_method=AuthenticationMethod.WINDOWS,
        )

        assert mock_create_engine.call_args.kwargs["pool_recycle"] == 3600

    @patch("src.db.connection.event")
    @patch("src.db.connection.AzureTokenProvider")
    @patch("src.db.connection.create_engine")
    def test_custom_azure_ad_pool_recycle_respected(self, mock_create_engine, mock_provider_cls, mock_event):
        """Custom azure_ad_pool_recycle=1800 in PoolConfig is respected for Azure AD."""
        mock_provider = MagicMock()
        mock_provider.get_token.return_value = "fake-token"
        mock_provider.pack_token_for_pyodbc.return_value = b"\x00\x00\x00\x00"
        mock_provider_cls.return_value = mock_provider

        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019", database_name="testdb")
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        from src.db.connection import PoolConfig
        manager = ConnectionManager(pool_config=PoolConfig(azure_ad_pool_recycle=1800))
        manager.connect(
            server="myserver.database.windows.net",
            database="testdb",
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
        )

        assert mock_create_engine.call_args.kwargs["pool_recycle"] == 1800

    @patch("src.db.connection.event")
    @patch("src.db.connection.create_engine")
    def test_custom_pool_recycle_used_for_non_azure(self, mock_create_engine, mock_event):
        """Custom pool_recycle=1800 in PoolConfig is still used for non-Azure auth."""
        mock_connection = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchone.return_value = MagicMock(version="SQL Server 2019", database_name="testdb")
        mock_connection.execute.return_value = mock_result
        mock_engine_instance = MagicMock()
        mock_engine_instance.connect.return_value.__enter__.return_value = mock_connection
        mock_create_engine.return_value = mock_engine_instance

        from src.db.connection import PoolConfig
        manager = ConnectionManager(pool_config=PoolConfig(pool_recycle=1800))
        manager.connect(
            server="localhost",
            database="testdb",
            username="user",
            password="pass",
            authentication_method=AuthenticationMethod.SQL,
        )

        assert mock_create_engine.call_args.kwargs["pool_recycle"] == 1800

    def test_pool_config_azure_ad_pool_recycle_default(self):
        """PoolConfig.azure_ad_pool_recycle defaults to 2700."""
        from src.db.connection import PoolConfig
        config = PoolConfig()
        assert config.azure_ad_pool_recycle == 2700


class TestAzureAdIntegratedErrorPropagation:
    """T026: Tests for error propagation from AzureTokenProvider through connect()."""

    @patch("src.db.connection.AzureTokenProvider")
    def test_connect_propagates_token_provider_error_as_connection_error(self, mock_provider_cls):
        """connect() wraps token provider errors in ConnectionError with actionable message."""
        mock_provider = MagicMock()
        mock_provider.get_token.side_effect = ConnectionError(
            "Azure AD authentication failed: No credential sources available. "
            "Run 'az login' or set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, and AZURE_TENANT_ID environment variables."
        )
        mock_provider_cls.return_value = mock_provider

        manager = ConnectionManager()

        with pytest.raises(ConnectionError) as exc_info:
            manager.connect(
                server="myserver.database.windows.net",
                database="testdb",
                authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
            )

        error_msg = str(exc_info.value)
        assert "az login" in error_msg or "Azure AD" in error_msg
