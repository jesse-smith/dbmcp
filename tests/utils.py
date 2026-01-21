"""Test utilities for dbmcp tests.

This module provides helper functions and mock objects for testing.
"""

from typing import Any
from unittest.mock import MagicMock


def create_mock_execute_result(rows: list[dict]) -> MagicMock:
    """Create a mock SQLAlchemy execute result.

    Args:
        rows: List of dictionaries representing result rows

    Returns:
        Mock execute result with proper iteration
    """
    result = MagicMock()

    # Create mock row objects with attribute access
    mock_rows = []
    for row in rows:
        mock_row = MagicMock()
        for key, value in row.items():
            setattr(mock_row, key, value)
        mock_rows.append(mock_row)

    result.__iter__ = lambda self: iter(mock_rows)
    result.fetchone.return_value = mock_rows[0] if mock_rows else None
    result.fetchall.return_value = mock_rows
    result.scalar.return_value = rows[0].get(list(rows[0].keys())[0]) if rows else None

    return result


def create_mock_connection_context(execute_results: dict[str, list[dict]]) -> MagicMock:
    """Create a mock connection context manager.

    Args:
        execute_results: Dictionary mapping query patterns to result rows

    Returns:
        Mock connection context manager
    """
    connection = MagicMock()

    def mock_execute(query, params=None):
        query_str = str(query)
        for pattern, rows in execute_results.items():
            if pattern.lower() in query_str.lower():
                # Handle limit parameter if present (simulates TOP clause)
                result_rows = rows
                if params and "limit" in params:
                    limit = params["limit"]
                    result_rows = rows[:limit]
                return create_mock_execute_result(result_rows)
        return create_mock_execute_result([])

    connection.execute = mock_execute
    return connection


def create_mock_engine(execute_results: dict[str, list[dict]] = None) -> MagicMock:
    """Create a mock SQLAlchemy engine with connection context.

    Args:
        execute_results: Dictionary mapping query patterns to result rows

    Returns:
        Mock SQLAlchemy engine
    """
    engine = MagicMock()
    connection = create_mock_connection_context(execute_results or {})

    # Set up context manager
    engine.connect.return_value.__enter__ = MagicMock(return_value=connection)
    engine.connect.return_value.__exit__ = MagicMock(return_value=None)

    return engine


# Sample data for tests
SAMPLE_SCHEMA_ROWS = [
    {"schema_name": "dbo", "table_count": 10, "view_count": 2},
    {"schema_name": "sales", "table_count": 5, "view_count": 1},
    {"schema_name": "hr", "table_count": 3, "view_count": 0},
]

SAMPLE_TABLE_ROWS = [
    {
        "schema_name": "dbo",
        "table_name": "Customers",
        "row_count": 10000,
        "last_modified": None,
        "has_primary_key": 1,
    },
    {
        "schema_name": "dbo",
        "table_name": "Orders",
        "row_count": 50000,
        "last_modified": None,
        "has_primary_key": 1,
    },
    {
        "schema_name": "dbo",
        "table_name": "Products",
        "row_count": 500,
        "last_modified": None,
        "has_primary_key": 1,
    },
]


def assert_json_contains(json_str: str, expected: dict[str, Any]) -> None:
    """Assert that a JSON string contains expected key-value pairs.

    Args:
        json_str: JSON string to check
        expected: Dictionary of expected key-value pairs
    """
    import json as json_module

    data = json_module.loads(json_str)
    for key, value in expected.items():
        assert key in data, f"Key '{key}' not found in JSON"
        assert data[key] == value, f"Key '{key}': expected {value}, got {data[key]}"


def assert_json_has_keys(json_str: str, keys: list[str]) -> None:
    """Assert that a JSON string contains expected keys.

    Args:
        json_str: JSON string to check
        keys: List of keys that should be present
    """
    import json as json_module

    data = json_module.loads(json_str)
    for key in keys:
        assert key in data, f"Key '{key}' not found in JSON"
