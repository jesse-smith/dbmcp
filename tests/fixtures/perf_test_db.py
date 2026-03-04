"""Performance test database fixture generator.

T121: Creates test databases with configurable scale for performance testing.

This module provides utilities to create SQLite databases with varying numbers
of tables and rows for NFR validation testing.

Usage:
    from tests.fixtures.perf_test_db import create_performance_db

    # Create a database with 100 tables
    engine = create_performance_db(table_count=100)

    # Create with specific row counts
    engine = create_performance_db(
        table_count=50,
        min_rows=0,
        max_rows=10000,
    )
"""

import random
from datetime import datetime, timedelta
from typing import Any

from sqlalchemy import create_engine, text
from sqlalchemy.engine import Engine


def create_performance_db(
    table_count: int = 100,
    min_rows: int = 0,
    max_rows: int = 1000,
    seed: int = 42,
    db_path: str | None = None,
) -> Engine:
    """Create a test database with specified number of tables.

    Args:
        table_count: Number of tables to create (default: 100)
        min_rows: Minimum rows per table (default: 0)
        max_rows: Maximum rows per table (default: 1000)
        seed: Random seed for reproducibility (default: 42)
        db_path: Path to SQLite database file, or None for in-memory

    Returns:
        SQLAlchemy engine connected to the test database

    Example table distribution for 1000 tables:
        - ~10% empty tables (0 rows)
        - ~30% small tables (1-100 rows)
        - ~40% medium tables (100-10000 rows)
        - ~20% large tables (10000-100000 rows)
    """
    random.seed(seed)

    # Create engine
    if db_path:
        engine = create_engine(f"sqlite:///{db_path}", echo=False)
    else:
        engine = create_engine("sqlite:///:memory:", echo=False)

    # Table templates with varying column counts
    table_templates = [
        # Simple 3-column table
        {
            "columns": [
                ("id", "INTEGER PRIMARY KEY"),
                ("name", "TEXT NOT NULL"),
                ("value", "REAL"),
            ],
            "has_pk": True,
        },
        # Customer-like table
        {
            "columns": [
                ("customer_id", "INTEGER PRIMARY KEY"),
                ("first_name", "TEXT"),
                ("last_name", "TEXT"),
                ("email", "TEXT"),
                ("created_at", "TEXT"),
                ("status", "TEXT DEFAULT 'active'"),
            ],
            "has_pk": True,
        },
        # Order-like table (with FK pattern)
        {
            "columns": [
                ("order_id", "INTEGER PRIMARY KEY"),
                ("customer_id", "INTEGER"),
                ("order_date", "TEXT"),
                ("total", "REAL"),
                ("status", "TEXT"),
            ],
            "has_pk": True,
        },
        # Product-like table
        {
            "columns": [
                ("product_id", "INTEGER PRIMARY KEY"),
                ("sku", "TEXT UNIQUE"),
                ("name", "TEXT NOT NULL"),
                ("description", "TEXT"),
                ("price", "REAL"),
                ("quantity", "INTEGER"),
                ("category_id", "INTEGER"),
            ],
            "has_pk": True,
        },
        # Audit/log-like table (no explicit PK)
        {
            "columns": [
                ("log_id", "INTEGER PRIMARY KEY AUTOINCREMENT"),
                ("event_type", "TEXT"),
                ("event_data", "TEXT"),
                ("created_at", "TEXT"),
                ("user_id", "INTEGER"),
            ],
            "has_pk": True,
        },
        # Junction/mapping table
        {
            "columns": [
                ("id", "INTEGER PRIMARY KEY"),
                ("left_id", "INTEGER NOT NULL"),
                ("right_id", "INTEGER NOT NULL"),
            ],
            "has_pk": True,
        },
    ]

    with engine.connect() as conn:
        for i in range(table_count):
            # Select template based on table number
            template = table_templates[i % len(table_templates)]

            # Generate table name
            table_name = f"perf_test_{i:04d}"

            # Create table
            columns_sql = ", ".join(
                f"{name} {definition}"
                for name, definition in template["columns"]
            )
            conn.execute(text(f"CREATE TABLE {table_name} ({columns_sql})"))

            # Determine row count for this table
            row_count = random.randint(min_rows, max_rows)

            # Insert sample data
            if row_count > 0:
                _insert_sample_data(conn, table_name, template["columns"], row_count)

        conn.commit()

    return engine


def _insert_sample_data(
    conn,
    table_name: str,
    columns: list[tuple[str, str]],
    row_count: int,
):
    """Insert sample data into a table.

    Args:
        conn: Database connection
        table_name: Name of the table
        columns: List of (column_name, definition) tuples
        row_count: Number of rows to insert
    """
    # Filter out auto-increment columns from insert
    insert_columns = [
        (name, defn) for name, defn in columns
        if "AUTOINCREMENT" not in defn.upper()
    ]

    column_names = [name for name, _ in insert_columns]

    # Insert in batches for efficiency
    batch_size = 100
    for batch_start in range(0, row_count, batch_size):
        batch_end = min(batch_start + batch_size, row_count)
        values_list = []

        for row_idx in range(batch_start, batch_end):
            values = []
            for name, defn in insert_columns:
                values.append(_generate_value(name, defn, row_idx))
            values_list.append(f"({', '.join(str(v) for v in values)})")

        if values_list:
            sql = f"INSERT INTO {table_name} ({', '.join(column_names)}) VALUES {', '.join(values_list)}"
            conn.execute(text(sql))


