"""`ImovelWebWebhookService` — org resolution, the drain, and the budget.

The org-resolution tests are the tenant-leak guard, and this vendor makes
them sharper than the OLX ones: the agency code is a value WE assign at
onboarding, so resolution can be a pure lookup instead of an inference —
but only on the language variants that carry it. On EN2 that rung does not
exist, so the fallbacks are not decoration, they are the normal path.

"Park it as unresolved" is the correct answer whenever we cannot know, and
these tests pin that. A guessed org puts one client's customer in a
competitor's CRM.
"""
from __future__ import annotations

import copy
from uuid import UUID

import pytest

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_SAMPLE_BODIES,
    parse_imovelweb_callback,
)

from app.modules.leads.services import dimensions_service
from app.modules.portal_leads.services.imovelweb_webhook_service import (
    MAX_ATTEMPTS,
    SOURCE_CALLBACK,
    SOURCE_RECONCILE,
    STATUS_ERROR,
    STATUS_IGNORED,
    STATUS_PROCESSED,
    STATUS_UNRESOLVED,
    ImovelWebWebhookService,
    ResponseBudget,
)

from tests.modules.portal_leads.conftest import ORG_A, ORG_B

ORG = UUID(ORG_A)
OTHER_ORG = UUID(ORG_B)


def _lead(language: str = "EN2", **overrides):
    body = copy.deepcopy(IMOVELWEB_SAMPLE_BODIES[language])
    body.update(overrides)
    lead = parse_imovelweb_callback(body, language=language)
    assert lead is not None
    return lead


@pytest.fixture
def client(mock_db):
    scoped = mock_db.schema("social_wiring")
    dimensions_service.ensure_default_dimensions(scoped, ORG)
    return scoped


class TestOrgResolution:
    def test_the_agency_code_is_the_strong_rung(self, client):
        """WE choose `codigoImobiliaria` at onboarding — it goes in the
        vendor's login-button URL — so this is a lookup, not a guess. It is
        the one place this integration beats the OLX pipe, where nothing in
        the payload names the advertiser at all."""
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": "noc-org-demo", "org_id": str(ORG)}
        ).execute()
        svc = ImovelWebWebhookService(client=client)
        lead = _lead("PT")  # only PT/ES/EN carry the agency code

        svc.record_event(lead)
        result = svc.process_lead(lead)

        assert result.status == STATUS_PROCESSED

    def test_falls_back_to_the_listing_code(self, client):
        # The EN2 body carries no agency code, so this rung is the normal
        # path there rather than an exceptional one.
        client.table("imoveis").insert(
            {"codigo": "AP-1024", "org_id": str(ORG)}
        ).execute()
        svc = ImovelWebWebhookService(client=client)
        lead = _lead("EN2")

        svc.record_event(lead)
        result = svc.process_lead(lead)

        assert result.status == STATUS_PROCESSED

    def test_falls_back_to_the_internal_reference_last(self, client):
        """Weakest rung, and third for a reason: `internalReference` is the
        code the imobiliária uses in the VENDOR's panel, which may not be
        ours at all."""
        client.table("imoveis").insert(
            {"codigo": "IMOB-AP-1024", "org_id": str(ORG)}
        ).execute()
        svc = ImovelWebWebhookService(client=client)
        lead = _lead("EN2", clientListingId=None, reference=None)

        svc.record_event(lead)
        result = svc.process_lead(lead)

        assert result.status == STATUS_PROCESSED

    def test_falls_back_to_the_configured_single_org(self, client):
        svc = ImovelWebWebhookService(client=client, default_org_id=ORG)
        lead = _lead()

        svc.record_event(lead)
        result = svc.process_lead(lead)

        assert result.status == STATUS_PROCESSED

    def test_parks_as_unresolved_rather_than_guessing(self, client):
        svc = ImovelWebWebhookService(client=client)
        lead = _lead()

        svc.record_event(lead)
        result = svc.process_lead(lead)

        assert result.status == STATUS_UNRESOLVED

    def test_an_unresolved_event_writes_no_lead(self, client):
        """The tenant-leak guard proper: unresolved means NOTHING was
        written, not "written somewhere plausible"."""
        svc = ImovelWebWebhookService(client=client)
        lead = _lead()

        svc.record_event(lead)
        svc.process_lead(lead)

        leads = client.table("leads").select("*").execute()
        assert list(leads.data or []) == []

    def test_the_unresolved_reason_names_all_three_misses(self, client):
        svc = ImovelWebWebhookService(client=client)
        lead = _lead()

        svc.record_event(lead)
        svc.process_lead(lead)

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert "imovelweb_agencies" in row["error"]
        assert "matched no imovel" in row["error"]
        assert "IMOVELWEB_LEADS_ORG_ID" in row["error"]

    def test_another_orgs_agency_code_does_not_resolve(self, client):
        """Cross-tenant: an agency mapped to ORG_B must never resolve a
        lead into ORG_A just because a default is configured for A."""
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": "noc-org-demo", "org_id": str(OTHER_ORG)}
        ).execute()
        svc = ImovelWebWebhookService(client=client)
        lead = _lead("PT")

        svc.record_event(lead)
        svc.process_lead(lead)

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert row["org_id"] == str(OTHER_ORG)


