"""Pytest configuration and shared fixtures for dbmcp tests.

This module provides fixtures for:
- Mock database connections
- Test metadata services
- Sample data for unit tests
"""

from unittest.mock import MagicMock

import pytest

from src.db.connection import ConnectionManager
from src.models.schema import (
    AuthenticationMethod,
    Column,
    Connection,
    Index,
    Schema,
    Table,
    TableType,
)

# =============================================================================
# Mock Connection Fixtures
# =============================================================================


@pytest.fixture
def mock_engine():
    """Create a mock SQLAlchemy engine."""
    engine = MagicMock()
    engine.connect.return_value.__enter__ = MagicMock()
    engine.connect.return_value.__exit__ = MagicMock()
    return engine


@pytest.fixture
def mock_connection():
    """Create a mock Connection object."""
    return Connection(
        connection_id="test123abc",
        server="localhost",
        database="TestDB",
        port=1433,
        authentication_method=AuthenticationMethod.SQL,
        username="testuser",
    )


@pytest.fixture
def connection_manager():
    """Create a fresh ConnectionManager instance."""
    return ConnectionManager()


# =============================================================================
# Sample Metadata Fixtures
# =============================================================================


@pytest.fixture
def sample_schemas():
    """Sample schema data for testing."""
    return [
        Schema(
            schema_id="test_dbo",
            connection_id="test123abc",
            schema_name="dbo",
            table_count=10,
            view_count=2,
        ),
        Schema(
            schema_id="test_sales",
            connection_id="test123abc",
            schema_name="sales",
            table_count=5,
            view_count=1,
        ),
        Schema(
            schema_id="test_hr",
            connection_id="test123abc",
            schema_name="hr",
            table_count=3,
            view_count=0,
        ),
    ]


@pytest.fixture
def sample_tables():
    """Sample table data for testing."""
    return [
        Table(
            table_id="dbo.Customers",
            schema_id="dbo",
            table_name="Customers",
            table_type=TableType.TABLE,
            row_count=10000,
            has_primary_key=True,
            access_denied=False,
        ),
        Table(
            table_id="dbo.Orders",
            schema_id="dbo",
            table_name="Orders",
            table_type=TableType.TABLE,
            row_count=50000,
            has_primary_key=True,
            access_denied=False,
        ),
        Table(
            table_id="dbo.Products",
            schema_id="dbo",
            table_name="Products",
            table_type=TableType.TABLE,
            row_count=500,
            has_primary_key=True,
            access_denied=False,
        ),
        Table(
            table_id="hr.Employees",
            schema_id="hr",
            table_name="Employees",
            table_type=TableType.TABLE,
            row_count=100,
            has_primary_key=True,
            access_denied=False,
        ),
        Table(
            table_id="hr.Salaries",
            schema_id="hr",
            table_name="Salaries",
            table_type=TableType.TABLE,
            row_count=None,
            has_primary_key=True,
            access_denied=True,  # No permission
        ),
    ]


@pytest.fixture
def sample_columns():
    """Sample column data for testing."""
    return [
        Column(
            column_id="dbo.Customers.CustomerID",
            table_id="dbo.Customers",
            column_name="CustomerID",
            ordinal_position=1,
            data_type="INT",
            is_nullable=False,
            is_identity=True,
            is_primary_key=True,
            is_foreign_key=False,
        ),
        Column(
            column_id="dbo.Customers.CustomerName",
            table_id="dbo.Customers",
            column_name="CustomerName",
            ordinal_position=2,
            data_type="VARCHAR(100)",
            max_length=100,
            is_nullable=False,
            is_primary_key=False,
            is_foreign_key=False,
        ),
        Column(
            column_id="dbo.Customers.Status",
            table_id="dbo.Customers",
            column_name="Status",
            ordinal_position=3,
            data_type="VARCHAR(20)",
            max_length=20,
            is_nullable=True,
            is_primary_key=False,
            is_foreign_key=False,
        ),
        Column(
            column_id="dbo.Orders.OrderID",
            table_id="dbo.Orders",
            column_name="OrderID",
            ordinal_position=1,
            data_type="INT",
            is_nullable=False,
            is_identity=True,
            is_primary_key=True,
            is_foreign_key=False,
        ),
        Column(
            column_id="dbo.Orders.CustomerID",
            table_id="dbo.Orders",
            column_name="CustomerID",
            ordinal_position=2,
            data_type="INT",
            is_nullable=True,
            is_primary_key=False,
            is_foreign_key=True,
        ),
    ]


