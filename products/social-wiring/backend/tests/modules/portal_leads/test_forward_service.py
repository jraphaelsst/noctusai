"""`forward_service` — the store-and-forward outbox.

Every assertion here exists because of one fact: Grupo OLX considers a
lead delivered the moment we answer 2xx, never resends it, and offers no
replay API. Once NoctusAI takes over the Canal Pro URL, this outbox is
the ONLY path by which the advertiser's previous CRM ever sees the lead.

So the behaviours worth pinning are the ones that decide whether a lead
survives: enqueue is idempotent, a transient failure is retried on a
schedule, a refusal is not retried at all, and a delivered row keeps its
identity while shedding its PII.
"""
from __future__ import annotations

import base64
import json

import pytest

from noctusai_lib.integrations.outbound_webhook import (
    DeliveryFailureKind,
    FakeOutboundWebhookSender,
    failure,
    success,
)

from app.modules.portal_leads.services import forward_service as fs

from tests.modules.portal_leads.conftest import ORG_A, ORG_B, WEBHOOK_SECRET

BODY = '{"originLeadId":"lead-1","name":"Fulano"}'


@pytest.fixture
def client(mock_db):
    return mock_db.schema("social_wiring")


def _target(client, *, org_id=ORG_A, url="https://crm.test/hook",
            auth_mode="passthrough", active=True, label="Lais"):
    row = {
        "id": f"tgt-{url}-{org_id}",
        "org_id": org_id,
        "provider": "olx",
        "label": label,
        "url": url,
        "auth_mode": auth_mode,
        "is_active": active,
    }
    client.table("portal_lead_forward_targets").insert(row).execute()
    return row


def _forwards(client):
    return client.table("portal_lead_forwards").select("*").execute().data or []


class TestEnqueue:
    def test_no_targets_is_not_an_error(self, client):
        """Most orgs forward nowhere. That is the common case, not a fault."""
        assert fs.enqueue_forwards(
            client, org_id=ORG_A, provider="olx",
            origin_lead_id="lead-1", body=BODY,
        ) == 0

    def test_one_row_per_active_target(self, client):
        _target(client, url="https://a.test/h")
        _target(client, url="https://b.test/h")

        enqueued = fs.enqueue_forwards(
            client, org_id=ORG_A, provider="olx",
            origin_lead_id="lead-1", body=BODY,
        )

        assert enqueued == 2

    def test_inactive_targets_are_skipped(self, client):
        _target(client, url="https://a.test/h", active=False)

        assert fs.enqueue_forwards(
            client, org_id=ORG_A, provider="olx",
            origin_lead_id="lead-1", body=BODY,
        ) == 0

    def test_another_orgs_target_is_not_used(self, client):
        _target(client, org_id=ORG_B, url="https://b.test/h")

        assert fs.enqueue_forwards(
            client, org_id=ORG_A, provider="olx",
            origin_lead_id="lead-1", body=BODY,
        ) == 0

    def test_the_body_is_stored_for_the_drain(self, client):
        _target(client)

        fs.enqueue_forwards(
            client, org_id=ORG_A, provider="olx",
            origin_lead_id="lead-1", body=BODY,
        )

        assert _forwards(client)[0]["body"] == BODY


class TestBuildHeaders:
    def test_passthrough_rebuilds_the_vendors_own_basic_header(self):
        """The point of `passthrough`: no credential is stored per row.

        The header is re-derived from the secret the receiver already
        validates against, so it is by construction the value Grupo OLX
        sent us.
        """
        headers = fs.build_headers("passthrough", webhook_secret=WEBHOOK_SECRET)

        expected = base64.b64encode(f"vivareal:{WEBHOOK_SECRET}".encode()).decode()
        assert headers["Authorization"] == f"Basic {expected}"

    def test_none_sends_no_authorization(self):
        assert fs.build_headers("none", webhook_secret=WEBHOOK_SECRET) == {}

    def test_passthrough_without_a_secret_refuses(self):
        """Silently dropping the header would look like a downstream auth
        failure and send an operator hunting in the wrong system."""
        with pytest.raises(fs.ForwardTargetMisconfigured):
            fs.build_headers("passthrough", webhook_secret=None)

    def test_an_unsupported_mode_refuses(self):
        """`basic`/`bearer` are deliberately absent until the downstream
        vendor answers what it accepts — see migration 066."""
        with pytest.raises(fs.ForwardTargetMisconfigured):
            fs.build_headers("bearer", webhook_secret=WEBHOOK_SECRET)


