"""Connection management for SQL Server databases.

This module provides connection pooling and management using SQLAlchemy.
Credentials are never logged per NFR-005.
"""

from __future__ import annotations

import hashlib
import time
from dataclasses import dataclass
from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.exc import SQLAlchemyError

from src.db.dialects.mssql import MssqlDialect
from src.db.dialects.protocol import DialectStrategy
from src.logging_config import get_logger
from src.models.schema import AuthenticationMethod, Connection

if TYPE_CHECKING:
    from src.config import ConnectionConfig

logger = get_logger(__name__)

CONNECTION_ID_LENGTH = 12
"""Length of connection ID hex prefix.

12 characters provides 2^48 possible IDs (collision probability ~1e-14 for
1000 connections) while keeping IDs compact for logging and display.
"""


@dataclass
class PoolConfig:
    """Configuration for connection pool tuning.

    Attributes:
        pool_size: Number of connections to keep open (default: 5)
        max_overflow: Max additional connections beyond pool_size (default: 10)
        pool_timeout: Seconds to wait for connection before timeout (default: 30)
        pool_recycle: Seconds before recycling idle connections (default: 3600)
        pool_pre_ping: Validate connections before use (default: True)
        query_timeout: Per-statement query timeout in seconds. 0 disables timeout. (default: 30)
    """

    pool_size: int = 5
    max_overflow: int = 10
    pool_timeout: int = 30
    pool_recycle: int = 3600
    pool_pre_ping: bool = True
    query_timeout: int = 30
    azure_ad_pool_recycle: int = 2700
    """Token-aware recycle interval for Azure AD connections.

    Azure AD tokens expire at ~3600s; default 2700s (45 min) recycles
    before expiry.
    """


class ConnectionError(Exception):
    """Exception raised when database connection fails."""

    pass


