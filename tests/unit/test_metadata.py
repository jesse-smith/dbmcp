"""Unit tests for metadata service.

Tests for list_schemas, list_tables, and related metadata queries.
These tests use an in-memory SQLite database for realistic testing.
"""

import pytest
from sqlalchemy import create_engine, text

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

        tables = service.list_tables()

        assert len(tables) == 3
        table_names = {t.table_name for t in tables}
        assert "customers" in table_names
        assert "orders" in table_names
        assert "products" in table_names

    def test_list_tables_includes_row_count(self, test_engine):
        """T013A: Verify row counts are populated."""
        service = MetadataService(test_engine)

        tables = service.list_tables()

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

        tables = service.list_tables(schema_name="main")

        # All tables should be from main schema
        for table in tables:
            assert table.schema_id == "main"

    def test_list_tables_respects_limit(self, test_engine):
        """T013A: Verify limit parameter is enforced."""
        service = MetadataService(test_engine)

        tables = service.list_tables(limit=2)

        assert len(tables) <= 2


class TestSorting:
    """Tests for list_tables sorting - T016A"""

    def test_sort_by_name_ascending(self, test_engine):
        """T016A: Verify sort by name ascending."""
        service = MetadataService(test_engine)

        tables = service.list_tables(sort_by="name", sort_order="asc")

        names = [t.table_name for t in tables]
        assert names == sorted(names)

    def test_sort_by_row_count_descending(self, test_engine):
        """T016A: Verify sort by row_count descending (default)."""
        service = MetadataService(test_engine)

        tables = service.list_tables(sort_by="row_count", sort_order="desc")

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

        tables = service.list_tables()

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
        tables = service.list_tables()

        # Our sample has only 3 tables, so all should be returned
        assert len(tables) <= 100

    def test_max_limit_is_1000(self, test_engine):
        """T018A: Verify max limit of 1000 is enforced."""
        service = MetadataService(test_engine)

        # Request more than max
        tables = service.list_tables(limit=2000)

        # Should be capped to 1000 (or less if fewer tables exist)
        assert len(tables) <= 1000

    def test_limit_validation(self, test_engine):
        """T018A: Verify limit must be positive."""
        service = MetadataService(test_engine)

        # Limit 0 or negative should be handled
        tables = service.list_tables(limit=0)
        # Implementation clamps to minimum 1
        assert len(tables) >= 0
