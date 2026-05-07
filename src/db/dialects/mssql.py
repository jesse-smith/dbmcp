"""SQL Server dialect implementation.

Encapsulates MSSQL-specific behavior: ODBC connection strings,
Azure AD authentication, DMV-based fast metadata, bracket quoting.
"""

from __future__ import annotations

import builtins
from collections.abc import Callable
from urllib.parse import quote_plus

try:
    import pyodbc
    _pyodbc_import_error = None
except ImportError as e:
    # Set to None to allow import of this module even when pyodbc is unavailable.
    # create_engine() will raise a helpful error if pyodbc is actually needed.
    pyodbc = None  # type: ignore[assignment]
    _pyodbc_import_error = e

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy import event, text
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url
from sqlalchemy.pool import QueuePool

from src.db.dialects.azure_auth import SQL_COPT_SS_ACCESS_TOKEN, AzureTokenProvider
from src.logging_config import get_logger
from src.models.schema import AuthenticationMethod, SamplingMethod

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

    @property
    def safe_operational_commands(self) -> frozenset[str]:
        """MSSQL has no SHOW/DESCRIBE primitives -- empty allowlist."""
        return frozenset()

    def quote_identifier(self, identifier: str) -> str:
        """Quote using SQL Server square brackets."""
        return f"[{identifier.replace(']', ']]')}]"

    def build_sample_query(
        self,
        method: SamplingMethod,
        full_table_name: str,
        column_sql: str,
        sample_size: int,
    ) -> str:
        """Build MSSQL sample-data query using TOP / TABLESAMPLE / ROW_NUMBER."""
        if method == SamplingMethod.TOP:
            return f"SELECT TOP ({sample_size}) {column_sql} FROM {full_table_name}"
        if method == SamplingMethod.TABLESAMPLE:
            return (
                f"SELECT TOP ({sample_size}) {column_sql} FROM {full_table_name} "
                f"TABLESAMPLE ({sample_size} ROWS)"
            )
        if method == SamplingMethod.MODULO:
            return f"""
            SELECT TOP ({sample_size}) {column_sql} FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS _rn,
                       COUNT(*) OVER () AS _total
                FROM {full_table_name}
            ) _sampled
            WHERE _rn % CASE WHEN _total / {sample_size} < 1 THEN 1 ELSE _total / {sample_size} END = 0
            """
        raise ValueError(f"Unknown sampling method: {method}")

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine with MSSQL-specific ODBC configuration.

        Two entry modes:

        1. **Kwargs mode** (named connections): pass server, database,
           authentication_method explicitly.
        2. **URL mode** (sqlalchemy_url): pass ``sqlalchemy_url="mssql+pyodbc://..."``
           and the dialect parses host, database, port, credentials, and auth
           parameters from the URL. URL values take precedence — any
           conflicting kwargs (server, database, username, password,
           authentication_method, trust_server_cert, tenant_id) are ignored
           when ``sqlalchemy_url`` is present; only ``query_timeout``,
           ``pool_config``, ``connection_id``, and ``disconnect_callback``
           survive from kwargs.

        Supported URL query parameters (URL mode):

        - ``authentication_method``: ``sql`` | ``windows`` | ``azure_ad`` |
          ``azure_ad_integrated``. If omitted, defaults to ``sql`` when
          username+password are present, else ``windows``.
        - ``trust_server_cert``: ``true`` / ``false`` / ``1`` / ``0`` /
          ``yes`` / ``no`` (case-insensitive). Default ``false``.
        - ``tenant_id``: Azure AD tenant (optional).

        Args:
            **kwargs: Connection parameters:
                sqlalchemy_url (str | None): SQLAlchemy URL — when present,
                    populates server/database/credentials/auth from URL.
                server (str): SQL Server host (kwargs mode).
                database (str): Database name (kwargs mode).
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

        Raises:
            ValueError: If sqlalchemy_url is malformed — missing host,
                missing database, or invalid authentication_method value.
        """
        if pyodbc is None:
            if _pyodbc_import_error and "driver" in str(_pyodbc_import_error).lower():
                raise ImportError(
                    "MSSQL support requires ODBC Driver 18 for SQL Server. "
                    "Install from: https://learn.microsoft.com/en-us/sql/connect/odbc/download-odbc-driver-for-sql-server"
                ) from _pyodbc_import_error
            else:
                raise ImportError(
                    "MSSQL support requires pyodbc. Reinstall dbmcp to pull it in."
                ) from _pyodbc_import_error

        # URL-mode branch: when sqlalchemy_url is provided, parse it and
        # overwrite any conflicting kwargs (URL wins). See method docstring.
        sqlalchemy_url = kwargs.get("sqlalchemy_url")
        if sqlalchemy_url is not None:
            kwargs = self._kwargs_from_url(sqlalchemy_url, kwargs)

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
        driver: str | None = kwargs.get("driver")
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
            driver=driver,
        )

        pool_kwargs = self._build_pool_kwargs(pool_config, authentication_method)

        if authentication_method == AuthenticationMethod.AZURE_AD_INTEGRATED:
            creator = self._build_azure_ad_creator(
                odbc_conn_str=odbc_conn_str,
                tenant_id=tenant_id,
                connection_id=connection_id,
                disconnect_callback=disconnect_callback,
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

    @staticmethod
    def _build_pool_kwargs(pool_config, authentication_method: AuthenticationMethod) -> dict:
        """Build the pool kwargs dict for ``sa_create_engine``.

        Azure AD (either flavor) overrides ``pool_recycle`` with the shorter
        ``azure_ad_pool_recycle`` so pooled connections are recycled before
        the AD access token expires (~3600s).
        """
        pool_kwargs = {
            "poolclass": QueuePool,
            "pool_size": pool_config.pool_size,
            "max_overflow": pool_config.max_overflow,
            "pool_timeout": pool_config.pool_timeout,
            "pool_pre_ping": pool_config.pool_pre_ping,
            "pool_recycle": pool_config.pool_recycle,
            "echo": False,
        }
        if authentication_method in (
            AuthenticationMethod.AZURE_AD,
            AuthenticationMethod.AZURE_AD_INTEGRATED,
        ):
            pool_kwargs["pool_recycle"] = pool_config.azure_ad_pool_recycle
            logger.debug(
                f"Azure AD auth: pool_recycle set to {pool_kwargs['pool_recycle']}s (token-aware)"
            )
        return pool_kwargs

    @staticmethod
    def _build_azure_ad_creator(
        odbc_conn_str: str,
        tenant_id: str | None,
        connection_id: str | None,
        disconnect_callback: Callable[[str], None] | None,
    ):
        """Build the pyodbc ``creator`` closure for Azure AD Integrated auth.

        The closure fetches a fresh AD token on each new pooled connection and
        attaches it via ``SQL_COPT_SS_ACCESS_TOKEN``. Token acquisition failure
        triggers ``disconnect_callback`` so the stale connection is purged.
        """
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

        return creator

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
    def _kwargs_from_url(sqlalchemy_url: str, original_kwargs: dict) -> dict:
        """Parse a SQLAlchemy URL into the kwargs dict create_engine expects.

        URL wins: any conflicting original kwargs are dropped. Preserved
        keys: query_timeout, pool_config, connection_id, disconnect_callback.

        Args:
            sqlalchemy_url: The ``mssql+pyodbc://...`` URL to parse.
            original_kwargs: The kwargs dict passed to create_engine.

        Returns:
            A new kwargs dict with URL-derived server/database/credentials/auth
            merged with preserved runtime kwargs.

        Raises:
            ValueError: If URL is missing host, missing database, or carries
                an unrecognized ``authentication_method`` query value.
        """
        url = make_url(sqlalchemy_url)

        if not url.host:
            raise ValueError(
                f"sqlalchemy_url missing server (host): {sqlalchemy_url!r}"
            )
        if not url.database:
            raise ValueError(
                f"sqlalchemy_url missing database: {sqlalchemy_url!r}"
            )

        # url.query is an immutabledict; normalize to a plain dict of
        # single-value strings (SQLAlchemy collapses scalar query params).
        query = dict(url.query)

        # authentication_method: explicit value wins; otherwise default by
        # presence of credentials (SQL if user+pass, else WINDOWS).
        auth_raw = query.get("authentication_method")
        if auth_raw is not None:
            try:
                authentication_method = AuthenticationMethod(auth_raw.lower())
            except ValueError as e:
                accepted = ", ".join(m.value for m in AuthenticationMethod)
                raise ValueError(
                    f"Invalid authentication_method {auth_raw!r} in sqlalchemy_url. "
                    f"Accepted values: {accepted}"
                ) from e
        elif url.username and url.password:
            authentication_method = AuthenticationMethod.SQL
        else:
            authentication_method = AuthenticationMethod.WINDOWS

        # trust_server_cert: parse as bool (case-insensitive).
        tsc_raw = query.get("trust_server_cert", "")
        trust_server_cert = tsc_raw.strip().lower() in ("true", "1", "yes")

        # Build the normalized kwargs the existing code path expects.
        # Preserve only runtime kwargs (timeouts, pool, callbacks) from original.
        preserved_keys = {
            "query_timeout",
            "pool_config",
            "connection_id",
            "disconnect_callback",
            "connection_timeout",
        }
        conflicting = [
            k
            for k in original_kwargs
            if k != "sqlalchemy_url" and k not in preserved_keys
        ]
        if conflicting:
            logger.debug(
                "sqlalchemy_url supplied; ignoring conflicting kwargs: %s",
                conflicting,
            )

        new_kwargs = {k: original_kwargs[k] for k in preserved_keys if k in original_kwargs}
        new_kwargs.update({
            "server": url.host,
            "database": url.database,
            "port": url.port or 1433,
            "username": url.username,
            "password": url.password,
            "authentication_method": authentication_method,
            "trust_server_cert": trust_server_cert,
            "tenant_id": query.get("tenant_id"),
            "driver": query.get("driver"),
        })
        return new_kwargs

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
        driver: str | None = None,
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
            driver: ODBC driver name (e.g. "ODBC Driver 17 for SQL Server").
                When None, defaults to "ODBC Driver 18 for SQL Server". Intended
                to be populated via the ``driver`` URL query param; kwargs-mode
                callers typically leave this as the default.

        Returns:
            ODBC connection string.
        """
        driver_name = driver or "ODBC Driver 18 for SQL Server"
        parts = [
            f"Driver={{{driver_name}}}",
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
