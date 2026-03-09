"""Tests for Query dataclass fields: columns, rows, total_rows_available.

Verifies that the Query dataclass has proper typed fields instead of
monkey-patched attributes with type: ignore suppressions.
"""

from src.models.schema import Query


class TestQueryDataclassFields:
    """Test that Query dataclass has columns, rows, total_rows_available fields."""

    def test_query_columns_default_empty_list(self):
        """Query().columns should return an empty list by default."""
        q = Query(query_id="test", connection_id="conn1", query_text="SELECT 1")
        assert q.columns == []

    def test_query_rows_default_empty_list(self):
        """Query().rows should return an empty list by default."""
        q = Query(query_id="test", connection_id="conn1", query_text="SELECT 1")
        assert q.rows == []

    def test_query_total_rows_available_default_none(self):
        """Query().total_rows_available should return None by default."""
        q = Query(query_id="test", connection_id="conn1", query_text="SELECT 1")
        assert q.total_rows_available is None

    def test_query_accepts_fields_as_constructor_args(self):
        """Query should accept columns, rows, total_rows_available in constructor."""
        q = Query(
            query_id="test",
            connection_id="conn1",
            query_text="SELECT 1",
            columns=["id", "name"],
            rows=[{"id": 1, "name": "Alice"}],
            total_rows_available=100,
        )
        assert q.columns == ["id", "name"]
        assert q.rows == [{"id": 1, "name": "Alice"}]
        assert q.total_rows_available == 100

    def test_existing_query_construction_still_works(self):
        """Existing Query construction without new fields should still work."""
        q = Query(
            query_id="test",
            connection_id="conn1",
            query_text="SELECT 1",
            query_type=Query.__dataclass_fields__["query_type"].default,
            is_allowed=True,
            row_limit=500,
        )
        assert q.query_id == "test"
        assert q.row_limit == 500
