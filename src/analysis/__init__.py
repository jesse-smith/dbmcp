"""Data-exposure analysis module.

Provides raw statistical analysis and structural metadata for database columns,
tables, and relationships. No interpretive logic or confidence scoring.
"""

from src.analysis.column_stats import ColumnStatsCollector

__all__ = [
    "ColumnStatsCollector",
]
