"""Unit tests for MssqlDialect implementation.

Tests protocol conformance, identifier quoting, engine creation with
all auth methods, DMV-based fast row counts, and registry integration.
"""

from unittest.mock import MagicMock, patch

from src.db.connection import PoolConfig
from src.db.dialects.mssql import MssqlDialect
from src.db.dialects.protocol import DialectStrategy
from src.models.schema import AuthenticationMethod


class TestProtocolConformance:
    """Verify MssqlDialect satisfies the DialectStrategy protocol."""

    def test_isinstance_check_passes(self):
        """MssqlDialect passes isinstance(dialect, DialectStrategy)."""
        dialect = MssqlDialect()
        assert isinstance(dialect, DialectStrategy)

    def test_name_is_mssql(self):
        """dialect.name == 'mssql'."""
        dialect = MssqlDialect()
        assert dialect.name == "mssql"

    def test_sqlglot_dialect_is_tsql(self):
        """dialect.sqlglot_dialect == 'tsql'."""
        dialect = MssqlDialect()
        assert dialect.sqlglot_dialect == "tsql"

    def test_supports_indexes_is_true(self):
        """dialect.supports_indexes is True."""
        dialect = MssqlDialect()
        assert dialect.supports_indexes is True

    def test_has_fast_row_counts_is_true(self):
        """dialect.has_fast_row_counts is True."""
        dialect = MssqlDialect()
        assert dialect.has_fast_row_counts is True

    def test_default_schema_is_dbo(self):
        """dialect.default_schema == 'dbo'."""
        dialect = MssqlDialect()
        assert dialect.default_schema == "dbo"

    def test_max_identifier_depth_is_2(self):
        """dialect.max_identifier_depth == 2."""
        dialect = MssqlDialect()
        assert dialect.max_identifier_depth == 2


class TestQuoteIdentifier:
    """Verify bracket quoting for SQL Server identifiers."""

    def test_simple_identifier(self):
        """Simple name gets bracket-quoted."""
        dialect = MssqlDialect()
        assert dialect.quote_identifier("Users") == "[Users]"

    def test_identifier_with_spaces(self):
        """Name with spaces gets bracket-quoted as a whole."""
        dialect = MssqlDialect()
        assert dialect.quote_identifier("my column") == "[my column]"

    def test_dotted_identifier(self):
        """Dotted name gets bracket-quoted as a whole (caller handles splitting)."""
        dialect = MssqlDialect()
        assert dialect.quote_identifier("schema.table") == "[schema.table]"


