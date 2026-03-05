"""TOON serialization wrapper with recursive pre-serialization.

Converts Python dicts (potentially containing datetime, StrEnum, Decimal, etc.)
into TOON-encoded strings suitable for MCP tool responses.
"""

from datetime import date, datetime
from decimal import Decimal
from enum import StrEnum
from typing import Any

from toon_format import encode


def _pre_serialize(value: Any) -> Any:
    """Recursively convert non-primitive types to TOON-compatible values.

    Handles:
        - None, bool, int, float, str: passthrough
        - dict: recurse on values
        - list: recurse on items
        - tuple: convert to list, recurse on items
        - datetime/date: .isoformat()
        - StrEnum: str(value)
        - Decimal: float(value)
        - Unknown: raise TypeError
    """
    # Primitives pass through unchanged.
    # Check bool before int (bool is a subclass of int).
    if value is None or isinstance(value, (bool, int, float, str)) and not isinstance(value, StrEnum):
        return value

    if isinstance(value, StrEnum):
        return str(value.value)

    if isinstance(value, dict):
        return {k: _pre_serialize(v) for k, v in value.items()}

    if isinstance(value, list):
        return [_pre_serialize(item) for item in value]

    if isinstance(value, tuple):
        return [_pre_serialize(item) for item in value]

    if isinstance(value, datetime):
        return value.isoformat()

    if isinstance(value, date):
        return value.isoformat()

    if isinstance(value, Decimal):
        return float(value)

    raise TypeError(f"Cannot serialize type {type(value).__name__}")


def encode_response(data: dict) -> str:
    """Encode a dict as a TOON string, pre-serializing special types.

    Args:
        data: Dictionary to encode. May contain datetime, StrEnum, Decimal values.

    Returns:
        TOON-encoded string.

    Raises:
        TypeError: If data contains unrecognized types.
    """
    return encode(_pre_serialize(data))
