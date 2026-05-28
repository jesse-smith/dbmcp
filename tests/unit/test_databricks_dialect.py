"""Unit tests for DatabricksDialect protocol compliance and engine construction."""

from __future__ import annotations

from unittest.mock import MagicMock, patch
from urllib.parse import parse_qs, urlparse

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

    def test_default_schema_is_none(self):
        dialect = self._make_dialect()
        assert dialect.default_schema is None

    def test_max_identifier_depth_is_3(self):
        dialect = self._make_dialect()
        assert dialect.max_identifier_depth == 3

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
                    catalog="main",
                )
            with pytest.raises(ImportError, match="Reinstall dbmcp"):
                dialect.create_engine(
                    host="test.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="dapi123",
                    catalog="main",
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
            parsed = urlparse(url)
            query = parse_qs(parsed.query)

            # Verify URL structure
            assert parsed.scheme == "databricks"
            assert parsed.username == "token"
            assert parsed.password == "dapi_test_token"
            assert parsed.hostname == "my-workspace.cloud.databricks.com"
            assert query["http_path"] == ["/sql/1.0/warehouses/abc123"]
            assert query["catalog"] == ["analytics"]
            assert query["schema"] == ["production"]

            # Verify pool_pre_ping and echo settings
            assert call_args[1]["pool_pre_ping"] is True
            assert call_args[1]["echo"] is False
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_missing_catalog_raises_value_error(self, mock_sa_create_engine):
        """create_engine with no catalog kwarg raises ValueError (IDENT-01 / D-01)."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            with pytest.raises(ValueError, match="Databricks catalog is required"):
                dialect.create_engine(
                    host="test.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="tok",
                )
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_empty_catalog_raises_value_error(self, mock_sa_create_engine):
        """create_engine with catalog="" raises ValueError (IDENT-01 / D-03)."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            with pytest.raises(ValueError, match="Databricks catalog is required"):
                dialect.create_engine(
                    host="test.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="tok",
                    catalog="",
                )
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_none_catalog_raises_value_error(self, mock_sa_create_engine):
        """create_engine with catalog=None raises ValueError (None is falsy)."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            with pytest.raises(ValueError, match="Databricks catalog is required"):
                dialect.create_engine(
                    host="test.databricks.com",
                    http_path="/sql/1.0/warehouses/abc",
                    token="tok",
                    catalog=None,
                )
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_create_engine_explicit_main_catalog_succeeds(self, mock_sa_create_engine):
        """Explicit catalog='main' is accepted — only missing/empty is rejected."""
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
                catalog="main",
            )

            url = mock_sa_create_engine.call_args[0][0]
            assert "catalog=main" in url
            # schema still defaults to "default" (out of scope per D-02)
            assert "schema=default" in url
        finally:
            databricks_mod._databricks_import_error = original_error

    def test_kwargs_from_url_missing_catalog_returns_empty_string(self):
        """_kwargs_from_url returns catalog="" (NOT "main") when URL lacks ?catalog="""
        from src.db.dialects.databricks import DatabricksDialect

        kwargs = DatabricksDialect._kwargs_from_url(
            "databricks://token:t@host.cloud.databricks.com?http_path=/x",
            {},
        )
        assert kwargs["catalog"] == ""

    def test_kwargs_from_url_with_catalog_returns_value(self):
        """_kwargs_from_url returns the URL-supplied catalog verbatim."""
        from src.db.dialects.databricks import DatabricksDialect

        kwargs = DatabricksDialect._kwargs_from_url(
            "databricks://token:t@host.cloud.databricks.com?http_path=/x&catalog=my_cat",
            {},
        )
        assert kwargs["catalog"] == "my_cat"

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
                catalog="main",
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
                catalog="main",
            )

            url = mock_sa_create_engine.call_args[0][0]
            parsed = urlparse(url)
            assert parsed.scheme == "databricks"
            assert parsed.username == "token"
            assert parsed.password == ""
            assert parsed.hostname == "test.databricks.com"
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
            parsed = urlparse(url)
            query = parse_qs(parsed.query)
            assert parsed.hostname == "host.cloud.databricks.com"
            assert parsed.password == "dapi_abc"
            assert query["http_path"] == ["/sql/1.0/warehouses/xyz"]
            assert query["catalog"] == ["analytics"]
            assert query["schema"] == ["production"]
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
    def test_create_engine_url_missing_catalog_raises(self, mock_sa_create_engine):
        """URL without ?catalog= raises ValueError (IDENT-01: no implicit default)."""
        databricks_mod = self._dialect_mod()
        original_error = databricks_mod._databricks_import_error
        try:
            databricks_mod._databricks_import_error = None
            dialect = databricks_mod.DatabricksDialect()
            mock_sa_create_engine.return_value = MagicMock()

            with pytest.raises(ValueError, match="Databricks catalog is required"):
                dialect.create_engine(
                    sqlalchemy_url=(
                        "databricks://token:tok@host.cloud.databricks.com?http_path=/p"
                    ),
                )
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
                    "?http_path=/p&catalog=main"
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
                    "databricks://token:tok@url-host.cloud.databricks.com"
                    "?http_path=/p&catalog=main"
                ),
                host="other.databricks.com",
                http_path="/other/path",
            )

            url = mock_sa_create_engine.call_args[0][0]
            parsed = urlparse(url)
            assert parsed.hostname == "url-host.cloud.databricks.com"
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
            parsed = urlparse(url)
            assert url.startswith("databricks://token:")
            assert parsed.hostname == "legacy.databricks.com"
            assert "legacy_tok" in url
            assert "catalog=legacy_cat" in url
            assert "schema=legacy_schema" in url
        finally:
            databricks_mod._databricks_import_error = original_error


class TestCreateEngineConnectArgs:
    """Tests for connect_args plumbing (socket timeout + retry cap)."""

    def _prep(self, databricks_mod):
        databricks_mod._databricks_import_error = None
        return databricks_mod.DatabricksDialect()

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_default_connect_args_applied(self, mock_sa_create_engine):
        """Kwargs-mode with no connection_timeout → defaults (30s socket, 2 retries)."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            dialect = self._prep(databricks_mod)
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="h.databricks.com",
                http_path="/sql/1.0/warehouses/x",
                token="t",
                catalog="main",
            )

            call_kwargs = mock_sa_create_engine.call_args.kwargs
            assert call_kwargs["connect_args"] == {
                "_socket_timeout": 30,
                "_retry_stop_after_attempts_count": 2,
            }
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_connection_timeout_kwarg_overrides_default(self, mock_sa_create_engine):
        """connection_timeout=N → _socket_timeout=N, retry cap still 2."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            dialect = self._prep(databricks_mod)
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="h.databricks.com",
                http_path="/sql/1.0/warehouses/x",
                token="t",
                catalog="main",
                connection_timeout=5,
            )

            ca = mock_sa_create_engine.call_args.kwargs["connect_args"]
            assert ca["_socket_timeout"] == 5
            assert ca["_retry_stop_after_attempts_count"] == 2
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_user_connect_args_merged_user_wins_per_key(self, mock_sa_create_engine):
        """User-supplied connect_args override dialect defaults per-key; extras preserved."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            dialect = self._prep(databricks_mod)
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="h.databricks.com",
                http_path="/sql/1.0/warehouses/x",
                token="t",
                catalog="main",
                connect_args={"_socket_timeout": 10, "_retry_delay_max": 15},
            )

            ca = mock_sa_create_engine.call_args.kwargs["connect_args"]
            assert ca == {
                "_socket_timeout": 10,
                "_retry_stop_after_attempts_count": 2,
                "_retry_delay_max": 15,
            }
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_user_retry_cap_override(self, mock_sa_create_engine):
        """User-supplied _retry_stop_after_attempts_count wins over default 2."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            dialect = self._prep(databricks_mod)
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                host="h.databricks.com",
                http_path="/sql/1.0/warehouses/x",
                token="t",
                catalog="main",
                connect_args={"_retry_stop_after_attempts_count": 5},
            )

            ca = mock_sa_create_engine.call_args.kwargs["connect_args"]
            assert ca["_retry_stop_after_attempts_count"] == 5
            assert ca["_socket_timeout"] == 30
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_connect_args_applied_on_url_path(self, mock_sa_create_engine):
        """URL-mode with no connection_timeout → same defaults (30, 2)."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            dialect = self._prep(databricks_mod)
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                sqlalchemy_url=(
                    "databricks://token:T@host.com/main"
                    "?http_path=/sql/1.0/warehouses/p&catalog=main"
                ),
            )

            ca = mock_sa_create_engine.call_args.kwargs["connect_args"]
            assert ca == {
                "_socket_timeout": 30,
                "_retry_stop_after_attempts_count": 2,
            }
        finally:
            databricks_mod._databricks_import_error = original_error

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_connect_args_url_path_respects_connection_timeout_kwarg(
        self, mock_sa_create_engine
    ):
        """URL-mode + connection_timeout=7 → _socket_timeout=7 (preserved through _kwargs_from_url)."""
        from src.db.dialects import databricks as databricks_mod

        original_error = databricks_mod._databricks_import_error
        try:
            dialect = self._prep(databricks_mod)
            mock_sa_create_engine.return_value = MagicMock()

            dialect.create_engine(
                sqlalchemy_url=(
                    "databricks://token:T@host.com/main"
                    "?http_path=/sql/1.0/warehouses/p&catalog=main"
                ),
                connection_timeout=7,
            )

            ca = mock_sa_create_engine.call_args.kwargs["connect_args"]
            assert ca["_socket_timeout"] == 7
            assert ca["_retry_stop_after_attempts_count"] == 2
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


