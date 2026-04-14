"""Azure AD token provider for SQL Server authentication.

Acquires Azure AD tokens via DefaultAzureCredential and packs them
for pyodbc's SQL_COPT_SS_ACCESS_TOKEN connection attribute.
"""

import struct

from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError, DefaultAzureCredential

from src.logging_config import get_logger

logger = get_logger(__name__)

# Azure SQL Database token scope
_AZURE_SQL_SCOPE = "https://database.windows.net/.default"

# pyodbc connection attribute for access token (SQL_COPT_SS_ACCESS_TOKEN)
SQL_COPT_SS_ACCESS_TOKEN = 1256


class AzureTokenProvider:
    """Provides Azure AD tokens for SQL Server connections.

    Uses DefaultAzureCredential with non-interactive sources only.
    Token packing follows the ODBC Driver 18 C struct format:
    4-byte LE length prefix + UTF-16LE encoded token.

    Attributes:
        tenant_id: Optional Azure AD tenant ID to target.
    """

    def __init__(self, tenant_id: str | None = None):
        self._tenant_id = tenant_id
        self._credential = DefaultAzureCredential(
            exclude_interactive_browser_credential=True,
            exclude_visual_studio_code_credential=True,
        )

    def get_token(self) -> str:
        """Acquire an Azure AD access token for Azure SQL.

        Returns:
            Token string from the credential chain.

        Raises:
            ConnectionError: If token acquisition fails, with actionable guidance.
        """
        try:
            if self._tenant_id:
                access_token = self._credential.get_token(
                    _AZURE_SQL_SCOPE,
                    tenant_id=self._tenant_id,
                )
            else:
                access_token = self._credential.get_token(_AZURE_SQL_SCOPE)
            return access_token.token
        except CredentialUnavailableError as e:
            logger.error(f"Azure AD credential unavailable: {type(e).__name__}")
            raise ConnectionError(
                "Azure AD authentication failed: No credential sources available. "
                "Run 'az login' or set AZURE_CLIENT_ID, AZURE_CLIENT_SECRET, "
                "and AZURE_TENANT_ID environment variables."
            ) from e
        except ClientAuthenticationError as e:
            logger.error(f"Azure AD authentication error: {type(e).__name__}")
            raise ConnectionError(
                "Azure AD authentication failed: Credentials are expired or invalid. "
                "Re-authenticate with 'az login' or refresh your service principal credentials."
            ) from e

    @staticmethod
    def pack_token_for_pyodbc(token: str) -> bytes:
        """Pack an access token for pyodbc's SQL_COPT_SS_ACCESS_TOKEN.

        The ODBC Driver 18 expects a C struct: 4-byte little-endian length
        prefix followed by the UTF-16LE encoded token (no null terminator).

        Args:
            token: Azure AD access token string.

        Returns:
            Packed bytes suitable for attrs_before={1256: packed}.
        """
        encoded = token.encode("utf-16-le")
        return struct.pack("<I", len(encoded)) + encoded
