"""Generic dialect for any SQLAlchemy-supported database.

Uses Inspector-only metadata with COUNT(*) fallback for row counts.
Provides ANSI SQL quoting and generic query parsing.
"""

from __future__ import annotations

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine

from src.logging_config import get_logger

logger = get_logger(__name__)

# URL scheme (from SQLAlchemy get_backend_name()) -> sqlglot dialect name
# Only schemes where sqlglot has a dedicated dialect are listed.
# Unlisted schemes get None (generic SQL parsing).
_URL_SCHEME_TO_SQLGLOT: dict[str, str] = {
    "postgresql": "postgres",
    "mysql": "mysql",
    "sqlite": "sqlite",
}


class GenericDialect:
    """Generic dialect for any SQLAlchemy-supported database.

    Accepts any SQLAlchemy URL and uses Inspector-only metadata.
    Does not assume driver-specific features (no DMV, no stored procedures).
    """

    def __init__(self, sqlglot_dialect_name: str | None = None):
        self._sqlglot_dialect = sqlglot_dialect_name

    @property
    def name(self) -> str:
        """Dialect identifier string."""
        return "generic"

    @property
    def sqlglot_dialect(self) -> str | None:
        """Sqlglot dialect name for query parsing, or None for generic SQL."""
        return self._sqlglot_dialect

    @property
    def supports_indexes(self) -> bool:
        """Whether this dialect supports traditional index metadata."""
        return True

    @property
    def has_fast_row_counts(self) -> bool:
        """Whether this dialect has DMV/system-table-based fast row counts."""
        return False

    @property
    def safe_procedures(self) -> frozenset[str]:
        """No known-safe stored procedures for generic dialects."""
        return frozenset()

    def quote_identifier(self, identifier: str) -> str:
        """Quote using ANSI SQL double-quotes."""
        return f'"{identifier}"'

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine from any supported URL.

        Args:
            **kwargs: Connection parameters. Required:
                sqlalchemy_url (str): Full SQLAlchemy connection URL.

        Returns:
            Configured SQLAlchemy Engine.
        """
        url = kwargs["sqlalchemy_url"]
        return sa_create_engine(
            url,
            pool_pre_ping=True,
            echo=False,
        )

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        """No fast path; callers use COUNT(*) fallback.

        Args:
            engine: SQLAlchemy engine (unused).
            schema_name: Optional schema filter (unused).

        Returns:
            Empty dict -- generic dialect has no DMV-based fast counts.
        """
        return {}