class TestDatabricksDialectSampleQueries:
    """Databricks dialect builds LIMIT-based sample queries (never TOP/TABLESAMPLE)."""

    def _make(self):
        from src.db.dialects.databricks import DatabricksDialect
        return DatabricksDialect()

    def test_build_sample_query_top_emits_limit(self):
        from src.models.schema import SamplingMethod
        sql = self._make().build_sample_query(
            SamplingMethod.TOP, "`main`.`t`", "*", 5
        )
        assert "SELECT * FROM `main`.`t`" in sql
        assert "LIMIT 5" in sql
        assert "TOP (" not in sql
        assert "TABLESAMPLE" not in sql

    def test_build_sample_query_tablesample_falls_back_to_rand_limit(self):
        from src.models.schema import SamplingMethod
        sql = self._make().build_sample_query(
            SamplingMethod.TABLESAMPLE, "`main`.`t`", "*", 5
        )
        assert "ORDER BY RAND()" in sql
        assert "LIMIT 5" in sql
        assert "TABLESAMPLE" not in sql
        assert "TOP (" not in sql

    def test_build_sample_query_modulo_uses_row_number_with_limit(self):
        from src.models.schema import SamplingMethod
        sql = self._make().build_sample_query(
            SamplingMethod.MODULO, "`main`.`t`", "*", 5
        )
        assert "ROW_NUMBER() OVER" in sql
        assert "LIMIT 5" in sql
        assert "TOP (" not in sql


