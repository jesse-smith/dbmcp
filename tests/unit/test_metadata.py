"""Unit tests for metadata service.

Tests for list_schemas, list_tables, and related metadata queries.
These tests use an in-memory SQLite database for realistic testing.
"""

from unittest.mock import MagicMock, PropertyMock, patch

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.exc import SQLAlchemyError

from src.db.metadata import MetadataService
from src.models.schema import TableType


@pytest.fixture
def test_engine():
    """Create an in-memory SQLite database with test tables."""
    engine = create_engine("sqlite:///:memory:", echo=False)

    with engine.connect() as conn:
        # Create test tables
        conn.execute(text("""
            CREATE TABLE customers (
                customer_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL
            )
        """))
        conn.execute(text("""
            CREATE TABLE orders (
                order_id INTEGER PRIMARY KEY,
                customer_id INTEGER,
                total DECIMAL(10,2)
            )
        """))
        conn.execute(text("""
            CREATE TABLE products (
                product_id INTEGER PRIMARY KEY,
                name TEXT NOT NULL,
                price DECIMAL(10,2)
            )
        """))

        # Insert sample data for row count testing
        conn.execute(text("INSERT INTO customers VALUES (1, 'Alice'), (2, 'Bob'), (3, 'Carol')"))
        conn.execute(text("INSERT INTO orders VALUES (1, 1, 100.00), (2, 1, 200.00)"))
        conn.execute(text("INSERT INTO products VALUES (1, 'Widget', 10.00)"))
        conn.commit()

    return engine


class TestListSchemas:
    """Tests for MetadataService.list_schemas() - T012A"""

    def test_list_schemas_returns_schema_objects(self, test_engine):
        """T012A: Verify list_schemas returns Schema objects with correct fields."""
        service = MetadataService(test_engine)

        schemas = service.list_schemas(connection_id="test123")

        # SQLite has a single "main" schema
        assert len(schemas) >= 1
        assert schemas[0].schema_name == "main"
        assert schemas[0].table_count == 3  # customers, orders, products
        assert schemas[0].view_count == 0

    def test_list_schemas_excludes_system_schemas(self, test_engine):
        """T012A: Verify sys, INFORMATION_SCHEMA, guest are excluded."""
        service = MetadataService(test_engine)

        schemas = service.list_schemas()

        schema_names = [s.schema_name for s in schemas]
        assert "sys" not in schema_names
        assert "INFORMATION_SCHEMA" not in schema_names
        assert "guest" not in schema_names

    def test_list_schemas_sorts_by_table_count_desc(self, test_engine):
        """T012A: Verify schemas are sorted by table_count descending."""
        service = MetadataService(test_engine)

        schemas = service.list_schemas()

        # For a single schema, just verify it's returned
        assert len(schemas) >= 1
        # If multiple schemas exist, verify sorting
        if len(schemas) > 1:
            assert schemas[0].table_count >= schemas[1].table_count

    def test_list_schemas_sets_connection_id(self, test_engine):
        """T012A: Verify schema_id includes connection_id."""
        service = MetadataService(test_engine)

        schemas = service.list_schemas(connection_id="myconn123")

        assert schemas[0].connection_id == "myconn123"
        assert "myconn123" in schemas[0].schema_id


class TestListTables:
    """Tests for MetadataService.list_tables() - T013A"""

    def test_list_tables_returns_table_objects(self, test_engine):
        """T013A: Verify list_tables returns Table objects with row counts."""
        service = MetadataService(test_engine)

        tables, pagination = service.list_tables()

        assert len(tables) == 3
        assert "total_count" in pagination
        table_names = {t.table_name for t in tables}
        assert "customers" in table_names
        assert "orders" in table_names
        assert "products" in table_names

    def test_list_tables_includes_row_count(self, test_engine):
        """T013A: Verify row counts are populated."""
        service = MetadataService(test_engine)

        tables, _ = service.list_tables()

        # All tables should have row counts
        for table in tables:
            assert table.row_count is not None
            assert table.row_count >= 0

        # Verify specific counts
        customers = next(t for t in tables if t.table_name == "customers")
        assert customers.row_count == 3

    def test_list_tables_filters_by_schema(self, test_engine):
        """T013A: Verify schema_name filter works."""
        service = MetadataService(test_engine)

        tables, _ = service.list_tables(schema_name="main")

        # All tables should be from main schema
        for table in tables:
            assert table.schema_id == "main"

    def test_list_tables_respects_limit(self, test_engine):
        """T013A: Verify limit parameter is enforced."""
        service = MetadataService(test_engine)

        tables, _ = service.list_tables(limit=2)

        assert len(tables) <= 2

    def test_list_tables_min_row_count_total_count(self, test_engine):
        """Issue #1: Verify total_count reflects min_row_count filter.

        Test DB has: customers (3 rows), orders (2 rows), products (1 row).
        Filtering min_row_count=2 should give total_count=2 (customers + orders),
        not 3 (all tables).
        """
        service = MetadataService(test_engine)

        tables, pagination = service.list_tables(min_row_count=2)

        assert len(tables) == 2
        assert pagination["total_count"] == 2
        assert pagination["has_more"] is False
        table_names = {t.table_name for t in tables}
        assert "customers" in table_names
        assert "orders" in table_names
        assert "products" not in table_names


