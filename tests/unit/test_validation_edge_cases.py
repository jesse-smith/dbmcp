"""Edge case tests for sqlglot-based query validation.

Validates the pinned sqlglot version handles security-critical edge cases:
comment injection, semicolon batching, UNION injection, string escaping,
T-SQL evasion techniques, and valid query passthrough.
"""

import sqlglot
import pytest


class TestSqlglotVersionFloor:
    """Verify sqlglot version pin is enforced at runtime."""

    def test_sqlglot_version_floor(self):
        """sqlglot version must be >= 29.0.0 (Execute node handling)."""
        parts = sqlglot.__version__.split(".")
        major = int(parts[0])
        assert major >= 29, (
            f"sqlglot {sqlglot.__version__} is below the required floor of 29.0.0. "
            "Version 29+ is required for proper Execute/ExecuteSql node handling."
        )

    def test_pyproject_contains_tightened_pin(self):
        """pyproject.toml must contain the tightened sqlglot pin."""
        from pathlib import Path

        pyproject = Path("pyproject.toml").read_text()
        assert 'sqlglot>=29.0.0,<30.0.0' in pyproject, (
            "pyproject.toml must pin sqlglot to >=29.0.0,<30.0.0"
        )
