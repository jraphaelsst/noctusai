"""
Unit tests for meta_api_service — Meta Graph API config, dry-run, webhook parsing.
"""
import pytest

from tests.conftest import MockSupabaseClient


# ---------------------------------------------------------------------------
# MetaApiConfig
# ---------------------------------------------------------------------------

class TestMetaApiConfig:

    def test_not_configured_without_token(self):
        from app.services.meta_api_service import MetaApiConfig
        config = MetaApiConfig()

        assert config.is_configured is False

    def test_configured_with_token(self):
        from app.services.meta_api_service import MetaApiConfig
        config = MetaApiConfig(access_token="tok-123")

        assert config.is_configured is True

    def test_headers_include_bearer(self):
        from app.services.meta_api_service import MetaApiConfig
        config = MetaApiConfig(access_token="my-token")

        assert config.headers == {"Authorization": "Bearer my-token"}

    def test_base_url_includes_version(self):
        from app.services.meta_api_service import MetaApiConfig
        config = MetaApiConfig(api_version="v19.0")

        assert config.base_url == "https://graph.facebook.com/v19.0"

    def test_default_api_version(self):
        from app.services.meta_api_service import MetaApiConfig
        config = MetaApiConfig()

        assert "v18.0" in config.base_url


# ---------------------------------------------------------------------------
# sync_leads — dry-run mode
# ---------------------------------------------------------------------------

class TestSyncLeadsDryRun:

    @pytest.mark.asyncio
    async def test_dry_run_returns_empty(self):
        from app.services.meta_api_service import MetaApiConfig, sync_leads
        config = MetaApiConfig()  # no token -> dry-run

        result = await sync_leads(config)

        assert result == []

    @pytest.mark.asyncio
    async def test_dry_run_with_form_id(self):
        from app.services.meta_api_service import MetaApiConfig, sync_leads
        config = MetaApiConfig()

        result = await sync_leads(config, form_id="form-123")

        assert result == []


# ---------------------------------------------------------------------------
# sync_campaigns — dry-run mode
# ---------------------------------------------------------------------------

class TestSyncCampaignsDryRun:

    @pytest.mark.asyncio
    async def test_dry_run_no_token(self):
        from app.services.meta_api_service import MetaApiConfig, sync_campaigns
        config = MetaApiConfig()

        result = await sync_campaigns(config)

        assert result == []

    @pytest.mark.asyncio
    async def test_dry_run_no_ad_account(self):
        from app.services.meta_api_service import MetaApiConfig, sync_campaigns
        config = MetaApiConfig(access_token="tok-123")  # token but no ad_account

        result = await sync_campaigns(config)

        assert result == []
