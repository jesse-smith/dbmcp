"""Shared fixtures for integration tests.

Centralizes fixtures previously duplicated across test_caching.py,
test_sample_data.py, and test_fk_inference.py.

Note: These fixtures use dict-organized structures (tables by schema,
columns by table) matching the DocumentationStorage API. The root
conftest.py provides list-organized versions for unit tests.
"""

import tempfile
from pathlib import Path

import pytest

from src.models.relationship import DeclaredFK, InferredFK, RelationshipType
from src.models.schema import Column, Schema, Table, TableType


@pytest.fixture
def temp_cache_dir():
    """Create a temporary directory for cache storage."""
    with tempfile.TemporaryDirectory() as tmpdir:
        yield Path(tmpdir)


@pytest.fixture
def sample_schemas():
    """Sample schema objects for integration testing.

    Single-schema setup matching a simple database layout.
    """
    return [
        Schema(
            schema_id="conn1:main",
            schema_name="main",
            connection_id="conn1",
            table_count=3,
            view_count=0,
        ),
    ]


@pytest.fixture
def sample_tables():
    """Sample table objects organized by schema name.

    Returns a dict[str, list[Table]] matching the DocumentationStorage API.
    """
    return {
        "main": [
            Table(
                table_id="main.customers",
                schema_id="main",
                table_name="customers",
                table_type=TableType.TABLE,
                row_count=100,
                has_primary_key=True,
            ),
            Table(
                table_id="main.orders",
                schema_id="main",
                table_name="orders",
                table_type=TableType.TABLE,
                row_count=500,
                has_primary_key=True,
            ),
            Table(
                table_id="main.products",
                schema_id="main",
                table_name="products",
                table_type=TableType.TABLE,
                row_count=50,
                has_primary_key=True,
            ),
        ],
    }


@pytest.fixture
def sample_columns():
    """Sample column objects organized by table ID.

    Returns a dict[str, list[Column]] matching the DocumentationStorage API.
    """
    return {
        "main.customers": [
            Column(column_id="main.customers.customer_id", table_id="main.customers", column_name="customer_id", data_type="INTEGER", is_nullable=False, is_primary_key=True, ordinal_position=1),
            Column(column_id="main.customers.name", table_id="main.customers", column_name="name", data_type="VARCHAR(100)", is_nullable=False, ordinal_position=2),
        ],
        "main.orders": [
            Column(column_id="main.orders.order_id", table_id="main.orders", column_name="order_id", data_type="INTEGER", is_nullable=False, is_primary_key=True, ordinal_position=1),
            Column(column_id="main.orders.customer_id", table_id="main.orders", column_name="customer_id", data_type="INTEGER", is_nullable=False, ordinal_position=2),
            Column(column_id="main.orders.total", table_id="main.orders", column_name="total", data_type="DECIMAL(10,2)", is_nullable=False, ordinal_position=3),
        ],
        "main.products": [
            Column(column_id="main.products.product_id", table_id="main.products", column_name="product_id", data_type="INTEGER", is_nullable=False, is_primary_key=True, ordinal_position=1),
            Column(column_id="main.products.name", table_id="main.products", column_name="name", data_type="VARCHAR(100)", is_nullable=False, ordinal_position=2),
            Column(column_id="main.products.price", table_id="main.products", column_name="price", data_type="DECIMAL(10,2)", is_nullable=False, ordinal_position=3),
        ],
    }


@pytest.fixture
def sample_declared_fks():
    """Sample declared foreign keys for integration testing."""
    return [
        DeclaredFK(
            relationship_id="fk_orders_customers",
            source_table_id="main.orders",
            source_column="customer_id",
            target_table_id="main.customers",
            target_column="customer_id",
            relationship_type=RelationshipType.DECLARED,
            constraint_name="fk_orders_customers",
        ),
    ]


@pytest.fixture
def sample_inferred_fks():
    """Sample inferred foreign keys for integration testing."""
    return [
        InferredFK(
            relationship_id="inferred_order_items_products",
            source_table_id="main.order_items",
            source_column="product_id",
            target_table_id="main.products",
            target_column="product_id",
            relationship_type=RelationshipType.INFERRED,
            confidence_score=0.92,
            reasoning="Name match; PK target; type compatible",
        ),
    ]
