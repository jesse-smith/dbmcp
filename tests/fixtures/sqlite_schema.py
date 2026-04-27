"""SQLite schema builder for generic-dialect Inspector tests.

Provides a minimal schema with PK, FK, and UNIQUE constraints so the generic
dialect path can exercise Inspector.get_columns / get_pk_constraint /
get_unique_constraints / get_foreign_keys against real SQLAlchemy behavior.

Do NOT adapt tests/fixtures/test_db_schema.sql — that file uses MSSQL-specific
syntax (IDENTITY(1,1), GO, NVARCHAR, IF NOT EXISTS EXEC('CREATE SCHEMA ...')).
Maintaining two DDL dialects is explicitly rejected per 13-RESEARCH.md §2.
"""
from sqlalchemy import text
from sqlalchemy.engine import Engine


def load_sqlite_schema(engine: Engine) -> None:
    """Load the shared test schema into an in-memory SQLite engine.

    Schema:
        customers(customer_id PK, name NOT NULL, email UNIQUE)
        orders(order_id PK, customer_id FK -> customers.customer_id, total NUMERIC)
        products(product_id PK, name NOT NULL, sku UNIQUE, price NUMERIC)

    Also seeds a small amount of sample data for row-count assertions.
    """
    assert engine.dialect.name == "sqlite", (
        f"load_sqlite_schema requires a SQLite engine, got {engine.dialect.name!r}"
    )
    with engine.connect() as conn:
        conn.execute(text(
            "CREATE TABLE customers ("
            "customer_id INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "email TEXT UNIQUE"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE orders ("
            "order_id INTEGER PRIMARY KEY, "
            "customer_id INTEGER REFERENCES customers(customer_id), "
            "total NUMERIC"
            ")"
        ))
        conn.execute(text(
            "CREATE TABLE products ("
            "product_id INTEGER PRIMARY KEY, "
            "name TEXT NOT NULL, "
            "sku TEXT UNIQUE, "
            "price NUMERIC"
            ")"
        ))
        conn.execute(text("INSERT INTO customers VALUES (1,'Alice','alice@example.com'),(2,'Bob','bob@example.com')"))
        conn.execute(text("INSERT INTO orders VALUES (1,1,100.00),(2,1,200.00)"))
        conn.execute(text("INSERT INTO products VALUES (1,'Widget','SKU-001',10.00)"))
        conn.commit()
