"""Connection management for SQL Server databases.

This module provides connection pooling and management using SQLAlchemy.
Credentials are never logged per NFR-005.
"""

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from urllib.parse import quote_plus

import pyodbc
from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from src.db.azure_auth import SQL_COPT_SS_ACCESS_TOKEN, AzureTokenProvider
from src.logging_config import get_logger
from src.models.schema import AuthenticationMethod, Connection

logger = get_logger(__name__)


@dataclass
class PoolConfig:
    """Configuration for connection pool tuning.

    Attributes:
        pool_size: Number of connections to keep open (default: 5)
        max_overflow: Max additional connections beyond pool_size (default: 10)
        pool_timeout: Seconds to wait for connection before timeout (default: 30)
        pool_recycle: Seconds before recycling idle connections (default: 3600)
        pool_pre_ping: Validate connections before use (default: True)
    """

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True


class ConnectionError(Exception):
    """Exception raised when database connection fails."""

    pass


class ConnectionManager:
    """Manages database connections with SQLAlchemy pooling.

    This class handles:
    - Connection establishment and validation
    - Connection pooling via SQLAlchemy QueuePool (configurable via PoolConfig)
    - Connection lifecycle management
    - Secure credential handling (never logged)
    - Performance logging for NFR-001/NFR-002 tracking

    Attributes:
        engines: Dictionary mapping connection_id to SQLAlchemy engine
        connections: Dictionary mapping connection_id to Connection metadata
        pool_config: Connection pool configuration
    """

    def __init__(self, pool_config: PoolConfig | None = None):
        """Initialize connection manager.

        Args:
            pool_config: Optional pool configuration. Uses defaults if not provided.
        """
        self._engines: dict[str, Engine] = {}
        self._connections: dict[str, Connection] = {}
        self._pool_config = pool_config or PoolConfig()

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
        tenant_id: str | None = None,
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
            tenant_id: Azure AD tenant ID (only for azure_ad_integrated auth)

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
        if authentication_method == AuthenticationMethod.AZURE_AD_INTEGRATED:
            user_component = "azure_ad"
        else:
            user_component = username or "windows"
        conn_str_hash = f"{server}:{port}/{database}/{user_component}"
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

        # Create SQLAlchemy engine with connection pooling (T113: configurable)
        start_time = time.time()
        try:
            if authentication_method == AuthenticationMethod.AZURE_AD_INTEGRATED:
                provider = AzureTokenProvider(tenant_id=tenant_id)

                def creator():
                    token = provider.get_token()
                    packed = provider.pack_token_for_pyodbc(token)
                    return pyodbc.connect(odbc_conn_str, attrs_before={SQL_COPT_SS_ACCESS_TOKEN: packed})

                engine = create_engine(
                    "mssql+pyodbc://",
                    creator=creator,
                    poolclass=QueuePool,
                    pool_size=self._pool_config.pool_size,
                    max_overflow=self._pool_config.max_overflow,
                    pool_timeout=self._pool_config.pool_timeout,
                    pool_pre_ping=self._pool_config.pool_pre_ping,
                    pool_recycle=self._pool_config.pool_recycle,
                    echo=False,
                )
            else:
                engine = create_engine(
                    f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_conn_str)}",
                    poolclass=QueuePool,
                    pool_size=self._pool_config.pool_size,
                    max_overflow=self._pool_config.max_overflow,
                    pool_timeout=self._pool_config.pool_timeout,
                    pool_pre_ping=self._pool_config.pool_pre_ping,
                    pool_recycle=self._pool_config.pool_recycle,
                    echo=False,
                )

            # Test connection (T131: timeout already in ODBC string)
            with engine.connect() as conn:
                result = conn.execute(text("SELECT @@VERSION AS version, DB_NAME() AS database_name"))
                row = result.fetchone()
                version = row.version if row else "Unknown"
                elapsed_ms = int((time.time() - start_time) * 1000)
                logger.info(f"Connected to {database} on {server}:{port} in {elapsed_ms}ms")
                logger.debug(f"SQL Server version: {version[:100]}...")  # Truncate for log

                # T105: Performance logging
                if elapsed_ms > 5000:
                    logger.warning(f"Slow connection: {elapsed_ms}ms (>5s threshold)")

        except Exception as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            # Log error without credentials (T105: include timing)
            logger.error(f"Connection to {server}:{port}/{database} failed after {elapsed_ms}ms: {type(e).__name__}")
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
        elif authentication_method == AuthenticationMethod.AZURE_AD_INTEGRATED:
            pass  # No UID/PWD/Authentication — token is passed via attrs_before

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
