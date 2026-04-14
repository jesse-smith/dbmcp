"""Database dialect abstractions for multi-dialect support."""

from src.db.dialects.generic import GenericDialect
from src.db.dialects.mssql import MssqlDialect
from src.db.dialects.protocol import DialectStrategy
from src.db.dialects.registry import get_dialect, register_dialect, resolve_dialect_from_url

register_dialect("mssql", MssqlDialect)
register_dialect("generic", GenericDialect)

__all__ = [
    "DialectStrategy",
    "GenericDialect",
    "MssqlDialect",
    "get_dialect",
    "register_dialect",
    "resolve_dialect_from_url",
]
