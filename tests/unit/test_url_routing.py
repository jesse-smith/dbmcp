"""Tests for URL-scheme-to-dialect routing via resolve_dialect_from_url."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from src.db.dialects.generic import GenericDialect
from src.db.dialects.mssql import MssqlDialect
from src.db.dialects.registry import resolve_dialect_from_url


class TestKnownSchemeRouting:
    """Known URL schemes route to registered dialect classes."""

    def test_mssql_pyodbc_url(self):
        dialect = resolve_dialect_from_url("mssql+pyodbc://server/db")
        assert isinstance(dialect, MssqlDialect)

    def test_mssql_bare_url(self):
        dialect = resolve_dialect_from_url("mssql://server/db")
        assert isinstance(dialect, MssqlDialect)


class TestGenericFallbackRouting:
    """Unknown or generic schemes route to GenericDialect."""

    def test_postgresql_url(self):
        dialect = resolve_dialect_from_url("postgresql://host/db")
        assert isinstance(dialect, GenericDialect)
        assert dialect.sqlglot_dialect == "postgres"

    def test_mysql_pymysql_url(self):
        dialect = resolve_dialect_from_url("mysql+pymysql://host/db")
        assert isinstance(dialect, GenericDialect)
        assert dialect.sqlglot_dialect == "mysql"

    def test_sqlite_url(self):
        dialect = resolve_dialect_from_url("sqlite:///test.db")
        assert isinstance(dialect, GenericDialect)
        assert dialect.sqlglot_dialect == "sqlite"

    def test_oracle_url_generic_fallback(self):
        dialect = resolve_dialect_from_url("oracle+cx_oracle://host/db")
        assert isinstance(dialect, GenericDialect)
        assert dialect.sqlglot_dialect is None

    def test_unknown_scheme_warning(self):
        """Unknown schemes emit a warning log."""
        with patch("src.db.dialects.registry.logger") as mock_logger:
            dialect = resolve_dialect_from_url("oracle+cx_oracle://host/db")
        assert isinstance(dialect, GenericDialect)
        mock_logger.warning.assert_called_once()
        warning_msg = mock_logger.warning.call_args[0][0] % mock_logger.warning.call_args[0][1:]
        assert "No optimized dialect for 'oracle'" in warning_msg


class TestDatabricksSchemeMapping:
    """Databricks maps to a registered dialect name (class not yet implemented)."""

    def test_databricks_scheme_in_mapping(self):
        """Databricks is in the URL scheme mapping (will raise ValueError until dialect is registered)."""
        from src.db.dialects.registry import _URL_SCHEME_TO_DIALECT

        assert "databricks" in _URL_SCHEME_TO_DIALECT
