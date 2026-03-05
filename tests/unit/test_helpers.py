"""Unit tests for test helper parse_tool_response."""

import pytest

from src.serialization import encode_response
from tests.helpers import parse_tool_response


class TestParseToolResponse:
    """Tests for the TOON-decoding test helper."""

    def test_parse_simple_dict(self):
        data = {"status": "success"}
        result = parse_tool_response(encode_response(data))
        assert result == data

    def test_parse_nested_dict(self):
        data = {"outer": {"inner": [1, 2, 3], "flag": True}}
        result = parse_tool_response(encode_response(data))
        assert result == data

    def test_parse_non_dict_raises(self):
        """If TOON decodes to a non-dict (e.g. list), raise ValueError."""
        from toon_format import encode

        toon_list = encode([1, 2, 3])
        with pytest.raises(ValueError, match="dict"):
            parse_tool_response(toon_list)

    def test_parse_invalid_toon_raises(self):
        """Malformed TOON string raises an exception."""
        with pytest.raises(Exception):
            parse_tool_response("<<<totally invalid toon>>>")
