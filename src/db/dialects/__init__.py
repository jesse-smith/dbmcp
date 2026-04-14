"""Database dialect abstractions for multi-dialect support."""

from src.db.dialects.protocol import DialectStrategy
from src.db.dialects.registry import get_dialect, register_dialect

__all__ = ["DialectStrategy", "get_dialect", "register_dialect"]
