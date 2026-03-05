"""Parametrized staleness guard test over all 9 MCP tools.

Validates that docstring field declarations match actual response schemas
for both success and error paths. Uses mock-based tool invocation to get
real response shapes without requiring a database connection.
"""

import pytest

from tests.helpers import parse_tool_response
from tests.staleness.comparison import compare_fields
from tests.staleness.docstring_parser import extract_fields
from tests.staleness.tool_invoker import TOOL_CONFIGS, invoke_tool


def _extract_nested_keys(value) -> set[str]:
    """Recursively extract all dict keys from a nested structure.

    For dicts: collects all keys, then recurses into values.
    For lists of dicts: collects union of all keys across items, then recurses.
    This mirrors how the docstring parser flattens nested field declarations
    under a single parent.
    """
    keys = set()
    if isinstance(value, dict):
        keys.update(value.keys())
        for v in value.values():
            keys.update(_extract_nested_keys(v))
    elif isinstance(value, list):
        for item in value:
            if isinstance(item, dict):
                keys.update(item.keys())
                for v in item.values():
                    keys.update(_extract_nested_keys(v))
    return keys


class TestStalenessGuard:
    """Automated test: docstring field declarations must match actual response schemas."""

    @pytest.mark.parametrize("tool_config", TOOL_CONFIGS, ids=lambda c: c["name"])
    async def test_success_path_fields_match_docstring(self, tool_config):
        """Docstring fields (excluding error-only) match success response keys."""
        fn = tool_config["fn"]
        declared = extract_fields(fn.__doc__)
        response_str = await invoke_tool(tool_config, path="success")
        response = parse_tool_response(response_str)

        actual_keys = set(response.keys())
        actual_nested = {
            k: _extract_nested_keys(v)
            for k, v in response.items()
            if isinstance(v, (dict, list))
        }

        drift = compare_fields(
            declared, actual_keys, actual_nested, "success", tool_config["name"]
        )
        assert not drift, "\n".join(drift)

    @pytest.mark.parametrize("tool_config", TOOL_CONFIGS, ids=lambda c: c["name"])
    async def test_error_path_fields_match_docstring(self, tool_config):
        """Docstring fields (excluding success-only) match error response keys."""
        fn = tool_config["fn"]
        declared = extract_fields(fn.__doc__)
        response_str = await invoke_tool(tool_config, path="error")
        response = parse_tool_response(response_str)

        actual_keys = set(response.keys())
        actual_nested = {}  # Error responses are typically flat

        drift = compare_fields(
            declared, actual_keys, actual_nested, "error", tool_config["name"]
        )
        assert not drift, "\n".join(drift)


class TestToolDiscovery:
    """Verify all tools are covered by staleness guard."""

    def test_all_nine_tools_covered(self):
        """TOOL_CONFIGS covers all 9 registered MCP tools."""
        known_tools = {
            "connect_database",
            "list_schemas",
            "list_tables",
            "get_table_schema",
            "get_sample_data",
            "execute_query",
            "get_column_info",
            "find_pk_candidates",
            "find_fk_candidates",
        }
        configured_tools = {c["name"] for c in TOOL_CONFIGS}
        assert configured_tools == known_tools

    def test_tool_count_matches_mcp_registry(self):
        """If a new tool is added to the MCP server, this test fails until TOOL_CONFIGS is updated."""
        from src.mcp_server.server import mcp

        # FastMCP stores registered tools in _tool_manager._tools
        registered_count = len(mcp._tool_manager._tools)
        configured_count = len(TOOL_CONFIGS)
        assert configured_count == registered_count, (
            f"MCP registry has {registered_count} tools but TOOL_CONFIGS has {configured_count}. "
            f"Update TOOL_CONFIGS if tools were added/removed."
        )


class TestDriftDetection:
    """Verify that synthetic drift is detected."""

    @pytest.mark.parametrize("tool_config", TOOL_CONFIGS[:1], ids=lambda c: c["name"])
    async def test_synthetic_drift_detected(self, tool_config):
        """Adding a key to a mock response causes the staleness test to fail."""
        fn = tool_config["fn"]
        declared = extract_fields(fn.__doc__)
        response_str = await invoke_tool(tool_config, path="success")
        response = parse_tool_response(response_str)

        # Inject synthetic drift: add an undocumented key
        response["_synthetic_undocumented_field"] = "should cause drift"

        actual_keys = set(response.keys())
        actual_nested = {}

        drift = compare_fields(
            declared, actual_keys, actual_nested, "success", tool_config["name"]
        )
        assert drift, "Synthetic drift should have been detected but wasn't"
        assert any("_synthetic_undocumented_field" in msg for msg in drift)
