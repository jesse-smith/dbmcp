"""Shared SQL transpilation utilities for analysis modules."""

from typing import TYPE_CHECKING

import sqlglot
from sqlalchemy import text
from sqlalchemy import types as sa_types

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from src.db.dialects.protocol import DialectStrategy


# Cross-dialect type-name sets for the string-classification path. Names are
# matched after lowercasing and stripping any ``(...)`` parameter suffix, so
# ``DECIMAL(10,2)`` -> ``decimal`` and ``VARCHAR(50)`` -> ``varchar``. Covers
# MSSQL (INFORMATION_SCHEMA names), Databricks (STRING/DOUBLE/TIMESTAMP/LONG),
# and SQLAlchemy ``str(type)`` reprs so the FK type-compat filter classifies
# every dialect it can hit (UE-01), not just MSSQL.
_NUMERIC_TYPES_STR = frozenset({
    # MSSQL
    "int", "bigint", "smallint", "tinyint", "decimal", "numeric",
    "float", "real", "money", "smallmoney",
    # Databricks / generic / SQLAlchemy reprs
    "integer", "double", "double precision", "long", "byte", "short",
})
_DATETIME_TYPES_STR = frozenset({
    # MSSQL
    "date", "datetime", "datetime2", "smalldatetime", "datetimeoffset", "time",
    # Databricks / generic
    "timestamp", "timestamp_ntz",
})
_STRING_TYPES_STR = frozenset({
    # MSSQL
    "char", "varchar", "text", "nchar", "nvarchar", "ntext",
    # Databricks / generic
    "string", "character varying", "character",
})


def type_category(data_type: "sa_types.TypeEngine | str") -> str:
    """Classify a type into a coarse analysis category.

    Returns one of ``"numeric"``, ``"datetime"``, ``"string"``, or ``"other"``.

    Accepts either a SQLAlchemy ``TypeEngine`` (isinstance-based, dialect-neutral)
    or a raw dialect type string (set-based, normalized for case and ``(...)``
    parameters). Used by column statistics (which branch fires depends on whether
    an Inspector resolved a ``TypeEngine``) and by the FK candidate search, where
    a category mismatch with neither side ``"other"`` proves a non-FK pairing and
    is skipped before the overlap INTERSECT runs (UE-01).

    Args:
        data_type: A SQLAlchemy type object or a dialect type-name string.

    Returns:
        The coarse category string.
    """
    if isinstance(data_type, sa_types.TypeEngine):
        if isinstance(data_type, (sa_types.Integer, sa_types.Numeric, sa_types.Float)):
            return "numeric"
        # MSSQL MONEY/SMALLMONEY don't inherit from Numeric.
        type_name = type(data_type).__name__.upper()
        if type_name in ("MONEY", "SMALLMONEY"):
            return "numeric"
        if isinstance(data_type, (sa_types.DateTime, sa_types.Date, sa_types.Time)):
            return "datetime"
        if isinstance(data_type, (sa_types.String, sa_types.Text)):
            return "string"
        return "other"

    # String path: lowercase and strip any "(...)" parameter suffix.
    normalized = data_type.split("(", 1)[0].strip().lower()
    if normalized in _NUMERIC_TYPES_STR:
        return "numeric"
    if normalized in _DATETIME_TYPES_STR:
        return "datetime"
    if normalized in _STRING_TYPES_STR:
        return "string"
    return "other"


def quote_tsql_identifier(identifier: str) -> str:
    """Quote an identifier as a TSQL bracket token, escaping ``]``.

    Analysis SQL is authored in TSQL syntax (bracket-quoted identifiers) and
    then run through :func:`transpile_query` (``read="tsql"``). An untrusted
    catalog/schema/table/column value containing ``]`` would otherwise close
    the bracket early and inject arbitrary SQL during sqlglot's parse stage.
    Doubling ``]`` -> ``]]`` keeps the value contained within a single token
    (mirrors ``MSSQLDialect.quote_identifier``). On the MSSQL default path,
    where ``transpile_query`` is a passthrough, this is the same escaping the
    server expects.

    Args:
        identifier: A raw identifier segment (catalog, schema, table, column).

    Returns:
        The identifier wrapped in ``[...]`` with embedded ``]`` doubled.
    """
    return f"[{identifier.replace(']', ']]')}]"


def transpile_query(sql: str, dialect: "DialectStrategy | None") -> str:
    """Transpile TSQL-syntax SQL to target dialect.

    Base queries are written in TSQL syntax (matching existing MSSQL code).
    When dialect is None or dialect.sqlglot_dialect == 'tsql', returns
    the original SQL unchanged. Otherwise transpiles via sqlglot.

    Args:
        sql: SQL string in TSQL syntax (bracket-quoted identifiers OK).
        dialect: Target dialect strategy, or None for MSSQL default.

    Returns:
        SQL string in target dialect syntax.
    """
    if dialect is None or dialect.sqlglot_dialect == "tsql":
        return sql
    result = sqlglot.transpile(sql, read="tsql", write=dialect.sqlglot_dialect)
    return result[0]


