"""Dialect registry mapping dialect names to strategy implementations."""

from src.db.dialects.protocol import DialectStrategy

_REGISTRY: dict[str, type[DialectStrategy]] = {}


def register_dialect(name: str, dialect_class: type[DialectStrategy]) -> None:
    """Register a dialect strategy implementation.

    Args:
        name: Dialect identifier (e.g., 'mssql', 'generic').
        dialect_class: Class implementing DialectStrategy protocol.
    """
    _REGISTRY[name] = dialect_class


def get_dialect(name: str) -> type[DialectStrategy]:
    """Look up a dialect strategy class by name.

    Args:
        name: Dialect identifier.

    Returns:
        The dialect strategy class.

    Raises:
        ValueError: If dialect name is not registered.
    """
    if name not in _REGISTRY:
        registered = ", ".join(sorted(_REGISTRY.keys())) or "(none)"
        raise ValueError(
            f"Unknown dialect '{name}'. Registered dialects: {registered}"
        )
    return _REGISTRY[name]
