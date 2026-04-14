"""Backward-compatibility shim -- azure_auth moved to src/db/dialects/azure_auth.

All imports from this module are re-exported from the new location.
"""

from src.db.dialects.azure_auth import (  # noqa: F401
    SQL_COPT_SS_ACCESS_TOKEN,
    AzureTokenProvider,
)
