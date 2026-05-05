"""Unit tests for DatabricksDialect protocol compliance and engine construction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.db.dialects.protocol import DialectStrategy


class TestDatabricksDialect:
    """Tests for DatabricksDialect class."""

    def _make_dialect(self):
        from src.db.dialects.databricks import DatabricksDialect

        return DatabricksDialect()

    def test_name_returns_databricks(self):
        dialect = self._make_dialect()
        assert dialect.name == "databricks"

    def test_sqlglot_dialect_returns_databricks(self):
        dialect = self._make_dialect()
        assert dialect.sqlglot_dialect == "databricks"

    def test_supports_indexes_returns_false(self):
        dialect = self._make_dialect()
        assert dialect.supports_indexes is False

    def test_has_fast_row_counts_returns_false(self):
        dialect = self._make_dialect()
        assert dialect.has_fast_row_counts is False

    def test_safe_procedures_returns_empty_frozenset(self):
        dialect = self._make_dialect()
        assert dialect.safe_procedures == frozenset()

    def test_quote_identifier_wraps_in_backticks(self):
        dialect = self._make_dialect()
        assert dialect.quote_identifier("my_table") == "`my_table`"

    def test_fast_row_counts_returns_empty_dict(self):
        dialect = self._make_dialect()
        engine = MagicMock()
        assert dialect.fast_row_counts(engine) == {}
        assert dialect.fast_row_counts(engine, schema_name="test") == {}

    def test_satisfies_dialect_strategy_protocol(self):
        dialect = self._make_dialect()
        assert isinstance(dialect, DialectStrategy)

    def test_create_engine_raises_import_error_when_databricks_unavailable(self):
        """When databricks.sql is not importable, create_engine raises ImportError."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = ImportError("No module named 'databricks'")
            dialect = databricks_mod.DatabricksDialect()
            with pytest.raises(ImportError, match="databricks-sqlalchemy"):
                dialect.create_engine(
                    host="test.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="dapi123",
                )
            with pytest.raises(ImportError, match="pip install dbmcp\\[databricks\\]"):
                dialect.create_engine(
                    host="test.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="dapi123",
                )
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_builds_correct_url(self, mock_sa_create_engine):
        """create_engine builds databricks:// URL with proper encoding."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            # Pretend databricks packages are available
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()

            mock_engine = MagicMock()
            mock_sa_create_engine.return_value = mock_engine

            result = dialect.create_engine(
                host="my-workspace.cloud.databricks.com",
                http_path="/sql/1.0/warehouses/abc123",
                token="dapi_test_token",
                catalog="analytics",
                schema="production",
            )

            assert result is mock_engine
            mock_sa_create_engine.assert_called_once()
            call_args = mock_sa_create_engine.call_args
            url = call_args[0][0]

            # Verify URL structure
            assert url.startswith("databricks://token:")
            assert "dapi_test_token" in url
            assert "my-workspace.cloud.databricks.com" in url
            assert "http_path" in url
            assert "catalog=analytics" in url
            assert "schema=production" in url

            # Verify pool_pre_ping and echo settings
            assert call_args[1]["pool_pre_ping"] is True
            assert call_args[1]["echo"] is False
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_uses_defaults_for_catalog_and_schema(self, mock_sa_create_engine):
        """create_engine defaults catalog to 'main' and schema to 'default'."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="test.databricks.com",
                http_path="/sql/1.0/warehouses/abc",
                token="tok",
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "catalog=main" in url
            assert "schema=default" in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_url_encodes_token_special_chars(self, mock_sa_create_engine):
        """Token with special characters is URL-encoded via quote_plus."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="test.databricks.com",
                http_path="/sql/1.0/warehouses/abc",
                token="tok+en/with=special&chars",
            )

            url = mock_sa_create_engine.call_args[0][0]
            # Special chars should be encoded
            assert "tok+en/with=special&chars" not in url
            assert "tok%2Ben%2Fwith%3Dspecial%26chars" in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_empty_token(self, mock_sa_create_engine):
        """Empty token results in databricks://token:@host URL."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="test.databricks.com",
                http_path="/sql/1.0/warehouses/abc",
                token="",
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "databricks://token:@test.databricks.com" in url
        finally:
            databricks_mod._databricks_import_error = original_error


