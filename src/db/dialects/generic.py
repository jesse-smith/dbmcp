"""Generic dialect for any SQLAlchemy-supported database.

Uses Inspector-only metadata with COUNT(*) fallback for row counts.
Provides ANSI SQL quoting and generic query parsing.
"""

from __future__ import annotations

from sqlalchemy import create_engine as sa_create_engine
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.models.schema import SamplingMethod

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
        """Initialize GenericDialect.

        Args:
            sqlglot_dialect_name: Sqlglot dialect name (e.g., 'postgres', 'mysql').
                Caller must ensure this is a valid sqlglot dialect name; no validation
                is performed here. Invalid names will cause parse errors at query time.
        """
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
    def default_schema(self) -> str | None:
        """No default schema; the engine/connection decides."""
        return None

    @property
    def max_identifier_depth(self) -> int:
        """Max dotted identifier parts: table only."""
        return 1

    @property
    def safe_procedures(self) -> frozenset[str]:
        """No known-safe stored procedures for generic dialects."""
        return frozenset()

    @property
    def safe_operational_commands(self) -> frozenset[str]:
        """No dialect-specific SHOW/DESCRIBE allowlist for generic SQL."""
        return frozenset()

    def quote_identifier(self, identifier: str) -> str:
        """Quote using ANSI SQL double-quotes."""
        return f'"{identifier}"'

    def build_sample_query(
        self,
        method: SamplingMethod,
        full_table_name: str,
        column_sql: str,
        sample_size: int,
    ) -> str:
        """Build generic SQL sample-data query (LIMIT + RANDOM() + ROW_NUMBER)."""
        if method == SamplingMethod.TOP:
            return f"SELECT {column_sql} FROM {full_table_name} LIMIT {sample_size}"
        if method == SamplingMethod.TABLESAMPLE:
            return (
                f"SELECT {column_sql} FROM {full_table_name} "
                f"ORDER BY RANDOM() LIMIT {sample_size}"
            )
        if method == SamplingMethod.MODULO:
            order_by = "ROWID" if self._sqlglot_dialect == "sqlite" else "1"
            return f"""
            SELECT {column_sql} FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY {order_by}) AS _rn,
                       COUNT(*) OVER () AS _total
                FROM {full_table_name}
            ) _sampled
            WHERE _rn % CASE WHEN _total / {sample_size} < 1 THEN 1 ELSE _total / {sample_size} END = 0
            LIMIT {sample_size}
            """
        raise ValueError(f"Unknown sampling method: {method}")

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
