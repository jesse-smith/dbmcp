"""Query execution service for sample data retrieval and ad-hoc queries.

This module provides methods for executing queries, sampling table data,
and handling data truncation for large or binary values.
"""

import hashlib
import re
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.models.schema import SampleData, SamplingMethod

logger = get_logger(__name__)


class QueryService:
    """Service for executing queries and sampling data.

    Handles sample data retrieval with multiple sampling strategies,
    binary/text truncation, and proper formatting of results.

    Attributes:
        engine: SQLAlchemy engine for database connection
    """

    def __init__(self, engine: Engine):
        """Initialize query service.

        Args:
            engine: SQLAlchemy engine
        """
        self.engine = engine

    def get_sample_data(
        self,
        table_name: str,
        schema_name: str = "dbo",
        sample_size: int = 5,
        sampling_method: SamplingMethod = SamplingMethod.TOP,
        columns: list[str] | None = None,
    ) -> SampleData:
        """Retrieve sample data from a table.

        Args:
            table_name: Table name to sample from
            schema_name: Schema name (default: 'dbo')
            sample_size: Number of rows to return (1-1000)
            sampling_method: Sampling strategy to use
            columns: Optional list of columns to include (None = all columns)

        Returns:
            SampleData object with rows and metadata

        Raises:
            ValueError: If parameters are invalid
        """
        # Validate parameters
        if sample_size < 1 or sample_size > 1000:
            raise ValueError("sample_size must be between 1 and 1000")

        if not table_name:
            raise ValueError("table_name is required")

        # Build column list
        column_sql = "*"
        if columns:
            # Sanitize column names (basic protection against SQL injection)
            sanitized_columns = [self._sanitize_identifier(col) for col in columns]
            column_sql = ", ".join(sanitized_columns)

        # Build query based on sampling method
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite doesn't use schema prefixes in the same way
            full_table_name = f"{table_name}"
        else:
            # SQL Server uses [schema].[table]
            full_table_name = f"[{schema_name}].[{table_name}]"

        if sampling_method == SamplingMethod.TOP:
            query = self._build_top_query(full_table_name, column_sql, sample_size)
        elif sampling_method == SamplingMethod.TABLESAMPLE:
            query = self._build_tablesample_query(full_table_name, column_sql, sample_size)
        elif sampling_method == SamplingMethod.MODULO:
            query = self._build_modulo_query(full_table_name, column_sql, sample_size)
        else:
            raise ValueError(f"Unknown sampling method: {sampling_method}")

        # Execute query and fetch results
        rows = []
        truncated_columns = []

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))

                for row in result:
                    row_dict = {}
                    for column_name, value in row._mapping.items():
                        truncated_value, was_truncated = self._truncate_value(value, column_name)
                        row_dict[column_name] = truncated_value

                        if was_truncated and column_name not in truncated_columns:
                            truncated_columns.append(column_name)

                    rows.append(row_dict)

        except Exception as e:
            logger.error(f"Error sampling data from {schema_name}.{table_name}: {e}")
            raise

        # Create sample ID
        table_id = f"{schema_name}.{table_name}"
        timestamp = datetime.now().isoformat()
        sample_id = hashlib.sha256(f"{table_id}_{timestamp}".encode()).hexdigest()[:12]

        return SampleData(
            sample_id=sample_id,
            table_id=table_id,
            sample_size=len(rows),
            sampling_method=sampling_method,
            rows=rows,
            truncated_columns=truncated_columns,
            sampled_at=datetime.now(),
        )

    def _build_top_query(self, table_name: str, column_sql: str, sample_size: int) -> str:
        """Build SELECT TOP N query (fast, not representative).

        Args:
            table_name: Fully qualified table name
            column_sql: Column selection SQL
            sample_size: Number of rows

        Returns:
            SQL query string
        """
        # Detect database dialect
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite uses LIMIT
            return f"SELECT {column_sql} FROM {table_name} LIMIT {sample_size}"
        else:
            # SQL Server uses TOP
            return f"SELECT TOP ({sample_size}) {column_sql} FROM {table_name}"

    def _build_tablesample_query(self, table_name: str, column_sql: str, sample_size: int) -> str:
        """Build TABLESAMPLE query (statistical sampling).

        Args:
            table_name: Fully qualified table name
            column_sql: Column selection SQL
            sample_size: Number of rows

        Returns:
            SQL query string
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite doesn't support TABLESAMPLE, fall back to RANDOM()
            return f"SELECT {column_sql} FROM {table_name} ORDER BY RANDOM() LIMIT {sample_size}"
        else:
            # SQL Server TABLESAMPLE requires percentage or ROWS
            # We use ROWS for more predictable sample size
            return f"SELECT TOP ({sample_size}) {column_sql} FROM {table_name} TABLESAMPLE ({sample_size} ROWS)"

    def _build_modulo_query(self, table_name: str, column_sql: str, sample_size: int) -> str:
        """Build modulo-based deterministic sampling query.

        Assumes table has an ID or similar sequential column.
        Falls back to TOP/LIMIT if no suitable column found.

        Args:
            table_name: Fully qualified table name
            column_sql: Column selection SQL
            sample_size: Number of rows

        Returns:
            SQL query string
        """
        dialect_name = self.engine.dialect.name

        # For Phase 1, we use a simple deterministic approach with ordering
        # More sophisticated modulo sampling would require column metadata
        if dialect_name == "sqlite":
            # SQLite: deterministic sampling by ordering by ROWID
            return f"SELECT {column_sql} FROM {table_name} ORDER BY ROWID LIMIT {sample_size}"
        else:
            # SQL Server: deterministic sampling with explicit ordering
            return f"""
            SELECT TOP ({sample_size}) {column_sql}
            FROM {table_name}
            ORDER BY (SELECT NULL)
            """

    def _sanitize_identifier(self, identifier: str) -> str:
        """Sanitize SQL identifier to prevent injection.

        Args:
            identifier: Column or table name

        Returns:
            Sanitized identifier (quoted for SQL Server, unquoted for SQLite)

        Raises:
            ValueError: If identifier contains suspicious characters
        """
        # Allow only alphanumeric, underscore, and spaces
        if not re.match(r'^[a-zA-Z0-9_\s]+$', identifier):
            raise ValueError(f"Invalid identifier: {identifier}")

        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite doesn't require brackets, use as-is
            return identifier
        else:
            # SQL Server uses brackets
            return f"[{identifier}]"

    def _truncate_value(self, value: Any, column_name: str) -> tuple[Any, bool]:
        """Truncate large or binary values for display.

        Args:
            value: Column value
            column_name: Name of column (for context)

        Returns:
            Tuple of (truncated_value, was_truncated)
        """
        # Handle None
        if value is None:
            return None, False

        # Handle binary data (bytes)
        if isinstance(value, bytes):
            if len(value) > 32:
                hex_preview = value[:32].hex()
                return f"<binary: {hex_preview}... ({len(value)} bytes)>", True
            else:
                return f"<binary: {value.hex()} ({len(value)} bytes)>", True

        # Handle large text (>1000 characters)
        if isinstance(value, str):
            if len(value) > 1000:
                return value[:1000] + f"... ({len(value)} chars total)", True

        # All other types: return as-is
        return value, False
