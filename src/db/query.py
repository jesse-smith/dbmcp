"""Query execution service for sample data retrieval and ad-hoc queries.

This module provides methods for executing queries, sampling table data,
and handling data truncation for large or binary values.
"""

import hashlib
import re
import time
import uuid
from datetime import datetime
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from src.logging_config import get_logger
from src.models.schema import Query, QueryType, SampleData, SamplingMethod

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

    # =========================================================================
    # Query Execution Methods (User Story 7)
    # =========================================================================

    def parse_query_type(self, query_text: str) -> QueryType:
        """Parse the type of SQL query from the query text.

        Args:
            query_text: SQL query string

        Returns:
            QueryType enum value (SELECT, INSERT, UPDATE, DELETE, or OTHER)
        """
        if not query_text:
            return QueryType.OTHER

        # Normalize: remove comments and leading whitespace
        cleaned = self._remove_sql_comments(query_text.strip())

        # Get first keyword
        first_word = cleaned.split()[0].upper() if cleaned.split() else ""

        query_type_map = {
            "SELECT": QueryType.SELECT,
            "INSERT": QueryType.INSERT,
            "UPDATE": QueryType.UPDATE,
            "DELETE": QueryType.DELETE,
        }

        return query_type_map.get(first_word, QueryType.OTHER)

    def _remove_sql_comments(self, query_text: str) -> str:
        """Remove SQL comments from query text.

        Args:
            query_text: SQL query string

        Returns:
            Query text with comments removed
        """
        # Remove single-line comments (-- to end of line)
        cleaned = re.sub(r'--[^\n]*', '', query_text)
        # Remove multi-line comments (/* ... */)
        cleaned = re.sub(r'/\*.*?\*/', '', cleaned, flags=re.DOTALL)
        return cleaned.strip()

    def is_query_allowed(
        self,
        query_type: QueryType,
        allow_write: bool = False,
    ) -> tuple[bool, str | None]:
        """Check if a query type is allowed to execute.

        Args:
            query_type: Type of query
            allow_write: Whether write operations are explicitly enabled

        Returns:
            Tuple of (is_allowed, error_message if not allowed)
        """
        if query_type == QueryType.SELECT:
            return True, None

        if query_type in (QueryType.INSERT, QueryType.UPDATE, QueryType.DELETE):
            if allow_write:
                return True, None
            return False, (
                f"Write operations ({query_type.value.upper()}) are blocked by default. "
                "Enable allow_write=True to execute write operations."
            )

        if query_type == QueryType.OTHER:
            return False, (
                "Only SELECT queries are allowed by default. "
                "DDL and other statements are not supported."
            )

        return False, f"Unknown query type: {query_type}"

    def inject_row_limit(self, query_text: str, row_limit: int) -> str:
        """Inject a row limit (TOP clause for SQL Server) into a SELECT query.

        Args:
            query_text: Original SQL query
            row_limit: Maximum rows to return

        Returns:
            Query with row limit injected
        """
        if row_limit <= 0:
            return query_text

        # Remove comments for parsing but keep original for execution
        cleaned = self._remove_sql_comments(query_text.strip())

        # Check if it's a SELECT query
        if not cleaned.upper().startswith("SELECT"):
            return query_text

        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite: Add LIMIT clause if not present
            if " LIMIT " not in query_text.upper():
                return f"{query_text} LIMIT {row_limit}"
            return query_text
        else:
            # SQL Server: Inject TOP clause after SELECT
            # Handle SELECT DISTINCT, SELECT ALL, etc.
            select_pattern = re.compile(
                r'^(SELECT\s+(?:DISTINCT\s+|ALL\s+)?)',
                re.IGNORECASE
            )

            # Check if TOP already exists
            if re.search(r'\bTOP\s*\(?\s*\d+\s*\)?', query_text, re.IGNORECASE):
                return query_text

            match = select_pattern.match(cleaned)
            if match:
                prefix = match.group(1)
                rest = cleaned[len(prefix):]
                return f"{prefix}TOP ({row_limit}) {rest}"

            return query_text

    def execute_query(
        self,
        connection_id: str,
        query_text: str,
        row_limit: int = 1000,
        allow_write: bool = False,
    ) -> Query:
        """Execute a SQL query and return results.

        Args:
            connection_id: Connection ID
            query_text: SQL query to execute
            row_limit: Maximum rows to return (1-10000, default: 1000)
            allow_write: Allow write operations (default: False)

        Returns:
            Query object with results and metadata

        Raises:
            ValueError: If parameters are invalid or query is blocked
        """
        # Validate parameters
        if not query_text or not query_text.strip():
            raise ValueError("query_text is required and cannot be empty")

        if row_limit < 1 or row_limit > 10000:
            raise ValueError("row_limit must be between 1 and 10000")

        # Generate query ID
        query_id = str(uuid.uuid4())

        # Parse query type
        query_type = self.parse_query_type(query_text)

        # Check if query is allowed
        is_allowed, error_message = self.is_query_allowed(query_type, allow_write)

        if not is_allowed:
            return Query(
                query_id=query_id,
                connection_id=connection_id,
                query_text=query_text,
                query_type=query_type,
                is_allowed=False,
                row_limit=row_limit,
                error_message=error_message,
            )

        # Inject row limit for SELECT queries
        if query_type == QueryType.SELECT:
            executed_query = self.inject_row_limit(query_text, row_limit)
        else:
            executed_query = query_text

        # Execute query
        start_time = time.perf_counter()
        columns: list[str] = []
        rows: list[dict[str, Any]] = []
        rows_affected = 0
        error_message = None
        total_rows_available: int | None = None

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(executed_query))

                if query_type == QueryType.SELECT:
                    # Get column names
                    columns = list(result.keys())

                    # Fetch all rows (already limited by TOP/LIMIT)
                    fetched_rows = result.fetchall()
                    rows_affected = len(fetched_rows)

                    # Convert to list of dicts with value truncation
                    for row in fetched_rows:
                        row_dict = {}
                        for col_name, value in zip(columns, row, strict=True):
                            truncated_value, _ = self._truncate_value(value, col_name)
                            row_dict[col_name] = truncated_value
                        rows.append(row_dict)

                    # Check if we hit the limit (more rows might be available)
                    if len(rows) == row_limit:
                        # Try to get count of total rows
                        try:
                            count_query = self._build_count_query(query_text)
                            if count_query:
                                count_result = conn.execute(text(count_query))
                                count_value = count_result.scalar()
                                # Only use count if it's a valid integer
                                if isinstance(count_value, int):
                                    total_rows_available = count_value
                        except Exception:
                            # If count fails, leave total_rows_available as None
                            pass
                else:
                    # For write operations, get rowcount
                    rows_affected = result.rowcount if result.rowcount >= 0 else 0
                    conn.commit()

        except Exception as e:
            error_message = f"Query execution failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Query execution error: {e}")

        end_time = time.perf_counter()
        execution_time_ms = int((end_time - start_time) * 1000)

        query = Query(
            query_id=query_id,
            connection_id=connection_id,
            query_text=query_text,
            query_type=query_type,
            is_allowed=True,
            row_limit=row_limit,
            execution_time_ms=execution_time_ms,
            rows_affected=rows_affected,
            error_message=error_message,
            executed_at=datetime.now(),
        )

        # Store additional result data as attributes (not in dataclass)
        # These are returned separately in the response
        query._columns = columns  # type: ignore
        query._rows = rows  # type: ignore
        query._total_rows_available = total_rows_available  # type: ignore

        return query

    def _build_count_query(self, query_text: str) -> str | None:
        """Build a COUNT(*) query from a SELECT query to get total row count.

        Args:
            query_text: Original SELECT query

        Returns:
            COUNT query string, or None if cannot be built
        """
        cleaned = self._remove_sql_comments(query_text.strip())

        # Very basic approach: wrap query in subquery
        # This works for simple queries but may fail for complex ones
        # We don't want to slow down every query with a count, so this is best-effort
        try:
            return f"SELECT COUNT(*) FROM ({cleaned}) AS count_subquery"
        except Exception:
            return None

    def get_query_results(self, query: Query) -> dict[str, Any]:
        """Get the result data from an executed query.

        Args:
            query: Query object from execute_query

        Returns:
            Dict with columns, rows, and metadata
        """
        columns = getattr(query, '_columns', [])
        rows = getattr(query, '_rows', [])
        total_rows_available = getattr(query, '_total_rows_available', None)

        result: dict[str, Any] = {
            "query_id": query.query_id,
            "query_type": query.query_type.value,
            "is_allowed": query.is_allowed,
            "execution_time_ms": query.execution_time_ms,
            "rows_returned": len(rows),
            "rows_affected": query.rows_affected,
        }

        if not query.is_allowed:
            # Query was blocked by read-only enforcement
            result["status"] = "blocked"
            if query.error_message:
                result["error_message"] = query.error_message
        elif query.error_message:
            # Query execution failed with an error
            result["error_message"] = query.error_message
            result["status"] = "error"
        else:
            result["status"] = "success"
            result["columns"] = columns
            result["rows"] = rows

            # Indicate if more rows are available
            if total_rows_available is not None and total_rows_available > len(rows):
                result["rows_available"] = total_rows_available
                result["limited"] = True
            else:
                result["limited"] = len(rows) == query.row_limit

        if query.executed_at:
            result["executed_at"] = query.executed_at.isoformat()

        return result