class TestCreateEngine:
    """Verify engine creation with different auth methods."""

    def _base_kwargs(self, **overrides):
        """Build default kwargs for create_engine, with optional overrides."""
        defaults = {
            "server": "testserver",
            "database": "testdb",
            "port": 1433,
            "username": "testuser",
            "password": "testpass",
            "authentication_method": AuthenticationMethod.SQL,
            "trust_server_cert": True,
            "connection_timeout": 30,
            "query_timeout": 30,
            "pool_config": PoolConfig(),
        }
        defaults.update(overrides)
        return defaults

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_sql_auth_odbc_string_contains_uid_pwd(self, mock_create_engine, _mock_event):
        """SQL auth builds ODBC string with UID= and PWD=."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(**self._base_kwargs())

        # Verify the URL passed to create_engine contains the ODBC string
        url_arg = mock_create_engine.call_args[0][0]
        assert "UID%3Dtestuser" in url_arg or "UID=testuser" in url_arg
        assert "PWD%3Dtestpass" in url_arg or "PWD=testpass" in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_windows_auth_odbc_string_contains_trusted_connection(self, mock_create_engine, _mock_event):
        """Windows auth builds ODBC string with Trusted_Connection=yes."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(**self._base_kwargs(
            authentication_method=AuthenticationMethod.WINDOWS,
            username=None,
            password=None,
        ))

        url_arg = mock_create_engine.call_args[0][0]
        assert "Trusted_Connection" in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.AzureTokenProvider")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_azure_ad_integrated_uses_creator(self, mock_create_engine, mock_provider_cls, _mock_event):
        """Azure AD integrated auth creates engine with creator= kwarg."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(**self._base_kwargs(
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
            username=None,
            password=None,
            tenant_id="test-tenant-id",
        ))

        # Verify create_engine was called with creator kwarg
        call_kwargs = mock_create_engine.call_args[1]
        assert "creator" in call_kwargs
        # Verify URL is the bare mssql+pyodbc:// (no odbc_connect param)
        url_arg = mock_create_engine.call_args[0][0]
        assert url_arg == "mssql+pyodbc://"

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.AzureTokenProvider")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_azure_ad_integrated_creates_provider_with_tenant(self, mock_create_engine, mock_provider_cls, _mock_event):
        """Azure AD integrated auth passes tenant_id to AzureTokenProvider."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(**self._base_kwargs(
            authentication_method=AuthenticationMethod.AZURE_AD_INTEGRATED,
            username=None,
            password=None,
            tenant_id="my-tenant",
        ))

        mock_provider_cls.assert_called_once_with(tenant_id="my-tenant")

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_azure_ad_pool_recycle_uses_shorter_interval(self, mock_create_engine, _mock_event):
        """Azure AD auth uses azure_ad_pool_recycle instead of default."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()
        pool_config = PoolConfig(pool_recycle=3600, azure_ad_pool_recycle=2700)

        dialect.create_engine(**self._base_kwargs(
            authentication_method=AuthenticationMethod.AZURE_AD,
            pool_config=pool_config,
        ))

        call_kwargs = mock_create_engine.call_args[1]
        assert call_kwargs["pool_recycle"] == 2700

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_sql_auth_pool_recycle_uses_default(self, mock_create_engine, _mock_event):
        """SQL auth uses default pool_recycle (not azure_ad_pool_recycle)."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()
        pool_config = PoolConfig(pool_recycle=3600, azure_ad_pool_recycle=2700)

        dialect.create_engine(**self._base_kwargs(pool_config=pool_config))

        call_kwargs = mock_create_engine.call_args[1]
        assert call_kwargs["pool_recycle"] == 3600

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_query_timeout_registers_connect_event(self, mock_create_engine, mock_event):
        """Non-zero query_timeout registers a connect event listener."""
        mock_engine = MagicMock()
        mock_create_engine.return_value = mock_engine
        dialect = MssqlDialect()

        dialect.create_engine(**self._base_kwargs(query_timeout=60))

        mock_event.listens_for.assert_called_once_with(mock_engine, "connect")

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_zero_query_timeout_skips_event(self, mock_create_engine, mock_event):
        """Zero query_timeout does not register connect event."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(**self._base_kwargs(query_timeout=0))

        mock_event.listens_for.assert_not_called()


class TestFastRowCounts:
    """Verify DMV-based fast row count queries."""

    def test_returns_dict_mapping_schema_table_to_count(self):
        """fast_row_counts returns dict with 'schema.table' -> int."""
        dialect = MssqlDialect()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_row1 = MagicMock()
        mock_row1.table_key = "dbo.Users"
        mock_row1.row_count = 100
        mock_row2 = MagicMock()
        mock_row2.table_key = "dbo.Orders"
        mock_row2.row_count = 5000
        mock_conn.execute.return_value = [mock_row1, mock_row2]

        result = dialect.fast_row_counts(mock_engine)

        assert result == {"dbo.Users": 100, "dbo.Orders": 5000}

    def test_with_schema_filter(self):
        """fast_row_counts passes schema_name as bound parameter."""
        dialect = MssqlDialect()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)

        mock_row = MagicMock()
        mock_row.table_key = "sales.Orders"
        mock_row.row_count = 200
        mock_conn.execute.return_value = [mock_row]

        result = dialect.fast_row_counts(mock_engine, schema_name="sales")

        assert result == {"sales.Orders": 200}
        # Verify the params include schema_name
        execute_call = mock_conn.execute.call_args
        params = execute_call[0][1] if len(execute_call[0]) > 1 else execute_call[1]
        assert params["schema_name"] == "sales"

    def test_empty_result_returns_empty_dict(self):
        """fast_row_counts returns empty dict when no tables exist."""
        dialect = MssqlDialect()
        mock_engine = MagicMock()
        mock_conn = MagicMock()
        mock_engine.connect.return_value.__enter__ = MagicMock(return_value=mock_conn)
        mock_engine.connect.return_value.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.return_value = []

        result = dialect.fast_row_counts(mock_engine)

        assert result == {}


class TestCreateEngineFromUrl:
    """Verify MssqlDialect.create_engine parses sqlalchemy_url kwarg.

    See plan 260505-mhm: URL-based connection must work for MSSQL — the
    URL takes precedence over conflicting kwargs when provided.
    """

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_parses_url_sql_auth(self, mock_create_engine, _mock_event):
        """URL with user:pass@host:1433/db derives SQL auth params."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            sqlalchemy_url="mssql+pyodbc://user:pass@host:1433/mydb",
            query_timeout=30,
        )

        url_arg = mock_create_engine.call_args[0][0]
        # SQL auth ODBC string has UID/PWD and Server=host,1433; DB=mydb
        assert "UID%3Duser" in url_arg or "UID=user" in url_arg
        assert "PWD%3Dpass" in url_arg or "PWD=pass" in url_arg
        assert "Server%3Dhost%2C1433" in url_arg or "Server=host,1433" in url_arg
        assert "Database%3Dmydb" in url_arg or "Database=mydb" in url_arg
        # trust_server_cert default False
        assert "TrustServerCertificate%3Dno" in url_arg or "TrustServerCertificate=no" in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_parses_url_windows_auth(self, mock_create_engine, _mock_event):
        """URL with authentication_method=windows uses Trusted_Connection."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            sqlalchemy_url="mssql+pyodbc://host/mydb?authentication_method=windows",
            query_timeout=30,
        )

        url_arg = mock_create_engine.call_args[0][0]
        assert "Trusted_Connection" in url_arg
        # No UID/PWD for Windows auth
        assert "UID%3D" not in url_arg and "UID=" not in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_parses_url_trust_server_cert_true(self, mock_create_engine, _mock_event):
        """trust_server_cert=true in query string sets TrustServerCertificate=yes."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            sqlalchemy_url="mssql+pyodbc://user:pass@host/mydb?trust_server_cert=true",
            query_timeout=30,
        )

        url_arg = mock_create_engine.call_args[0][0]
        assert "TrustServerCertificate%3Dyes" in url_arg or "TrustServerCertificate=yes" in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_parses_url_trust_server_cert_variants(self, mock_create_engine, _mock_event):
        """trust_server_cert accepts '1'/'yes' as truthy, '0'/'false' as falsy."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        for truthy in ("1", "yes", "TRUE", "True"):
            mock_create_engine.reset_mock()
            dialect.create_engine(
                sqlalchemy_url=f"mssql+pyodbc://u:p@h/d?trust_server_cert={truthy}",
                query_timeout=30,
            )
            url_arg = mock_create_engine.call_args[0][0]
            assert (
                "TrustServerCertificate%3Dyes" in url_arg
                or "TrustServerCertificate=yes" in url_arg
            ), f"truthy value {truthy!r} should produce yes"

        for falsy in ("0", "false", "FALSE", "no"):
            mock_create_engine.reset_mock()
            dialect.create_engine(
                sqlalchemy_url=f"mssql+pyodbc://u:p@h/d?trust_server_cert={falsy}",
                query_timeout=30,
            )
            url_arg = mock_create_engine.call_args[0][0]
            assert (
                "TrustServerCertificate%3Dno" in url_arg
                or "TrustServerCertificate=no" in url_arg
            ), f"falsy value {falsy!r} should produce no"

    def test_create_engine_url_missing_host_raises(self):
        """URL without host raises ValueError mentioning 'server'."""
        import pytest

        dialect = MssqlDialect()
        with pytest.raises(ValueError, match="server"):
            dialect.create_engine(sqlalchemy_url="mssql+pyodbc:///mydb")

    def test_create_engine_url_missing_database_raises(self):
        """URL without database raises ValueError mentioning 'database'."""
        import pytest

        dialect = MssqlDialect()
        with pytest.raises(ValueError, match="database"):
            dialect.create_engine(sqlalchemy_url="mssql+pyodbc://host/")

    def test_create_engine_url_invalid_auth_method_raises(self):
        """Invalid authentication_method query value raises ValueError listing accepted values."""
        import pytest

        dialect = MssqlDialect()
        with pytest.raises(ValueError, match="authentication_method"):
            dialect.create_engine(
                sqlalchemy_url="mssql+pyodbc://u:p@h/d?authentication_method=bogus"
            )

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_url_ignores_conflicting_kwargs(self, mock_create_engine, _mock_event):
        """When sqlalchemy_url is provided, conflicting kwargs (server=) are ignored — URL wins."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            sqlalchemy_url="mssql+pyodbc://user:pass@url_host/url_db",
            server="other_host",
            database="other_db",
            authentication_method=AuthenticationMethod.WINDOWS,
            query_timeout=30,
        )

        url_arg = mock_create_engine.call_args[0][0]
        assert "Server%3Durl_host" in url_arg or "Server=url_host" in url_arg
        assert "Server=other_host" not in url_arg and "Server%3Dother_host" not in url_arg
        assert "Database%3Durl_db" in url_arg or "Database=url_db" in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_kwargs_only_path_unchanged(self, mock_create_engine, _mock_event):
        """Regression: kwargs-only call (no sqlalchemy_url) still works."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            server="kwserver",
            database="kwdb",
            port=1433,
            username="kwuser",
            password="kwpass",
            authentication_method=AuthenticationMethod.SQL,
            trust_server_cert=True,
            connection_timeout=30,
            query_timeout=30,
            pool_config=PoolConfig(),
        )

        url_arg = mock_create_engine.call_args[0][0]
        assert "Server%3Dkwserver%2C1433" in url_arg or "Server=kwserver,1433" in url_arg
        assert "Database%3Dkwdb" in url_arg or "Database=kwdb" in url_arg
        assert "UID%3Dkwuser" in url_arg or "UID=kwuser" in url_arg

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_url_driver_overrides_default(self, mock_create_engine, _mock_event):
        """URL ?driver=ODBC+Driver+17+... overrides the hardcoded Driver 18 default."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            sqlalchemy_url=(
                "mssql+pyodbc://user:pass@host/db"
                "?driver=ODBC+Driver+17+for+SQL+Server"
            ),
            query_timeout=30,
        )

        url_arg = mock_create_engine.call_args[0][0]
        # URL arg is quote_plus-encoded: "ODBC Driver 17 for SQL Server" -> "ODBC+Driver+17+for+SQL+Server"
        # Driver={...} -> Driver%3D%7BODBC+Driver+17+for+SQL+Server%7D
        assert (
            "Driver%3D%7BODBC+Driver+17+for+SQL+Server%7D" in url_arg
            or "Driver={ODBC Driver 17 for SQL Server}" in url_arg
        ), f"expected Driver 17 in url_arg, got: {url_arg}"
        assert (
            "ODBC+Driver+18+for+SQL+Server" not in url_arg
            and "ODBC Driver 18 for SQL Server" not in url_arg
        ), f"Driver 18 should not appear when URL supplies Driver 17: {url_arg}"

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_url_without_driver_uses_default(self, mock_create_engine, _mock_event):
        """URL without driver= query param falls back to Driver 18 default (backward compat)."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            sqlalchemy_url="mssql+pyodbc://user:pass@host/db",
            query_timeout=30,
        )

        url_arg = mock_create_engine.call_args[0][0]
        assert (
            "ODBC+Driver+18+for+SQL+Server" in url_arg
            or "ODBC Driver 18 for SQL Server" in url_arg
        ), f"expected Driver 18 default when URL has no driver query: {url_arg}"

    @patch("src.db.dialects.mssql.event")
    @patch("src.db.dialects.mssql.sa_create_engine")
    def test_create_engine_kwargs_path_uses_default_driver(self, mock_create_engine, _mock_event):
        """Regression: kwargs-only path (no sqlalchemy_url) continues to use Driver 18."""
        mock_create_engine.return_value = MagicMock()
        dialect = MssqlDialect()

        dialect.create_engine(
            server="kwserver",
            database="kwdb",
            port=1433,
            username="kwuser",
            password="kwpass",
            authentication_method=AuthenticationMethod.SQL,
            trust_server_cert=True,
            connection_timeout=30,
            query_timeout=30,
            pool_config=PoolConfig(),
        )

        url_arg = mock_create_engine.call_args[0][0]
        assert (
            "ODBC+Driver+18+for+SQL+Server" in url_arg
            or "ODBC Driver 18 for SQL Server" in url_arg
        )


class TestRegistryIntegration:
    """Verify MssqlDialect is auto-registered via __init__.py."""

    def test_get_dialect_returns_mssql_class(self):
        """get_dialect('mssql') returns MssqlDialect after import."""
        # Importing src.db.dialects triggers register_dialect("mssql", MssqlDialect)
        import src.db.dialects  # noqa: F401
        from src.db.dialects.registry import get_dialect

        result = get_dialect("mssql")
        assert result is MssqlDialect


class TestMssqlDialectSampleQueries:
    """MSSQL dialect builds TOP/TABLESAMPLE/ROW_NUMBER sample queries."""

    def test_build_sample_query_top_emits_top_n(self):
        from src.models.schema import SamplingMethod
        dialect = MssqlDialect()
        sql = dialect.build_sample_query(
            SamplingMethod.TOP, "[dbo].[T]", "*", 5
        )
        assert "SELECT TOP (5) * FROM [dbo].[T]" in sql

    def test_build_sample_query_tablesample_emits_tablesample_rows(self):
        from src.models.schema import SamplingMethod
        dialect = MssqlDialect()
        sql = dialect.build_sample_query(
            SamplingMethod.TABLESAMPLE, "[dbo].[T]", "*", 5
        )
        assert "TOP (5)" in sql
        assert "TABLESAMPLE (5 ROWS)" in sql

    def test_build_sample_query_modulo_uses_row_number_with_top(self):
        from src.models.schema import SamplingMethod
        dialect = MssqlDialect()
        sql = dialect.build_sample_query(
            SamplingMethod.MODULO, "[dbo].[T]", "*", 5
        )
        assert "TOP (5)" in sql
        assert "ROW_NUMBER() OVER" in sql
        assert "ORDER BY (SELECT NULL)" in sql