def _generate_value(column_name: str, definition: str, row_idx: int) -> Any:
    """Generate a sample value for a column.

    Args:
        column_name: Name of the column
        definition: Column definition
        row_idx: Row index for generating unique values

    Returns:
        Generated value (formatted for SQL)
    """
    defn_upper = definition.upper()

    # Primary key columns
    if "PRIMARY KEY" in defn_upper and "id" in column_name.lower():
        return row_idx + 1

    # Foreign key-like columns (ending in _id)
    if column_name.lower().endswith("_id") and "PRIMARY KEY" not in defn_upper:
        return random.randint(1, 100)

    # Text columns
    if "TEXT" in defn_upper:
        if "email" in column_name.lower():
            return f"'user_{row_idx}@example.com'"
        elif "name" in column_name.lower():
            return f"'Name_{row_idx}'"
        elif "status" in column_name.lower():
            return f"'{random.choice(['active', 'pending', 'closed'])}'"
        elif "date" in column_name.lower() or "created_at" in column_name.lower():
            date = datetime.now() - timedelta(days=random.randint(0, 365))
            return f"'{date.isoformat()}'"
        elif "sku" in column_name.lower():
            return f"'SKU-{row_idx:06d}'"
        elif "description" in column_name.lower() or "data" in column_name.lower():
            return f"'Sample text content for row {row_idx}'"
        else:
            return f"'value_{row_idx}'"

    # Real/float columns
    if "REAL" in defn_upper:
        if "price" in column_name.lower() or "total" in column_name.lower():
            return round(random.uniform(1.0, 1000.0), 2)
        else:
            return round(random.uniform(0.0, 100.0), 4)

    # Integer columns
    if "INTEGER" in defn_upper:
        if "quantity" in column_name.lower():
            return random.randint(0, 1000)
        else:
            return random.randint(1, 10000)

    # Default
    return "NULL"


def create_large_test_db(table_count: int = 1000, db_path: str | None = None) -> Engine:
    """Create a large test database matching NFR-001 requirements.

    Creates a database with 1000 tables of varying sizes for
    performance testing metadata retrieval.

    Args:
        table_count: Number of tables (default: 1000 per NFR-001)
        db_path: Optional path for persistent database

    Returns:
        SQLAlchemy engine
    """
    return create_performance_db(
        table_count=table_count,
        min_rows=0,
        max_rows=100000,  # Up to 100K rows per table
        seed=42,
        db_path=db_path,
    )


def create_relationship_test_db(
    table_count: int = 50,
    relationship_count: int = 80,
) -> tuple[Engine, list[dict]]:
    """Create a test database with known FK relationships for inference testing.

    T111: Creates ground truth database for FK inference accuracy testing.

    Args:
        table_count: Number of tables to create
        relationship_count: Number of FK relationships (declared + undeclared)

    Returns:
        Tuple of (engine, relationships) where relationships is a list of dicts
        containing source_table, source_column, target_table, target_column.
    """
    engine = create_engine("sqlite:///:memory:", echo=False)
    relationships = []

    with engine.connect() as conn:
        # Create dimension/lookup tables first (targets for FKs)
        dimension_tables = [
            ("customers", "customer_id"),
            ("products", "product_id"),
            ("categories", "category_id"),
            ("employees", "employee_id"),
            ("suppliers", "supplier_id"),
            ("regions", "region_id"),
            ("departments", "department_id"),
            ("statuses", "status_id"),
            ("types", "type_id"),
            ("priorities", "priority_id"),
        ]

        # Create dimension tables
        for table_name, pk_name in dimension_tables:
            conn.execute(text(f"""
                CREATE TABLE {table_name} (
                    {pk_name} INTEGER PRIMARY KEY,
                    name TEXT NOT NULL,
                    description TEXT,
                    created_at TEXT
                )
            """))
            # Insert some data
            for i in range(10):
                conn.execute(text(f"""
                    INSERT INTO {table_name} ({pk_name}, name, description, created_at)
                    VALUES ({i+1}, '{table_name[:-1]}_{i+1}', 'Description for {i+1}', datetime('now'))
                """))

        # Create fact tables with FK references
        fact_table_count = table_count - len(dimension_tables)
        for i in range(fact_table_count):
            table_name = f"fact_table_{i:03d}"

            # Randomly select 1-3 dimension tables to reference
            num_fks = random.randint(1, min(3, len(dimension_tables)))
            selected_dims = random.sample(dimension_tables, num_fks)

            # Build columns
            columns = ["id INTEGER PRIMARY KEY"]
            for dim_table, dim_pk in selected_dims:
                # FK column naming patterns
                fk_column = random.choice([
                    dim_pk,  # Exact match: customer_id
                    f"{dim_table[:-1]}_id" if not dim_table.endswith("ies") else f"{dim_table[:-3]}y_id",  # Singular: customer_id
                    f"fk_{dim_table}",  # Prefixed: fk_customers
                ])
                columns.append(f"{fk_column} INTEGER")

                # Record relationship
                relationships.append({
                    "source_table": table_name,
                    "source_column": fk_column,
                    "target_table": dim_table,
                    "target_column": dim_pk,
                    "declared": (i < fact_table_count // 2),  # Half declared, half inferred
                })

            columns.extend(["amount REAL", "notes TEXT", "created_at TEXT"])

            conn.execute(text(f"CREATE TABLE {table_name} ({', '.join(columns)})"))

        conn.commit()

    return engine, relationships[:relationship_count]
