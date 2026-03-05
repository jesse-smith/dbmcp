"""Meta-tests for the bidirectional field comparison logic.

Verifies that compare_fields() correctly detects drift between declared
docstring fields and actual response keys, handling conditional field
exclusion and nested field comparison.
"""

import pytest

from tests.staleness.comparison import compare_fields


class TestCompareFieldsNoDrift:
    """Cases where declared and actual fields match perfectly."""

    def test_exact_match_returns_empty(self):
        declared = {
            "top_level": {"status", "message", "data"},
            "nested": {},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "message", "data"},
            actual_nested={},
            response_path="success",
            tool_name="test_tool",
        )
        assert result == []

    def test_success_path_excludes_error_only_fields(self):
        """Fields marked 'on error only' should not be expected in success responses."""
        declared = {
            "top_level": {"status", "data", "error_message"},
            "nested": {},
            "conditional": {"error_message": "on error only"},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "data"},
            actual_nested={},
            response_path="success",
            tool_name="test_tool",
        )
        assert result == []

    def test_error_path_excludes_success_only_fields(self):
        """Fields marked 'on success only' should not be expected in error responses."""
        declared = {
            "top_level": {"status", "connection_id", "error_message"},
            "nested": {},
            "conditional": {
                "connection_id": "on success only",
            },
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "error_message"},
            actual_nested={},
            response_path="error",
            tool_name="test_tool",
        )
        assert result == []


class TestCompareFieldsDrift:
    """Cases where drift is detected."""

    def test_extra_field_detected(self):
        declared = {
            "top_level": {"status", "data"},
            "nested": {},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "data", "extra_field"},
            actual_nested={},
            response_path="success",
            tool_name="my_tool",
        )
        assert len(result) == 1
        assert "undocumented" in result[0].lower() or "extra" in result[0].lower()
        assert "extra_field" in result[0]
        assert "my_tool" in result[0]

    def test_missing_field_detected(self):
        declared = {
            "top_level": {"status", "data", "count"},
            "nested": {},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "data"},
            actual_nested={},
            response_path="success",
            tool_name="my_tool",
        )
        assert len(result) == 1
        assert "missing" in result[0].lower()
        assert "count" in result[0]
        assert "my_tool" in result[0]

    def test_multiple_drift_issues(self):
        declared = {
            "top_level": {"status", "expected_field"},
            "nested": {},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "surprise_field"},
            actual_nested={},
            response_path="success",
            tool_name="my_tool",
        )
        # Should have both missing and extra
        assert len(result) == 2


class TestCompareFieldsConditional:
    """Conditional field exclusion edge cases."""

    def test_detailed_mode_only_treated_as_optional(self):
        """Fields with non-standard conditions like 'detailed mode only' are optional."""
        declared = {
            "top_level": {"status", "tables", "columns"},
            "nested": {},
            "conditional": {"columns": "detailed mode only"},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "tables"},
            actual_nested={},
            response_path="success",
            tool_name="test_tool",
        )
        assert result == []

    def test_conditional_field_present_is_not_flagged(self):
        """A conditional field that IS present should not be flagged as extra."""
        declared = {
            "top_level": {"status", "error_message"},
            "nested": {},
            "conditional": {"error_message": "on error only"},
        }
        # error_message is declared AND present -- should be fine
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "error_message"},
            actual_nested={},
            response_path="error",
            tool_name="test_tool",
        )
        assert result == []


class TestCompareFieldsNested:
    """Nested field comparison."""

    def test_nested_match_no_drift(self):
        declared = {
            "top_level": {"status", "schemas"},
            "nested": {"schemas": {"schema_name", "table_count"}},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "schemas"},
            actual_nested={"schemas": {"schema_name", "table_count"}},
            response_path="success",
            tool_name="test_tool",
        )
        assert result == []

    def test_nested_extra_field(self):
        declared = {
            "top_level": {"status", "schemas"},
            "nested": {"schemas": {"schema_name"}},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "schemas"},
            actual_nested={"schemas": {"schema_name", "surprise"}},
            response_path="success",
            tool_name="test_tool",
        )
        assert len(result) == 1
        assert "surprise" in result[0]
        assert "schemas" in result[0]

    def test_nested_missing_field(self):
        declared = {
            "top_level": {"status", "schemas"},
            "nested": {"schemas": {"schema_name", "table_count"}},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "schemas"},
            actual_nested={"schemas": {"schema_name"}},
            response_path="success",
            tool_name="test_tool",
        )
        assert len(result) == 1
        assert "table_count" in result[0]


class TestCompareFieldsMessageClarity:
    """Drift messages should be clear and actionable."""

    def test_message_includes_tool_name(self):
        declared = {
            "top_level": {"status"},
            "nested": {},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status", "bonus"},
            actual_nested={},
            response_path="success",
            tool_name="connect_database",
        )
        assert any("connect_database" in msg for msg in result)

    def test_message_includes_field_names(self):
        declared = {
            "top_level": {"status", "missing_a", "missing_b"},
            "nested": {},
            "conditional": {},
        }
        result = compare_fields(
            declared=declared,
            actual_keys={"status"},
            actual_nested={},
            response_path="success",
            tool_name="test_tool",
        )
        combined = " ".join(result)
        assert "missing_a" in combined
        assert "missing_b" in combined
