"""Shared SQL transpilation utilities for analysis modules."""

from typing import TYPE_CHECKING

import sqlglot

if TYPE_CHECKING:
    from src.db.dialects.protocol import DialectStrategy


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