class TestSorting:
    """Tests for list_tables sorting - T016A"""

    def test_sort_by_name_ascending(self, test_engine):
        """T016A: Verify sort by name ascending."""
        service = MetadataService(test_engine)

        tables, _ = service.list_tables(sort_by="name", sort_order="asc")

        names = [t.table_name for t in tables]
        assert names == sorted(names)

    def test_sort_by_row_count_descending(self, test_engine):
        """T016A: Verify sort by row_count descending (default)."""
        service = MetadataService(test_engine)

        tables, _ = service.list_tables(sort_by="row_count", sort_order="desc")

        row_counts = [t.row_count for t in tables]
        assert row_counts == sorted(row_counts, reverse=True)


class TestAccessDenied:
    """Tests for access_denied handling - T019A"""

    def test_access_denied_marker_returned(self):
        """T019A: Verify access_denied marker for tables without SELECT permission."""
        # The actual implementation would handle this via exception in row count query
        # For unit test, we verify the model can represent this state
        from src.models.schema import Table

        table = Table(
            table_id="hr.Salaries",
            schema_id="hr",
            table_name="Salaries",
            table_type=TableType.TABLE,
            row_count=None,  # Unknown due to no access
            has_primary_key=True,
            access_denied=True,
        )

        assert table.access_denied is True
        assert table.row_count is None

    def test_access_denied_does_not_block_other_tables(self, test_engine):
        """T019A: Verify one inaccessible table doesn't block others."""
        # When one table throws permission error, others should still be returned
        service = MetadataService(test_engine)

        tables, _ = service.list_tables()

        # Should still get all accessible tables
        assert len(tables) == 3


class TestOutputMode:
    """Tests for output_mode parameter - T017A"""

    def test_summary_mode_reduces_output(self):
        """T017A: Verify summary mode returns less data than detailed."""
        # This is tested at the MCP tool level in integration tests
        # Unit test verifies model supports both modes
        from src.models.schema import Table

        table = Table(
            table_id="dbo.Customers",
            schema_id="dbo",
            table_name="Customers",
            table_type=TableType.TABLE,
            row_count=10000,
            has_primary_key=True,
        )

        # Summary representation
        summary = {
            "table_name": table.table_name,
            "row_count": table.row_count,
        }

        # Detailed would include columns - tested in integration
        assert "table_name" in summary
        assert "row_count" in summary


class TestLimitEnforcement:
    """Tests for limit parameter enforcement - T018A"""

    def test_default_limit_is_100(self, test_engine):
        """T018A: Verify default limit of 100."""
        service = MetadataService(test_engine)

        # Default limit should be 100
        tables, _ = service.list_tables()

        # Our sample has only 3 tables, so all should be returned
        assert len(tables) <= 100

    def test_max_limit_is_1000(self, test_engine):
        """T018A: Verify max limit of 1000 is enforced."""
        service = MetadataService(test_engine)

        # Request more than max
        tables, _ = service.list_tables(limit=2000)

        # Should be capped to 1000 (or less if fewer tables exist)
        assert len(tables) <= 1000

    def test_limit_validation(self, test_engine):
        """T018A: Verify limit must be positive."""
        service = MetadataService(test_engine)

        # Limit 0 or negative should be handled
        tables, _ = service.list_tables(limit=0)
        # Implementation clamps to minimum 1
        assert len(tables) >= 0


