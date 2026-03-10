"""Unit tests for TOON serialization wrapper."""

from datetime import date, datetime
from enum import StrEnum

import pytest
import toon_format

from src.serialization import encode_response
from src.type_registry import convert


class SampleEnum(StrEnum):
    """Test StrEnum for serialization tests."""

    OPTION_A = "alpha"
    OPTION_B = "beta"


class CustomObj:
    """Unrecognized type for TypeError testing."""

    pass


# ---------------------------------------------------------------------------
# toon_format import sanity
# ---------------------------------------------------------------------------


def test_toon_import():
    """toon_format is importable with encode and decode callables."""
    assert callable(toon_format.encode)
    assert callable(toon_format.decode)


# ---------------------------------------------------------------------------
# _pre_serialize
# ---------------------------------------------------------------------------


class TestConvertForSerialization:
    """Tests for the type registry convert() used by serialization.

    These tests verify the same behaviors previously covered by _pre_serialize,
    now handled by the unified type registry.
    """

    @pytest.mark.parametrize(
        "value",
        [None, True, False, 42, 3.14, "hello"],
        ids=["none", "true", "false", "int", "float", "str"],
    )
    def test_primitives_passthrough(self, value):
        result, _ = convert(value)
        assert result is value

    def test_dict_values_recursed(self):
        result, _ = convert({"ts": datetime(2026, 1, 1, 12, 0, 0)})
        assert result == {"ts": "2026-01-01T12:00:00"}

    def test_list_values_recursed(self):
        result, _ = convert([datetime(2026, 1, 1)])
        assert result == ["2026-01-01T00:00:00"]

    def test_tuple_converted_to_list(self):
        result, _ = convert((3, 2, 1))
        assert result == [3, 2, 1]
        assert isinstance(result, list)

    def test_datetime_to_isoformat(self):
        dt = datetime(2026, 3, 4, 15, 30, 0)
        result, _ = convert(dt)
        assert result == "2026-03-04T15:30:00"

    def test_date_to_isoformat(self):
        d = date(2026, 3, 4)
        result, _ = convert(d)
        assert result == "2026-03-04"

    def test_strenum_to_string(self):
        from src.models.schema import AuthenticationMethod

        result, _ = convert(AuthenticationMethod.SQL)
        assert result == "sql"
        assert isinstance(result, str)
        assert type(result) is str  # not StrEnum subclass

    def test_unknown_type_raises_typeerror(self):
        obj = CustomObj()
        with pytest.raises(TypeError, match="CustomObj"):
            convert(obj)

    def test_nested_structure(self):
        """Dict containing list of dicts with datetime and StrEnum values."""
        data = {
            "items": [
                {"ts": datetime(2026, 1, 1), "kind": SampleEnum.OPTION_A},
                {"ts": datetime(2026, 6, 15), "kind": SampleEnum.OPTION_B},
            ]
        }
        result, _ = convert(data)
        assert result == {
            "items": [
                {"ts": "2026-01-01T00:00:00", "kind": "alpha"},
                {"ts": "2026-06-15T00:00:00", "kind": "beta"},
            ]
        }


# ---------------------------------------------------------------------------
# encode_response
# ---------------------------------------------------------------------------


class TestEncodeResponse:
    """Tests for the top-level encode_response function."""

    def test_simple_dict_returns_nonempty_string(self):
        result = encode_response({"status": "success"})
        assert isinstance(result, str)
        assert len(result) > 0

    def test_result_is_not_json(self):
        result = encode_response({"status": "success"})
        assert not result.strip().startswith("{")

    def test_roundtrip_primitive_dict(self):
        data = {"status": "success", "count": 42, "flag": True}
        encoded = encode_response(data)
        decoded = toon_format.decode(encoded)
        assert decoded == data

    def test_roundtrip_datetime(self):
        data = {"created_at": datetime(2026, 3, 4, 12, 0, 0)}
        encoded = encode_response(data)
        decoded = toon_format.decode(encoded)
        assert decoded == {"created_at": "2026-03-04T12:00:00"}

    def test_roundtrip_strenum(self):
        data = {"method": SampleEnum.OPTION_A}
        encoded = encode_response(data)
        decoded = toon_format.decode(encoded)
        assert decoded == {"method": "alpha"}

    def test_typeerror_propagates(self):
        data = {"bad": CustomObj()}
        with pytest.raises(TypeError):
            encode_response(data)
