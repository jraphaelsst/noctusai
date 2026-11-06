"""Tests for `app.services.website_lead_fanout` — every config value and
collaborator is DI-injected, never monkeypatching `settings` or our own
functions (`KB § PATTERNS/compliance/testing.md`)."""
import pytest

from app.services import website_lead_fanout
from noctusai_lib.integrations.outbound_webhook.fake import FakeOutboundWebhookSender, failure, success

LEAD = {
    "id": "lead-1", "source": "waitlist", "name": "Ana", "email": "ana@example.com",
    "phone_e164": None, "landing_path": "/",
}


@pytest.fixture
def recorded_failures():
    calls = []

    def _record(lead_id, channel, error):
        calls.append((lead_id, channel, error))

    return calls, _record


class TestRunFanout:
    @pytest.mark.asyncio
    async def test_optional_channels_skipped_when_unconfigured(self, recorded_failures):
        calls, record = recorded_failures
        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="", in_app_notifier=lambda lead: 1, record_failure=record,
        )
        assert calls == []

    @pytest.mark.asyncio
    async def test_in_app_notice_is_written(self, recorded_failures):
        calls, record = recorded_failures
        seen = []

        def notifier(lead):
            seen.append(lead)
            return 2

        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="", in_app_notifier=notifier, record_failure=record,
        )
        assert seen == [LEAD]
        assert calls == []

    @pytest.mark.asyncio
    async def test_in_app_zero_rows_records_failure(self, recorded_failures):
        calls, record = recorded_failures
        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="", in_app_notifier=lambda lead: 0, record_failure=record,
        )
        assert [(c[0], c[1]) for c in calls] == [("lead-1", "in_app")]

    @pytest.mark.asyncio
    async def test_in_app_raising_records_failure(self, recorded_failures):
        calls, record = recorded_failures

        def boom(lead):
            raise RuntimeError("db down")

        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="", in_app_notifier=boom, record_failure=record,
        )
        assert [(c[0], c[1]) for c in calls] == [("lead-1", "in_app")]
        assert "db down" in calls[0][2]

    def test_fanout_has_no_email_seam_and_core_has_no_lead_email_sender(self):
        import inspect
        from app.services import email_service
        params = inspect.signature(website_lead_fanout.run_fanout).parameters
        assert not {"email_sender", "notify_email"} & set(params)
        assert not hasattr(email_service, "send_website_lead_notification")
        assert hasattr(email_service, "send_owner_brief")  # the owner brief keeps its e-mail

    def test_notice_text_names_lead_source_and_interest(self):
        title, message = website_lead_fanout.lead_notice_text({**LEAD, "product_interest": ["core", "erp"]})
        assert title == "Novo lead do site: Ana"
        assert "waitlist" in message and "core, erp" in message

    @pytest.mark.asyncio
    async def test_whatsapp_configured_records_sem_linha_and_never_sends(self, recorded_failures):
        """Core owns no WhatsApp line (julia-line §A4): a configured target is a loud failure, not a send."""
        calls, record = recorded_failures
        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="+5511999999999", webhook_url="", in_app_notifier=lambda lead: 1, record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][1] == "whatsapp"
        assert calls[0][2].startswith("sem_linha_da_plataforma")

    def test_fanout_has_no_whatsapp_client_seam(self):
        import inspect
        params = inspect.signature(website_lead_fanout.run_fanout).parameters
        assert not {"whatsapp_client", "waha_base_url", "waha_api_key", "waha_session"} & set(params)

    @pytest.mark.asyncio
    async def test_webhook_configured_and_succeeds(self, recorded_failures):
        calls, record = recorded_failures
        fake_sender = FakeOutboundWebhookSender(default_outcome=success(status_code=200))
        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="https://example.com/hook",
            webhook_sender=fake_sender, in_app_notifier=lambda lead: 1, record_failure=record,
        )
        assert calls == []
        assert len(fake_sender.requests) == 1

    @pytest.mark.asyncio
    async def test_webhook_failure_records_fanout_failed(self, recorded_failures):
        calls, record = recorded_failures
        fake_sender = FakeOutboundWebhookSender(default_outcome=failure(status_code=500))
        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="https://example.com/hook",
            webhook_sender=fake_sender, in_app_notifier=lambda lead: 1, record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][1] == "webhook"

    @pytest.mark.asyncio
    async def test_one_channel_failing_does_not_block_the_others(self, recorded_failures):
        calls, record = recorded_failures
        fake_sender = FakeOutboundWebhookSender(default_outcome=success(status_code=200))
        await website_lead_fanout.run_fanout(
            LEAD, sales_whatsapp="", webhook_url="https://example.com/hook",
            in_app_notifier=lambda lead: 0, webhook_sender=fake_sender, record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][1] == "in_app"
        assert len(fake_sender.requests) == 1
