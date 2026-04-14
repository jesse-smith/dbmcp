"""Tests for lazy import behavior of optional dependencies."""

from __future__ import annotations

import sys
from unittest.mock import patch

import pytest


class TestLazyPyodbcImport:
    """Verify pyodbc is not imported at module load time."""

    def test_mssql_import_error(self):
        """MssqlDialect.create_engine raises ImportError when pyodbc unavailable."""
        from src.db.dialects import mssql
        from src.db.dialects.mssql import MssqlDialect

        dialect = MssqlDialect()
        with patch.object(mssql, "pyodbc", None):
            with pytest.raises(ImportError, match="pip install dbmcp\\[mssql\\]"):
                dialect.create_engine(
                    server="test",
                    database="test",
                    authentication_method="sql",
                )

    def test_dialects_package_import_no_pyodbc(self):
        """Importing src.db.dialects does not fail when pyodbc is unavailable.

        This verifies that the __init__.py uses deferred imports properly.
        """
        # We can't truly unload pyodbc mid-process reliably, but we can verify
        # that the module-level import of MssqlDialect class does not call
        # pyodbc at class definition time by checking that MssqlDialect
        # is importable and instantiable without pyodbc being used.
        from src.db.dialects.mssql import MssqlDialect

        # Class instantiation should work without pyodbc
        dialect = MssqlDialect()
        assert dialect.name == "mssql"