class TestCreateEngineFromUrl:
    """Tests for URL-based (`sqlalchemy_url=`) create_engine path."""

    def _dialect_mod(self):
        from src.db.dialects import databricks as databricks_mod

        return databricks_mod

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_parses_url_query_form(self, mock_sa_create_engine):
        """Query-form URL: databricks://token:T@host?http_path=...&catalog=...&schema=..."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                sqlalchemy_url=(
                    "databricks://token:dapi_abc@host.cloud.databricks.com"
                    "?http_path=/sql/1.0/warehouses/xyz&catalog=analytics&schema=production"
                ),
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "host.cloud.databricks.com" in url
            assert "dapi_abc" in url
            assert "http_path" in url
            assert "%2Fsql%2F1.0%2Fwarehouses%2Fxyz" in url or "/sql/1.0/warehouses/xyz" in url
            assert "catalog=analytics" in url
            assert "schema=production" in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_parses_url_path_form(self, mock_sa_create_engine):
        """Path-form URL: schema from url.database path component."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                sqlalchemy_url=(
                    "databricks://token:dapi_abc@host.cloud.databricks.com:443/production"
                    "?http_path=/sql/1.0/warehouses/xyz&catalog=analytics"
                ),
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "schema=production" in url
            assert "catalog=analytics" in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_url_defaults_catalog_and_schema(self, mock_sa_create_engine):
        """URL without catalog/schema uses defaults main/default."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                sqlalchemy_url="databricks://token:tok@host.cloud.databricks.com?http_path=/p",
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "catalog=main" in url
            assert "schema=default" in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_url_missing_host_raises(self, mock_sa_create_engine):
        """URL missing host raises ValueError mentioning host."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            with pytest.raises(ValueError, match="host"):
                dialect.create_engine(sqlalchemy_url="databricks://token:tok@?http_path=/p")
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_url_missing_http_path_raises(self, mock_sa_create_engine):
        """URL missing http_path raises ValueError mentioning http_path."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            with pytest.raises(ValueError, match="http_path"):
                dialect.create_engine(sqlalchemy_url="databricks://token:tok@host.cloud.databricks.com")
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_url_token_url_encoded(self, mock_sa_create_engine):
        """Token with special chars passed via URL password is url-encoded in outgoing URL."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            # Pre-encode special chars into URL (make_url requires valid URL syntax)
            from urllib.parse import quote_plus as _qp

            raw_token = "tok+en/with=special&chars"
            encoded_for_url = _qp(raw_token)
            dialect.create_engine(
                sqlalchemy_url=(
                    f"databricks://token:{encoded_for_url}@host.cloud.databricks.com"
                    "?http_path=/p"
                ),
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "tok%2Ben%2Fwith%3Dspecial%26chars" in url
            assert raw_token not in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_url_ignores_conflicting_kwargs(self, mock_sa_create_engine):
        """Both sqlalchemy_url= and host= -> URL wins."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                sqlalchemy_url=(
                    "databricks://token:tok@url-host.cloud.databricks.com?http_path=/p"
                ),
                host="other.databricks.com",
                http_path="/other/path",
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "url-host.cloud.databricks.com" in url
            assert "other.databricks.com" not in url
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_kwargs_only_path_unchanged(self, mock_sa_create_engine):
        """Regression: kwargs-only call path (no sqlalchemy_url) still works unchanged."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="legacy.databricks.com",
                http_path="/sql/1.0/warehouses/legacy",
                token="legacy_tok",
                catalog="legacy_cat",
                schema="legacy_schema",
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert url.startswith("databricks://token:")
            assert "legacy.databricks.com" in url
            assert "legacy_tok" in url
            assert "catalog=legacy_cat" in url
            assert "schema=legacy_schema" in url
        finally:
            databricks_mod._databricks_import_error = original_error


class TestDatabricksDialectRegistration:
    """Tests for dialect registry integration."""

    def test_get_dialect_returns_databricks_class(self):
        from src.db.dialects import get_dialect
        from src.db.dialects.databricks import DatabricksDialect

        assert get_dialect("databricks") is DatabricksDialect

    def test_resolve_dialect_from_url_returns_databricks_instance(self):
        from src.db.dialects import resolve_dialect_from_url
        from src.db.dialects.databricks import DatabricksDialect

        dialect = resolve_dialect_from_url("databricks://token:x@host")
        assert isinstance(dialect, DatabricksDialect)
