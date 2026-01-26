#!/usr/bin/env python3
"""Setup script for DBMCP example test database.

This script creates and populates a SQLite database from schema.sql
for use with example notebooks.
"""
import sqlite3
from pathlib import Path


def setup_database(db_path: str = "examples/test_database/example.db") -> None:
    """Create and populate test database from schema.sql.

    Args:
        db_path: Path where database file will be created

    Raises:
        FileNotFoundError: If schema.sql not found
        sqlite3.Error: If database creation fails
    """
    schema_path = Path(__file__).parent / "schema.sql"

    if not schema_path.exists():
        raise FileNotFoundError(f"Schema file not found: {schema_path}")

    # Remove existing database
    db_file = Path(db_path)
    if db_file.exists():
        db_file.unlink()
        print(f"Removed existing database: {db_path}")

    # Create new database and execute schema
    try:
        conn = sqlite3.connect(db_path)
        with open(schema_path) as f:
            conn.executescript(f.read())
        conn.commit()
        conn.close()

        print(f"✓ Test database created at {db_path}")
        print(f"✓ Schema loaded from {schema_path}")

        # Verify tables created
        conn = sqlite3.connect(db_path)
        cursor = conn.cursor()
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name")
        tables = [row[0] for row in cursor.fetchall()]
        conn.close()

        print(f"✓ Tables created: {', '.join(tables)}")

    except sqlite3.Error as e:
        print(f"✗ Database creation failed: {e}")
        raise


if __name__ == "__main__":
    setup_database()
