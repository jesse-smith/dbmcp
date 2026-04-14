"""SQL Server dialect implementation.

Encapsulates MSSQL-specific behavior: ODBC connection strings,
Azure AD authentication, DMV-based fast metadata, bracket quoting.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from urllib.parse import quote_plus

import pyodbc
from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.pool import QueuePool

from src.db.dialects.azure_auth import SQL_COPT_SS_ACCESS_TOKEN, AzureTokenProvider
from src.logging_config import get_logger
from src.models.schema import AuthenticationMethod

logger = get_logger(__name__)


class MssqlDialect:
    """SQL Server dialect implementation.

    Encapsulates MSSQL-specific behavior: ODBC connection strings,
    Azure AD authentication, DMV-based fast metadata, bracket quoting.
    """

    @property
    def name(self) -> str:
        """Dialect identifier string."""
        return "mssql"

    @property
    def sqlglot_dialect(self) -> str:
        """Sqlglot dialect name for query parsing."""
        return "tsql"

    @property
    def supports_indexes(self) -> bool:
        """Whether this dialect supports traditional index metadata."""
        return True

    @property
    def has_fast_row_counts(self) -> bool:
        """Whether this dialect has DMV-based fast row counts."""
        return True

    @property
    def safe_procedures(self) -> frozenset[str]:
        """21 known-safe SQL Server system stored procedures."""
        return frozenset({
            # Catalog/ODBC (12)
            "sp_column_privileges",
            "sp_columns",
            "sp_databases",
            "sp_fkeys",
            "sp_pkeys",
            "sp_server_info",
            "sp_special_columns",
            "sp_sproc_columns",
            "sp_statistics",
            "sp_stored_procedures",
            "sp_table_privileges",
            "sp_tables",
            # Object/Metadata (4)
            "sp_help",
            "sp_helptext",
            "sp_helpindex",
            "sp_helpconstraint",
            # Session/Server (3)
            "sp_who",
            "sp_who2",
            "sp_spaceused",
            # Result Set Metadata (2)
            "sp_describe_first_result_set",
            "sp_describe_undeclared_parameters",
        })

    def quote_identifier(self, identifier: str) -> str:
        """Quote using SQL Server square brackets."""
        return f"[{identifier.replace(']', ']]')}]"

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine with MSSQL-specific ODBC configuration.

        Args:
            **kwargs: Connection parameters:
                server (str): SQL Server host.
                database (str): Database name.
                port (int): Server port (default 1433).
                username (str | None): Username for SQL/Azure AD auth.
                password (str | None): Password for SQL/Azure AD auth.
                authentication_method (AuthenticationMethod): Auth method.
                trust_server_cert (bool): Trust server certificate.
                connection_timeout (int): Connection timeout seconds.
                query_timeout (int): Per-statement timeout seconds.
                pool_config: PoolConfig dataclass with pool settings.
                tenant_id (str | None): Azure AD tenant ID.
                connection_id (str | None): Connection ID for disconnect callback.
                disconnect_callback (Callable[[str], None] | None): Called on token failure.

        Returns:
            Configured SQLAlchemy Engine.
        """
        server: str = kwargs["server"]
        database: str = kwargs["database"]
        port: int = kwargs.get("port", 1433)
        username: str | None = kwargs.get("username")
        password: str | None = kwargs.get("password")
        authentication_method: AuthenticationMethod = kwargs["authentication_method"]
        trust_server_cert: bool = kwargs.get("trust_server_cert", False)
        connection_timeout: int = kwargs.get("connection_timeout", 30)
        query_timeout: int = kwargs.get("query_timeout", 30)
        pool_config = kwargs.get("pool_config")
        tenant_id: str | None = kwargs.get("tenant_id")
        connection_id: str | None = kwargs.get("connection_id")
        disconnect_callback: Callable[[str], None] | None = kwargs.get("disconnect_callback")

        # Import PoolConfig here to avoid circular imports at module level
        from src.db.connection import PoolConfig

        if pool_config is None:
            pool_config = PoolConfig()

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

        pool_kwargs = {
            "poolclass": QueuePool,
            "pool_size": pool_config.pool_size,
            "max_overflow": pool_config.max_overflow,
            "pool_timeout": pool_config.pool_timeout,
            "pool_pre_ping": pool_config.pool_pre_ping,
            "pool_recycle": pool_config.pool_recycle,
            "echo": False,
        }

        # Auth-aware pool_recycle: Azure AD connections use a shorter recycle
        # interval to discard connections before token expiry (~3600s).
        if authentication_method in (
            AuthenticationMethod.AZURE_AD,
            AuthenticationMethod.AZURE_AD_INTEGRATED,
        ):
            pool_kwargs["pool_recycle"] = pool_config.azure_ad_pool_recycle
            logger.debug(
                f"Azure AD auth: pool_recycle set to {pool_kwargs['pool_recycle']}s (token-aware)"
            )

        if authentication_method == AuthenticationMethod.AZURE_AD_INTEGRATED:
            provider = AzureTokenProvider(tenant_id=tenant_id)

            def creator():
                try:
                    token = provider.get_token()
                except builtins.ConnectionError:
                    logger.debug("Azure AD token re-acquisition failed, cleaning up connection")
                    if disconnect_callback and connection_id:
                        disconnect_callback(connection_id)
                    raise
                packed = provider.pack_token_for_pyodbc(token)
                return pyodbc.connect(
                    odbc_conn_str,
                    attrs_before={SQL_COPT_SS_ACCESS_TOKEN: packed},
                )

            engine = sa_create_engine("mssql+pyodbc://", creator=creator, **pool_kwargs)
        else:
            engine = sa_create_engine(
                f"mssql+pyodbc:///?odbc_connect={quote_plus(odbc_conn_str)}",
                **pool_kwargs,
            )

        # Set query timeout on raw pyodbc connections via pool event.
        if query_timeout > 0:

            @event.listens_for(engine, "connect")
            def _set_query_timeout(dbapi_connection, connection_record):
                dbapi_connection.timeout = query_timeout

        return engine

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        """Get row counts using SQL Server DMV system queries.

        Queries sys.dm_db_partition_stats joined with sys.objects and
        sys.schemas to get approximate row counts without scanning tables.

        Args:
            engine: SQLAlchemy engine to query against.
            schema_name: Optional schema filter.

        Returns:
            Dict mapping 'schema.table' to approximate row count.
        """
        query = """
            SELECT
                s.name + '.' + o.name AS table_key,
                SUM(CASE WHEN ps.index_id IN (0, 1) THEN ps.row_count ELSE 0 END) AS row_count
            FROM sys.dm_db_partition_stats ps
            JOIN sys.objects o ON ps.object_id = o.object_id
            JOIN sys.schemas s ON o.schema_id = s.schema_id
            WHERE o.type = 'U'
        """

        params: dict = {}
        if schema_name is not None:
            query += " AND s.name = :schema_name"
            params["schema_name"] = schema_name

        query += " GROUP BY s.name, o.name"

        result: dict[str, int] = {}
        with engine.connect() as conn:
            rows = conn.execute(text(query), params)
            for row in rows:
                result[row.table_key] = int(row.row_count)

        return result

    @staticmethod
    def _build_odbc_connection_string(
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
            server: SQL Server host.
            database: Database name.
            username: Username (optional for Windows auth).
            password: Password (optional for Windows auth).
            port: Port number.
            authentication_method: Auth method.
            trust_server_cert: Trust server certificate.
            connection_timeout: Timeout in seconds.

        Returns:
            ODBC connection string.
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
            pass  # No UID/PWD/Authentication -- token is passed via attrs_before

        return ";".join(parts)
