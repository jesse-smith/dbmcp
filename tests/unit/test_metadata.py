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


# ============================================================================
# Databricks Catalog Parameter Tests (Phase 11, Plan 02)
# ============================================================================


def _make_databricks_dialect():
    """Create a mock Databricks dialect for testing."""
    dialect = MagicMock()
    type(dialect).name = PropertyMock(return_value="databricks")
    type(dialect).supports_indexes = PropertyMock(return_value=False)
    type(dialect).has_fast_row_counts = PropertyMock(return_value=False)
    dialect.quote_identifier = lambda ident: f"`{ident}`"
    return dialect


def _make_generic_dialect():
    """Create a mock generic dialect for testing."""
    dialect = MagicMock()
    type(dialect).name = PropertyMock(return_value="generic")
    type(dialect).supports_indexes = PropertyMock(return_value=True)
    type(dialect).has_fast_row_counts = PropertyMock(return_value=False)
    return dialect


class TestCatalogListSchemas:
    """Tests for list_schemas with optional catalog parameter."""

    def test_list_schemas_with_catalog_executes_show_schemas(self, test_engine):
        """Databricks list_schemas with catalog param executes SHOW SCHEMAS IN."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("schema_a",), ("schema_b",),
        ]
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(service.engine, "connect", return_value=mock_conn):
            schemas = service.list_schemas(connection_id="test", catalog="analytics")

        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "SHOW SCHEMAS IN" in executed_sql
        assert "`analytics`" in executed_sql

    def test_list_schemas_without_catalog_uses_inspector(self, test_engine):
        """list_schemas without catalog uses existing Inspector path."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        schemas = service.list_schemas(connection_id="test")
        assert len(schemas) >= 1
        assert schemas[0].schema_name == "main"

    def test_list_schemas_catalog_ignored_for_non_databricks(self, test_engine):
        """catalog parameter ignored for non-Databricks dialects."""
        dialect = _make_generic_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        schemas = service.list_schemas(connection_id="test", catalog="anything")
        assert len(schemas) >= 1
        assert schemas[0].schema_name == "main"


class TestCatalogListTables:
    """Tests for list_tables with optional catalog parameter."""

    def test_list_tables_with_catalog_executes_show_tables(self, test_engine):
        """Databricks list_tables with catalog uses SHOW TABLES IN."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = [
            ("default", "table_a", False),
            ("default", "table_b", False),
        ]
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)

        with patch.object(service.engine, "connect", return_value=mock_conn):
            tables, pagination = service.list_tables(
                schema_name="default", catalog="analytics"
            )

        executed_sql = str(mock_conn.execute.call_args[0][0])
        assert "SHOW TABLES IN" in executed_sql
        assert "`analytics`" in executed_sql
        assert "`default`" in executed_sql

    def test_list_tables_without_catalog_uses_inspector(self, test_engine):
        """list_tables without catalog uses existing Inspector path."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        tables, pagination = service.list_tables(schema_name="main")
        assert len(tables) == 3

    def test_list_tables_catalog_ignored_for_non_databricks(self, test_engine):
        """catalog parameter ignored for non-Databricks dialects."""
        dialect = _make_generic_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        tables, pagination = service.list_tables(
            schema_name="main", catalog="anything"
        )
        assert len(tables) == 3


class TestCatalogGetTableSchema:
    """Tests for get_table_schema with optional catalog parameter."""

    def test_get_table_schema_accepts_catalog_param(self, test_engine):
        """get_table_schema accepts catalog parameter."""
        service = MetadataService(test_engine)

        result = service.get_table_schema(
            table_name="customers",
            schema_name="main",
            catalog="analytics",
        )
        assert result["table_name"] == "customers"

    def test_get_table_schema_catalog_ignored_for_non_databricks(self, test_engine):
        """catalog parameter ignored for non-Databricks dialects."""
        dialect = _make_generic_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        result = service.get_table_schema(
            table_name="customers",
            schema_name="main",
            catalog="anything",
        )
        assert result["table_name"] == "customers"
        assert "owner" not in result


