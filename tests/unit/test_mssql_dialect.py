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


class TestRegistryIntegration:
    """Verify MssqlDialect is auto-registered via __init__.py."""

    def test_get_dialect_returns_mssql_class(self):
        """get_dialect('mssql') returns MssqlDialect after import."""
        # Importing src.db.dialects triggers register_dialect("mssql", MssqlDialect)
        import src.db.dialects  # noqa: F401
        from src.db.dialects.registry import get_dialect

        result = get_dialect("mssql")
        assert result is MssqlDialect