class TestDatabricksDialectListCatalogs:
    """Tests for DatabricksDialect.list_catalogs (D-08)."""

    def _make_dialect(self):
        from src.db.dialects.databricks import DatabricksDialect

        return DatabricksDialect()

    def _engine_with_rows(self, rows):
        """Build a MagicMock engine whose conn.execute(...).fetchall() returns rows."""
        engine = MagicMock(name="Engine")
        conn = MagicMock(name="SQLAConnection")
        result = MagicMock()
        result.fetchall.return_value = rows
        conn.execute.return_value = result
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = ctx
        return engine, conn

    def test_list_catalogs_returns_row_zero_values(self):
        """list_catalogs returns row[0] for each row, order preserved."""
        from sqlalchemy import text as sa_text

        dialect = self._make_dialect()
        engine, conn = self._engine_with_rows(
            [("main",), ("hive_metastore",), ("samples",)]
        )

        result = dialect.list_catalogs(engine)

        assert result == ["main", "hive_metastore", "samples"]
        # SHOW CATALOGS executed via sqlalchemy.text
        conn.execute.assert_called_once()
        executed_arg = conn.execute.call_args.args[0]
        # Compare via the rendered SQL string for either text() instance or string
        assert str(executed_arg) == str(sa_text("SHOW CATALOGS"))

    def test_list_catalogs_returns_empty_list_when_no_rows(self):
        """list_catalogs returns [] when SHOW CATALOGS yields no rows."""
        dialect = self._make_dialect()
        engine, _conn = self._engine_with_rows([])

        result = dialect.list_catalogs(engine)

        assert result == []

    def test_list_catalogs_propagates_sqlalchemy_error(self):
        """list_catalogs lets SQLAlchemyError propagate (caller wraps per D-08)."""
        from sqlalchemy.exc import SQLAlchemyError

        dialect = self._make_dialect()
        engine = MagicMock(name="Engine")
        conn = MagicMock(name="SQLAConnection")
        conn.execute.side_effect = SQLAlchemyError("boom")
        ctx = MagicMock()
        ctx.__enter__ = MagicMock(return_value=conn)
        ctx.__exit__ = MagicMock(return_value=False)
        engine.connect.return_value = ctx

        with pytest.raises(SQLAlchemyError, match="boom"):
            dialect.list_catalogs(engine)


