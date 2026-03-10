"""TOON serialization wrapper using the unified type handler registry.

Converts Python dicts (potentially containing datetime, StrEnum, Decimal, etc.)
into TOON-encoded strings suitable for MCP tool responses.
"""

import sys

from toon_format import encode

from src.type_registry import convert


def encode_response(data: dict) -> str:
    """Encode a dict as a TOON string, converting special types via the registry.

    Uses the type handler registry with no truncation (sys.maxsize limit)
    since serialization callers don't need text truncation.

    Args:
        data: Dictionary to encode. May contain datetime, StrEnum, Decimal values.

    Returns:
        TOON-encoded string.

    Raises:
        TypeError: If data contains unrecognized types.
    """
    converted, _ = convert(data, trunc_limit=sys.maxsize)
    return encode(converted)
