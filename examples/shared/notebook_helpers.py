"""Shared utilities for DBMCP example notebooks."""
import os
import sys
from pathlib import Path
from typing import Any, Optional


def setup_connection(connection_string: Optional[str] = None) -> Any:
    """Establish DBMCP connection with fallback to local test database.

    Args:
        connection_string: Optional connection string. If None, uses
                          DBMCP_CONNECTION_STRING env var or local test DB.

    Returns:
        Connected database connection object

    Raises:
        ConnectionError: If connection fails with helpful message
    """
    if connection_string is None:
        connection_string = os.getenv("DBMCP_CONNECTION_STRING", "sqlite:///examples/test_database/example.db")

    try:
        # Import SQLAlchemy for connection
        from sqlalchemy import create_engine

        engine = create_engine(connection_string)
        connection = engine.connect()
        print(f"✓ Connected to database: {connection_string.split('://')[0]}")
        return connection

    except ImportError as e:
        raise ConnectionError(
            f"Required package not available: {e}\n" "Ensure SQLAlchemy is installed: pip install sqlalchemy"
        )
    except Exception as e:
        raise ConnectionError(
            f"Connection failed: {e}\n"
            f"Connection string: {connection_string}\n"
            "Check connection details and database availability."
        )


def print_table(rows: list, headers: list, max_rows: int = 20) -> None:
    """Print query results as formatted ASCII table.

    Args:
        rows: List of row tuples/lists
        headers: Column headers
        max_rows: Maximum rows to display (rest shown as "...")
    """
    if not rows:
        print("(No rows returned)")
        return

    # Calculate column widths
    col_widths = [len(str(h)) for h in headers]
    for row in rows[:max_rows]:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(val)))

    # Print header
    header_line = " | ".join(str(h).ljust(w) for h, w in zip(headers, col_widths))
    print(header_line)
    print("-" * len(header_line))

    # Print rows
    for row in rows[:max_rows]:
        print(" | ".join(str(val).ljust(w) for val, w in zip(row, col_widths)))

    if len(rows) > max_rows:
        print(f"... ({len(rows) - max_rows} more rows)")

    print(f"\nTotal: {len(rows)} rows")


def verify_notebook_environment() -> bool:
    """Check that notebook environment has required dependencies.

    Returns:
        True if all dependencies available, False otherwise
    """
    missing = []

    # Check critical imports
    try:
        import mcp  # noqa: F401
    except ImportError:
        missing.append("mcp (install: pip install mcp[cli])")

    try:
        import sqlalchemy  # noqa: F401
    except ImportError:
        missing.append("sqlalchemy (install: pip install sqlalchemy)")

    # Check test database
    test_db = Path("examples/test_database/example.db")
    if not test_db.exists():
        missing.append("test database (run: python examples/test_database/setup.py)")

    if missing:
        print("⚠️ Missing dependencies:")
        for item in missing:
            print(f"  - {item}")
        return False

    print("✓ All dependencies available")
    return True