# ---------------------------------------------------------------------------
# 260528-gsk: ca_bundle plumbing (kwargs + URL + DBMCP_CA_BUNDLE env fallback)
# ---------------------------------------------------------------------------


class TestDatabricksCaBundle:
    """Plumbing tests for ca_bundle → connect_args['_tls_trusted_ca_file'].

    Covers kwargs mode, URL ?ca_bundle= mode, env-var fallback, and absent-when-unset.
    Stubs _merge_ca_bundle_with_certifi so assertions track the user-supplied path
    rather than the merged temp file (merge behavior covered separately).
    """

    @pytest.fixture(autouse=True)
    def _bypass_merge(self, monkeypatch):
        monkeypatch.setattr(
            "src.db.dialects.databricks._merge_ca_bundle_with_certifi",
            lambda path: path,
        )

    def _make_dialect(self):
        from src.db.dialects import databricks as databricks_mod

        databricks_mod._databricks_import_error = None
        return databricks_mod.DatabricksDialect()

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_kwargs_passes_tls_trusted_ca_file(
        self, mock_sa_create_engine, monkeypatch
    ):
        """Explicit kwargs ca_bundle (absolute path) → _tls_trusted_ca_file in connect_args."""
        monkeypatch.delenv("DBMCP_CA_BUNDLE", raising=False)
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            host="h.example.com",
            http_path="/sql/1.0/warehouses/x",
            token="tok",
            catalog="c",
            ca_bundle="/abs/ca.pem",
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert connect_args["_tls_trusted_ca_file"] == "/abs/ca.pem"

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_tilde_expansion(
        self, mock_sa_create_engine, monkeypatch
    ):
        """Tilde in ca_bundle gets expanduser-expanded before reaching connector."""
        import os

        monkeypatch.delenv("DBMCP_CA_BUNDLE", raising=False)
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            host="h.example.com",
            http_path="/sql/1.0/warehouses/x",
            token="tok",
            catalog="c",
            ca_bundle="~/x.pem",
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert connect_args["_tls_trusted_ca_file"] == os.path.expanduser("~/x.pem")

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_absent_when_unset(
        self, mock_sa_create_engine, monkeypatch
    ):
        """No kwarg, no env → _tls_trusted_ca_file MISSING (not empty string)."""
        monkeypatch.delenv("DBMCP_CA_BUNDLE", raising=False)
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            host="h.example.com",
            http_path="/sql/1.0/warehouses/x",
            token="tok",
            catalog="c",
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert "_tls_trusted_ca_file" not in connect_args

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_url_query_param(
        self, mock_sa_create_engine, monkeypatch
    ):
        """URL ?ca_bundle= flows through _kwargs_from_url to connect_args."""
        monkeypatch.delenv("DBMCP_CA_BUNDLE", raising=False)
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            sqlalchemy_url=(
                "databricks://token:T@h.example.com/"
                "?http_path=/sql/1.0/warehouses/x&catalog=c&ca_bundle=/url/ca.pem"
            ),
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert connect_args["_tls_trusted_ca_file"] == "/url/ca.pem"

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_env_fallback(
        self, mock_sa_create_engine, monkeypatch
    ):
        """DBMCP_CA_BUNDLE env var supplies value when no kwarg/URL value set."""
        monkeypatch.setenv("DBMCP_CA_BUNDLE", "/env/ca.pem")
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            host="h.example.com",
            http_path="/sql/1.0/warehouses/x",
            token="tok",
            catalog="c",
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert connect_args["_tls_trusted_ca_file"] == "/env/ca.pem"

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_kwarg_beats_env(
        self, mock_sa_create_engine, monkeypatch
    ):
        """Explicit kwarg wins over DBMCP_CA_BUNDLE env."""
        monkeypatch.setenv("DBMCP_CA_BUNDLE", "/env/ca.pem")
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            host="h.example.com",
            http_path="/sql/1.0/warehouses/x",
            token="tok",
            catalog="c",
            ca_bundle="/explicit/ca.pem",
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert connect_args["_tls_trusted_ca_file"] == "/explicit/ca.pem"

    @patch("src.db.dialects.databricks.sa_create_engine")
    def test_databricks_ca_bundle_url_beats_env(
        self, mock_sa_create_engine, monkeypatch
    ):
        """URL ?ca_bundle= wins over DBMCP_CA_BUNDLE env."""
        monkeypatch.setenv("DBMCP_CA_BUNDLE", "/env/ca.pem")
        mock_sa_create_engine.return_value = MagicMock()
        dialect = self._make_dialect()

        dialect.create_engine(
            sqlalchemy_url=(
                "databricks://token:T@h.example.com/"
                "?http_path=/sql/1.0/warehouses/x&catalog=c&ca_bundle=/url/ca.pem"
            ),
        )
        connect_args = mock_sa_create_engine.call_args[1]["connect_args"]
        assert connect_args["_tls_trusted_ca_file"] == "/url/ca.pem"


