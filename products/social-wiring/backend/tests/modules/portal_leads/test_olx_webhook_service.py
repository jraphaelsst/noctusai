"""`OlxWebhookService` — org resolution and the retry drain.

The org-resolution tests are the tenant-leak guard. One webhook secret
serves the whole CRM, so the payload is the only thing that says which
client a lead belongs to; getting it wrong puts one customer's enquiry in
a competitor's CRM. "Park it as unresolved" is therefore the correct
answer whenever we cannot know, and these tests pin that.
"""
from __future__ import annotations

import copy
from uuid import UUID

import pytest

from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD, parse_olx_lead_webhook

from app.modules.leads.services import dimensions_service
from app.modules.portal_leads.services.olx_webhook_service import (
    MAX_ATTEMPTS,
    STATUS_ERROR,
    STATUS_PROCESSED,
    STATUS_UNRESOLVED,
    OlxWebhookService,
)

from tests.modules.portal_leads.conftest import ORG_A, ORG_B

ORG = UUID(ORG_A)
OTHER_ORG = UUID(ORG_B)


def _lead(**overrides):
    body = copy.deepcopy(OLX_SAMPLE_LEAD)
    body.update(overrides)
    lead = parse_olx_lead_webhook(body)
    assert lead is not None
    return lead


@pytest.fixture
def client(mock_db):
    scoped = mock_db.schema("social_wiring")
    dimensions_service.ensure_default_dimensions(scoped, ORG)
    return scoped


class TestOrgResolution:
    def test_resolves_the_org_from_the_client_listing_id(self, client):
        """`clientListingId` is OUR listing code, published by us in the
        feed — the only field that genuinely identifies the advertiser."""
        client.table("imoveis").insert(
            {"codigo": "a40171", "org_id": str(ORG)}
        ).execute()
        svc = OlxWebhookService(client=client)

        svc.record_event(_lead())
        result = svc.process_lead(_lead())

        assert result.status == STATUS_PROCESSED

    def test_falls_back_to_the_configured_single_org(self, client):
        svc = OlxWebhookService(client=client, default_org_id=ORG)

        svc.record_event(_lead())
        result = svc.process_lead(_lead())

        assert result.status == STATUS_PROCESSED

    def test_parks_as_unresolved_rather_than_guessing_an_org(self, client):
        """No listing match and no configured default ⇒ write nothing. A
        guessed org would leak a lead into another client's CRM, which is
        worse than one that needs a human to place it."""
        svc = OlxWebhookService(client=client)

        svc.record_event(_lead())
        result = svc.process_lead(_lead())

        assert result.status == STATUS_UNRESOLVED
        assert client.table("leads").select("*").execute().data == []

    def test_the_listing_match_wins_over_the_configured_default(self, client):
        """A multi-tenant deployment with a legacy default must not have
        that default override a positive identification."""
        client.table("imoveis").insert(
            {"codigo": "a40171", "org_id": str(ORG)}
        ).execute()
        svc = OlxWebhookService(client=client, default_org_id=OTHER_ORG)

        svc.record_event(_lead())
        svc.process_lead(_lead())

        leads = client.table("leads").select("*").execute().data
        assert len(leads) == 1
        assert leads[0]["org_id"] == str(ORG)

    def test_an_unresolved_event_is_kept_for_a_later_retry(self, client):
        svc = OlxWebhookService(client=client)

        svc.record_event(_lead())
        svc.process_lead(_lead())

        events = client.table("olx_lead_events").select("*").execute().data
        assert events[0]["status"] == STATUS_UNRESOLVED
        assert events[0]["error"]
        assert events[0]["attempts"] == 1


class TestFailureRecording:
    def test_an_ingest_failure_is_recorded_never_swallowed(self, client):
        svc = OlxWebhookService(client=client, default_org_id=ORG)
        lead = _lead(timestamp="???")

        svc.record_event(lead)
        result = svc.process_lead(lead)

        assert result.status == STATUS_ERROR
        events = client.table("olx_lead_events").select("*").execute().data
        assert events[0]["status"] == STATUS_ERROR
        assert "timestamp" in events[0]["error"]

    def test_record_event_is_idempotent(self, client):
        svc = OlxWebhookService(client=client, default_org_id=ORG)

        assert svc.record_event(_lead()) is True
        assert svc.record_event(_lead()) is False
        assert len(client.table("olx_lead_events").select("*").execute().data) == 1


class TestDrainPending:
    def test_drain_reprocesses_a_previously_unresolved_event(self, client):
        """The whole point of the inbox: a lead that could not be placed
        when it arrived gets placed once the config catches up."""
        stuck = OlxWebhookService(client=client)
        stuck.record_event(_lead())
        stuck.process_lead(_lead())

        fixed = OlxWebhookService(client=client, default_org_id=ORG)
        result = fixed.drain_pending()

        assert result["processed"] == 1
        assert len(client.table("leads").select("*").execute().data) == 1

    def test_drain_ignores_already_processed_events(self, client):
        svc = OlxWebhookService(client=client, default_org_id=ORG)
        svc.record_event(_lead())
        svc.process_lead(_lead())

        result = svc.drain_pending()

        assert result["examined"] == 0

    def test_drain_gives_up_after_max_attempts_but_keeps_the_row(self, client):
        """An unprocessable real lead is exactly what an operator must be
        able to find, so it is never deleted — only stopped."""
        svc = OlxWebhookService(client=client, default_org_id=ORG)
        lead = _lead(timestamp="???")
        svc.record_event(lead)
        svc._update_event(lead.origin_lead_id, attempts=MAX_ATTEMPTS, status=STATUS_ERROR)

        result = svc.drain_pending()

        assert result["exhausted"] == 1
        assert result["processed"] == 0
        assert len(client.table("olx_lead_events").select("*").execute().data) == 1


class TestDedup:
    def test_a_dedup_outage_degrades_to_the_db_layers(self, client):
        """Redis is an optimisation in front of two DB guarantees. If it
        throws, the delivery must still be processed — treating a cache
        outage as a duplicate would silently drop real leads."""

        class _BrokenDedup:
            def claim(self, key):
                raise RuntimeError("redis down")

        svc = OlxWebhookService(client=client, default_org_id=ORG, dedup=_BrokenDedup())

        assert svc.is_duplicate("anything") is False

    def test_dedup_reports_a_replay(self, client):
        class _Dedup:
            def __init__(self):
                self.seen = set()

            def claim(self, key):
                if key in self.seen:
                    return False
                self.seen.add(key)
                return True

        svc = OlxWebhookService(client=client, default_org_id=ORG, dedup=_Dedup())

        assert svc.is_duplicate("lead-1") is False
        assert svc.is_duplicate("lead-1") is True
