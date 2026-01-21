"""Tests for example database setup."""
import sqlite3
from pathlib import Path

import pytest


@pytest.fixture(scope="module")
def test_db_path():
    """Path to test database."""
    return "examples/test_database/example.db"


def test_database_file_exists(test_db_path):
    """Verify database file was created."""
    assert Path(test_db_path).exists(), f"Database file should exist at {test_db_path}"


def test_database_schema_creates_all_tables(test_db_path):
    """Verify all 6 tables are created."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
    tables = [row[0] for row in cursor.fetchall()]

    expected = ["customers", "order_items", "orders", "product_reviews", "products", "shipping_addresses"]
    assert tables == expected, f"Expected tables {expected}, got {tables}"

    conn.close()


def test_database_has_sample_data(test_db_path):
    """Verify sample data is populated."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    # Check record counts
    cursor.execute("SELECT COUNT(*) FROM customers")
    assert cursor.fetchone()[0] == 10, "Should have 10 customers"

    cursor.execute("SELECT COUNT(*) FROM products")
    assert cursor.fetchone()[0] == 20, "Should have 20 products"

    cursor.execute("SELECT COUNT(*) FROM orders")
    assert cursor.fetchone()[0] >= 10, "Should have at least 10 orders"

    cursor.execute("SELECT COUNT(*) FROM order_items")
    assert cursor.fetchone()[0] >= 15, "Should have at least 15 order items"

    cursor.execute("SELECT COUNT(*) FROM shipping_addresses")
    assert cursor.fetchone()[0] >= 10, "Should have at least 10 shipping addresses"

    cursor.execute("SELECT COUNT(*) FROM product_reviews")
    assert cursor.fetchone()[0] >= 15, "Should have at least 15 product reviews"

    conn.close()


def test_database_foreign_keys(test_db_path):
    """Verify declared foreign key constraints."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    # Check orders table has FK to customers
    cursor.execute("PRAGMA foreign_key_list(orders)")
    fks = cursor.fetchall()
    assert len(fks) == 1, "orders should have 1 FK"
    assert fks[0][2] == "customers", "FK should reference customers"

    # Check order_items has 2 FKs
    cursor.execute("PRAGMA foreign_key_list(order_items)")
    fks = cursor.fetchall()
    assert len(fks) == 2, "order_items should have 2 FKs"

    # Verify FK references
    fk_tables = {fk[2] for fk in fks}
    assert "orders" in fk_tables, "order_items should reference orders"
    assert "products" in fk_tables, "order_items should reference products"

    conn.close()


def test_database_undeclared_relationships(test_db_path):
    """Verify undeclared relationships have no FK constraints (for inference testing)."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    # Verify shipping_addresses has NO FK constraint
    cursor.execute("PRAGMA foreign_key_list(shipping_addresses)")
    fks = cursor.fetchall()
    assert len(fks) == 0, "shipping_addresses should have no declared FKs (for inference testing)"

    # Verify product_reviews has NO FK constraints
    cursor.execute("PRAGMA foreign_key_list(product_reviews)")
    fks = cursor.fetchall()
    assert len(fks) == 0, "product_reviews should have no declared FKs (for inference testing)"

    conn.close()


def test_database_data_integrity(test_db_path):
    """Verify referential integrity (all IDs reference valid records)."""
    conn = sqlite3.connect(test_db_path)
    cursor = conn.cursor()

    # Check shipping_addresses customer_id references valid customers
    cursor.execute(
        """
        SELECT COUNT(*) FROM shipping_addresses
        WHERE customer_id NOT IN (SELECT customer_id FROM customers)
    """
    )
    assert cursor.fetchone()[0] == 0, "All shipping addresses should reference valid customers"

    # Check product_reviews customer_id references valid customers
    cursor.execute(
        """
        SELECT COUNT(*) FROM product_reviews
        WHERE customer_id NOT IN (SELECT customer_id FROM customers)
    """
    )
    assert cursor.fetchone()[0] == 0, "All reviews should reference valid customers"

    # Check product_reviews product_id references valid products
    cursor.execute(
        """
        SELECT COUNT(*) FROM product_reviews
        WHERE product_id NOT IN (SELECT product_id FROM products)
    """
    )
    assert cursor.fetchone()[0] == 0, "All reviews should reference valid products"

    conn.close()
