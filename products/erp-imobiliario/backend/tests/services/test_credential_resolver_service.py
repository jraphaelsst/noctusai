"""
Unit tests for Credential Resolver — resolution chain, fallbacks, and error handling.
"""
import pytest
from unittest.mock import patch, MagicMock

from tests.conftest import MockSupabaseClient, MockSupabaseResponse


# ---------------------------------------------------------------------------
# resolve_credential — org_settings → platform_settings → env
# ---------------------------------------------------------------------------

class TestResolveCredentialChain:
    """Tests for the 3-step resolution chain."""

    def _make_public_client(self, org_data=None, platform_data=None):
        """Build a MockSupabaseClient with org_settings and platform_settings tables."""
        client = MockSupabaseClient()
        client.set_table_data("org_settings", org_data or [])
        client.set_table_data("platform_settings", platform_data or [])
        return client

    def test_resolves_from_org_settings_first(self):
        """Step 1: org_settings value takes priority over everything else."""
        from app.services.credential_resolver import resolve_credential

        mock_client = self._make_public_client(
            org_data=[{"value": "org-level-key"}],
            platform_data=[{"value": "platform-level-key"}],
        )

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.openai_api_key = "env-level-key"
            result = resolve_credential("openai_api_key", org_id="test-org-123")
            assert result == "org-level-key"

    def test_falls_back_to_platform_settings(self):
        """Step 2: platform_settings when org_settings has no match."""
        from app.services.credential_resolver import resolve_credential

        mock_client = self._make_public_client(
            org_data=[],
            platform_data=[{"value": "platform-level-key"}],
        )

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.openai_api_key = "env-level-key"
            result = resolve_credential("openai_api_key", org_id="test-org-123")
            assert result == "platform-level-key"

    def test_falls_back_to_env_variable(self):
        """Step 3: environment variable when both tables return nothing."""
        from app.services.credential_resolver import resolve_credential

        mock_client = self._make_public_client(org_data=[], platform_data=[])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.openai_api_key = "env-level-key"
            result = resolve_credential("openai_api_key", org_id="test-org-123")
            assert result == "env-level-key"

    def test_returns_none_when_not_found_anywhere(self):
        """None when credential is missing from all 3 sources."""
        from app.services.credential_resolver import resolve_credential

        mock_client = self._make_public_client(org_data=[], platform_data=[])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.nonexistent_key = None
            result = resolve_credential("nonexistent_key", org_id="test-org-123")
            assert result is None


class TestResolveCredentialNoOrgId:
    """Tests when org_id is not provided (skips step 1)."""

    def test_skips_org_settings_without_org_id(self):
        """When org_id is None, skip org_settings and go straight to platform_settings."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("platform_settings", [{"value": "platform-key"}])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.resend_api_key = "env-key"
            result = resolve_credential("resend_api_key")
            assert result == "platform-key"

    def test_falls_to_env_without_org_id(self):
        """Without org_id and empty platform_settings, fall to env."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("platform_settings", [])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.infosimples_token = "env-token"
            result = resolve_credential("infosimples_token")
            assert result == "env-token"


class TestResolveCredentialEdgeCases:
    """Edge cases: empty values, exceptions, missing attributes."""

    def test_skips_org_settings_with_empty_value(self):
        """Empty string in org_settings is treated as missing."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("org_settings", [{"value": ""}])
        mock_client.set_table_data("platform_settings", [{"value": "platform-key"}])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.openai_api_key = None
            result = resolve_credential("openai_api_key", org_id="org-1")
            assert result == "platform-key"

    def test_skips_platform_settings_with_empty_value(self):
        """Empty string in platform_settings is treated as missing."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("org_settings", [])
        mock_client.set_table_data("platform_settings", [{"value": ""}])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.clicksign_api_token = "env-token"
            result = resolve_credential("clicksign_api_token", org_id="org-1")
            assert result == "env-token"

    def test_handles_org_settings_exception_gracefully(self):
        """Database error on org_settings lookup falls through to platform_settings."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        # Make org_settings raise, but platform_settings work
        mock_client._tables["org_settings"] = MagicMock()
        mock_client._tables["org_settings"].select.side_effect = Exception("DB error")
        mock_client.set_table_data("platform_settings", [{"value": "fallback-key"}])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.openai_api_key = None
            result = resolve_credential("openai_api_key", org_id="org-1")
            assert result == "fallback-key"

    def test_handles_platform_settings_exception_gracefully(self):
        """Database error on platform_settings falls through to env."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("org_settings", [])
        mock_client._tables["platform_settings"] = MagicMock()
        mock_client._tables["platform_settings"].select.side_effect = Exception("DB error")

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.resend_api_key = "env-key"
            result = resolve_credential("resend_api_key", org_id="org-1")
            assert result == "env-key"

    def test_missing_settings_attribute_returns_none(self):
        """When the key does not exist as a Settings attribute, return None."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("org_settings", [])
        mock_client.set_table_data("platform_settings", [])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            # Simulate missing attribute via spec
            del mock_settings.totally_fake_key
            result = resolve_credential("totally_fake_key")
            assert result is None

    def test_env_value_empty_string_returns_none(self):
        """Empty string from env (falsy) is treated as None."""
        from app.services.credential_resolver import resolve_credential

        mock_client = MockSupabaseClient()
        mock_client.set_table_data("org_settings", [])
        mock_client.set_table_data("platform_settings", [])

        with patch("app.services.credential_resolver._get_public_client", return_value=mock_client), \
             patch("app.services.credential_resolver.settings") as mock_settings:
            mock_settings.openai_api_key = ""
            result = resolve_credential("openai_api_key")
            assert result is None
