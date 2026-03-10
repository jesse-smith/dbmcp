"""Unit tests for the unified type handler registry.

Tests cover:
- All 13 type handlers (None + 12 isinstance-based)
- Subclass ordering edge cases (bool/int, StrEnum/str, datetime/date)
- Recursive dict/list/tuple handling with truncation aggregation
- TypeError for unknown types
- String truncation at configurable limit
- Binary hex representation
- DEFAULT_TRUNCATION_LIMIT export
"""

from datetime import date, datetime
from datetime import time as dt_time
from decimal import Decimal
from enum import StrEnum

import pytest

from src.type_registry import DEFAULT_TRUNCATION_LIMIT, convert


class SampleStrEnum(StrEnum):
    """Test StrEnum for subclass ordering tests."""

    ALPHA = "alpha"
    BETA = "beta"


# ---------------------------------------------------------------------------
# Primitive types
# ---------------------------------------------------------------------------


class TestNoneHandler:
    def test_none_returns_none_not_truncated(self):
        assert convert(None) == (None, False)

    def test_none_with_custom_limit(self):
        assert convert(None, trunc_limit=10) == (None, False)


class TestBoolHandler:
    def test_true_passthrough(self):
        result, truncated = convert(True)
        assert result is True
        assert truncated is False

    def test_false_passthrough(self):
        result, truncated = convert(False)
        assert result is False
        assert truncated is False

    def test_bool_not_converted_to_int(self):
        """bool must NOT become 1/0 -- subclass ordering check."""
        result, _ = convert(True)
        assert result is not 1
        assert type(result) is bool


class TestIntHandler:
    def test_int_passthrough(self):
        assert convert(42) == (42, False)

    def test_zero(self):
        assert convert(0) == (0, False)

    def test_negative(self):
        assert convert(-7) == (-7, False)


class TestFloatHandler:
    def test_float_passthrough(self):
        assert convert(3.14) == (3.14, False)

    def test_zero_float(self):
        assert convert(0.0) == (0.0, False)


class TestStrHandler:
    def test_short_string_passthrough(self):
        assert convert("hello") == ("hello", False)

    def test_empty_string(self):
        assert convert("") == ("", False)

    def test_string_at_limit_not_truncated(self):
        s = "a" * 1000
        result, truncated = convert(s, trunc_limit=1000)
        assert result == s
        assert truncated is False

    def test_string_over_limit_truncated(self):
        s = "a" * 1500
        result, truncated = convert(s, trunc_limit=1000)
        assert truncated is True
        assert len(result) < 1500
        assert result.startswith("a" * 1000)
        assert "1500 chars total" in result

    def test_string_truncation_with_custom_limit(self):
        s = "abcdefghij"  # 10 chars
        result, truncated = convert(s, trunc_limit=5)
        assert truncated is True
        assert result.startswith("abcde")
        assert "10 chars total" in result


class TestBytesHandler:
    def test_small_binary_hex_representation(self):
        data = b"\x01\x02\x03"
        result, truncated = convert(data)
        assert truncated is True
        assert "<binary:" in result
        assert "010203" in result
        assert "3 bytes" in result
        assert "..." not in result

    def test_large_binary_truncated_hex(self):
        data = b"x" * 100
        result, truncated = convert(data)
        assert truncated is True
        assert "<binary:" in result
        assert "100 bytes" in result
        assert "..." in result

    def test_exactly_32_bytes_not_truncated_hex(self):
        data = b"\xff" * 32
        result, truncated = convert(data)
        assert truncated is True
        assert "32 bytes" in result
        assert "..." not in result

    def test_33_bytes_truncated_hex(self):
        data = b"\xff" * 33
        result, truncated = convert(data)
        assert truncated is True
        assert "33 bytes" in result
        assert "..." in result


class TestDatetimeHandler:
    def test_datetime_to_isoformat(self):
        dt = datetime(2026, 3, 10, 15, 30, 0)
        assert convert(dt) == ("2026-03-10T15:30:00", False)

    def test_datetime_with_microseconds(self):
        dt = datetime(2026, 1, 1, 0, 0, 0, 123456)
        result, truncated = convert(dt)
        assert "123456" in result
        assert truncated is False


class TestDateHandler:
    def test_date_to_isoformat(self):
        d = date(2026, 3, 10)
        assert convert(d) == ("2026-03-10", False)


class TestTimeHandler:
    def test_time_to_isoformat(self):
        t = dt_time(10, 30, 0)
        assert convert(t) == ("10:30:00", False)

    def test_time_with_microseconds(self):
        t = dt_time(10, 30, 0, 123456)
        result, truncated = convert(t)
        assert "123456" in result
        assert truncated is False


