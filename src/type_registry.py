"""Unified type handler registry for value conversion and truncation.

Provides a single `convert()` function that handles all Python types returned
by database queries or used in MCP tool responses. Each handler converts a
value to a JSON/TOON-compatible type and reports whether truncation occurred.

Replaces both `_pre_serialize()` (serialization.py) and `_truncate_value()`
(query.py) with a single, ordered handler chain.

Subclass ordering is critical:
  - bool before int (bool is a subclass of int)
  - StrEnum before str (StrEnum is a subclass of str)
  - datetime before date (datetime is a subclass of date)
"""

from collections.abc import Callable
from datetime import date, datetime
from datetime import time as dt_time
from decimal import Decimal
from enum import StrEnum
from typing import Any

DEFAULT_TRUNCATION_LIMIT = 1000

# ---------------------------------------------------------------------------
# Individual handlers: (value, trunc_limit) -> (converted, was_truncated)
# ---------------------------------------------------------------------------


def _handle_bool(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return value, False


def _handle_strenum(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return str(value.value), False


def _handle_int(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return value, False


def _handle_float(value: Any, trunc_limit: int) -> tuple[Any, bool]:
    return value, False


def _handle_str(value: Any, trunc_limit: int) -> tuple[str, bool]:
    if len(value) > trunc_limit:
        return value[:trunc_limit] + f"... ({len(value)} chars total)", True
    return value, False


def _handle_bytes(value: Any, trunc_limit: int) -> tuple[str, bool]:
    if len(value) > 32:
        hex_preview = value[:32].hex()
        return f"<binary: {hex_preview}... ({len(value)} bytes)>", True
    return f"<binary: {value.hex()} ({len(value)} bytes)>", True


def _handle_datetime(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return value.isoformat(), False


def _handle_date(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return value.isoformat(), False


def _handle_time(value: Any, trunc_limit: int) -> tuple[str, bool]:
    return value.isoformat(), False


def _handle_decimal(value: Any, trunc_limit: int) -> tuple[float, bool]:
    return float(value), False


def _handle_dict(value: Any, trunc_limit: int) -> tuple[dict, bool]:
    any_truncated = False
    result = {}
    for k, v in value.items():
        converted, was_truncated = convert(v, trunc_limit)
        result[k] = converted
        any_truncated = any_truncated or was_truncated
    return result, any_truncated


def _handle_list(value: Any, trunc_limit: int) -> tuple[list, bool]:
    any_truncated = False
    result = []
    for item in value:
        converted, was_truncated = convert(item, trunc_limit)
        result.append(converted)
        any_truncated = any_truncated or was_truncated
    return result, any_truncated


def _handle_tuple(value: Any, trunc_limit: int) -> tuple[list, bool]:
    return _handle_list(list(value), trunc_limit)


# ---------------------------------------------------------------------------
# Ordered handler chain -- order matters for subclass correctness
# ---------------------------------------------------------------------------

_HANDLER_CHAIN: list[tuple[type, Callable]] = [
    (bool, _handle_bool),  # before int
    (StrEnum, _handle_strenum),  # before str
    (int, _handle_int),  # after bool
    (float, _handle_float),
    (str, _handle_str),  # after StrEnum
    (bytes, _handle_bytes),
    (datetime, _handle_datetime),  # before date
    (date, _handle_date),
    (dt_time, _handle_time),
    (Decimal, _handle_decimal),
    (dict, _handle_dict),
    (list, _handle_list),
    (tuple, _handle_tuple),
]


def convert(
    value: Any, trunc_limit: int = DEFAULT_TRUNCATION_LIMIT
) -> tuple[Any, bool]:
    """Convert a value through the type handler registry.

    Handles conversion to JSON/TOON-compatible types and applies text/binary
    truncation in a single pass.

    Args:
        value: The value to convert.
        trunc_limit: Maximum character length for string values before
            truncation. Defaults to DEFAULT_TRUNCATION_LIMIT (1000).

    Returns:
        Tuple of (converted_value, was_truncated). was_truncated is True
        if any value in the tree was truncated.

    Raises:
        TypeError: If the value's type is not handled by any registered handler.
    """
    if value is None:
        return None, False

    for type_check, handler in _HANDLER_CHAIN:
        if isinstance(value, type_check):
            return handler(value, trunc_limit)

    raise TypeError(f"Cannot serialize type {type(value).__name__}")