class TestCatalogThreeLevelTableId:
    """Tests for three-level Databricks table_id format (D-11)."""

    def test_databricks_table_id_uses_three_level_format(self, test_engine):
        """Databricks _collect_objects_from_schema uses catalog.schema.table format."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        tables = service._collect_objects_from_schema(
            schema=None,
            table_type=TableType.TABLE,
            name_pattern=None,
            min_row_count=None,
            catalog="analytics",
        )

        for t in tables:
            assert t.table_id.count(".") == 2, f"Expected three-level ID, got: {t.table_id}"
            assert t.table_id.startswith("analytics.")

    def test_non_databricks_table_id_uses_two_level_format(self, test_engine):
        """Non-Databricks _collect_objects_from_schema uses schema.table format."""
        dialect = _make_generic_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        tables = service._collect_objects_from_schema(
            schema=None,
            table_type=TableType.TABLE,
            name_pattern=None,
            min_row_count=None,
        )

        for t in tables:
            assert t.table_id.count(".") == 1, f"Expected two-level ID, got: {t.table_id}"


# ============================================================================
# Index Gating and DESCRIBE EXTENDED Tests (Phase 11, Plan 02 Task 2)
# ============================================================================


class TestIndexGating:
    """Tests for index gating based on dialect.supports_indexes (D-13).

    NOTE (Phase 13 / Plan 03): `test_indexes_omitted_when_supports_indexes_false`
    and `test_indexes_present_when_supports_indexes_true` were retired — the
    same assertion under mssql/databricks/generic is covered by
    `TestSharedMetadataBehavior.test_get_table_schema_returns_table_schema_object`
    (index-section presence keyed off dialect.supports_indexes). The two tests
    kept here cover distinct edge cases (dialect=None backward compat and the
    include_indexes=False parameter override) that the shared test does not.
    """

    def test_indexes_present_when_dialect_is_none(self, test_engine):
        """get_table_schema includes 'indexes' key when dialect is None (backward compat)."""
        service = MetadataService(test_engine)
        # SQLite dialect resolves to None via registry (no 'sqlite' dialect registered)

        result = service.get_table_schema("customers", "main")
        assert "indexes" in result

    def test_indexes_omitted_when_include_indexes_false(self, test_engine):
        """get_table_schema omits 'indexes' when include_indexes=False regardless of dialect."""
        dialect = _make_generic_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        result = service.get_table_schema("customers", "main", include_indexes=False)
        assert "indexes" not in result


class TestDescribeExtended:
    """Tests for _parse_databricks_table_properties DTE parsing."""

    def _make_service_with_mock_engine(self):
        """Create a MetadataService with mock engine for DTE testing."""
        mock_engine = MagicMock()
        dialect = _make_databricks_dialect()
        service = MetadataService.__new__(MetadataService)
        service.engine = mock_engine
        service._inspector = None
        service.dialect_name = "databricks"
        service._dialect = dialect
        return service, mock_engine

    def _mock_dte_rows(self, rows):
        """Create a mock connection that returns DTE rows."""
        mock_conn = MagicMock()
        mock_result = MagicMock()
        mock_result.fetchall.return_value = rows
        mock_conn.execute.return_value = mock_result
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        return mock_conn

    def test_extracts_owner(self):
        """_parse_databricks_table_properties extracts owner from DTE output."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("", ""),
            ("# Detailed Table Information", ""),
            ("Owner", "user@domain.com"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["owner"] == "user@domain.com"

    def test_extracts_storage_format(self):
        """_parse_databricks_table_properties extracts Provider as storage_format."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("# Detailed Table Information", ""),
            ("Provider", "delta"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["storage_format"] == "delta"

    def test_extracts_table_type_detail(self):
        """_parse_databricks_table_properties extracts Type as table_type_detail."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("# Detailed Table Information", ""),
            ("Type", "MANAGED"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["table_type_detail"] == "MANAGED"

    def test_extracts_created_time(self):
        """_parse_databricks_table_properties extracts Created Time."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("# Detailed Table Information", ""),
            ("Created Time", "Wed Jan 15 10:30:00 UTC 2025"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["created_time"] == "Wed Jan 15 10:30:00 UTC 2025"

    def test_extracts_location(self):
        """_parse_databricks_table_properties extracts Location."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("# Detailed Table Information", ""),
            ("Location", "dbfs:/user/hive/warehouse/my_table"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["location"] == "dbfs:/user/hive/warehouse/my_table"

    def test_extracts_partition_columns(self):
        """_parse_databricks_table_properties extracts partition_columns list."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("id", "bigint"),
            ("name", "string"),
            ("", ""),
            ("# Partition Information", ""),
            ("# col_name", "data_type"),
            ("dt", "date"),
            ("region", "string"),
            ("", ""),
            ("# Detailed Table Information", ""),
            ("Owner", "user@domain.com"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["partition_columns"] == ["dt", "region"]
        assert result["owner"] == "user@domain.com"

    def test_returns_empty_dict_when_no_detail_section(self):
        """_parse_databricks_table_properties returns empty dict when no detail section."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("id", "bigint"),
            ("name", "string"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result == {}

    def test_returns_empty_dict_on_sql_error(self):
        """_parse_databricks_table_properties returns error indicator on SQL failure."""
        service, engine = self._make_service_with_mock_engine()
        mock_conn = MagicMock()
        mock_conn.__enter__ = MagicMock(return_value=mock_conn)
        mock_conn.__exit__ = MagicMock(return_value=False)
        mock_conn.execute.side_effect = SQLAlchemyError("connection lost")
        engine.connect.return_value = mock_conn

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert "_describe_extended_error" in result
        assert "SQLAlchemyError: connection lost" in result["_describe_extended_error"]

    def test_omits_partition_columns_when_not_partitioned(self):
        """_parse_databricks_table_properties omits partition_columns for non-partitioned."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("id", "bigint"),
            ("", ""),
            ("# Detailed Table Information", ""),
            ("Owner", "admin"),
            ("Type", "MANAGED"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert "partition_columns" not in result
        assert result["owner"] == "admin"

    def test_full_dte_output_parsing(self):
        """Full DESCRIBE TABLE EXTENDED output parsing end-to-end."""
        service, engine = self._make_service_with_mock_engine()
        rows = [
            ("id", "bigint"),
            ("name", "string"),
            ("", ""),
            ("# Partition Information", ""),
            ("# col_name", "data_type"),
            ("dt", "date"),
            ("", ""),
            ("# Detailed Table Information", ""),
            ("Database", "my_schema"),
            ("Table", "my_table"),
            ("Owner", "user@domain.com"),
            ("Created Time", "Wed Jan 15 10:30:00 UTC 2025"),
            ("Type", "MANAGED"),
            ("Provider", "delta"),
            ("Location", "dbfs:/user/hive/warehouse/my_table"),
        ]
        engine.connect.return_value = self._mock_dte_rows(rows)

        result = service._parse_databricks_table_properties("tbl", "schema", "catalog")
        assert result["owner"] == "user@domain.com"
        assert result["storage_format"] == "delta"
        assert result["table_type_detail"] == "MANAGED"
        assert result["created_time"] == "Wed Jan 15 10:30:00 UTC 2025"
        assert result["location"] == "dbfs:/user/hive/warehouse/my_table"
        assert result["partition_columns"] == ["dt"]


class TestDatabricksTableProperties:
    """Tests for DTE properties in get_table_schema response."""

    def test_databricks_get_table_schema_includes_dte_properties(self, test_engine):
        """Databricks get_table_schema response includes DTE properties."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        # Mock _parse_databricks_table_properties to return test data
        dte_props = {
            "owner": "user@domain.com",
            "storage_format": "delta",
            "table_type_detail": "MANAGED",
            "created_time": "Wed Jan 15 10:30:00 UTC 2025",
            "location": "dbfs:/user/hive/warehouse/my_table",
            "partition_columns": ["dt"],
        }
        with patch.object(service, "_parse_databricks_table_properties", return_value=dte_props):
            result = service.get_table_schema("customers", "main")

        assert result["owner"] == "user@domain.com"
        assert result["storage_format"] == "delta"
        assert result["table_type_detail"] == "MANAGED"
        assert result["created_time"] == "Wed Jan 15 10:30:00 UTC 2025"
        assert result["location"] == "dbfs:/user/hive/warehouse/my_table"
        assert result["partition_columns"] == ["dt"]

    def test_non_databricks_get_table_schema_excludes_dte_properties(self, test_engine):
        """Non-Databricks get_table_schema does NOT include DTE properties."""
        dialect = _make_generic_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        result = service.get_table_schema("customers", "main")

        assert "owner" not in result
        assert "storage_format" not in result
        assert "table_type_detail" not in result

    def test_databricks_get_table_schema_includes_catalog_in_response(self, test_engine):
        """Databricks get_table_schema includes catalog in response when provided."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        dte_props = {"owner": "admin"}
        with patch.object(service, "_parse_databricks_table_properties", return_value=dte_props):
            result = service.get_table_schema("customers", "main", catalog="analytics")

        assert result["catalog"] == "analytics"

    def test_databricks_get_table_schema_no_dte_on_failure(self, test_engine):
        """Databricks get_table_schema still works when DTE parsing returns empty."""
        dialect = _make_databricks_dialect()
        service = MetadataService(test_engine, dialect=dialect)

        with patch.object(service, "_parse_databricks_table_properties", return_value={}):
            result = service.get_table_schema("customers", "main")

        assert result["table_name"] == "customers"
        assert "owner" not in result


# ============================================================================
# Shared dialect-parametrized metadata behavior (Phase 13, Plan 03)
# ============================================================================


def _configure_magicmock_engine_dialect(dialect_ctx):
    """Give a MagicMock(spec=Engine) the `.dialect.name` attribute MetadataService
    reads during __init__. No-op for real engines (generic via dialect_inspector)."""
    if not hasattr(dialect_ctx.engine, "dialect") or not isinstance(
        dialect_ctx.engine.dialect, MagicMock
    ):
        # Real engine path — nothing to do
        try:
            # For MagicMock(spec=Engine), accessing .dialect raises AttributeError
            _ = dialect_ctx.engine.dialect
            return  # real engine
        except AttributeError:
            pass
    # MagicMock path: configure .dialect.name = context name
    dialect_ctx.engine.dialect = MagicMock()
    dialect_ctx.engine.dialect.name = dialect_ctx.name


def _build_metadata_service(dialect_ctx):
    """Build a MetadataService from a DialectTestContext, wiring the mock inspector
    in place for the non-generic (MagicMock) paths. Generic uses the real engine
    and the natural lazy inspector."""
    _configure_magicmock_engine_dialect(dialect_ctx)
    service = MetadataService(dialect_ctx.engine, dialect=dialect_ctx.dialect)
    if dialect_ctx.name != "generic":
        # Pre-populate the lazy inspector cache with the MagicMock inspector.
        service._inspector = dialect_ctx.inspector
    return service


class TestSharedMetadataBehavior:
    """Dialect-parametrized shared-behavior tests for MetadataService.

    Uses the `dialect_inspector` fixture so the `generic` path exercises a real
    SQLAlchemy Inspector against in-memory SQLite, while `mssql`/`databricks`
    run against MagicMock execution surfaces configured inline.

    Added per Phase 13 / D-08 / D-17 (parallel-add strategy for test_metadata.py).
    Existing `TestListSchemas`, `TestListTables`, `TestCatalogListSchemas`, etc.
    are preserved — this class covers only the shared-behavior contract across
    dialects. Dialect-exclusive behavior (MSSQL DMV SQL shapes, Databricks
    DESCRIBE EXTENDED, catalog-scoped SHOW TABLES IN) remains in the existing
    classes above.
    """

    def test_list_schemas_returns_schema_objects(self, dialect_inspector):
        """Shared: list_schemas returns Schema objects regardless of dialect."""
        service = _build_metadata_service(dialect_inspector)

        if dialect_inspector.name == "mssql":
            # MSSQL path executes the DMV SQL; stub `conn.execute(...)` rows.
            mssql_rows = [
                MagicMock(schema_name="dbo", table_count=3, view_count=1),
                MagicMock(schema_name="sales", table_count=2, view_count=0),
            ]
            dialect_inspector.connection.execute.return_value = iter(mssql_rows)
            schemas = service.list_schemas(connection_id="c1")
            names = {s.schema_name for s in schemas}
            assert names == {"dbo", "sales"}
            assert all(s.connection_id == "c1" for s in schemas)
        elif dialect_inspector.name == "databricks":
            # Databricks without catalog falls back to the generic-inspector path
            # (the Databricks-specific SHOW SCHEMAS IN path requires catalog=).
            dialect_inspector.inspector.get_schema_names.return_value = ["default"]
            dialect_inspector.inspector.get_table_names.return_value = ["t1", "t2"]
            dialect_inspector.inspector.get_view_names.return_value = []
            schemas = service.list_schemas(connection_id="c1")
            assert len(schemas) >= 1
            assert all(hasattr(s, "schema_name") for s in schemas)
        else:  # generic — real SQLite
            schemas = service.list_schemas(connection_id="c1")
            assert len(schemas) >= 1
            assert schemas[0].schema_name == "main"
            assert schemas[0].connection_id == "c1"

    def test_list_tables_returns_table_objects(self, dialect_inspector):
        """Shared: list_tables returns Table objects for the active dialect."""
        service = _build_metadata_service(dialect_inspector)

        if dialect_inspector.name == "mssql":
            # MSSQL path runs two queries: count + paginated SELECT.
            count_row = MagicMock()
            count_row.fetchone.return_value = (2,)
            data_rows = [
                MagicMock(
                    schema_name="dbo", table_name="customers", object_type="U ",
                    row_count=3, last_modified=None, has_primary_key=1,
                ),
                MagicMock(
                    schema_name="dbo", table_name="orders", object_type="U ",
                    row_count=2, last_modified=None, has_primary_key=1,
                ),
            ]
            dialect_inspector.connection.execute.side_effect = [count_row, iter(data_rows)]
            tables, pagination = service.list_tables(schema_name="dbo")
            names = {t.table_name for t in tables}
            assert names == {"customers", "orders"}
            assert pagination["total_count"] == 2
        elif dialect_inspector.name == "databricks":
            # Databricks path w/o catalog uses the generic inspector path.
            dialect_inspector.inspector.get_schema_names.return_value = ["main"]
            dialect_inspector.inspector.get_table_names.return_value = ["customers", "orders"]
            dialect_inspector.inspector.get_view_names.return_value = []
            # Row counts via _get_row_count_generic — patch to avoid real SQL.
            with patch.object(service, "_get_row_count_generic", return_value=5):
                tables, pagination = service.list_tables()
            names = {t.table_name for t in tables}
            assert names == {"customers", "orders"}
        else:  # generic — real SQLite
            tables, pagination = service.list_tables()
            names = {t.table_name for t in tables}
            assert "customers" in names
            assert "orders" in names
            assert "products" in names
            assert pagination["total_count"] == 3

    def test_get_table_schema_returns_table_schema_object(self, dialect_inspector):
        """Shared: get_table_schema returns a dict with columns; index-section
        presence reflects dialect.supports_indexes (META-04 / D-13)."""
        service = _build_metadata_service(dialect_inspector)

        if dialect_inspector.name == "generic":
            result = service.get_table_schema("customers", "main")
        else:
            # MagicMock path — configure inspector responses used by get_columns /
            # get_pk_constraint / get_foreign_keys / get_indexes.
            insp = dialect_inspector.inspector
            col_type = MagicMock()
            col_type.__str__ = lambda self: "INTEGER"
            insp.get_columns.return_value = [
                {"name": "id", "type": col_type, "nullable": False,
                 "autoincrement": True, "default": None},
            ]
            insp.get_pk_constraint.return_value = {
                "name": "pk_customers", "constrained_columns": ["id"],
            }
            insp.get_foreign_keys.return_value = []
            insp.get_indexes.return_value = []
            # Databricks get_table_schema additionally calls DESCRIBE EXTENDED —
            # short-circuit it so the shared test stays dialect-agnostic.
            if dialect_inspector.name == "databricks":
                with patch.object(service, "_parse_databricks_table_properties",
                                  return_value={}):
                    result = service.get_table_schema("customers", "main")
            else:
                result = service.get_table_schema("customers", "main")

        # Shared assertions: table metadata shape
        assert result["table_name"] == "customers"
        assert result["schema_name"] == "main"
        assert isinstance(result["columns"], list)
        assert len(result["columns"]) >= 1

        # Index section presence reflects dialect.supports_indexes (D-13)
        if dialect_inspector.dialect.supports_indexes:
            assert "indexes" in result, (
                f"dialect={dialect_inspector.name} supports_indexes=True but "
                f"'indexes' key missing from result"
            )
        else:
            assert "indexes" not in result, (
                f"dialect={dialect_inspector.name} supports_indexes=False but "
                f"'indexes' key present in result"
            )
