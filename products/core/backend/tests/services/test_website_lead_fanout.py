"""Tests for `app.services.website_lead_fanout` — every config value and
collaborator is DI-injected, never monkeypatching `settings` or our own
functions (`KB § PATTERNS/compliance/testing.md`)."""
import pytest

from app.services import website_lead_fanout
from noctusai_lib.integrations.outbound_webhook.fake import FakeOutboundWebhookSender, failure, success
from noctusai_lib.integrations.whatsapp import FakeWahaClient

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
    async def test_all_channels_skipped_when_unconfigured(self, recorded_failures):
        calls, record = recorded_failures
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="", sales_whatsapp="", webhook_url="", record_failure=record,
        )
        assert calls == []

    @pytest.mark.asyncio
    async def test_email_configured_and_succeeds(self, recorded_failures):
        calls, record = recorded_failures
        sent = {}

        def fake_sender(to, lead):
            sent["to"] = to
            sent["lead"] = lead
            return True

        await website_lead_fanout.run_fanout(
            LEAD, notify_email="sales@example.com", sales_whatsapp="", webhook_url="",
            email_sender=fake_sender, record_failure=record,
        )
        assert sent["to"] == "sales@example.com"
        assert calls == []

    @pytest.mark.asyncio
    async def test_email_configured_and_fails_records_fanout_failed(self, recorded_failures):
        calls, record = recorded_failures
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="sales@example.com", sales_whatsapp="", webhook_url="",
            email_sender=lambda to, lead: False, record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][0] == "lead-1"
        assert calls[0][1] == "email"

    @pytest.mark.asyncio
    async def test_whatsapp_configured_and_succeeds(self, recorded_failures):
        calls, record = recorded_failures
        fake_client = FakeWahaClient()
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="", sales_whatsapp="+5511999999999", webhook_url="",
            whatsapp_client=fake_client, record_failure=record,
        )
        assert len(fake_client.sent_messages) == 1
        assert calls == []

    @pytest.mark.asyncio
    async def test_whatsapp_bad_number_records_failure(self, recorded_failures):
        calls, record = recorded_failures
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="", sales_whatsapp="not-a-phone", webhook_url="", record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][1] == "whatsapp"

    @pytest.mark.asyncio
    async def test_webhook_configured_and_succeeds(self, recorded_failures):
        calls, record = recorded_failures
        fake_sender = FakeOutboundWebhookSender(default_outcome=success(status_code=200))
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="", sales_whatsapp="", webhook_url="https://example.com/hook",
            webhook_sender=fake_sender, record_failure=record,
        )
        assert calls == []
        assert len(fake_sender.requests) == 1

    @pytest.mark.asyncio
    async def test_webhook_failure_records_fanout_failed(self, recorded_failures):
        calls, record = recorded_failures
        fake_sender = FakeOutboundWebhookSender(default_outcome=failure(status_code=500))
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="", sales_whatsapp="", webhook_url="https://example.com/hook",
            webhook_sender=fake_sender, record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][1] == "webhook"

    @pytest.mark.asyncio
    async def test_one_channel_failing_does_not_block_the_others(self, recorded_failures):
        calls, record = recorded_failures
        fake_sender = FakeOutboundWebhookSender(default_outcome=success(status_code=200))
        await website_lead_fanout.run_fanout(
            LEAD, notify_email="sales@example.com", sales_whatsapp="", webhook_url="https://example.com/hook",
            email_sender=lambda to, lead: False, webhook_sender=fake_sender, record_failure=record,
        )
        assert len(calls) == 1
        assert calls[0][1] == "email"
        assert len(fake_sender.requests) == 1
