"""Shared SQL transpilation utilities for analysis modules."""

from typing import TYPE_CHECKING

import sqlglot
from sqlalchemy import text

if TYPE_CHECKING:
    from sqlalchemy.engine import Connection

    from src.db.dialects.protocol import DialectStrategy


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

        return [row[1] if len(row) > 1 else row[0] for row in rows]
