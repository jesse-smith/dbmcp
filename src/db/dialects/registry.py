"""Dialect registry mapping dialect names to strategy implementations."""

from __future__ import annotations

from sqlalchemy.engine.url import make_url

from src.db.dialects.protocol import DialectStrategy
from src.logging_config import get_logger

logger = get_logger(__name__)

_REGISTRY: dict[str, type[DialectStrategy]] = {}

# URL scheme (from make_url().get_backend_name()) -> registered dialect name
_URL_SCHEME_TO_DIALECT: dict[str, str] = {
    "mssql": "mssql",
    "databricks": "databricks",
}


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


def resolve_dialect_from_url(url: str) -> DialectStrategy:
    """Resolve a SQLAlchemy URL to an instantiated dialect.

    Known schemes (mssql, databricks) map to registered dialect classes.
    Other schemes map to GenericDialect with appropriate sqlglot dialect.
    Unknown schemes get GenericDialect with sqlglot_dialect=None and a warning.

    Args:
        url: SQLAlchemy connection URL string.

    Returns:
        Instantiated DialectStrategy.
    """
    from src.db.dialects.generic import _URL_SCHEME_TO_SQLGLOT, GenericDialect

    parsed = make_url(url)
    backend = parsed.get_backend_name()

    if backend in _URL_SCHEME_TO_DIALECT:
        dialect_name = _URL_SCHEME_TO_DIALECT[backend]
        dialect_cls = get_dialect(dialect_name)
        return dialect_cls()

    sqlglot_name = _URL_SCHEME_TO_SQLGLOT.get(backend)
    if sqlglot_name is None:
        logger.warning(
            "No optimized dialect for '%s' -- using generic fallback. "
            "Queries will use generic SQL parsing.",
            backend,
        )
    return GenericDialect(sqlglot_dialect_name=sqlglot_name)