class TestDecimalHandler:
    def test_decimal_to_float(self):
        assert convert(Decimal("123.45")) == (123.45, False)

    def test_decimal_high_precision(self):
        result, truncated = convert(Decimal("0.0750000000"))
        assert result == 0.075
        assert truncated is False


class TestStrEnumHandler:
    def test_strenum_to_value_string(self):
        result, truncated = convert(SampleStrEnum.ALPHA)
        assert result == "alpha"
        assert isinstance(result, str)
        assert type(result) is str  # not StrEnum subclass
        assert truncated is False

    def test_strenum_beta(self):
        assert convert(SampleStrEnum.BETA) == ("beta", False)


# ---------------------------------------------------------------------------
# Recursive container types
# ---------------------------------------------------------------------------


class TestDictHandler:
    def test_dict_values_recursed(self):
        data = {"ts": datetime(2026, 1, 1), "name": "test"}
        result, truncated = convert(data)
        assert result == {"ts": "2026-01-01T00:00:00", "name": "test"}
        assert truncated is False

    def test_dict_truncation_aggregated(self):
        data = {"short": "ok", "long": "a" * 1500}
        result, truncated = convert(data, trunc_limit=1000)
        assert truncated is True
        assert "1500 chars total" in result["long"]
        assert result["short"] == "ok"

    def test_empty_dict(self):
        assert convert({}) == ({}, False)


class TestListHandler:
    def test_list_items_recursed(self):
        data = [datetime(2026, 1, 1), "hello"]
        result, truncated = convert(data)
        assert result == ["2026-01-01T00:00:00", "hello"]
        assert truncated is False

    def test_list_truncation_aggregated(self):
        data = ["short", "a" * 1500]
        result, truncated = convert(data, trunc_limit=1000)
        assert truncated is True

    def test_empty_list(self):
        assert convert([]) == ([], False)


class TestTupleHandler:
    def test_tuple_converted_to_list(self):
        result, truncated = convert((1, 2, 3))
        assert result == [1, 2, 3]
        assert isinstance(result, list)
        assert truncated is False

    def test_tuple_items_recursed(self):
        result, truncated = convert((datetime(2026, 1, 1),))
        assert result == ["2026-01-01T00:00:00"]
        assert truncated is False


# ---------------------------------------------------------------------------
# Subclass ordering
# ---------------------------------------------------------------------------


class TestSubclassOrdering:
    """Ensure subclass types are checked before parent types."""

    def test_bool_before_int(self):
        """True must stay True (bool), not become 1 (int)."""
        result, _ = convert(True)
        assert result is True
        assert type(result) is bool

    def test_false_before_int(self):
        result, _ = convert(False)
        assert result is False
        assert type(result) is bool

    def test_strenum_before_str(self):
        """StrEnum must use value extraction, not passthrough as str."""
        result, _ = convert(SampleStrEnum.ALPHA)
        assert result == "alpha"
        assert type(result) is str

    def test_datetime_before_date(self):
        """datetime (subclass of date) must use datetime handler."""
        dt = datetime(2026, 3, 10, 15, 30)
        result, _ = convert(dt)
        # datetime.isoformat() includes time; date.isoformat() does not
        assert "T" in result


# ---------------------------------------------------------------------------
# Unknown type handling
# ---------------------------------------------------------------------------


class TestUnknownType:
    def test_unknown_type_raises_typeerror(self):
        with pytest.raises(TypeError, match="Cannot serialize type"):
            convert(object())

    def test_custom_class_raises_typeerror(self):
        class Custom:
            pass

        with pytest.raises(TypeError, match="Custom"):
            convert(Custom())


# ---------------------------------------------------------------------------
# Module-level constants
# ---------------------------------------------------------------------------


class TestConstants:
    def test_default_truncation_limit(self):
        assert DEFAULT_TRUNCATION_LIMIT == 1000

    def test_default_limit_used_when_not_specified(self):
        s = "a" * 1001
        result, truncated = convert(s)
        assert truncated is True
        assert "1001 chars total" in result


# ---------------------------------------------------------------------------
# Nested/complex structures
# ---------------------------------------------------------------------------


class TestNestedStructures:
    def test_dict_of_lists_of_dicts(self):
        data = {
            "items": [
                {"ts": datetime(2026, 1, 1), "val": Decimal("1.5")},
                {"ts": datetime(2026, 6, 15), "val": Decimal("2.5")},
            ]
        }
        result, truncated = convert(data)
        assert result == {
            "items": [
                {"ts": "2026-01-01T00:00:00", "val": 1.5},
                {"ts": "2026-06-15T00:00:00", "val": 2.5},
            ]
        }
        assert truncated is False

    def test_deeply_nested_truncation_propagates(self):
        data = {"a": {"b": {"c": "x" * 1500}}}
        result, truncated = convert(data, trunc_limit=1000)
        assert truncated is True
        assert "1500 chars total" in result["a"]["b"]["c"]
