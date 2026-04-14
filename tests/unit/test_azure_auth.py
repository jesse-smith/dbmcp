"""Unit tests for Azure AD token provider.

Tests for AzureTokenProvider: token packing, credential creation, token acquisition, and error handling.
"""

import struct
from unittest.mock import MagicMock, patch

import pytest
from azure.core.exceptions import ClientAuthenticationError
from azure.identity import CredentialUnavailableError

from src.db.azure_auth import AzureTokenProvider


class TestPackTokenForPyodbc:
    """T003: Tests for pack_token_for_pyodbc — correct struct packing."""

    def test_packs_with_4_byte_le_length_prefix(self):
        """Token bytes start with 4-byte little-endian length of UTF-16LE encoded token."""
        provider = AzureTokenProvider()
        token = "eyJ0eXAiOiJKV1QiLCJhbGciOiJSUzI1NiJ9"
        packed = provider.pack_token_for_pyodbc(token)

        encoded = token.encode("utf-16-le")
        expected_prefix = struct.pack("<I", len(encoded))
        assert packed[:4] == expected_prefix

    def test_packs_utf16le_encoded_token(self):
        """Token body is UTF-16LE encoded after the length prefix."""
        provider = AzureTokenProvider()
        token = "test-token-value"
        packed = provider.pack_token_for_pyodbc(token)

        encoded = token.encode("utf-16-le")
        assert packed[4:] == encoded

    def test_full_packed_structure(self):
        """Full packed bytes match struct.pack('<I', len) + utf16le."""
        provider = AzureTokenProvider()
        token = "abc123"
        packed = provider.pack_token_for_pyodbc(token)

        encoded = token.encode("utf-16-le")
        expected = struct.pack("<I", len(encoded)) + encoded
        assert packed == expected

    def test_empty_token_packs_correctly(self):
        """Empty token packs as 4-byte zero length prefix."""
        provider = AzureTokenProvider()
        packed = provider.pack_token_for_pyodbc("")

        assert packed == struct.pack("<I", 0)


class TestAzureTokenProviderInit:
    """T004: Tests for AzureTokenProvider.__init__ — credential creation."""

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_creates_credential_without_tenant(self, mock_credential_cls):
        """Creates DefaultAzureCredential when no tenant_id provided."""
        AzureTokenProvider()

        mock_credential_cls.assert_called_once_with(
            exclude_interactive_browser_credential=True,
            exclude_visual_studio_code_credential=True,
        )

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_creates_credential_with_tenant(self, mock_credential_cls):
        """Passes tenant_id to DefaultAzureCredential when provided."""
        AzureTokenProvider(tenant_id="12345678-1234-1234-1234-123456789012")

        mock_credential_cls.assert_called_once_with(
            exclude_interactive_browser_credential=True,
            exclude_visual_studio_code_credential=True,
        )

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_excludes_interactive_browser(self, mock_credential_cls):
        """exclude_interactive_browser_credential=True is always set."""
        AzureTokenProvider()
        call_kwargs = mock_credential_cls.call_args[1]
        assert call_kwargs["exclude_interactive_browser_credential"] is True

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_excludes_vscode_credential(self, mock_credential_cls):
        """exclude_visual_studio_code_credential=True is always set."""
        AzureTokenProvider()
        call_kwargs = mock_credential_cls.call_args[1]
        assert call_kwargs["exclude_visual_studio_code_credential"] is True


class TestAzureTokenProviderGetToken:
    """T005: Tests for AzureTokenProvider.get_token — token acquisition."""

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_returns_token_string(self, mock_credential_cls):
        """get_token() returns the token string from the credential."""
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = MagicMock(token="fake-access-token")
        mock_credential_cls.return_value = mock_credential

        provider = AzureTokenProvider()
        token = provider.get_token()

        assert token == "fake-access-token"

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_calls_with_correct_scope(self, mock_credential_cls):
        """get_token() requests the Azure SQL database scope."""
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = MagicMock(token="token")
        mock_credential_cls.return_value = mock_credential

        provider = AzureTokenProvider()
        provider.get_token()

        mock_credential.get_token.assert_called_once_with(
            "https://database.windows.net/.default",
        )

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_calls_with_tenant_id_when_provided(self, mock_credential_cls):
        """get_token() passes tenant_id to credential.get_token when set."""
        mock_credential = MagicMock()
        mock_credential.get_token.return_value = MagicMock(token="token")
        mock_credential_cls.return_value = mock_credential

        tenant = "12345678-1234-1234-1234-123456789012"
        provider = AzureTokenProvider(tenant_id=tenant)
        provider.get_token()

        mock_credential.get_token.assert_called_once_with(
            "https://database.windows.net/.default",
            tenant_id=tenant,
        )


class TestAzureTokenProviderErrorHandling:
    """T024-T025: Tests for error handling in AzureTokenProvider."""

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_credential_unavailable_produces_actionable_message(self, mock_credential_cls):
        """T024: CredentialUnavailableError is caught and translated to actionable message."""
        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = CredentialUnavailableError(
            message="No credentials found"
        )
        mock_credential_cls.return_value = mock_credential

        provider = AzureTokenProvider()

        with pytest.raises(ConnectionError) as exc_info:
            provider.get_token()

        error_msg = str(exc_info.value)
        assert "az login" in error_msg
        assert "AZURE_CLIENT_ID" in error_msg
        assert "AZURE_CLIENT_SECRET" in error_msg
        assert "AZURE_TENANT_ID" in error_msg

    @patch("src.db.azure_auth.DefaultAzureCredential")
    def test_client_auth_error_produces_expiry_message(self, mock_credential_cls):
        """T025: ClientAuthenticationError produces message about expired credentials."""
        mock_credential = MagicMock()
        mock_credential.get_token.side_effect = ClientAuthenticationError(
            message="Token has expired"
        )
        mock_credential_cls.return_value = mock_credential

        provider = AzureTokenProvider()

        with pytest.raises(ConnectionError) as exc_info:
            provider.get_token()

        error_msg = str(exc_info.value)
        assert "expired" in error_msg.lower() or "re-authenticat" in error_msg.lower()