class TestMergeCaBundleWithCertifi:
    """Tests for _merge_ca_bundle_with_certifi.

    Connector's _tls_trusted_ca_file replaces (not augments) the trust store,
    so a corp gateway CA alone loses access to standard intermediates. We merge
    with certifi's bundle to keep both.
    """

    def test_merge_concatenates_certifi_and_user_bundle(self, tmp_path):
        import os

        import certifi

        from src.db.dialects.databricks import _merge_ca_bundle_with_certifi

        user_ca = tmp_path / "gateway.pem"
        user_ca.write_text(
            "-----BEGIN CERTIFICATE-----\nUSERCA\n-----END CERTIFICATE-----\n"
        )

        merged_path = _merge_ca_bundle_with_certifi(str(user_ca))
        with open(merged_path) as f:
            merged = f.read()
        with open(certifi.where()) as f:
            certifi_head = f.read()[:200]

        assert "USERCA" in merged
        assert certifi_head in merged
        assert os.path.exists(merged_path)

    def test_merge_is_deterministic_for_same_input(self, tmp_path):
        from src.db.dialects.databricks import _merge_ca_bundle_with_certifi

        user_ca = tmp_path / "gateway.pem"
        user_ca.write_text("-----BEGIN CERTIFICATE-----\nABC\n-----END CERTIFICATE-----\n")
        first = _merge_ca_bundle_with_certifi(str(user_ca))
        second = _merge_ca_bundle_with_certifi(str(user_ca))
        assert first == second

    def test_merge_changes_path_when_user_bundle_changes(self, tmp_path):
        from src.db.dialects.databricks import _merge_ca_bundle_with_certifi

        ca_a = tmp_path / "a.pem"
        ca_a.write_text("-----BEGIN CERTIFICATE-----\nA\n-----END CERTIFICATE-----\n")
        ca_b = tmp_path / "b.pem"
        ca_b.write_text("-----BEGIN CERTIFICATE-----\nB\n-----END CERTIFICATE-----\n")
        assert _merge_ca_bundle_with_certifi(str(ca_a)) != _merge_ca_bundle_with_certifi(str(ca_b))
