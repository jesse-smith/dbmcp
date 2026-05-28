"""DialectStrategy protocol for database dialect-specific behavior.

Defines the contract that all dialect implementations must satisfy.
Uses structural subtyping (typing.Protocol) so implementations don't
need to explicitly inherit -- they just need to implement the interface.
"""

from typing import TYPE_CHECKING, Protocol, runtime_checkable

from sqlalchemy.engine import Engine

if TYPE_CHECKING:
    from src.models.schema import SamplingMethod


@runtime_checkable
class DialectStrategy(Protocol):
    """Protocol for database dialect-specific behavior.

    Implementations encapsulate all dialect-specific logic: engine creation,
    identifier quoting, fast metadata queries, and capability advertisement.

    Properties:
        name: Dialect identifier string (e.g., 'mssql', 'databricks', 'generic').
        sqlglot_dialect: Sqlglot dialect name for query parsing (e.g., 'tsql'), or None for generic SQL.
        supports_indexes: Whether this dialect supports traditional index metadata.
        has_fast_row_counts: Whether this dialect has DMV/system-table-based fast row counts.
        default_schema: Default schema for this dialect, or None if the engine/connection decides.
        max_identifier_depth: Max number of dotted identifier parts (Databricks=3, MSSQL=2, generic=1).
    """

    @property
    def name(self) -> str:
        """Dialect identifier string (e.g., 'mssql', 'databricks', 'generic')."""
        ...

    @property
    def sqlglot_dialect(self) -> str | None:
        """Sqlglot dialect name for query parsing (e.g., 'tsql', 'databricks'), or None for generic SQL."""
        ...

    @property
    def supports_indexes(self) -> bool:
        """Whether this dialect supports traditional index metadata."""
        ...

    @property
    def has_fast_row_counts(self) -> bool:
        """Whether this dialect has DMV/system-table-based fast row counts."""
        ...

    @property
    def default_schema(self) -> str | None:
        """Default schema for this dialect, or None if the engine/connection decides."""
        ...

    @property
    def max_identifier_depth(self) -> int:
        """Max number of dotted identifier parts: Databricks=3, MSSQL=2, generic=1."""
        ...

    def create_engine(self, **kwargs) -> Engine:
        """Create a SQLAlchemy Engine with dialect-specific configuration.

        Args:
            **kwargs: Dialect-specific connection parameters.

        Returns:
            Configured SQLAlchemy Engine.
        """
        ...

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        """Get row counts using dialect-optimized system queries.

        Args:
            engine: SQLAlchemy engine to query against.
            schema_name: Optional schema filter.

        Returns:
            Dict mapping 'schema.table' to approximate row count.
            Returns empty dict if dialect doesn't support fast row counts.
        """
        ...

    @property
    def safe_procedures(self) -> frozenset[str]:
        """Known-safe stored procedures for this dialect.

        Returns frozenset of procedure names (lowercase, unqualified).
        Dialects without stored procedure support return empty frozenset.
        """
        ...

    @property
    def safe_operational_commands(self) -> frozenset[str]:
        """Read-only operational command verbs allowed by the validator.

        Returns frozenset of uppercase command verbs (e.g. {'SHOW', 'DESCRIBE'}).
        The denylist is otherwise dialect-agnostic; this allowlist opens specific
        discovery primitives per dialect (e.g. Databricks needs SHOW CATALOGS).
        """
        ...

    def quote_identifier(self, identifier: str) -> str:
        """Quote an identifier using dialect-appropriate quoting.

        Args:
            identifier: Raw SQL identifier (table name, column name, etc.)

        Returns:
            Quoted identifier (e.g., '[name]' for MSSQL, '"name"' for generic).
        """
        ...

    def build_sample_query(
        self,
        method: "SamplingMethod",
        full_table_name: str,
        column_sql: str,
        sample_size: int,
    ) -> str:
        """Build a dialect-correct sample-data query for the given sampling method.

        Args:
            method: SamplingMethod enum value (TOP, TABLESAMPLE, or MODULO).
            full_table_name: Fully qualified, already-quoted table name.
            column_sql: Column selection SQL fragment (e.g. "*" or a list).
            sample_size: Number of rows to return.

        Returns:
            Dialect-correct SQL query string.
        """
        ...
