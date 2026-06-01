"""Unit tests for analysis_tools module-level helpers.

The v2.1 complexity refactor extracted the existence/reflection error branches
out of the three analysis tools into shared helpers. Their not-found paths were
previously only exercised by ``tests/integration/`` (skipif-gated on
``TEST_DB_SERVER`` and deselected from the CI coverage run), so they showed as
uncovered patch lines on codecov. These mock-driven unit tests cover those
branches in the CI ``not integration and not slow`` selection — no live DB.
"""

from unittest.mock import MagicMock, patch

# Import server first to fully initialize the module graph and resolve the
# analysis_tools <-> server circular import before reaching for the private
# helpers (mirrors the pattern in test_async_tools.py).
import src.mcp_server.server  # noqa: E402, F401
from src.db.identifiers import ResolvedIdentifier
from src.mcp_server.analysis_tools import (  # noqa: E402
    _check_table_exists,
    _is_cross_catalog,
    _reflect_source_column,
)


class TestIsCrossCatalog:
    """_is_cross_catalog: only an explicit catalog on Databricks is cross-catalog."""

    def test_databricks_with_catalog_is_cross_catalog(self):
        resolved = ResolvedIdentifier(catalog="analytics", schema="sales", table="t")
        dialect = MagicMock()
        dialect.name = "databricks"
        assert _is_cross_catalog(resolved, dialect) is True

    def test_databricks_without_catalog_is_not_cross_catalog(self):
        resolved = ResolvedIdentifier(catalog=None, schema="sales", table="t")
        dialect = MagicMock()
        dialect.name = "databricks"
        assert _is_cross_catalog(resolved, dialect) is False

    def test_non_databricks_with_catalog_is_not_cross_catalog(self):
        resolved = ResolvedIdentifier(catalog="analytics", schema="dbo", table="t")
        dialect = MagicMock()
        dialect.name = "mssql"
        assert _is_cross_catalog(resolved, dialect) is False

    def test_none_dialect_is_not_cross_catalog(self):
        resolved = ResolvedIdentifier(catalog="analytics", schema="sales", table="t")
        assert _is_cross_catalog(resolved, None) is False


class TestCheckTableExists:
    """_check_table_exists: returns None when present, an error dict when missing."""

    def test_inspector_path_present_returns_none(self):
        """Table found among inspector table names -> no error."""
        resolved = ResolvedIdentifier(catalog=None, schema="dbo", table="Customers")
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["Customers", "Orders"]

        assert (
            _check_table_exists(
                engine=MagicMock(),
                inspector=inspector,
                dialect=None,
                resolved=resolved,
                cross_catalog=False,
            )
            is None
        )

    def test_inspector_path_view_returns_none(self):
        """Table absent from tables but present as a view -> no error (views ok)."""
        resolved = ResolvedIdentifier(catalog=None, schema="dbo", table="ActiveView")
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["Customers"]
        inspector.get_view_names.return_value = ["ActiveView"]

        assert (
            _check_table_exists(
                engine=MagicMock(),
                inspector=inspector,
                dialect=None,
                resolved=resolved,
                cross_catalog=False,
            )
            is None
        )

    def test_inspector_path_missing_returns_error(self):
        """Table absent from both tables and views -> schema-qualified error dict."""
        resolved = ResolvedIdentifier(catalog=None, schema="dbo", table="Nope")
        inspector = MagicMock()
        inspector.get_table_names.return_value = ["Customers"]
        inspector.get_view_names.return_value = []

        result = _check_table_exists(
            engine=MagicMock(),
            inspector=inspector,
            dialect=None,
            resolved=resolved,
            cross_catalog=False,
        )

        assert result == {
            "status": "error",
            "error_message": "Table 'Nope' not found in schema 'dbo'",
        }

    def test_cross_catalog_present_returns_none(self):
        """Cross-catalog: MetadataService.table_exists True -> no error."""
        resolved = ResolvedIdentifier(catalog="analytics", schema="sales", table="t")
        dialect = MagicMock()
        dialect.name = "databricks"

        with patch("src.db.metadata.MetadataService") as mock_svc_cls:
            mock_svc_cls.return_value.table_exists.return_value = True
            result = _check_table_exists(
                engine=MagicMock(),
                inspector=MagicMock(),
                dialect=dialect,
                resolved=resolved,
                cross_catalog=True,
            )

        assert result is None
        mock_svc_cls.return_value.table_exists.assert_called_once_with(
            "t", "sales", catalog="analytics"
        )

    def test_cross_catalog_missing_returns_error(self):
        """Cross-catalog: MetadataService.table_exists False -> error dict."""
        resolved = ResolvedIdentifier(catalog="analytics", schema="sales", table="t")
        dialect = MagicMock()
        dialect.name = "databricks"

        with patch("src.db.metadata.MetadataService") as mock_svc_cls:
            mock_svc_cls.return_value.table_exists.return_value = False
            result = _check_table_exists(
                engine=MagicMock(),
                inspector=MagicMock(),
                dialect=dialect,
                resolved=resolved,
                cross_catalog=True,
            )

        assert result == {
            "status": "error",
            "error_message": "Table 'sales.t' not found",
        }


