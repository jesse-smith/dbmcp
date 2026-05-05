"""Shared formatting helpers for MCP tool error_message fields."""

from __future__ import annotations


def format_unexpected_error(exc: BaseException, *, include_type: bool = False) -> str:
    """Format a generic-handler exception for MCP client error_message field.

    ImportError/ModuleNotFoundError are surfaced verbatim (they carry an
    actionable install hint at their raise site — e.g., the databricks
    dialect's "Install with: pip install dbmcp[databricks]" message). All
    other exceptions keep the legacy "Unexpected error:" prefix so genuine
    bugs remain visible.

    Args:
        exc: The exception caught in a generic handler.
        include_type: If True, include the exception type name in the prefix
            (matches schema_tools.connect_database's existing format). If
            False, omit the type name (matches analysis_tools' format).

    Returns:
        The formatted error_message string for the MCP response.
    """
    if isinstance(exc, (ImportError, ModuleNotFoundError)):
        return str(exc)
    if include_type:
        return f"Unexpected error: {type(exc).__name__}: {exc}"
    return f"Unexpected error: {exc}"