class TestAttempt:
    @pytest.mark.asyncio
    async def test_success_marks_delivered_and_clears_the_pii(self, client):
        """LGPD minimisation by construction — but the ROW survives.

        Deleting it would drop the idempotency key and let a vendor
        redelivery forward the same lead a second time.
        """
        target = _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = _forwards(client)[0]

        status = await fs.attempt_forward(
            client, row, sender=FakeOutboundWebhookSender(),
            webhook_secret=WEBHOOK_SECRET, target=target,
        )

        assert status == fs.STATUS_DELIVERED
        stored = _forwards(client)[0]
        assert stored["body"] is None
        assert stored["delivered_at"] is not None
        assert stored["origin_lead_id"] == "lead-1"

    @pytest.mark.asyncio
    async def test_a_transient_failure_stays_pending_and_backs_off(self, client):
        target = _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = _forwards(client)[0]

        status = await fs.attempt_forward(
            client, row,
            sender=FakeOutboundWebhookSender(default_outcome=failure(status_code=503)),
            webhook_secret=WEBHOOK_SECRET, target=target,
        )

        assert status == fs.STATUS_PENDING
        stored = _forwards(client)[0]
        assert stored["attempts"] == 1
        # The body must survive a failure — it is the only copy.
        assert stored["body"] == BODY

    @pytest.mark.asyncio
    async def test_a_refusal_is_not_retried(self, client):
        """A 4xx means the downstream understood and said no. Retrying
        spends a budget a transient failure will need."""
        target = _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = _forwards(client)[0]

        status = await fs.attempt_forward(
            client, row,
            sender=FakeOutboundWebhookSender(default_outcome=failure(status_code=422)),
            webhook_secret=WEBHOOK_SECRET, target=target,
        )

        assert status == fs.STATUS_FAILED

    @pytest.mark.asyncio
    async def test_exhausting_the_budget_is_dead_not_pending(self, client):
        """A row that will never be tried again must not sit `pending`
        pretending it is still going somewhere."""
        target = _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = dict(_forwards(client)[0])
        row["attempts"] = fs.FORWARD_RETRY_POLICY.max_retries

        status = await fs.attempt_forward(
            client, row,
            sender=FakeOutboundWebhookSender(
                default_outcome=failure(kind=DeliveryFailureKind.TIMEOUT)
            ),
            webhook_secret=WEBHOOK_SECRET, target=target,
        )

        assert status == fs.STATUS_DEAD

    @pytest.mark.asyncio
    async def test_a_misconfigured_target_fails_once_not_forever(self, client):
        target = _target(client, auth_mode="passthrough")
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = _forwards(client)[0]

        status = await fs.attempt_forward(
            client, row, sender=FakeOutboundWebhookSender(),
            webhook_secret=None, target=target,
        )

        assert status == fs.STATUS_FAILED

    @pytest.mark.asyncio
    async def test_the_forwarded_body_is_sent_unaltered(self, client):
        target = _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = _forwards(client)[0]
        sender = FakeOutboundWebhookSender()

        await fs.attempt_forward(
            client, row, sender=sender,
            webhook_secret=WEBHOOK_SECRET, target=target,
        )

        assert sender.last_request.body == BODY
        assert sender.last_request.url == "https://crm.test/hook"

    @pytest.mark.asyncio
    async def test_a_deleted_target_does_not_retry_forever(self, client):
        """A destination removed under a queued row must settle, not sit
        `pending` pretending it is still going somewhere."""
        _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        row = dict(_forwards(client)[0])
        row["target_id"] = "tgt-vanished"

        # No `target=` argument: the service must look it up and find
        # nothing, which is the path under test.
        status = await fs.attempt_forward(
            client, row, sender=FakeOutboundWebhookSender(),
            webhook_secret=WEBHOOK_SECRET,
        )

        assert status == fs.STATUS_FAILED


class TestDrain:
    @pytest.mark.asyncio
    async def test_delivers_due_rows(self, client):
        _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)

        tally = await fs.drain_forwards(
            client, webhook_secret=WEBHOOK_SECRET,
            sender=FakeOutboundWebhookSender(),
        )

        assert tally["examined"] == 1
        assert tally[fs.STATUS_DELIVERED] == 1

    @pytest.mark.asyncio
    async def test_one_attempt_per_row_per_pass(self, client):
        """The backoff schedule decides when a row is tried again — not a
        loop inside the drain. Retrying in place would re-introduce the
        in-process retry this outbox exists to replace."""
        _target(client)
        fs.enqueue_forwards(client, org_id=ORG_A, provider="olx",
                            origin_lead_id="lead-1", body=BODY)
        sender = FakeOutboundWebhookSender(default_outcome=failure(status_code=503))

        await fs.drain_forwards(
            client, webhook_secret=WEBHOOK_SECRET, sender=sender,
        )

        assert sender.call_count == 1

    @pytest.mark.asyncio
    async def test_an_empty_outbox_is_a_no_op(self, client):
        tally = await fs.drain_forwards(
            client, webhook_secret=WEBHOOK_SECRET,
            sender=FakeOutboundWebhookSender(),
        )

        assert tally["examined"] == 0
