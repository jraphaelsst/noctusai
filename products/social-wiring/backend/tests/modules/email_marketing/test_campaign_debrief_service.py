"""Unit tests for the campaign debrief service (Phase 12 M4)."""
import logging

import pytest
from unittest.mock import AsyncMock, patch

from noctusai_lib.testing import MockSupabaseClient

_NARRATIVE_LLM = "noctusai_lib.domain.digest.narrative.chat_completion"
_DIGEST_CREDS = "noctusai_lib.integrations.email.digest.resolve_credential"


def _db(campaign=None, send_logs=(), link_clicks=()):
    """Real `_fetch_window` over the seed mock - no patching of our own code."""
    db = MockSupabaseClient()
    db.set_table_data("campaigns", [campaign] if campaign else [])
    db.set_table_data("send_logs", list(send_logs))
    db.set_table_data("link_clicks", list(link_clicks))
    return db


class TestAggregate:
    def test_status_buckets_and_rates(self):
        from app.modules.email_marketing.services.campaign_debrief_service import _aggregate
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
        from app.modules.email_marketing.services.campaign_debrief_service import _aggregate
        campaign = {"id": "c1", "nome": "x", "total_recipients": 0}
        metrics, top_links = _aggregate(campaign, [], [])
        assert metrics["sent_rate"] == 0.0
        assert metrics["open_rate"] == 0.0
        assert top_links == []


class TestBuildDebrief:
    @pytest.mark.asyncio
    async def test_returns_none_when_campaign_missing(self):
        from app.modules.email_marketing.services import campaign_debrief_service

        result = await campaign_debrief_service.build_debrief(
            _db(campaign=None), campaign_id="missing"
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_assembles_digest_and_summary(self):
        from app.modules.email_marketing.services import campaign_debrief_service

        db = _db(
            {"id": "c1", "nome": "BFCM 2026", "total_recipients": 50},
            [
                {"id": "s1", "campaign_id": "c1", "status": "delivered"},
                {"id": "s2", "campaign_id": "c1", "status": "opened"},
                {"id": "s3", "campaign_id": "c1", "status": "clicked"},
            ],
            [{"send_log_id": "s3", "url": "https://x.com/cta"}],
        )
        with patch(
            _NARRATIVE_LLM,
            new_callable=AsyncMock,
            return_value="Panorama.\n\nObservações.\n\nRecomendação.",
        ):
            built = await campaign_debrief_service.build_debrief(db, campaign_id="c1")
        assert built is not None
        digest, summary = built
        assert "BFCM 2026" in digest.subject
        assert "Panorama." in digest.html
        assert summary["metrics"]["sent"] == 3
        assert summary["top_links"][0]["url"] == "https://x.com/cta"

    @pytest.mark.asyncio
    async def test_other_campaigns_send_logs_are_not_counted(self):
        from app.modules.email_marketing.services import campaign_debrief_service

        db = _db(
            {"id": "c1", "nome": "Mine", "total_recipients": 5},
            [
                {"id": "s1", "campaign_id": "c1", "status": "delivered"},
                {"id": "s2", "campaign_id": "other", "status": "delivered"},
            ],
        )
        with patch(_NARRATIVE_LLM, new_callable=AsyncMock, return_value="x"):
            _, summary = await campaign_debrief_service.build_debrief(db, campaign_id="c1")
        assert summary["metrics"]["delivered"] == 1

    @pytest.mark.asyncio
    async def test_llm_failure_uses_template_fallback(self):
        from app.modules.email_marketing.services import campaign_debrief_service

        db = _db({"id": "c1", "nome": "Test", "total_recipients": 1})
        with patch(
            _NARRATIVE_LLM,
            new_callable=AsyncMock,
            side_effect=RuntimeError("LLM down"),
        ):
            built = await campaign_debrief_service.build_debrief(db, campaign_id="c1")
        digest, summary = built
        assert "LLM indisponível" in summary["narrative"]


class TestSendCampaignDebrief:
    @pytest.mark.asyncio
    async def test_no_email_backend_is_a_loud_dry_run(self, caplog):
        """No Resend/SMTP credential ⇒ send_digest's own dry-run branch: not
        sent, flagged dry_run, recipient logged - never a silent 'sent'."""
        from app.modules.email_marketing.services import campaign_debrief_service

        db = _db({"id": "c1", "nome": "X", "total_recipients": 1})
        with patch(_DIGEST_CREDS, return_value=None), patch(
            _NARRATIVE_LLM, new_callable=AsyncMock, return_value="x"
        ), caplog.at_level(logging.INFO):
            result = await campaign_debrief_service.send_campaign_debrief(
                db, campaign_id="c1", recipient="user@x.com"
            )
        assert result["sent"] is False
        assert result["dry_run"] is True
        assert result["summary"]["campaign_id"] == "c1"
        assert any("DRY-RUN" in r.getMessage() and "user@x.com" in r.getMessage()
                   for r in caplog.records)

    @pytest.mark.asyncio
    async def test_invalid_recipient_is_reported_not_sent(self):
        from app.modules.email_marketing.services import campaign_debrief_service

        db = _db({"id": "c1", "nome": "X", "total_recipients": 1})
        with patch(_NARRATIVE_LLM, new_callable=AsyncMock, return_value="x"):
            result = await campaign_debrief_service.send_campaign_debrief(
                db, campaign_id="c1", recipient="not-an-email"
            )
        assert result["sent"] is False
        assert "invalid recipient" in result["error"]

    @pytest.mark.asyncio
    async def test_send_returns_none_when_campaign_missing(self):
        from app.modules.email_marketing.services import campaign_debrief_service

        result = await campaign_debrief_service.send_campaign_debrief(
            _db(campaign=None), campaign_id="missing", recipient="user@x.com"
        )
        assert result is None
