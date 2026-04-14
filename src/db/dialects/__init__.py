"""Database dialect abstractions for multi-dialect support."""

from src.db.dialects.mssql import MssqlDialect
from src.db.dialects.protocol import DialectStrategy
from src.db.dialects.registry import get_dialect, register_dialect

register_dialect("mssql", MssqlDialect)

__all__ = ["DialectStrategy", "MssqlDialect", "get_dialect", "register_dialect"]
