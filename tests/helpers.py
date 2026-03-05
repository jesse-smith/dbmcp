"""Test helpers for TOON-based MCP tool response parsing."""

from toon_format import decode


def parse_tool_response(response: str) -> dict:
    """Decode a TOON-encoded MCP tool response string into a dict.

    Args:
        response: TOON-encoded string from an MCP tool.

    Returns:
        Decoded dictionary.

    Raises:
        ValueError: If decoded value is not a dict.
    """
    result = decode(response)
    if not isinstance(result, dict):
        raise ValueError(f"Expected dict from TOON response, got {type(result).__name__}")
    return result
