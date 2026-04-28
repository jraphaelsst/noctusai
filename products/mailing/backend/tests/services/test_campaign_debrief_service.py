"""Unit tests for the campaign debrief service (Phase 12 M4)."""
import pytest
from unittest.mock import AsyncMock, patch

from noctusai_lib.email.digest import DigestSendResult


class TestAggregate:
    def test_status_buckets_and_rates(self):
        from app.services.campaign_debrief_service import _aggregate
        campaign = {"id": "c1", "nome": "Black Friday", "total_recipients": 100}
        send_logs = [
            {"id": "s1", "status": "delivered"},
            {"id": "s2", "status": "delivered"},
            {"id": "s3", "status": "opened"},
            {"id": "s4", "status": "clicked"},
            {"id": "s5", "status": "bounced"},
            {"id": "s6", "status": "complained"},
            {"id": "s7", "status": "failed"},
        ]
        link_clicks = [
            {"send_log_id": "s4", "url": "https://x.com/promo"},
            {"send_log_id": "s4", "url": "https://x.com/promo"},
            {"send_log_id": "s4", "url": "https://x.com/about"},
        ]
        metrics, top_links = _aggregate(campaign, send_logs, link_clicks)
        # delivered + opened + clicked + bounced + complained = sent
        assert metrics["sent"] == 6
        assert metrics["delivered"] == 4  # delivered + opened + clicked
        assert metrics["opened"] == 2     # opened + clicked
        assert metrics["clicked"] == 1
        assert metrics["bounced"] == 1
        assert metrics["complained"] == 1
        assert metrics["failed"] == 1
        assert metrics["total_recipients"] == 100
        assert metrics["sent_rate"] == 6.0
        assert metrics["bounce_rate"] == round(1 / 6 * 100, 2)
        # delivered rate = 4 / 6 sent ≈ 66.67
        assert metrics["delivered_rate"] == round(4 / 6 * 100, 2)
        # open rate = 2 / 4 delivered = 50%
        assert metrics["open_rate"] == 50.0
        assert metrics["click_rate"] == 25.0
        assert top_links[0] == ("https://x.com/promo", 2)

    def test_empty_send_logs_keeps_zero_rates(self):
        from app.services.campaign_debrief_service import _aggregate
        campaign = {"id": "c1", "nome": "x", "total_recipients": 0}
        metrics, top_links = _aggregate(campaign, [], [])
        assert metrics["sent_rate"] == 0.0
        assert metrics["open_rate"] == 0.0
        assert top_links == []


class TestBuildDebrief:
    @pytest.mark.asyncio
    async def test_returns_none_when_campaign_missing(self):
        from app.services import campaign_debrief_service

        async def _fake_fetch(db, *, campaign_id):
            return None

        with patch(
            "app.services.campaign_debrief_service._fetch_window",
            side_effect=_fake_fetch,
        ):
            result = await campaign_debrief_service.build_debrief(
                db=object(), campaign_id="missing"
            )
        assert result is None

    @pytest.mark.asyncio
    async def test_assembles_digest_and_summary(self):
        from app.services import campaign_debrief_service

        async def _fake_fetch(db, *, campaign_id):
            return (
                {"id": campaign_id, "nome": "BFCM 2026", "total_recipients": 50},
                [
                    {"id": "s1", "status": "delivered"},
                    {"id": "s2", "status": "opened"},
                    {"id": "s3", "status": "clicked"},
                ],
                [{"send_log_id": "s3", "url": "https://x.com/cta"}],
            )

        with patch(
            "app.services.campaign_debrief_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.campaign_debrief_service.chat_completion",
            new_callable=AsyncMock,
            return_value="Panorama.\n\nObservações.\n\nRecomendação.",
        ):
            built = await campaign_debrief_service.build_debrief(
                db=object(), campaign_id="c1"
            )
        assert built is not None
        digest, summary = built
        assert "BFCM 2026" in digest.subject
        assert "Panorama." in digest.html
        assert summary["metrics"]["sent"] == 3
        assert summary["top_links"][0]["url"] == "https://x.com/cta"

    @pytest.mark.asyncio
    async def test_llm_failure_uses_template_fallback(self):
        from app.services import campaign_debrief_service

        async def _fake_fetch(db, *, campaign_id):
            return ({"id": campaign_id, "nome": "Test", "total_recipients": 1}, [], [])

        with patch(
            "app.services.campaign_debrief_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.campaign_debrief_service.chat_completion",
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            built = await campaign_debrief_service.build_debrief(
                db=object(), campaign_id="c1"
            )
        digest, summary = built
        assert "LLM indisponível" in summary["narrative"]


class TestSendCampaignDebrief:
    @pytest.mark.asyncio
    async def test_passes_through_send_digest_result(self):
        from app.services import campaign_debrief_service

        async def _fake_fetch(db, *, campaign_id):
            return ({"id": campaign_id, "nome": "X", "total_recipients": 1}, [], [])

        with patch(
            "app.services.campaign_debrief_service._fetch_window",
            side_effect=_fake_fetch,
        ), patch(
            "app.services.campaign_debrief_service.chat_completion",
            new_callable=AsyncMock,
            return_value="x",
        ), patch(
            "app.services.campaign_debrief_service.send_digest",
            new_callable=AsyncMock,
            return_value=DigestSendResult(sent=True, external_id="abc", subject="x"),
        ):
            result = await campaign_debrief_service.send_campaign_debrief(
                db=object(), campaign_id="c1", recipient="user@x"
            )
        assert result["sent"] is True
        assert result["external_id"] == "abc"

    @pytest.mark.asyncio
    async def test_send_returns_none_when_campaign_missing(self):
        from app.services import campaign_debrief_service

        async def _fake_fetch(db, *, campaign_id):
            return None

        with patch(
            "app.services.campaign_debrief_service._fetch_window",
            side_effect=_fake_fetch,
        ):
            result = await campaign_debrief_service.send_campaign_debrief(
                db=object(), campaign_id="missing", recipient="user@x"
            )
        assert result is None