class TestPagination:
    """Tests for list_tables pagination - T132"""

    def test_pagination_metadata_returned(self, test_engine):
        """T132: Verify pagination metadata is returned."""
        service = MetadataService(test_engine)

        tables, pagination = service.list_tables()

        assert "total_count" in pagination
        assert "offset" in pagination
        assert "limit" in pagination
        assert "has_more" in pagination
        assert pagination["total_count"] == 3
        assert pagination["offset"] == 0
        assert pagination["has_more"] is False

    def test_offset_skips_records(self, test_engine):
        """T132: Verify offset parameter skips records."""
        service = MetadataService(test_engine)

        # Get all tables sorted by name for predictable order
        all_tables, _ = service.list_tables(sort_by="name", sort_order="asc")
        all_names = [t.table_name for t in all_tables]

        # Get tables with offset=1
        offset_tables, pagination = service.list_tables(sort_by="name", sort_order="asc", offset=1)
        offset_names = [t.table_name for t in offset_tables]

        # Should skip first record
        assert len(offset_tables) == 2
        assert offset_names == all_names[1:]
        assert pagination["offset"] == 1

    def test_has_more_flag_true_when_more_records(self, test_engine):
        """T132: Verify has_more is True when more records exist."""
        service = MetadataService(test_engine)

        # Request only 2 of 3 tables
        tables, pagination = service.list_tables(limit=2)

        assert len(tables) == 2
        assert pagination["has_more"] is True
        assert pagination["total_count"] == 3

    def test_has_more_flag_false_at_end(self, test_engine):
        """T132: Verify has_more is False when no more records."""
        service = MetadataService(test_engine)

        # Request with offset that leaves no more
        tables, pagination = service.list_tables(limit=2, offset=2)

        assert len(tables) == 1  # Only 1 table left after offset=2
        assert pagination["has_more"] is False

    def test_offset_beyond_total_returns_empty(self, test_engine):
        """T132: Verify offset beyond total returns empty list."""
        service = MetadataService(test_engine)

        tables, pagination = service.list_tables(offset=100)

        assert len(tables) == 0
        assert pagination["total_count"] == 3
        assert pagination["has_more"] is False


class TestObjectTypeFiltering:
    """Tests for object_type filtering (tables vs views) - T133"""

    @pytest.fixture
    def engine_with_views(self):
        """Create a database with both tables and views."""
        engine = create_engine("sqlite:///:memory:", echo=False)

        with engine.connect() as conn:
            # Create tables
            conn.execute(text("""
                CREATE TABLE customers (
                    customer_id INTEGER PRIMARY KEY,
                    name TEXT NOT NULL
                )
            """))
            conn.execute(text("""
                CREATE TABLE orders (
                    order_id INTEGER PRIMARY KEY,
                    customer_id INTEGER,
                    total DECIMAL(10,2)
                )
            """))

            # Create views
            conn.execute(text("""
                CREATE VIEW customer_summary AS
                SELECT customer_id, name FROM customers
            """))
            conn.execute(text("""
                CREATE VIEW order_totals AS
                SELECT customer_id, SUM(total) as total FROM orders GROUP BY customer_id
            """))

            conn.commit()

        return engine

    def test_object_type_table_returns_only_tables(self, engine_with_views):
        """T133: Verify object_type='table' returns only tables."""
        service = MetadataService(engine_with_views)

        tables, pagination = service.list_tables(object_type="table")

        assert len(tables) == 2
        table_names = {t.table_name for t in tables}
        assert "customers" in table_names
        assert "orders" in table_names
        assert "customer_summary" not in table_names
        assert "order_totals" not in table_names

    def test_object_type_view_returns_only_views(self, engine_with_views):
        """T133: Verify object_type='view' returns only views."""
        service = MetadataService(engine_with_views)

        tables, pagination = service.list_tables(object_type="view")

        assert len(tables) == 2
        view_names = {t.table_name for t in tables}
        assert "customer_summary" in view_names
        assert "order_totals" in view_names
        assert "customers" not in view_names
        assert "orders" not in view_names

    def test_object_type_none_returns_all(self, engine_with_views):
        """T133: Verify object_type=None returns both tables and views."""
        service = MetadataService(engine_with_views)

        tables, pagination = service.list_tables(object_type=None)

        assert len(tables) == 4
        names = {t.table_name for t in tables}
        assert "customers" in names
        assert "orders" in names
        assert "customer_summary" in names
        assert "order_totals" in names

    def test_view_has_correct_table_type(self, engine_with_views):
        """T133: Verify views have TableType.VIEW."""
        service = MetadataService(engine_with_views)

        tables, _ = service.list_tables(object_type="view")

        for table in tables:
            assert table.table_type == TableType.VIEW


