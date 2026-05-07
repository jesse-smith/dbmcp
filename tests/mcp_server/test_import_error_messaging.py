"""Pin the wording contract for format_unexpected_error().

ImportError/ModuleNotFoundError must be surfaced verbatim (the raise site
already carries an actionable install hint). Other exceptions retain the
legacy "Unexpected error:" prefix so genuine bugs stay visible.
"""

from __future__ import annotations

from src.mcp_server._errors import format_unexpected_error


def test_import_error_is_verbatim_no_prefix() -> None:
    msg = "Databricks support requires databricks-sqlalchemy. Reinstall dbmcp to pull it in."
    result = format_unexpected_error(ImportError(msg))
    assert result == msg


def test_module_not_found_error_is_verbatim_no_prefix() -> None:
    msg = "No module named 'foo'"
    result = format_unexpected_error(ModuleNotFoundError(msg))
    assert result == msg


def test_generic_exception_with_type_prefix() -> None:
    result = format_unexpected_error(RuntimeError("boom"), include_type=True)
    assert result == "Unexpected error: RuntimeError: boom"


def test_generic_exception_without_type_prefix() -> None:
    result = format_unexpected_error(RuntimeError("boom"), include_type=False)
    assert result == "Unexpected error: boom"


def test_import_error_does_not_start_with_unexpected_prefix() -> None:
    """Acceptance pin for the source todo — ImportError must not be wrapped."""
    result = format_unexpected_error(
        ImportError(
            "Databricks support requires databricks-sqlalchemy. "
            "Reinstall dbmcp to pull it in."
        )
    )
    assert not result.startswith("Unexpected error:")
    assert result.startswith("Databricks support requires databricks-sqlalchemy")