class TestReflectSourceColumn:
    """_reflect_source_column: returns (data_type, None) or (None, error_dict)."""

    def test_inspector_path_found_returns_type(self):
        """Column present via inspector -> (str(type), None)."""
        resolved = ResolvedIdentifier(catalog=None, schema="dbo", table="Customers")
        inspector = MagicMock()
        inspector.get_columns.return_value = [
            {"name": "CustomerID", "type": "INTEGER"},
            {"name": "Name", "type": "VARCHAR"},
        ]

        data_type, error = _reflect_source_column(
            connection=MagicMock(),
            inspector=inspector,
            dialect=None,
            resolved=resolved,
            column_name="CustomerID",
            cross_catalog=False,
        )

        assert error is None
        assert data_type == "INTEGER"

    def test_inspector_path_missing_returns_error(self):
        """Column absent via inspector -> (None, error dict)."""
        resolved = ResolvedIdentifier(catalog=None, schema="dbo", table="Customers")
        inspector = MagicMock()
        inspector.get_columns.return_value = [{"name": "CustomerID", "type": "INTEGER"}]

        data_type, error = _reflect_source_column(
            connection=MagicMock(),
            inspector=inspector,
            dialect=None,
            resolved=resolved,
            column_name="Ghost",
            cross_catalog=False,
        )

        assert data_type is None
        assert error == {
            "status": "error",
            "error_message": "Column 'Ghost' not found in table 'dbo.Customers'",
        }

    def test_cross_catalog_found_returns_type(self):
        """Cross-catalog: reflected column data_type returned as-is."""
        resolved = ResolvedIdentifier(catalog="analytics", schema="sales", table="t")
        dialect = MagicMock()
        dialect.name = "databricks"

        with patch(
            "src.mcp_server.analysis_tools.CatalogAwareReflector"
        ) as mock_reflector_cls:
            mock_reflector_cls.return_value.reflect_columns.return_value = [
                {"name": "id", "data_type": "bigint"},
            ]
            data_type, error = _reflect_source_column(
                connection=MagicMock(),
                inspector=MagicMock(),
                dialect=dialect,
                resolved=resolved,
                column_name="id",
                cross_catalog=True,
            )

        assert error is None
        assert data_type == "bigint"

    def test_cross_catalog_missing_returns_error(self):
        """Cross-catalog: column absent in reflected set -> (None, error dict)."""
        resolved = ResolvedIdentifier(catalog="analytics", schema="sales", table="t")
        dialect = MagicMock()
        dialect.name = "databricks"

        with patch(
            "src.mcp_server.analysis_tools.CatalogAwareReflector"
        ) as mock_reflector_cls:
            mock_reflector_cls.return_value.reflect_columns.return_value = [
                {"name": "id", "data_type": "bigint"},
            ]
            data_type, error = _reflect_source_column(
                connection=MagicMock(),
                inspector=MagicMock(),
                dialect=dialect,
                resolved=resolved,
                column_name="missing",
                cross_catalog=True,
            )

        assert data_type is None
        assert error == {
            "status": "error",
            "error_message": "Column 'missing' not found in table 'sales.t'",
        }
