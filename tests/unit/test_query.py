"""Unit tests for QueryService (sample data retrieval).

Tests cover:
- Sample data retrieval with different sampling methods
- Parameter validation
- Binary and text truncation
- Column filtering
"""

from unittest.mock import MagicMock

import pytest

from src.db.query import QueryService
from src.models.schema import SamplingMethod


class TestQueryService:
    """Test QueryService functionality."""

    def test_get_sample_data_top_method(self, mock_engine):
        """Test TOP sampling method returns expected data."""
        # Mock database response
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "CustomerID": 1,
            "CustomerName": "Test Customer",
            "Status": "Active",
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        # Execute query
        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name="dbo",
            sample_size=5,
            sampling_method=SamplingMethod.TOP,
        )

        # Assertions
        assert sample.table_id == "dbo.Customers"
        assert sample.sample_size == 1  # One row returned
        assert sample.sampling_method == SamplingMethod.TOP
        assert len(sample.rows) == 1
        assert sample.rows[0]["CustomerID"] == 1
        assert sample.rows[0]["CustomerName"] == "Test Customer"

    def test_get_sample_data_with_column_filter(self, mock_engine):
        """Test column filtering works correctly."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "CustomerID": 1,
            "CustomerName": "Test Customer",
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Customers",
            schema_name="dbo",
            sample_size=5,
            columns=["CustomerID", "CustomerName"],
        )

        assert len(sample.rows) == 1
        assert "CustomerID" in sample.rows[0]
        assert "CustomerName" in sample.rows[0]

    def test_binary_truncation(self, mock_engine):
        """Test binary data is truncated and displayed as hex."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        # Binary data longer than 32 bytes
        long_binary = b"x" * 100
        mock_row._mapping = {
            "DocumentID": 1,
            "BinaryData": long_binary,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Documents",
            schema_name="dbo",
            sample_size=1,
        )

        assert len(sample.truncated_columns) == 1
        assert "BinaryData" in sample.truncated_columns
        assert "<binary:" in sample.rows[0]["BinaryData"]
        assert "100 bytes" in sample.rows[0]["BinaryData"]

    def test_text_truncation(self, mock_engine):
        """Test large text is truncated."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        # Text longer than 1000 characters
        long_text = "a" * 1500
        mock_row._mapping = {
            "ID": 1,
            "Description": long_text,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="Articles",
            schema_name="dbo",
            sample_size=1,
        )

        assert len(sample.truncated_columns) == 1
        assert "Description" in sample.truncated_columns
        assert len(sample.rows[0]["Description"]) < 1500
        assert "1500 chars total" in sample.rows[0]["Description"]

    def test_sample_size_validation(self, mock_engine):
        """Test sample_size parameter validation."""
        service = QueryService(mock_engine)

        # Test sample_size < 1
        with pytest.raises(ValueError, match="sample_size must be between 1 and 1000"):
            service.get_sample_data(
                table_name="Customers",
                schema_name="dbo",
                sample_size=0,
            )

        # Test sample_size > 1000
        with pytest.raises(ValueError, match="sample_size must be between 1 and 1000"):
            service.get_sample_data(
                table_name="Customers",
                schema_name="dbo",
                sample_size=1001,
            )

    def test_empty_table_name(self, mock_engine):
        """Test empty table_name raises ValueError."""
        service = QueryService(mock_engine)

        with pytest.raises(ValueError, match="table_name is required"):
            service.get_sample_data(
                table_name="",
                schema_name="dbo",
                sample_size=5,
            )

    def test_tablesample_query_generation(self, mock_engine):
        """Test TABLESAMPLE query is generated correctly."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda x: iter([])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="LargeTable",
            schema_name="dbo",
            sample_size=10,
            sampling_method=SamplingMethod.TABLESAMPLE,
        )

        # Verify the call was made
        assert mock_conn.execute.called
        # Verify sampling method in result
        assert sample.sampling_method == SamplingMethod.TABLESAMPLE

    def test_modulo_query_generation(self, mock_engine):
        """Test modulo-based sampling query is generated."""
        mock_result = MagicMock()
        mock_result.__iter__ = lambda x: iter([])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="SequentialTable",
            schema_name="dbo",
            sample_size=10,
            sampling_method=SamplingMethod.MODULO,
        )

        assert sample.sampling_method == SamplingMethod.MODULO

    def test_null_values_handled(self, mock_engine):
        """Test NULL values are handled correctly."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        mock_row._mapping = {
            "ID": 1,
            "OptionalField": None,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="TestTable",
            schema_name="dbo",
            sample_size=1,
        )

        assert sample.rows[0]["OptionalField"] is None
        assert len(sample.truncated_columns) == 0

    def test_small_binary_not_truncated(self, mock_engine):
        """Test small binary data (<= 32 bytes) is not truncated."""
        mock_result = MagicMock()
        mock_row = MagicMock()
        small_binary = b"small"
        mock_row._mapping = {
            "ID": 1,
            "SmallBinary": small_binary,
        }
        mock_result.__iter__ = lambda x: iter([mock_row])

        mock_conn = MagicMock()
        mock_conn.execute.return_value = mock_result
        mock_engine.connect.return_value.__enter__.return_value = mock_conn

        service = QueryService(mock_engine)
        sample = service.get_sample_data(
            table_name="TestTable",
            schema_name="dbo",
            sample_size=1,
        )

        # Small binary should still be marked as truncated (displayed as hex)
        # but won't have "..." suffix
        assert "<binary:" in sample.rows[0]["SmallBinary"]
        assert "5 bytes" in sample.rows[0]["SmallBinary"]
        assert "..." not in sample.rows[0]["SmallBinary"]
