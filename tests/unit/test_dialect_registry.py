"""Tests for dialect registry."""

from unittest.mock import MagicMock

import pytest
from sqlalchemy.engine import Engine

from src.db.dialects import registry
from src.db.dialects.registry import get_dialect, register_dialect


class _StubDialect:
    """Conforming stub for registry tests."""

    @property
    def name(self) -> str:
        return "stub"

    @property
    def sqlglot_dialect(self) -> str:
        return "stub"

    @property
    def supports_indexes(self) -> bool:
        return False

    @property
    def has_fast_row_counts(self) -> bool:
        return False

    def create_engine(self, **kwargs) -> Engine:
        return MagicMock(spec=Engine)

    def fast_row_counts(
        self, engine: Engine, schema_name: str | None = None
    ) -> dict[str, int]:
        return {}

    def quote_identifier(self, identifier: str) -> str:
        return f'"{identifier}"'


class _AnotherStubDialect(_StubDialect):
    """Second stub for overwrite tests."""

    @property
    def name(self) -> str:
        return "another"


@pytest.fixture(autouse=True)
def _clean_registry() -> None:
    """Reset registry between tests to avoid cross-test pollution."""
    saved = registry._REGISTRY.copy()
    registry._REGISTRY.clear()
    yield  # type: ignore[func-returns-value]
    registry._REGISTRY.clear()
    registry._REGISTRY.update(saved)


class TestRegisterDialect:
    """Test dialect registration."""

    def test_register_succeeds(self) -> None:
        register_dialect("test", _StubDialect)

    def test_get_returns_registered_class(self) -> None:
        register_dialect("test", _StubDialect)
        result = get_dialect("test")
        assert result is _StubDialect

    def test_overwrite_same_name(self) -> None:
        register_dialect("test", _StubDialect)
        register_dialect("test", _AnotherStubDialect)
        result = get_dialect("test")
        assert result is _AnotherStubDialect


class TestGetDialect:
    """Test dialect lookup."""

    def test_unknown_raises_value_error(self) -> None:
        with pytest.raises(ValueError, match=r"Unknown dialect 'unknown'"):
            get_dialect("unknown")

    def test_unknown_error_lists_registered_dialects(self) -> None:
        register_dialect("alpha", _StubDialect)
        register_dialect("beta", _StubDialect)
        with pytest.raises(ValueError, match=r"alpha, beta"):
            get_dialect("unknown")

    def test_empty_registry_shows_none(self) -> None:
        with pytest.raises(ValueError, match=r"\(none\)"):
            get_dialect("unknown")
