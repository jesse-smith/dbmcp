"""Data-exposure analysis module.

Provides raw statistical analysis and structural metadata for database columns,
tables, and relationships. No interpretive logic or confidence scoring.
"""

from src.analysis.column_stats import ColumnStatsCollector
from src.analysis.fk_candidates import FKCandidateSearch
from src.analysis.pk_discovery import PKDiscovery

__all__ = [
    "ColumnStatsCollector",
    "FKCandidateSearch",
    "PKDiscovery",
]