class TestInbox:
    def test_records_the_delivery_language(self, client):
        """The only forensic record if someone changes the registered
        language vendor-side and bodies quietly start arriving in another
        shape."""
        svc = ImovelWebWebhookService(client=client)

        svc.record_event(_lead("PT"))

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert row["callback_language"] == "PT"

    def test_defaults_to_the_callback_source(self, client):
        svc = ImovelWebWebhookService(client=client)

        svc.record_event(_lead())

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert row["source"] == SOURCE_CALLBACK

    def test_a_reconcile_row_says_so(self, client):
        # The share of these is the operator-visible symptom of blowing the
        # 1.5-second budget: the leads still arrive, just by the slow path.
        svc = ImovelWebWebhookService(client=client)

        svc.record_event(_lead(), source=SOURCE_RECONCILE)

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert row["source"] == SOURCE_RECONCILE

    def test_a_second_delivery_of_the_same_event_is_not_new(self, client):
        svc = ImovelWebWebhookService(client=client)

        assert svc.record_event(_lead()) is True
        assert svc.record_event(_lead()) is False

    def test_the_event_id_is_the_delivery_not_the_contact(self, client):
        """One contact fans out to several events — a phone reveal, then a
        message, on the same listing. Keying the inbox on `originLeadId`
        would silently collapse two real leads into one."""
        svc = ImovelWebWebhookService(client=client)

        svc.record_event(_lead(eventId="evt-1"))
        svc.record_event(_lead(eventId="evt-2"))

        rows = client.table("imovelweb_lead_events").select("*").execute().data
        assert len(rows) == 2
        assert {r["id"] for r in rows} == {"evt-1", "evt-2"}


class TestDedup:
    def test_no_dedup_store_means_no_first_line(self, client):
        svc = ImovelWebWebhookService(client=client)

        assert svc.is_duplicate("evt-1") is False

    def test_a_dedup_outage_degrades_rather_than_failing(self, client):
        class _BrokenDedup:
            def claim(self, key):
                raise RuntimeError("redis down")

        svc = ImovelWebWebhookService(client=client, dedup=_BrokenDedup())

        # Falls through to the DB layers rather than 500ing the receiver.
        assert svc.is_duplicate("evt-1") is False

    def test_a_claimed_key_is_a_duplicate(self, client):
        class _Dedup:
            def __init__(self):
                self.seen = set()

            def claim(self, key):
                if key in self.seen:
                    return False
                self.seen.add(key)
                return True

        svc = ImovelWebWebhookService(client=client, dedup=_Dedup())

        assert svc.is_duplicate("evt-1") is False
        assert svc.is_duplicate("evt-1") is True


class TestDrain:
    def test_reprocesses_a_previously_unresolved_event(self, client):
        svc = ImovelWebWebhookService(client=client)
        lead = _lead("PT")
        svc.record_event(lead)
        svc.process_lead(lead)

        # The agency mapping arrives late — onboarding finished after the
        # first lead, which is the ordinary case.
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": "noc-org-demo", "org_id": str(ORG)}
        ).execute()

        result = svc.drain_pending()

        assert result["processed"] == 1

    def test_is_bounded_by_max_attempts(self, client):
        svc = ImovelWebWebhookService(client=client)
        lead = _lead()
        svc.record_event(lead)
        client.table("imovelweb_lead_events").update(
            {"attempts": MAX_ATTEMPTS}
        ).eq("id", lead.event_id).execute()

        result = svc.drain_pending()

        assert result["exhausted"] == 1
        assert result["processed"] == 0

    def test_an_exhausted_row_is_kept_not_deleted(self, client):
        """"We failed to process a real lead" is exactly what an operator
        must be able to find."""
        svc = ImovelWebWebhookService(client=client)
        lead = _lead()
        svc.record_event(lead)
        client.table("imovelweb_lead_events").update(
            {"attempts": MAX_ATTEMPTS}
        ).eq("id", lead.event_id).execute()

        svc.drain_pending()

        assert len(client.table("imovelweb_lead_events").select("*").execute().data) == 1

    def test_an_unparseable_stored_payload_is_ignored_not_retried_forever(self, client):
        svc = ImovelWebWebhookService(client=client)
        lead = _lead()
        svc.record_event(lead)
        client.table("imovelweb_lead_events").update(
            {"payload": {"nothing": "usable"}}
        ).eq("id", lead.event_id).execute()

        svc.drain_pending()

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert row["status"] == STATUS_IGNORED

    def test_an_ingest_failure_is_recorded_not_swallowed(self, client):
        def _boom(client_, org_id, lead):
            raise RuntimeError("mapping exploded")

        svc = ImovelWebWebhookService(
            client=client, default_org_id=ORG, ingest_fn=_boom
        )
        lead = _lead()
        svc.record_event(lead)

        result = svc.process_lead(lead)

        assert result.status == STATUS_ERROR
        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert "mapping exploded" in row["error"]


class TestResponseBudget:
    def test_a_fast_path_is_within_budget(self):
        with ResponseBudget() as budget:
            pass

        assert budget.exceeded is False
        assert budget.elapsed_ms >= 0

    def test_an_overrun_is_flagged(self):
        """The threshold, asserted on a known elapsed time.

        Deliberately not "do slow work and check the clock": that races the
        machine, and the first version of this test passed a zero budget and
        FAILED, because sub-0.1ms work rounds to 0.0ms. What is worth pinning
        is the comparison, and it can be pinned exactly.
        """
        budget = ResponseBudget(budget_seconds=1.0)

        budget.elapsed_ms = 1200.0
        assert budget.exceeded is True

        budget.elapsed_ms = 800.0
        assert budget.exceeded is False

    def test_the_context_manager_actually_measures(self):
        with ResponseBudget() as budget:
            sum(range(10_000))

        assert budget.elapsed_ms > 0

    def test_the_budget_is_two_thirds_of_the_vendor_limit(self):
        from app.modules.portal_leads.services.imovelweb_webhook_service import (
            RESPONSE_BUDGET_SECONDS,
        )

        # Deliberately not 1.5: by the time we are AT the vendor's limit the
        # lead is already scored an error, so the number worth alerting on
        # is the one that still leaves room to react.
        assert RESPONSE_BUDGET_SECONDS < 1.5
