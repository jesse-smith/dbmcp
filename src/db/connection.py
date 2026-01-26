"""Connection management for SQL Server databases.

This module provides connection pooling and management using SQLAlchemy.
Credentials are never logged per NFR-005.
"""

import hashlib
from datetime import datetime
from urllib.parse import quote_plus

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from src.logging_config import get_logger
from src.models.schema import AuthenticationMethod, Connection

logger = get_logger(__name__)


class ConnectionError(Exception):
    """Exception raised when database connection fails."""

    pass


class ConnectionManager:
    """Manages database connections with SQLAlchemy pooling.

    This class handles:
    - Connection establishment and validation
    - Connection pooling via SQLAlchemy QueuePool
    - Connection lifecycle management
    - Secure credential handling (never logged)

    Attributes:
        engines: Dictionary mapping connection_id to SQLAlchemy engine
        connections: Dictionary mapping connection_id to Connection metadata
    """

    def __init__(self):
        self._engines: dict[str, Engine] = {}
        self._connections: dict[str, Connection] = {}

    def connect(
        self,
        server: str,
        database: str,
        username: str | None = None,
        password: str | None = None,
        port: int = 1433,
        authentication_method: AuthenticationMethod = AuthenticationMethod.SQL,
        trust_server_cert: bool = False,
        connection_timeout: int = 30,
    ) -> Connection:
        """Create a database connection and return Connection object.

        Args:
            server: SQL Server host (hostname or IP)
            database: Database name
            username: Username (required for SQL/Azure AD auth)
            password: Password (required for SQL/Azure AD auth)
            port: SQL Server port (default: 1433)
            authentication_method: Authentication method
            trust_server_cert: Trust server certificate without validation
            connection_timeout: Connection timeout in seconds (5-300)

        Returns:
            Connection object with connection metadata

        Raises:
            ConnectionError: If connection fails
            ValueError: If required credentials are missing
        """
        # Validate inputs
        if not server or not database:
            raise ValueError("Server and database are required")

        if authentication_method in (AuthenticationMethod.SQL, AuthenticationMethod.AZURE_AD):
            if not username or not password:
                raise ValueError(f"Username and password required for {authentication_method.value} authentication")

        if connection_timeout < 5 or connection_timeout > 300:
            raise ValueError("Connection timeout must be between 5 and 300 seconds")

        # Generate connection ID (excludes password for security)
        conn_str_hash = f"{server}:{port}/{database}/{username or 'windows'}"
        connection_id = hashlib.sha256(conn_str_hash.encode()).hexdigest()[:12]

        # Check if already connected
        if connection_id in self._engines:
            logger.info(f"Reusing existing connection: {connection_id}")
            return self._connections[connection_id]

        # Build ODBC connection string
        odbc_conn_str = self._build_odbc_connection_string(
            server=server,
            database=database,
            username=username,
            password=password,
            port=port,
            authentication_method=authentication_method,
            trust_server_cert=trust_server_cert,
            connection_timeout=connection_timeout,
        )

        # Create SQLAlchemy engine with connection pooling
        try:
            engine = create_engine(
                f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_conn_str)}",
                poolclass=QueuePool,
                pool_size=5,
                max_overflow=10,
                pool_pre_ping=True,  # Validate connections before use
                pool_recycle=3600,  # Recycle connections after 1 hour
                echo=False,
            )

            # Test connection
            with engine.connect() as conn:
                result = conn.execute(text("SELECT @@VERSION AS version, DB_NAME() AS database_name"))
                row = result.fetchone()
                version = row.version if row else "Unknown"
                logger.info(f"Connected to {database} on {server}:{port}")
                logger.debug(f"SQL Server version: {version[:100]}...")  # Truncate for log

        except Exception as e:
            # Log error without credentials
            logger.error(f"Connection to {server}:{port}/{database} failed: {type(e).__name__}")
            raise ConnectionError(f"Could not connect to {server}:{port}/{database}: {str(e)}") from e

        # Store engine and connection metadata
        self._engines[connection_id] = engine
        connection = Connection(
            connection_id=connection_id,
            server=server,
            database=database,
            port=port,
            authentication_method=authentication_method,
            username=username,
            created_at=datetime.now(),
        )
        self._connections[connection_id] = connection

        return connection

    def _build_odbc_connection_string(
        self,
        server: str,
        database: str,
        username: str | None,
        password: str | None,
        port: int,
        authentication_method: AuthenticationMethod,
        trust_server_cert: bool,
        connection_timeout: int,
    ) -> str:
        """Build ODBC connection string for SQL Server.

        Args:
            server: SQL Server host
            database: Database name
            username: Username (optional for Windows auth)
            password: Password (optional for Windows auth)
            port: Port number
            authentication_method: Auth method
            trust_server_cert: Trust server certificate
            connection_timeout: Timeout in seconds

        Returns:
            ODBC connection string
        """
        parts = [
            "Driver={ODBC Driver 18 for SQL Server}",
            f"Server={server},{port}",
            f"Database={database}",
            f"TrustServerCertificate={'yes' if trust_server_cert else 'no'}",
            f"Connection Timeout={connection_timeout}",
        ]

        if authentication_method == AuthenticationMethod.SQL:
            parts.extend([f"UID={username}", f"PWD={password}"])
        elif authentication_method == AuthenticationMethod.WINDOWS:
            parts.append("Trusted_Connection=yes")
        elif authentication_method == AuthenticationMethod.AZURE_AD:
            parts.extend([
                f"UID={username}",
                f"PWD={password}",
                "Authentication=ActiveDirectoryPassword",
            ])

        return ";".join(parts)

    def get_engine(self, connection_id: str) -> Engine:
        """Get SQLAlchemy engine for a connection ID.

        Args:
            connection_id: Connection identifier

        Returns:
            SQLAlchemy engine

        Raises:
            ValueError: If connection not found
        """
        if connection_id not in self._engines:
            raise ValueError(f"Connection '{connection_id}' not found. Use connect_database first.")
        return self._engines[connection_id]

    def get_connection(self, connection_id: str) -> Connection:
        """Get Connection metadata for a connection ID.

        Args:
            connection_id: Connection identifier

        Returns:
            Connection metadata object

        Raises:
            ValueError: If connection not found
        """
        if connection_id not in self._connections:
            raise ValueError(f"Connection '{connection_id}' not found. Use connect_database first.")
        return self._connections[connection_id]

    def disconnect(self, connection_id: str) -> bool:
        """Close a database connection.

        Args:
            connection_id: Connection identifier

        Returns:
            True if disconnected, False if not found
        """
        if connection_id not in self._engines:
            return False

        engine = self._engines.pop(connection_id)
        self._connections.pop(connection_id, None)
        engine.dispose()
        logger.info(f"Disconnected: {connection_id}")
        return True

    def disconnect_all(self) -> int:
        """Close all database connections.

        Returns:
            Number of connections closed
        """
        count = len(self._engines)
        for engine in self._engines.values():
            engine.dispose()
        self._engines.clear()
        self._connections.clear()
        logger.info(f"Disconnected {count} connections")
        return count

    def list_connections(self) -> list[Connection]:
        """List all active connections.

        Returns:
            List of Connection objects
        """
        return list(self._connections.values())

    def is_connected(self, connection_id: str) -> bool:
        """Check if a connection is active.

        Args:
            connection_id: Connection identifier

        Returns:
            True if connected
        """
        return connection_id in self._engines