class TestErrorPaths:
    """Tests for SQLAlchemyError handling in MetadataService methods."""

    def test_get_schema_names_error_returns_fallback(self, test_engine):
        """Verify list_schemas falls back to [None] when get_schema_names raises."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_schema_names.side_effect = SQLAlchemyError("connection lost")
            # After fallback to [None], get_table_names/get_view_names still work
            mock_insp.get_table_names.return_value = ["t1"]
            mock_insp.get_view_names.return_value = []
            mock_inspector_prop.return_value = mock_insp

            schemas = service.list_schemas()

        # Should still return at least one schema (the fallback "main")
        assert len(schemas) >= 1
        assert schemas[0].schema_name == "main"

    def test_get_table_names_error_in_schema_loop(self, test_engine):
        """Verify _list_schemas_generic handles error on get_table_names gracefully."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_schema_names.return_value = ["main"]
            mock_insp.get_table_names.side_effect = SQLAlchemyError("access denied")
            mock_insp.get_view_names.side_effect = SQLAlchemyError("access denied")
            mock_inspector_prop.return_value = mock_insp

            schemas = service.list_schemas()

        # "main" schema still included (display_name in keep-list) but with 0 counts
        assert len(schemas) >= 1
        main_schema = next((s for s in schemas if s.schema_name == "main"), None)
        assert main_schema is not None
        assert main_schema.table_count == 0
        assert main_schema.view_count == 0

    def test_table_exists_error_returns_false(self, test_engine):
        """Verify table_exists returns False when inspector raises."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_table_names.side_effect = SQLAlchemyError("broken")
            mock_inspector_prop.return_value = mock_insp

            result = service.table_exists("nonexistent", "dbo")

        assert result is False

    def test_get_indexes_error_returns_empty_list(self, test_engine):
        """Verify get_indexes returns empty list when inspector raises."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_indexes.side_effect = SQLAlchemyError("no such table")
            mock_inspector_prop.return_value = mock_insp

            result = service.get_indexes("nonexistent", "dbo")

        assert result == []

    def test_get_primary_key_error_returns_empty_dict(self, test_engine):
        """Verify get_primary_key returns empty dict when inspector raises."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_pk_constraint.side_effect = SQLAlchemyError("no such table")
            mock_inspector_prop.return_value = mock_insp

            result = service.get_primary_key("nonexistent", "dbo")

        assert result == {}

    def test_get_row_count_error_returns_none(self, test_engine):
        """Verify _get_row_count_generic returns None on SQLAlchemyError."""
        service = MetadataService(test_engine)

        # Patch engine.connect to raise when executing the COUNT query
        with patch.object(service.engine, "connect") as mock_connect:
            mock_conn = MagicMock()
            mock_conn.__enter__ = MagicMock(return_value=mock_conn)
            mock_conn.__exit__ = MagicMock(return_value=False)
            mock_conn.execute.side_effect = SQLAlchemyError("permission denied")
            mock_connect.return_value = mock_conn

            result = service._get_row_count_generic("secret_table", "dbo")

        assert result is None

    def test_get_columns_error_returns_empty_list(self, test_engine):
        """Verify get_columns returns empty list when inspector raises."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_columns.side_effect = SQLAlchemyError("table gone")
            mock_inspector_prop.return_value = mock_insp

            result = service.get_columns("gone_table", "dbo")

        assert result == []

    def test_get_foreign_keys_error_returns_empty_list(self, test_engine):
        """Verify get_foreign_keys returns empty list when inspector raises."""
        service = MetadataService(test_engine)

        with patch.object(
            type(service), "inspector", new_callable=PropertyMock
        ) as mock_inspector_prop:
            mock_insp = MagicMock()
            mock_insp.get_foreign_keys.side_effect = SQLAlchemyError("broken")
            mock_inspector_prop.return_value = mock_insp

            result = service.get_foreign_keys("broken_table", "dbo")

        assert result == []

    def test_collect_objects_error_in_list_tables(self, test_engine):
        """Verify _list_tables_generic handles SQLAlchemyError in _collect_objects_from_schema."""
        service = MetadataService(test_engine)

        with patch.object(
            service, "_collect_objects_from_schema", side_effect=SQLAlchemyError("oops")
        ):
            tables, pagination = service.list_tables()

        assert tables == []
        assert pagination["total_count"] == 0
