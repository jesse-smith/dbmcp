"""Unit tests for connection management.

Tests for ConnectionManager and NFR-005 compliance (credentials never logged) - T137.
"""

import logging
import re
from unittest.mock import MagicMock, patch

import pytest

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
            mock_engine.side_effect = Exception("Connection refused")

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

        with patch("src.db.connection.create_engine") as mock_engine:
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
            mock_engine.side_effect = Exception("Test error")

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
            mock_engine.side_effect = Exception("Test error")

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