class CatalogAwareReflector:
    """Catalog-scoped raw-SQL reflection over a live connection.

    Consolidates the catalog-aware DESCRIBE TABLE / SHOW TABLES pattern that
    was duplicated in ``MetadataService._get_databricks_columns`` and
    ``MetadataService._list_tables_databricks`` (RESEARCH Open Q2 — 4th
    occurrence, Rule of Three crossed). The key difference from
    MetadataService: this reflector operates over the *live* connection each
    analysis class already holds (it does NOT open a fresh ``engine.connect()``).

    Security: every identifier segment is quoted via ``dialect.quote_identifier``
    before concatenation, so untrusted catalog/schema/table values cannot break
    out of the backtick-quoted three-part name (T-15.1-01).

    Statelessness: the reflector emits only fully-qualified names and never
    mutates the session's active catalog, so it is safe to use over a pooled
    connection whose catalog is shared with other callers (T-15.1-02).
    """

    def __init__(self, connection: "Connection", dialect: "DialectStrategy") -> None:
        """Bind to a live connection and a dialect strategy.

        Args:
            connection: A live SQLAlchemy ``Connection`` owned by the caller.
            dialect: The dialect strategy providing ``quote_identifier``.
        """
        self.connection = connection
        self.dialect = dialect

    def reflect_columns(
        self, catalog: str, schema: str, table: str
    ) -> list[dict]:
        """Return columns for ``catalog.schema.table`` via DESCRIBE TABLE.

        Builds an injection-safe three-part name and parses the DESCRIBE output
        with the same contract as ``MetadataService._get_databricks_columns``:
        ``col_name = row[0]``, ``data_type = row[1]``, stopping at the first
        blank column name or any section marker (a name starting with ``#``).

        Args:
            catalog: Catalog name (threaded into the SQL — IDENT-08).
            schema: Schema (database) name.
            table: Table name.

        Returns:
            A list of ``{"name": col_name, "data_type": data_type}`` dicts.
        """
        qi = self.dialect.quote_identifier
        qualified = f"{qi(catalog)}.{qi(schema)}.{qi(table)}"
        result = self.connection.execute(text(f"DESCRIBE TABLE {qualified}"))
        rows = result.fetchall()

        columns: list[dict] = []
        for row in rows:
            col_name = (row[0] or "").strip()
            data_type = (row[1] or "").strip() if len(row) > 1 else ""

            # Stop at blank separator or any section marker (starts with "#").
            if not col_name or col_name.startswith("#"):
                break

            columns.append({"name": col_name, "data_type": data_type})

        return columns

    def reflect_column_nullability(
        self, catalog: str, schema: str, table: str
    ) -> dict[str, bool]:
        """Return a ``column_name -> is_nullable`` map for ``catalog.schema.table``.

        DESCRIBE TABLE (used by :meth:`reflect_columns`) does not expose
        nullability, so it is sourced from ``{catalog}.information_schema.columns``
        instead -- which is queryable cross-catalog without a ``USE CATALOG``
        statement. The catalog is an *identifier* (quoted via
        ``dialect.quote_identifier``, which escapes embedded backticks per CR-01);
        the schema and table are *string literals* in the WHERE clause and are
        therefore bound as ``:schema_name`` / ``:table_name`` params, never
        interpolated (T-WR03-01). No ``USE CATALOG`` is emitted, so the query is
        stateless over the pooled connection (T-WR03-02).

        Args:
            catalog: Catalog name (quoted identifier — IDENT-08).
            schema: Schema (database) name (bound as a param).
            table: Table name (bound as a param).

        Returns:
            A dict mapping ``column_name`` to ``is_nullable`` (``True`` when the
            reflected ``is_nullable`` string equals ``"YES"`` after trim + upper).
        """
        qi = self.dialect.quote_identifier
        info_schema = f"{qi(catalog)}.information_schema"
        query = text(
            f"SELECT column_name, is_nullable FROM {info_schema}.columns "
            "WHERE table_schema = :schema_name AND table_name = :table_name"
        )
        result = self.connection.execute(
            query, {"schema_name": schema, "table_name": table}
        )
        return {
            row[0]: (str(row[1]).strip().upper() == "YES")
            for row in result.fetchall()
        }

    def list_tables(self, catalog: str, schema: str) -> list[str]:
        """Return table names in ``catalog.schema`` via SHOW TABLES IN.

        Builds an injection-safe two-part name and extracts the table name from
        each row (SHOW TABLES returns ``(database, tableName, isTemporary)`` so
        ``row[1]`` is the table name), matching
        ``MetadataService._list_tables_databricks``.

        Args:
            catalog: Catalog name (threaded into the SQL — IDENT-08).
            schema: Schema (database) name.

        Returns:
            A list of table-name strings.
        """
        qi = self.dialect.quote_identifier
        qualified = f"{qi(catalog)}.{qi(schema)}"
        result = self.connection.execute(text(f"SHOW TABLES IN {qualified}"))
        rows = result.fetchall()

        # IN-01: SHOW TABLES returns (database, tableName, isTemporary); the
        # table name is row[1]. Fail fast on any row lacking that column rather
        # than silently falling back to row[0] (a *database* name) — that
        # fallback masked a contract violation the docstring says never occurs.
        table_names: list[str] = []
        for row in rows:
            if len(row) < 2:
                raise ValueError(
                    "SHOW TABLES returned an unexpected row shape "
                    f"(width {len(row)}): expected (database, tableName, "
                    f"isTemporary). Row: {row!r}"
                )
            table_names.append(row[1])
        return table_names
