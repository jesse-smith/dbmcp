"""Unit tests for metadata-based identifier validation in QueryService.

Tests cover:
- Backward compatibility: QueryService(engine) without metadata_service
- MetadataService injection and storage
- _validate_identifier with valid/invalid columns
- Case-insensitive matching (SQL Server default collation behavior)
- Fail-open fallback when metadata is unavailable
- Error message format
- get_sample_data integration with _validate_identifier
"""

from unittest.mock import MagicMock, patch

import pytest

from src.db.metadata import MetadataService
from src.db.query import QueryService
from src.models.schema import Column, SamplingMethod


def _make_column(name: str) -> Column:
    """Create a minimal Column object for testing."""
    return Column(
        column_id=f"dbo.Users.{name}",
        table_id="dbo.Users",
        column_name=name,
        ordinal_position=1,
        data_type="nvarchar",
        max_length=255,
        is_nullable=True,
        default_value=None,
        is_identity=False,
        is_computed=False,
        is_primary_key=False,
        is_foreign_key=False,
    )


class TestQueryServiceBackwardCompat:
    """Test that QueryService(engine) without metadata_service still works."""

    def test_constructor_without_metadata_service(self, mock_engine):
        """QueryService(engine) still works (backward compat)."""
        service = QueryService(mock_engine)
        assert service.engine is mock_engine
        assert service._metadata_service is None

    def test_constructor_with_metadata_service(self, mock_engine):
        """QueryService(engine, metadata_service=ms) stores the metadata_service."""
        ms = MagicMock(spec=MetadataService)
        service = QueryService(mock_engine, metadata_service=ms)
        assert service._metadata_service is ms


class TestValidateIdentifier:
    """Test _validate_identifier method."""

    def test_valid_column_returns_bracket_quoted(self, mock_engine):
        """Valid column (case-insensitive) returns bracket-quoted actual-cased name."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)
        result = service._validate_identifier(
            "userid", ["UserID", "UserName", "Email"], "[dbo].[Users]"
        )
        assert result == "[UserID]"

    def test_valid_column_sqlite_no_brackets(self, mock_engine):
        """Valid column on SQLite returns unquoted actual-cased name."""
        mock_engine.dialect.name = "sqlite"
        service = QueryService(mock_engine)
        result = service._validate_identifier(
            "userid", ["UserID", "UserName"], "[dbo].[Users]"
        )
        assert result == "UserID"

    def test_invalid_column_raises_valueerror(self, mock_engine):
        """Invalid column raises ValueError naming the column and table context."""
        service = QueryService(mock_engine)
        with pytest.raises(ValueError, match="Column 'foobar' does not exist in \\[dbo\\]\\.\\[Users\\]"):
            service._validate_identifier(
                "foobar", ["UserID", "UserName"], "[dbo].[Users]"
            )

    def test_case_insensitive_matching(self, mock_engine):
        """Case insensitivity: 'username' matches metadata 'UserName', returns '[UserName]'."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)
        result = service._validate_identifier(
            "username", ["UserID", "UserName", "Email"], "[dbo].[Users]"
        )
        assert result == "[UserName]"

    def test_error_message_format(self, mock_engine):
        """Error message format: "Column 'foobar' does not exist in [dbo].[Users]"."""
        service = QueryService(mock_engine)
        with pytest.raises(ValueError) as exc_info:
            service._validate_identifier(
                "foobar", ["UserID", "UserName"], "[dbo].[Users]"
            )
        assert str(exc_info.value) == "Column 'foobar' does not exist in [dbo].[Users]"


class TestGetValidatedColumns:
    """Test _get_validated_columns method (integration of metadata + validation)."""

    def test_no_metadata_service_falls_back_to_regex(self, mock_engine):
        """With no metadata_service, falls back to regex validation."""
        mock_engine.dialect.name = "mssql"
        service = QueryService(mock_engine)
        # Should use _sanitize_identifier (regex path)
        result = service._get_validated_columns(
            ["UserID", "UserName"], "Users", "dbo"
        )
        assert result == ["[UserID]", "[UserName]"]

    def test_metadata_service_validates_columns(self, mock_engine):
        """With metadata_service, validates against metadata."""
        mock_engine.dialect.name = "mssql"
        ms = MagicMock(spec=MetadataService)
        ms.get_columns.return_value = [
            _make_column("UserID"),
            _make_column("UserName"),
            _make_column("Email"),
        ]
        service = QueryService(mock_engine, metadata_service=ms)
        result = service._get_validated_columns(
            ["userid", "username"], "Users", "dbo"
        )
        assert result == ["[UserID]", "[UserName]"]
        ms.get_columns.assert_called_once_with("Users", "dbo")

    def test_metadata_failure_falls_back_to_regex_with_warning(self, mock_engine):
        """When get_columns returns empty list, falls back to regex and logs warning."""
        mock_engine.dialect.name = "mssql"
        ms = MagicMock(spec=MetadataService)
        ms.get_columns.return_value = []  # metadata failure
        service = QueryService(mock_engine, metadata_service=ms)

        with patch("src.db.query.logger") as mock_logger:
            result = service._get_validated_columns(
                ["UserID", "UserName"], "Users", "dbo"
            )
            mock_logger.warning.assert_called_once()
            assert "metadata" in mock_logger.warning.call_args[0][0].lower() or \
                   "fallback" in mock_logger.warning.call_args[0][0].lower() or \
                   "empty" in mock_logger.warning.call_args[0][0].lower()

        # Should have fallen back to regex
        assert result == ["[UserID]", "[UserName]"]

    def test_invalid_column_with_metadata_raises(self, mock_engine):
        """Invalid column with metadata present raises ValueError."""
        ms = MagicMock(spec=MetadataService)
        ms.get_columns.return_value = [
            _make_column("UserID"),
            _make_column("Email"),
        ]
        service = QueryService(mock_engine, metadata_service=ms)
        with pytest.raises(ValueError, match="Column 'BadColumn' does not exist"):
            service._get_validated_columns(
                ["UserID", "BadColumn"], "Users", "dbo"
            )


class TestGetSampleDataWithValidation:
    """Test that get_sample_data uses _validate_identifier when metadata_service is present."""

    def test_get_sample_data_with_columns_calls_validate(self, mock_engine):
        """get_sample_data with columns param calls _validate_identifier (not _sanitize_identifier)."""
        mock_engine.dialect.name = "mssql"

        # Setup metadata service
        ms = MagicMock(spec=MetadataService)
        ms.get_columns.return_value = [
            _make_column("CustomerID"),
            _make_column("CustomerName"),
        ]

        # Setup DB result
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"CustomerID": 1, "CustomerName": "Test"}
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine, metadata_service=ms)
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name="dbo",
            sample_size=5,
            columns=["customerid", "customername"],
        )

        # Verify metadata was consulted
        ms.get_columns.assert_called_once_with("Customers", "dbo")
        assert sample.sample_size == 1

    def test_get_sample_data_without_columns_skips_validation(self, mock_engine):
        """get_sample_data without columns param does not call validation."""
        mock_engine.dialect.name = "mssql"
        ms = MagicMock(spec=MetadataService)

        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {"ID": 1}
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine, metadata_service=ms)
        service.get_sample_data(
            table_name="Customers",
            schema_name="dbo",
            sample_size=5,
        )

        # get_columns should NOT be called when no column filter
        ms.get_columns.assert_not_called()
