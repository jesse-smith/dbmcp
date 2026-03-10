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

import sqlglot
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlalchemy.exc import SQLAlchemyError
from sqlglot import exp

from src.config import get_config
from src.db.metadata import MetadataService
from src.db.validation import validate_query
from src.logging_config import get_logger
from src.models.schema import (
    Query,
    QueryType,
    SampleData,
    SamplingMethod,
)
from src.type_registry import convert

logger = get_logger(__name__)


class QueryService:
    """Service for executing queries and sampling data.

    Handles sample data retrieval with multiple sampling strategies,
    binary/text truncation, and proper formatting of results.

    Attributes:
        engine: SQLAlchemy engine for database connection
    """

    def __init__(self, engine: Engine, metadata_service: MetadataService | None = None):
        """Initialize query service.

        Args:
            engine: SQLAlchemy engine
            metadata_service: Optional MetadataService for metadata-based
                identifier validation. When None, falls back to regex validation.
        """
        self.engine = engine
        self._metadata_service = metadata_service

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
            sanitized_columns = self._get_validated_columns(columns, table_name, schema_name)
            column_sql = ", ".join(sanitized_columns)

        # Build query based on sampling method
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite doesn't use schema prefixes in the same way
            full_table_name = table_name
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
        actual_method = sampling_method

        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(query))
                self._process_rows(result, rows, truncated_columns)

                # TABLESAMPLE can return 0 rows on large tables with small sample sizes
                # because SQL Server samples at the 8KB page level, not individual rows.
                # Fall back to TOP when this happens.
                if not rows and sampling_method == SamplingMethod.TABLESAMPLE:
                    logger.warning(
                        f"TABLESAMPLE returned 0 rows for {schema_name}.{table_name} "
                        f"with sample_size={sample_size}; falling back to TOP"
                    )
                    fallback_query = self._build_top_query(full_table_name, column_sql, sample_size)
                    fallback_result = conn.execute(text(fallback_query))
                    actual_method = SamplingMethod.TOP
                    self._process_rows(fallback_result, rows, truncated_columns)

        except SQLAlchemyError as e:
            logger.error(f"Error sampling data from {schema_name}.{table_name}: {type(e).__name__}: {e}")
            raise

        # Create sample ID
        table_id = f"{schema_name}.{table_name}"
        timestamp = datetime.now().isoformat()
        sample_id = hashlib.sha256(f"{table_id}_{timestamp}".encode()).hexdigest()[:12]

        return SampleData(
            sample_id=sample_id,
            table_id=table_id,
            sample_size=len(rows),
            sampling_method=actual_method,
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

        Uses ROW_NUMBER to assign sequential numbers, then selects rows
        where row_number % interval = 0 to get evenly spaced samples.
        This is deterministic and repeatable for the same data.

        Args:
            table_name: Fully qualified table name
            column_sql: Column selection SQL
            sample_size: Number of rows

        Returns:
            SQL query string
        """
        dialect_name = self.engine.dialect.name

        if dialect_name == "sqlite":
            # SQLite: use ROWID for deterministic evenly-spaced sampling
            return f"""
            SELECT {column_sql} FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY ROWID) AS _rn,
                       COUNT(*) OVER () AS _total
                FROM {table_name}
            ) _sampled
            WHERE _rn % MAX((_total / {sample_size}), 1) = 0
            LIMIT {sample_size}
            """
        else:
            # SQL Server: use ROW_NUMBER with modulo for evenly-spaced sampling
            return f"""
            SELECT TOP ({sample_size}) {column_sql} FROM (
                SELECT *, ROW_NUMBER() OVER (ORDER BY (SELECT NULL)) AS _rn,
                       COUNT(*) OVER () AS _total
                FROM {table_name}
            ) _sampled
            WHERE _rn % CASE WHEN _total / {sample_size} < 1 THEN 1 ELSE _total / {sample_size} END = 0
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

    def _validate_identifier(self, identifier: str, valid_names: list[str], context: str) -> str:
        """Validate an identifier against a list of known valid names.

        Uses case-insensitive comparison matching SQL Server default collation.
        Returns the actual-cased name from metadata, bracket-quoted for SQL Server.

        Args:
            identifier: User-supplied column name to validate
            valid_names: List of valid column names from metadata
            context: Table context for error messages (e.g. "[dbo].[Users]")

        Returns:
            Bracket-quoted (SQL Server) or bare (SQLite) validated identifier

        Raises:
            ValueError: If identifier does not match any valid name
        """
        lookup = {name.lower(): name for name in valid_names}
        actual_name = lookup.get(identifier.lower())
        if actual_name is None:
            raise ValueError(f"Column '{identifier}' does not exist in {context}")

        dialect_name = self.engine.dialect.name
        if dialect_name == "sqlite":
            return actual_name
        return f"[{actual_name}]"

    def _get_validated_columns(
        self, columns: list[str], table_name: str, schema_name: str
    ) -> list[str]:
        """Validate and quote column names, using metadata when available.

        When a MetadataService is injected, validates columns against actual
        database metadata. Falls back to regex-based sanitization when
        metadata_service is None or metadata lookup returns no columns.

        Args:
            columns: User-supplied column names
            table_name: Table name for metadata lookup
            schema_name: Schema name for metadata lookup

        Returns:
            List of validated, bracket-quoted column names
        """
        if self._metadata_service is None:
            return [self._sanitize_identifier(col) for col in columns]

        meta_columns = self._metadata_service.get_columns(table_name, schema_name)
        if not meta_columns:
            logger.warning(
                f"Metadata returned no columns for {schema_name}.{table_name}; "
                f"falling back to regex validation"
            )
            return [self._sanitize_identifier(col) for col in columns]

        valid_names = [c.column_name for c in meta_columns]
        context = f"[{schema_name}].[{table_name}]"
        return [self._validate_identifier(col, valid_names, context) for col in columns]

    def _process_rows(
        self,
        result,
        rows: list[dict[str, Any]],
        truncated_columns: list[str],
    ) -> None:
        """Process result rows, applying truncation and appending to rows list.

        Args:
            result: SQLAlchemy result proxy
            rows: List to append processed row dicts to (mutated in place)
            truncated_columns: List to track truncated columns (mutated in place)
        """
        for row in result:
            row_dict = {}
            for column_name, value in row._mapping.items():
                truncated_value, was_truncated = convert(value, get_config().defaults.text_truncation_limit)
                row_dict[column_name] = truncated_value
                if was_truncated and column_name not in truncated_columns:
                    truncated_columns.append(column_name)
            rows.append(row_dict)

    # =========================================================================
    # Query Execution Methods (User Story 7)
    # =========================================================================

    def parse_query_type(self, query_text: str) -> QueryType:
        """Parse the type of SQL query from the query text using sqlglot AST.

        Args:
            query_text: SQL query string

        Returns:
            QueryType enum value (SELECT, INSERT, UPDATE, DELETE, or OTHER)
        """
        if not query_text or not query_text.strip():
            return QueryType.OTHER

        try:
            statements = sqlglot.parse(query_text, dialect="tsql")
        except sqlglot.errors.ParseError:
            return QueryType.OTHER

        if not statements or statements[0] is None:
            return QueryType.OTHER

        stmt = statements[0]
        ast_type_map: dict[type[exp.Expression], QueryType] = {
            exp.Select: QueryType.SELECT,
            exp.Insert: QueryType.INSERT,
            exp.Update: QueryType.UPDATE,
            exp.Delete: QueryType.DELETE,
        }

        for ast_type, query_type in ast_type_map.items():
            if isinstance(stmt, ast_type):
                return query_type

        # Union/Intersect/Except are query types that return data like SELECT
        if isinstance(stmt, exp.SetOperation):
            return QueryType.SELECT

        return QueryType.OTHER

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

    def inject_row_limit(self, query_text: str, row_limit: int) -> str:
        """Inject a row limit (TOP clause for SQL Server) into a SELECT query.

        Handles both regular SELECT queries and CTE queries (WITH...SELECT).

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
        cleaned_upper = cleaned.upper()

        # Check if it's a SELECT query or CTE+SELECT query
        is_direct_select = cleaned_upper.startswith("SELECT")
        is_cte_select = (
            cleaned_upper.startswith("WITH")
            and self.parse_query_type(cleaned) == QueryType.SELECT
        )

        if not is_direct_select and not is_cte_select:
            return query_text

        dialect_name = self.engine.dialect.name

        # SQLite: Add LIMIT clause if not present
        if dialect_name == "sqlite":
            if " LIMIT " not in query_text.upper():
                return f"{query_text} LIMIT {row_limit}"
            return query_text

        # SQL Server: Return early if TOP already exists
        if re.search(r'\bTOP\s*\(?\s*\d+\s*\)?', query_text, re.IGNORECASE):
            return query_text

        # For CTE queries, find the final SELECT and inject TOP there
        if is_cte_select:
            return self._inject_top_in_cte(cleaned, row_limit)

        # Regular SELECT: Inject TOP after SELECT
        # Handle SELECT DISTINCT, SELECT ALL, etc.
        select_pattern = re.compile(
            r'^(SELECT\s+(?:DISTINCT\s+|ALL\s+)?)',
            re.IGNORECASE
        )

        match = select_pattern.match(cleaned)
        if match:
            prefix = match.group(1)
            rest = cleaned[len(prefix):]
            return f"{prefix}TOP ({row_limit}) {rest}"

        return query_text

    def _inject_top_in_cte(self, cleaned_query: str, row_limit: int) -> str:
        """Inject TOP clause into the final SELECT of a CTE query.

        Args:
            cleaned_query: CTE query with comments already removed
            row_limit: Maximum rows to return

        Returns:
            Query with TOP injected into the final SELECT
        """
        # Find the position of the final SELECT (after all CTE definitions)
        paren_depth = 0
        i = 0
        query_upper = cleaned_query.upper()

        # Skip past "WITH" keyword
        i = query_upper.find("WITH") + 4

        while i < len(cleaned_query):
            char = cleaned_query[i]
            if char == '(':
                paren_depth += 1
            elif char == ')':
                paren_depth -= 1
            elif paren_depth == 0:
                # Outside all parentheses - look for SELECT keyword
                remaining_upper = query_upper[i:].lstrip()
                if remaining_upper.startswith("SELECT"):
                    # Find the actual position in the original string
                    whitespace_len = len(query_upper[i:]) - len(query_upper[i:].lstrip())
                    select_start = i + whitespace_len

                    # Handle SELECT DISTINCT, SELECT ALL, etc.
                    select_pattern = re.compile(
                        r'^(SELECT\s+(?:DISTINCT\s+|ALL\s+)?)',
                        re.IGNORECASE
                    )
                    match = select_pattern.match(cleaned_query[select_start:])
                    if match:
                        prefix_part = cleaned_query[:select_start]
                        select_prefix = match.group(1)
                        rest = cleaned_query[select_start + len(select_prefix):]
                        return f"{prefix_part}{select_prefix}TOP ({row_limit}) {rest}"
            i += 1

        return cleaned_query

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
        if not query_text or not query_text.strip():
            raise ValueError("query_text is required and cannot be empty")

        if row_limit < 1 or row_limit > 10000:
            raise ValueError("row_limit must be between 1 and 10000")

        query_id = str(uuid.uuid4())
        validation = validate_query(query_text, allow_write=allow_write)
        query_type = self.parse_query_type(query_text)

        if not validation.is_safe:
            return self._build_blocked_query(
                query_id, connection_id, query_text, query_type, row_limit, validation.reasons
            )

        executed_query = (
            self.inject_row_limit(query_text, row_limit)
            if query_type == QueryType.SELECT
            else query_text
        )

        start_time = time.perf_counter()
        columns, rows, rows_affected, error_message, total_rows_available = (
            self._run_query(executed_query, query_type, query_text, row_limit)
        )
        execution_time_ms = int((time.perf_counter() - start_time) * 1000)

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

        # Store result data in proper dataclass fields
        query.columns = columns
        query.rows = rows
        query.total_rows_available = total_rows_available

        return query

    def _build_blocked_query(
        self,
        query_id: str,
        connection_id: str,
        query_text: str,
        query_type: QueryType,
        row_limit: int,
        reasons: list,
    ) -> Query:
        """Build a Query object for a blocked (unsafe) query.

        Args:
            query_id: Unique query identifier
            connection_id: Connection ID
            query_text: Original SQL query text
            query_type: Parsed query type
            row_limit: Requested row limit
            reasons: List of denial reasons from validation

        Returns:
            Query object marked as not allowed
        """
        reason_strs = [f"{r.category.value.upper()} - {r.detail}" for r in reasons]
        error_message = f"Query blocked: {'; '.join(reason_strs)}"
        return Query(
            query_id=query_id,
            connection_id=connection_id,
            query_text=query_text,
            query_type=query_type,
            is_allowed=False,
            row_limit=row_limit,
            error_message=error_message,
            denial_reasons=reasons,
        )

    def _run_query(
        self,
        executed_query: str,
        query_type: QueryType,
        original_query: str,
        row_limit: int,
    ) -> tuple[list[str], list[dict[str, Any]], int, str | None, int | None]:
        """Execute a query and return raw results.

        Args:
            executed_query: SQL query to execute (may have row limit injected)
            query_type: Parsed query type
            original_query: Original query text (used for count query)
            row_limit: Requested row limit

        Returns:
            Tuple of (columns, rows, rows_affected, error_message, total_rows_available)
        """
        try:
            with self.engine.connect() as conn:
                result = conn.execute(text(executed_query))

                if query_type == QueryType.SELECT:
                    return self._process_select_results(result, conn, original_query, row_limit)

                rows_affected = result.rowcount if result.rowcount >= 0 else 0
                conn.commit()
                return [], [], rows_affected, None, None

        except SQLAlchemyError as e:
            error_message = f"Query execution failed: {type(e).__name__}: {str(e)}"
            logger.error(f"Query execution error: {e}")
            return [], [], 0, error_message, None

    def _process_select_results(
        self,
        result,
        conn,
        original_query: str,
        row_limit: int,
    ) -> tuple[list[str], list[dict[str, Any]], int, str | None, int | None]:
        """Process results from a SELECT query.

        Fetches rows, applies value truncation, and optionally queries total row count.

        Args:
            result: SQLAlchemy result proxy
            conn: Active database connection
            original_query: Original query text (used for count query)
            row_limit: Requested row limit

        Returns:
            Tuple of (columns, rows, rows_affected, error_message, total_rows_available)
        """
        columns = list(result.keys())
        fetched_rows = result.fetchall()

        rows = []
        for row in fetched_rows:
            row_dict = {}
            for col_name, value in zip(columns, row, strict=True):
                truncated_value, _ = convert(value, get_config().defaults.text_truncation_limit)
                row_dict[col_name] = truncated_value
            rows.append(row_dict)

        total_rows_available = self._get_total_row_count(conn, original_query, row_limit, len(rows))

        return columns, rows, len(fetched_rows), None, total_rows_available

    def _get_total_row_count(
        self,
        conn,
        original_query: str,
        row_limit: int,
        fetched_count: int,
    ) -> int | None:
        """Get total row count when results hit the row limit.

        Args:
            conn: Active database connection
            original_query: Original query text
            row_limit: Requested row limit
            fetched_count: Number of rows actually fetched

        Returns:
            Total row count, or None if not applicable or count fails
        """
        if fetched_count != row_limit:
            return None

        count_query = self._build_count_query(original_query)
        if not count_query:
            return None

        try:
            count_result = conn.execute(text(count_query))
            count_value = count_result.scalar()
            if isinstance(count_value, int):
                return count_value
        except SQLAlchemyError:
            pass

        return None

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
        return f"SELECT COUNT(*) FROM ({cleaned}) AS count_subquery"

    def get_query_results(self, query: Query) -> dict[str, Any]:
        """Get the result data from an executed query.

        Args:
            query: Query object from execute_query

        Returns:
            Dict with columns, rows, and metadata
        """
        columns = query.columns
        rows = query.rows
        total_rows_available = query.total_rows_available

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
