"""Databricks dialect implementation.

Encapsulates Databricks-specific behavior: token-based auth URL construction,
lazy import gating for optional dependencies, and capability flags.
"""

from __future__ import annotations

from urllib.parse import quote_plus, urlencode

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine

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

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine with Databricks token auth.

        Args:
            **kwargs: Connection parameters:
                host (str): Databricks workspace hostname. (required)
                http_path (str): SQL warehouse HTTP path. (required)
                token (str): Personal access token or OAuth token. (optional)
                catalog (str): Unity Catalog name (default "main"). (optional)
                schema (str): Schema name (default "default"). (optional)

        Returns:
            Configured SQLAlchemy Engine.

        Raises:
            ImportError: If databricks-sqlalchemy is not installed.
            ValueError: If required parameters are missing.
        """
        if _databricks_import_error is not None:
            raise ImportError(
                "Databricks support requires databricks-sqlalchemy. "
                "Install with: pip install dbmcp[databricks]"
            ) from _databricks_import_error

        # Validate required parameters
        try:
            host: str = kwargs["host"]
            http_path: str = kwargs["http_path"]
        except KeyError as e:
            raise ValueError(f"Missing required parameter: {e.args[0]}") from e

        token: str = kwargs.get("token", "")
        catalog: str = kwargs.get("catalog", "main")
        schema: str = kwargs.get("schema", "default")

        query_params = urlencode({
            "http_path": http_path,
            "catalog": catalog,
            "schema": schema,
        })
        url = f"databricks://token:{quote_plus(token)}@{host}?{query_params}"

        return sa_create_engine(url, pool_pre_ping=True, echo=False)

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
