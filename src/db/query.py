"""Query execution service for sample data retrieval and ad-hoc queries.

This module provides methods for executing queries, sampling table data,
and handling data truncation for large or binary values.
"""

import hashlib
import re
import time
import uuid
from datetime import date, datetime
from datetime import time as dt_time
from decimal import Decimal
from typing import Any

import sqlglot
from sqlalchemy import text
from sqlalchemy.engine import Engine
from sqlglot import exp

from src.logging_config import get_logger
from src.models.schema import (
    DenialCategory,
    DenialReason,
    Query,
    QueryType,
    SampleData,
    SamplingMethod,
    ValidationResult,
)

# AST expression types mapped to denial categories
DENIED_TYPES: dict[type[exp.Expression], DenialCategory] = {
    # DML
    exp.Insert: DenialCategory.DML,
    exp.Update: DenialCategory.DML,
    exp.Delete: DenialCategory.DML,
    exp.Merge: DenialCategory.DML,
    # DDL
    exp.Create: DenialCategory.DDL,
    exp.Alter: DenialCategory.DDL,
    exp.Drop: DenialCategory.DDL,
    exp.TruncateTable: DenialCategory.DDL,
    # DCL
    exp.Grant: DenialCategory.DCL,
    # Operational
    exp.Command: DenialCategory.OPERATIONAL,
}

