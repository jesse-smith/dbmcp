"""Tests for connect_database surfacing config parse errors (FR7).

When dbmcp.toml fails to parse, AppConfig.load_error is populated. connect_database
must surface that error to the MCP client instead of emitting the misleading
"Available: none" message.
"""

from unittest.mock import patch

import toon_format

from src.config import AppConfig
from src.mcp_server.server import connect_database


def _decode(toon_str: str) -> dict:
    """Decode a TOON-encoded tool response to a dict."""
    return toon_format.decode(toon_str)


class TestConnectDatabaseConfigParseError:
    """connect_database surfaces config.load_error to the MCP client."""

    async def test_connect_database_surfaces_parse_error_when_load_error_set(self):
        """When config.load_error is set, connect_database returns the parse error (not 'Available: none')."""
        load_err = "TOMLDecodeError: expected '=' (path=/tmp/dbmcp.toml)"
        mock_config = AppConfig(connections={}, load_error=load_err)

        with patch("src.mcp_server.schema_tools.get_config", return_value=mock_config):
            result = await connect_database(connection_name="anything")

        data = _decode(result)
        assert data["status"] == "error"
        assert data["error_message"].startswith("config parse error:")
        assert "TOMLDecodeError" in data["error_message"]
        assert "/tmp/dbmcp.toml" in data["error_message"]
        # The misleading legacy message must not appear.
        assert "Available: none" not in data["error_message"]
        assert "not found in config" not in data["error_message"]

    async def test_connect_database_unknown_connection_message_unchanged_when_no_load_error(self):
        """When load_error is None, unknown connection name still emits the legacy 'not found' message."""
        mock_config = AppConfig(connections={}, load_error=None)

        with patch("src.mcp_server.schema_tools.get_config", return_value=mock_config):
            result = await connect_database(connection_name="missing")

        data = _decode(result)
        assert data["status"] == "error"
        assert "Named connection 'missing' not found" in data["error_message"]
        assert "Available: none" in data["error_message"]
        # The parse-error prefix must not fire in this path.
        assert not data["error_message"].startswith("config parse error:")