@pytest.fixture
def sample_indexes():
    """Sample index data for testing."""
    return [
        Index(
            index_id="dbo.Customers.PK_Customers",
            table_id="dbo.Customers",
            index_name="PK_Customers",
            is_unique=True,
            is_primary_key=True,
            is_clustered=True,
            columns=["CustomerID"],
        ),
        Index(
            index_id="dbo.Orders.PK_Orders",
            table_id="dbo.Orders",
            index_name="PK_Orders",
            is_unique=True,
            is_primary_key=True,
            is_clustered=True,
            columns=["OrderID"],
        ),
        Index(
            index_id="dbo.Orders.IX_Orders_CustomerID",
            table_id="dbo.Orders",
            index_name="IX_Orders_CustomerID",
            is_unique=False,
            is_primary_key=False,
            is_clustered=False,
            columns=["CustomerID"],
        ),
    ]


# =============================================================================
# Mock Inspector Fixture
# =============================================================================


@pytest.fixture
def mock_inspector(sample_columns, sample_indexes):
    """Create a mock SQLAlchemy inspector with sample data."""
    inspector = MagicMock()

    # Mock get_table_names
    inspector.get_table_names.return_value = ["Customers", "Orders", "Products"]

    # Mock get_columns
    def mock_get_columns(table_name, schema=None):
        columns_data = {
            "Customers": [
                {"name": "CustomerID", "type": MagicMock(__str__=lambda x: "INTEGER"), "nullable": False, "autoincrement": True, "default": None},
                {"name": "CustomerName", "type": MagicMock(__str__=lambda x: "VARCHAR(100)"), "nullable": False, "autoincrement": False, "default": None},
                {"name": "Status", "type": MagicMock(__str__=lambda x: "VARCHAR(20)"), "nullable": True, "autoincrement": False, "default": None},
            ],
            "Orders": [
                {"name": "OrderID", "type": MagicMock(__str__=lambda x: "INTEGER"), "nullable": False, "autoincrement": True, "default": None},
                {"name": "CustomerID", "type": MagicMock(__str__=lambda x: "INTEGER"), "nullable": True, "autoincrement": False, "default": None},
                {"name": "OrderDate", "type": MagicMock(__str__=lambda x: "DATETIME"), "nullable": False, "autoincrement": False, "default": None},
            ],
        }
        return columns_data.get(table_name, [])

    inspector.get_columns.side_effect = mock_get_columns

    # Mock get_pk_constraint
    def mock_get_pk_constraint(table_name, schema=None):
        pk_data = {
            "Customers": {"name": "PK_Customers", "constrained_columns": ["CustomerID"]},
            "Orders": {"name": "PK_Orders", "constrained_columns": ["OrderID"]},
        }
        return pk_data.get(table_name, {"constrained_columns": []})

    inspector.get_pk_constraint.side_effect = mock_get_pk_constraint

    # Mock get_indexes
    def mock_get_indexes(table_name, schema=None):
        index_data = {
            "Customers": [
                {"name": "PK_Customers", "unique": True, "clustered": True, "column_names": ["CustomerID"]},
            ],
            "Orders": [
                {"name": "PK_Orders", "unique": True, "clustered": True, "column_names": ["OrderID"]},
                {"name": "IX_Orders_CustomerID", "unique": False, "clustered": False, "column_names": ["CustomerID"]},
            ],
        }
        return index_data.get(table_name, [])

    inspector.get_indexes.side_effect = mock_get_indexes

    # Mock get_foreign_keys
    def mock_get_foreign_keys(table_name, schema=None):
        fk_data = {
            "Orders": [
                {
                    "name": "FK_Orders_Customers",
                    "constrained_columns": ["CustomerID"],
                    "referred_schema": "dbo",
                    "referred_table": "Customers",
                    "referred_columns": ["CustomerID"],
                },
            ],
        }
        return fk_data.get(table_name, [])

    inspector.get_foreign_keys.side_effect = mock_get_foreign_keys

    return inspector


# =============================================================================
# Integration Test Markers
# =============================================================================


def pytest_configure(config):
    """Register custom markers."""
    config.addinivalue_line(
        "markers", "integration: marks tests as integration tests requiring database"
    )
    config.addinivalue_line(
        "markers", "slow: marks tests as slow running"
    )