# 22 known-safe SQL Server system stored procedures (lowercase, unqualified)
SAFE_PROCEDURES: frozenset[str] = frozenset({
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

logger = get_logger(__name__)

# Types that indicate a garbage parse (not real SQL statements)
_GARBAGE_PARSE_TYPES = (exp.Alias, exp.Column, exp.Identifier, exp.Literal)


def validate_query(sql: str, allow_write: bool = False) -> ValidationResult:
    """Validate a SQL query against the AST-based denylist.

    Pure function — no side effects, no database connection required.

    Args:
        sql: Raw SQL text
        allow_write: If True, DML operations (INSERT/UPDATE/DELETE/MERGE) are allowed

    Returns:
        ValidationResult with is_safe and categorized denial reasons
    """
    if not sql or not sql.strip():
        return ValidationResult(
            is_safe=False,
            reasons=[DenialReason(DenialCategory.PARSE_FAILURE, "Empty or whitespace-only query", 0)],
        )

    try:
        statements = sqlglot.parse(sql, dialect="tsql")
    except sqlglot.errors.ParseError as e:
        return ValidationResult(
            is_safe=False,
            reasons=[DenialReason(DenialCategory.PARSE_FAILURE, str(e), 0)],
        )

    if not statements or all(s is None for s in statements):
        return ValidationResult(
            is_safe=False,
            reasons=[DenialReason(DenialCategory.PARSE_FAILURE, "No statements parsed", 0)],
        )

    reasons: list[DenialReason] = []
    for idx, stmt in enumerate(statements):
        if stmt is None:
            continue
        reasons.extend(_classify_statement(stmt, idx))

    # allow_write bypass: remove DML and CTE-wrapped write denials
    if allow_write:
        reasons = [r for r in reasons if r.category not in (DenialCategory.DML, DenialCategory.CTE_WRAPPED_WRITE)]

    return ValidationResult(is_safe=len(reasons) == 0, reasons=reasons)


def _classify_statement(stmt: exp.Expression, idx: int) -> list[DenialReason]:
    """Classify a single parsed statement and return denial reasons (if any)."""
    # Garbage parse detection (e.g., DBCC → Alias)
    if isinstance(stmt, _GARBAGE_PARSE_TYPES):
        return [DenialReason(DenialCategory.PARSE_FAILURE, "Unrecognized statement", idx)]

    # Command: EXEC/EXECUTE → stored procedure check; others → Operational
    # Must be checked before DENIED_TYPES since Command is in that map
    if isinstance(stmt, exp.Command):
        return _check_command(stmt, idx)

    # Kill → Operational (not in DENIED_TYPES to avoid confusion with Command handling)
    if isinstance(stmt, exp.Kill):
        return [DenialReason(DenialCategory.OPERATIONAL, "KILL operations are not permitted", idx)]

    # Check against denied types map
    for denied_type, category in DENIED_TYPES.items():
        if isinstance(stmt, denied_type):
            # CTE-wrapped write: DML with a WITH clause
            if category == DenialCategory.DML and stmt.find(exp.With):
                return [DenialReason(
                    DenialCategory.CTE_WRAPPED_WRITE,
                    f"CTE-wrapped {type(stmt).__name__.upper()} operations are not permitted",
                    idx,
                )]
            detail = f"{type(stmt).__name__.upper()} operations are not permitted"
            return [DenialReason(category, detail, idx)]

    # Select: check for INTO (creates a table)
    if isinstance(stmt, exp.Select) and stmt.find(exp.Into):
        return [DenialReason(DenialCategory.SELECT_INTO, "SELECT INTO creates a new table and is not permitted", idx)]

    return []


def _check_command(stmt: exp.Command, idx: int) -> list[DenialReason]:
    """Check a Command node (EXEC/EXECUTE or other unrecognized command)."""
    cmd_name = str(stmt.this).upper() if stmt.this else ""
    if cmd_name in ("EXEC", "EXECUTE"):
        return _check_stored_procedure(stmt, idx)
    return [DenialReason(DenialCategory.OPERATIONAL, f"{cmd_name} operations are not permitted", idx)]


def _check_stored_procedure(stmt: exp.Command, idx: int) -> list[DenialReason]:
    """Check if a stored procedure call is in the safe allowlist."""
    # Extract procedure name from the expression arg
    proc_expr = stmt.args.get("expression")
    proc_name = str(proc_expr.this) if proc_expr else ""
    # For multi-part names (master.dbo.sp_help), take the last part
    canonical = proc_name.rsplit(".", 1)[-1].lower()

    if canonical == "sp_executesql":
        return [DenialReason(
            DenialCategory.STORED_PROCEDURE,
            "sp_executesql is explicitly denied (executes arbitrary SQL)",
            idx,
        )]

    if canonical in SAFE_PROCEDURES:
        return []

    return [DenialReason(
        DenialCategory.STORED_PROCEDURE,
        f"Stored procedure '{proc_name}' is not in the safe allowlist",
        idx,
    )]


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
        actual_method = sampling_method

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
                    for row in fallback_result:
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

        # Handle datetime/date/time types (not JSON serializable)
        if isinstance(value, datetime):
            return value.isoformat(), False
        if isinstance(value, date):
            return value.isoformat(), False
        if isinstance(value, dt_time):
            return value.isoformat(), False

        # Handle Decimal (not JSON serializable)
        if isinstance(value, Decimal):
            return float(value), False

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

        if dialect_name == "sqlite":
            # SQLite: Add LIMIT clause if not present
            if " LIMIT " not in query_text.upper():
                return f"{query_text} LIMIT {row_limit}"
            return query_text
        else:
            # SQL Server: Inject TOP clause after the final SELECT
            # Check if TOP already exists
            if re.search(r'\bTOP\s*\(?\s*\d+\s*\)?', query_text, re.IGNORECASE):
                return query_text

            if is_cte_select:
                # For CTE queries, find the final SELECT and inject TOP there
                return self._inject_top_in_cte(cleaned, row_limit)
            else:
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
        # Validate parameters
        if not query_text or not query_text.strip():
            raise ValueError("query_text is required and cannot be empty")

        if row_limit < 1 or row_limit > 10000:
            raise ValueError("row_limit must be between 1 and 10000")

        # Generate query ID
        query_id = str(uuid.uuid4())

        # AST-based validation (replaces keyword blocklist + type-based allow/deny)
        validation = validate_query(query_text, allow_write=allow_write)
        query_type = self.parse_query_type(query_text)

        if not validation.is_safe:
            # Build human-readable error message from denial reasons
            reason_strs = [f"{r.category.value.upper()} - {r.detail}" for r in validation.reasons]
            error_message = f"Query blocked: {'; '.join(reason_strs)}"
            return Query(
                query_id=query_id,
                connection_id=connection_id,
                query_text=query_text,
                query_type=query_type,
                is_allowed=False,
                row_limit=row_limit,
                error_message=error_message,
                denial_reasons=validation.reasons,
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