def _classify_db_error(exc: SQLAlchemyError) -> tuple[str, str]:
    """Classify a database error and return (category, user_guidance).

    Examines SQLSTATE codes and message content to produce actionable
    error categories for user-facing messages.

    Args:
        exc: The SQLAlchemy exception to classify.

    Returns:
        A tuple of (category, guidance) where category is one of:
        'auth_failure', 'connection_lost', 'token_expired', 'unknown'.
    """
    sqlstate = None
    message = str(exc)

    # Extract SQLSTATE from the underlying driver error if available
    if hasattr(exc, "orig") and exc.orig is not None and hasattr(exc.orig, "args"):
        args = exc.orig.args
        if args and isinstance(args[0], str) and len(args[0]) == 5:
            sqlstate = args[0]
        # Combine all args into the message for pattern matching
        message = " ".join(str(a) for a in args)

    # Check SQLSTATE-based categories
    if sqlstate and sqlstate.startswith("28"):
        return (
            "auth_failure",
            "Check your credentials (username/password) and verify the account has access to the database.",
        )

    if sqlstate and sqlstate.startswith("08"):
        return (
            "connection_lost",
            "The database server is unreachable. Check the server address, port, and network connectivity.",
        )

    # Check message-based patterns for Azure AD token issues
    msg_lower = message.lower()
    if "token" in msg_lower and "expired" in msg_lower:
        return (
            "token_expired",
            "The Azure AD token has expired. Run 'az login' to re-authenticate.",
        )

    return (
        "unknown",
        "An unexpected database error occurred. Check the server logs for details.",
    )


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
        self._dialects: dict[str, DialectStrategy] = {}
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
        query_timeout: int = 30,
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
            query_timeout: Per-statement query timeout in seconds. 0 = no timeout,
                5-300 = timeout in seconds. (default: 30)

        Returns:
            Connection object with connection metadata

        Raises:
            ConnectionError: If connection fails
            ValueError: If required credentials are missing
        """
        self._validate_connect_params(
            server, database, username, password,
            authentication_method, connection_timeout, query_timeout,
        )
        connection_id = self._generate_connection_id(
            server, port, database, username, authentication_method,
        )

        # Reuse existing connection if available
        if connection_id in self._engines:
            logger.info(f"Reusing existing connection: {connection_id}")
            return self._connections[connection_id]

        # Create engine via dialect, test connection, and store metadata
        dialect = MssqlDialect()
        start_time = time.time()
        try:
            engine = dialect.create_engine(
                server=server,
                database=database,
                port=port,
                username=username,
                password=password,
                authentication_method=authentication_method,
                trust_server_cert=trust_server_cert,
                connection_timeout=connection_timeout,
                query_timeout=query_timeout,
                pool_config=self._pool_config,
                tenant_id=tenant_id,
                connection_id=connection_id,
                disconnect_callback=self.disconnect,
            )
            self._test_connection(engine, start_time, dialect.name)
        except ConnectionError:
            raise
        except SQLAlchemyError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.error(f"Connection to {server}:{port}/{database} failed after {elapsed_ms}ms: {type(e).__name__}")
            raise ConnectionError(f"Could not connect to {server}:{port}/{database}: {str(e)}") from e

        self._engines[connection_id] = engine
        self._dialects[connection_id] = dialect
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

    def _validate_connect_params(
        self,
        server: str,
        database: str,
        username: str | None,
        password: str | None,
        authentication_method: AuthenticationMethod,
        connection_timeout: int,
        query_timeout: int,
    ) -> None:
        """Validate parameters for connect().

        Args:
            server: SQL Server host
            database: Database name
            username: Username (may be None for Windows/Azure AD Integrated)
            password: Password (may be None for Windows/Azure AD Integrated)
            authentication_method: Authentication method
            connection_timeout: Connection timeout in seconds
            query_timeout: Per-statement query timeout in seconds

        Raises:
            ValueError: If any parameter is invalid
        """
        if not server or not database:
            raise ValueError("Server and database are required")

        if authentication_method in (AuthenticationMethod.SQL, AuthenticationMethod.AZURE_AD):
            if not username or not password:
                raise ValueError(f"Username and password required for {authentication_method.value} authentication")

        if connection_timeout < 5 or connection_timeout > 300:
            raise ValueError("Connection timeout must be between 5 and 300 seconds")

        if query_timeout != 0 and (query_timeout < 5 or query_timeout > 300):
            raise ValueError("Query timeout must be 0 (no timeout) or between 5 and 300 seconds")

    def _generate_connection_id(
        self,
        server: str,
        port: int,
        database: str,
        username: str | None,
        authentication_method: AuthenticationMethod,
    ) -> str:
        """Generate a deterministic connection ID from connection parameters.

        The ID is a truncated SHA-256 hash of the connection key components.
        Password is excluded for security.

        Args:
            server: SQL Server host
            port: Port number
            database: Database name
            username: Username (may be None)
            authentication_method: Authentication method

        Returns:
            12-character hex connection ID
        """
        if authentication_method == AuthenticationMethod.AZURE_AD_INTEGRATED:
            user_component = "azure_ad"
        else:
            user_component = username or "windows"
        conn_str_hash = f"{server}:{port}/{database}/{user_component}"
        return hashlib.sha256(conn_str_hash.encode()).hexdigest()[:CONNECTION_ID_LENGTH]

    def get_dialect(self, connection_id: str) -> DialectStrategy:
        """Get the dialect strategy for a connection.

        Args:
            connection_id: Connection identifier

        Returns:
            DialectStrategy instance for the connection

        Raises:
            ValueError: If connection not found
        """
        if connection_id not in self._dialects:
            raise ValueError(f"Connection '{connection_id}' not found. Use connect_database first.")
        return self._dialects[connection_id]

    def connect_with_url(
        self,
        sqlalchemy_url: str,
        dialect: DialectStrategy,
        query_timeout: int = 30,
    ) -> Connection:
        """Connect using a SQLAlchemy URL with the given dialect.

        Args:
            sqlalchemy_url: Full SQLAlchemy connection URL.
            dialect: Instantiated dialect strategy.
            query_timeout: Per-statement timeout (default: 30).

        Returns:
            Connection metadata object.

        Raises:
            ConnectionError: If connection fails.
        """
        parsed_url = make_url(sqlalchemy_url)
        connection_id = self._generate_url_connection_id(sqlalchemy_url)

        if connection_id in self._engines:
            logger.info(f"Reusing existing connection: {connection_id}")
            return self._connections[connection_id]

        start_time = time.time()
        try:
            engine = dialect.create_engine(
                sqlalchemy_url=sqlalchemy_url,
                query_timeout=query_timeout,
            )
            self._test_connection(engine, start_time, dialect.name)
        except ConnectionError:
            raise
        except SQLAlchemyError as e:
            elapsed_ms = int((time.time() - start_time) * 1000)
            safe_url = parsed_url.render_as_string(hide_password=True)
            logger.error(f"Connection to {safe_url} failed after {elapsed_ms}ms: {type(e).__name__}")
            raise ConnectionError(f"Could not connect to {safe_url}: {str(e)}") from e

        self._engines[connection_id] = engine
        self._dialects[connection_id] = dialect
        connection = Connection(
            connection_id=connection_id,
            server=parsed_url.host or "",
            database=parsed_url.database or "",
            port=parsed_url.port or 0,
            dialect_name=dialect.name,
            username=parsed_url.username,
            created_at=datetime.now(),
        )
        self._connections[connection_id] = connection
        return connection

    def connect_with_config(
        self,
        config: ConnectionConfig,
        dialect: DialectStrategy,
        query_timeout: int = 30,
    ) -> Connection:
        """Connect using a typed config with the given dialect.

        Routes MssqlConnectionConfig to the existing connect() method.
        Routes GenericConnectionConfig to connect_with_url().
        Routes DatabricksConnectionConfig to connect_with_url() (Phase 11).

        Args:
            config: Typed connection configuration.
            dialect: Instantiated dialect strategy.
            query_timeout: Per-statement timeout.

        Returns:
            Connection metadata object.
        """
        from src.config import GenericConnectionConfig, MssqlConnectionConfig, resolve_env_vars

        if isinstance(config, MssqlConnectionConfig):
            password = resolve_env_vars(config.password) if config.password else None
            tenant_id = resolve_env_vars(config.tenant_id) if config.tenant_id else None
            return self.connect(
                server=config.server,
                database=config.database,
                port=config.port,
                username=config.username,
                password=password,
                authentication_method=AuthenticationMethod(config.authentication_method),
                trust_server_cert=config.trust_server_cert,
                connection_timeout=config.connection_timeout,
                tenant_id=tenant_id,
                query_timeout=query_timeout,
            )
        elif isinstance(config, GenericConnectionConfig):
            url = resolve_env_vars(config.sqlalchemy_url) if config.sqlalchemy_url else ""
            return self.connect_with_url(url, dialect, query_timeout)
        else:
            # DatabricksConnectionConfig -- Phase 11
            raise NotImplementedError(f"Config type {type(config).__name__} not yet supported")

    def _generate_url_connection_id(self, sqlalchemy_url: str) -> str:
        """Generate a deterministic connection ID from a SQLAlchemy URL.

        Credentials are excluded by hashing only host+database+driver.
        """
        parsed = make_url(sqlalchemy_url)
        safe_key = f"{parsed.get_backend_name()}://{parsed.host or ''}:{parsed.port or 0}/{parsed.database or ''}"
        return hashlib.sha256(safe_key.encode()).hexdigest()[:CONNECTION_ID_LENGTH]

    def _test_connection(
        self,
        engine: Engine,
        start_time: float,
        dialect_name: str,
    ) -> None:
        """Test a newly created engine by executing a probe query.

        Args:
            engine: SQLAlchemy engine to test
            start_time: Timestamp when connection attempt began (for timing)
            dialect_name: Dialect identifier string (for logging)
        """
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
            elapsed_ms = int((time.time() - start_time) * 1000)
            logger.info(f"Connected via {dialect_name} dialect in {elapsed_ms}ms")

            if elapsed_ms > 5000:
                logger.warning(f"Slow connection: {elapsed_ms}ms (>5s threshold)")

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
        self._dialects.pop(connection_id, None)
        engine.dispose()
        logger.info(f"Disconnected: {connection_id}")
        return True

    def disconnect_all(self) -> int:
        """Close all database connections (best-effort).

        Iterates over all engines and disposes each one. Per-engine errors
        are caught and logged at DEBUG level so that a single failed dispose
        does not prevent cleanup of remaining connections.

        Returns:
            Number of connections that were tracked (regardless of dispose success)
        """
        count = len(self._engines)
        for conn_id, engine in list(self._engines.items()):
            try:
                engine.dispose()
            except (SQLAlchemyError, OSError) as exc:
                logger.debug(
                    f"Error disposing engine {conn_id} during shutdown: {exc}",
                    exc_info=True,
                )
        self._engines.clear()
        self._connections.clear()
        self._dialects.clear()
        logger.debug(f"Shutdown cleanup: disposed {count} connection(s)")
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
