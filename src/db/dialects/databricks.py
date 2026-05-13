"""Databricks dialect implementation.

Encapsulates Databricks-specific behavior: token-based auth URL construction,
lazy import gating for optional dependencies, and capability flags.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.engine.url import make_url

from src.logging_config import get_logger
from src.models.schema import SamplingMethod

logger = get_logger(__name__)

try:
    import databricks.sql  # noqa: F401

    _databricks_import_error: ImportError | None = None
except ImportError as e:
    # Set to None to allow import of this module even when databricks packages
    # are unavailable.  create_engine() will raise a helpful error if needed.
    _databricks_import_error = e


class DatabricksDialect:
    """Databricks dialect implementation.

    Encapsulates Databricks-specific behavior: token-based auth URL construction,
    backtick identifier quoting, and capability advertisement.

    Databricks does not support:
    - Traditional index metadata
    - DMV-based fast row counts
    - Stored procedures
    """

    @property
    def name(self) -> str:
        """Dialect identifier string."""
        return "databricks"

    @property
    def sqlglot_dialect(self) -> str:
        """Sqlglot dialect name for query parsing."""
        return "databricks"

    @property
    def supports_indexes(self) -> bool:
        """Whether this dialect supports traditional index metadata."""
        return False

    @property
    def has_fast_row_counts(self) -> bool:
        """Whether this dialect has DMV/system-table-based fast row counts."""
        return False

    @property
    def safe_procedures(self) -> frozenset[str]:
        """No known-safe stored procedures for Databricks."""
        return frozenset()

    @property
    def safe_operational_commands(self) -> frozenset[str]:
        """Read-only discovery verbs (SHOW/DESCRIBE/DESC/EXPLAIN) are safe for Databricks."""
        return frozenset({"SHOW", "DESCRIBE", "DESC", "EXPLAIN"})

    def quote_identifier(self, identifier: str) -> str:
        """Quote using Databricks backticks."""
        return f"`{identifier}`"

    def build_sample_query(
        self,
        method: SamplingMethod,
        full_table_name: str,
        column_sql: str,
        sample_size: int,
    ) -> str:
        """Build Databricks sample-data query (LIMIT-based; no TOP/TABLESAMPLE)."""
        if method == SamplingMethod.TOP:
            return f"SELECT {column_sql} FROM {full_table_name} LIMIT {sample_size}"
        if method == SamplingMethod.TABLESAMPLE:
            return (
                f"SELECT {column_sql} FROM {full_table_name} "
                f"ORDER BY RAND() LIMIT {sample_size}"
            )
        if method == SamplingMethod.MODULO:
            return f"""
            SELECT {column_sql} FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY 1) AS _rn,
                       COUNT(*) OVER () AS _total
                FROM {full_table_name}
            ) _sampled
            WHERE _rn % CASE WHEN _total / {sample_size} < 1 THEN 1 ELSE _total / {sample_size} END = 0
            LIMIT {sample_size}
            """
        raise ValueError(f"Unknown sampling method: {method}")

    @staticmethod
    def _kwargs_from_url(sqlalchemy_url: str, original_kwargs: dict) -> dict:
        """Parse a SQLAlchemy ``databricks://...`` URL into create_engine kwargs.

        URL-derived keys: host, http_path, token, catalog, schema.

        Conflict policy: URL wins. Any original kwargs other than the
        preserved runtime set are dropped (and logged at DEBUG).

        Preserved runtime kwargs (passed through verbatim):
        ``query_timeout``, ``pool_config``, ``connection_id``,
        ``disconnect_callback``, ``connection_timeout``.

        URL → kwargs mapping:
            - host       ← url.host (required; ValueError if missing)
            - http_path  ← url.query["http_path"] (required; ValueError if missing)
            - token      ← url.password or "" (username expected literally "token")
            - catalog    ← url.query.get("catalog", "")  (empty when missing — caller must
                                                            supply or create_engine raises)
            - schema     ← url.database or url.query.get("schema") or "default"

        Args:
            sqlalchemy_url: The ``databricks://...`` URL to parse.
            original_kwargs: The kwargs dict passed to create_engine.

        Returns:
            A new kwargs dict suitable for the kwargs-only branch of
            ``create_engine``.

        Raises:
            ValueError: If URL is missing host or http_path.
        """
        url = make_url(sqlalchemy_url)

        if not url.host:
            raise ValueError(
                f"sqlalchemy_url missing host: {sqlalchemy_url!r}"
            )

        query = dict(url.query)
        http_path = query.get("http_path")
        if not http_path:
            raise ValueError(
                f"sqlalchemy_url missing http_path: {sqlalchemy_url!r}"
            )

        token = url.password or ""
        catalog = query.get("catalog", "")
        schema = url.database or query.get("schema") or "default"

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

        new_kwargs = {
            k: original_kwargs[k] for k in preserved_keys if k in original_kwargs
        }
        new_kwargs.update({
            "host": url.host,
            "http_path": http_path,
            "token": token,
            "catalog": catalog,
            "schema": schema,
        })
        return new_kwargs

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine with Databricks token auth.

        Two call styles are supported:

        1. **Kwargs-only (legacy):** pass ``host``, ``http_path``, ``token``,
           ``catalog``, ``schema`` directly.
        2. **URL-based:** pass ``sqlalchemy_url="databricks://token:T@host...?http_path=..."``.
           The URL is parsed via SQLAlchemy's ``make_url`` and its fields
           (host, password-as-token, ``http_path``/``catalog``/``schema`` query
           params, or schema from the path component) supply the connection
           identity.

        **Conflict policy (URL mode):** URL wins. Any conflicting kwargs
        (host, http_path, token, catalog, schema) are dropped and logged at
        DEBUG. Preserved runtime kwargs that pass through unchanged:
        ``query_timeout``, ``pool_config``, ``connection_id``,
        ``disconnect_callback``, ``connection_timeout``.

        Args:
            **kwargs: Connection parameters. Either ``sqlalchemy_url`` or
                the kwargs-only set below.

                sqlalchemy_url (str): Full ``databricks://`` URL. When
                    present, it supplies all connection identity fields.
                host (str): Databricks workspace hostname. (required in kwargs mode)
                http_path (str): SQL warehouse HTTP path. (required in kwargs mode)
                token (str): Personal access token or OAuth token. (optional)
                catalog (str): Unity Catalog name. **Required** — empty/missing/None
                    raises ValueError("Databricks catalog is required") (IDENT-01).
                schema (str): Schema name (default "default"). (optional)

        Returns:
            Configured SQLAlchemy Engine.

        Raises:
            ImportError: If databricks-sqlalchemy is not installed.
            ValueError: If required parameters are missing (kwargs mode)
                or the URL lacks host/http_path (URL mode).
        """
        if _databricks_import_error is not None:
            raise ImportError(
                "Databricks support requires databricks-sqlalchemy. "
                "Reinstall dbmcp to pull it in."
            ) from _databricks_import_error

        sqlalchemy_url = kwargs.get("sqlalchemy_url")
        if sqlalchemy_url is not None:
            kwargs = self._kwargs_from_url(sqlalchemy_url, kwargs)

        # Validate required parameters
        try:
            host: str = kwargs["host"]
            http_path: str = kwargs["http_path"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter: {e.args[0]}") from e

        token: str = kwargs.get("token", "")
        catalog: str = kwargs.get("catalog", "") or ""
        if not catalog:
            raise ValueError("Databricks catalog is required")
        schema: str = kwargs.get("schema", "default")

        query_params = urlencode({
            "http_path": http_path,
            "catalog": catalog,
            "schema": schema,
        })
        url = f"databricks://token:{quote_plus(token)}@{host}?{query_params}"

        # Defaults: 30s socket timeout (mirrors MSSQL), cap retries at 2 so bad
        # hosts fail fast instead of hanging for minutes on connector retries.
        connection_timeout = kwargs.get("connection_timeout", 30)
        dialect_defaults = {
            "_socket_timeout": connection_timeout,
            "_retry_stop_after_attempts_count": 2,
        }
        # User-supplied connect_args win on matching keys; defaults fill gaps.
        user_connect_args = kwargs.get("connect_args") or {}
        merged_connect_args = {**dialect_defaults, **user_connect_args}

        return sa_create_engine(
            url,
            pool_pre_ping=True,
            echo=False,
            connect_args=merged_connect_args,
        )

    def list_catalogs(self, engine: Engine) -> list[str]:
        """Return catalog names visible to the connected principal via SHOW CATALOGS.

        Used by the connect-time helper that enriches the catalog-required
        ValueError raised by ``create_engine`` (IDENT-01) and by future DISC-01
        tooling. Lets ``SQLAlchemyError`` propagate — callers decide how to wrap.

        Args:
            engine: A SQLAlchemy Engine already bound to a Databricks workspace.
                The engine does NOT need to point at a specific catalog;
                SHOW CATALOGS is workspace-scoped.

        Returns:
            List of catalog names (the row[0] of each SHOW CATALOGS row), in
            the order returned by Databricks.
        """
        from sqlalchemy import text

        with engine.connect() as conn:
            rows = conn.execute(text("SHOW CATALOGS")).fetchall()
        return [row[0] for row in rows]

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        """No fast path for Databricks; callers use COUNT(*) fallback.

        Args:
            engine: SQLAlchemy engine (unused).
            schema_name: Optional schema filter (unused).

        Returns:
            Empty dict -- Databricks has no DMV-based fast counts.
        """
        return {}
