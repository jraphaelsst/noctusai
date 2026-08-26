"""`imovelweb_ingest_service` — idempotency, attribution, and LGPD.

Three properties are load-bearing here, and each one is a bug if it slips:

* **The dedup key is the DELIVERY.** `(org, 'imovelweb', eventId)`. The
  vendor's `originLeadId` is the CONTACT and fans out to several events.
* **The pipe and the portal are different fields.** `external_source` is
  the constant `'imovelweb'`; `origem_id` is the per-portal source row. If
  the pipe varied with the portal, a re-delivery whose `leadOrigin` changed
  would insert a second lead.
* **The CPF is never projected.** It is parsed so the contract stays honest
  about what arrives, then dropped everywhere except the lossless ledger.
"""
from __future__ import annotations

import copy
from uuid import UUID

import pytest

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_PIPE,
    IMOVELWEB_SAMPLE_BODIES,
    parse_imovelweb_callback,
)

from app.modules.leads.services import dimensions_service
from app.modules.portal_leads.services import imovelweb_ingest_service

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


class TestIdempotency:
    def test_ingesting_twice_creates_one_lead(self, client):
        first = imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())
        second = imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        assert first["created"] is True
        assert second["created"] is False
        assert len(client.table("leads").select("*").execute().data) == 1

    def test_two_events_from_one_contact_are_two_leads(self, client):
        """The fan-out case: one contact, two separate enquiries.

        `originLeadId` is identical — it is the CONTACT — while `eventId`
        and `messageId` differ, because these are two distinct messages.
        Keying the projection on the contact would collapse them into one
        lead and lose a real customer enquiry.

        (Same `messageId` with different `eventId`s is the OPPOSITE case —
        one message delivered twice — and is deliberately collapsed by the
        twin guard in TestReconcileDedup below.)
        """
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="evt-1", messageId=111)
        )
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="evt-2", messageId=222)
        )

        rows = client.table("leads").select("*").execute().data
        assert len(rows) == 2
        ledger = client.table("imovelweb_leads").select("*").execute().data
        assert {r["origin_lead_id"] for r in ledger} == {"55512345"}

    def test_the_ledger_is_written_before_the_projection(self, client):
        """If the mapping raises, the vendor's body must still be ours —
        losing it is permanent, since the vendor stops after 72 hours."""
        bad = _lead(timestamp="not-a-date")

        with pytest.raises(ValueError):
            imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, bad)

        assert len(client.table("imovelweb_leads").select("*").execute().data) == 1
        assert client.table("leads").select("*").execute().data == []


class TestPipeVersusPortal:
    def test_external_source_is_the_constant_pipe(self, client):
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        row = client.table("leads").select("*").execute().data[0]
        assert row["external_source"] == IMOVELWEB_PIPE
        assert row["external_lead_id"] == "evt-0000000001"

    def test_the_pipe_does_not_vary_with_the_portal(self, client):
        """Casa Mineira and ImovelWeb are different PORTALS on the same
        PIPE. If `external_source` tracked the portal, the same event
        re-delivered with a changed `leadOrigin` would insert a second
        row — which is exactly what the idempotency key exists to stop."""
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(leadOrigin="CasaMineira")
        )

        row = client.table("leads").select("*").execute().data[0]
        assert row["external_source"] == IMOVELWEB_PIPE

    def test_the_portal_decides_the_source_row(self, client):
        result = imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(leadOrigin="CasaMineira")
        )

        assert result["source_slug"] == "casa-mineira"

    def test_an_unknown_portal_falls_back_without_minting_a_slug(self, client):
        """`wimoveis` has no `lead_sources` row and no observed BR lead. It
        folds into `imovel-web` with the true value preserved in the
        ledger — a dimension nobody can explain is worse than a coarse one."""
        result = imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(leadOrigin="Wimoveis")
        )

        assert result["source_slug"] == "imovel-web"
        ledger = client.table("imovelweb_leads").select("*").execute().data[0]
        assert ledger["lead_origin"] == "Wimoveis"


class TestReconcileDedup:
    def test_the_same_message_is_not_ingested_twice_under_two_ids(self, client):
        """The reconcile/callback duplicate, closed on `messageId`.

        A pulled `Mensaje` carries no eventId, so the reconcile path mints
        its own key — meaning the same enquiry can arrive twice under two
        different ids. Whether the two id spaces relate at all is an open
        vendor question (Gate 0.6); `messageId` closes it without needing
        the answer.
        """
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="evt-callback")
        )
        second = imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="reconcile:987654321")
        )

        assert second["created"] is False
        assert second["deduped_on"] == "message_id"
        assert len(client.table("leads").select("*").execute().data) == 1

    def test_both_deliveries_stay_in_the_ledger(self, client):
        """Both genuinely happened. Only the `leads` projection is
        deduplicated — that is what a lossless ledger is for."""
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="evt-callback")
        )
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="reconcile:987654321")
        )

        assert len(client.table("imovelweb_leads").select("*").execute().data) == 2

    def test_a_contacto_without_a_message_id_has_no_twin(self, client):
        """A phone reveal carries no `messageId`, and reconciliation pulls
        MESSAGES — so it can never collide, and must not be deduplicated
        against an unrelated lead."""
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead("PT", idEvento="evt-a")
        )
        second = imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead("PT", idEvento="evt-b")
        )

        assert second["created"] is True

    def test_another_orgs_message_is_not_a_twin(self, client):
        """Cross-tenant: the twin lookup is org-scoped, so two orgs holding
        the same vendor message id do not deduplicate against each other."""
        dimensions_service.ensure_default_dimensions(client, OTHER_ORG)
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead(eventId="evt-a")
        )
        result = imovelweb_ingest_service.ingest_imovelweb_lead(
            client, OTHER_ORG, _lead(eventId="evt-b")
        )

        assert result["created"] is True


class TestLgpdAndOmissions:
    def test_the_cpf_is_never_projected_into_leads(self, client):
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead("PT", cpf="12345678901")
        )

        row = client.table("leads").select("*").execute().data[0]
        assert "12345678901" not in str(row)

    def test_the_cpf_gets_no_ledger_column(self, client):
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead("PT", cpf="12345678901")
        )

        ledger = client.table("imovelweb_leads").select("*").execute().data[0]
        assert "identification_id" not in ledger

    def test_the_cpf_does_survive_in_raw(self, client):
        """The honest consequence: `raw` IS personal data, which is why the
        migration comments it and the events route never selects it."""
        imovelweb_ingest_service.ingest_imovelweb_lead(
            client, ORG, _lead("PT", cpf="12345678901")
        )

        ledger = client.table("imovelweb_leads").select("*").execute().data[0]
        assert ledger["raw"]["cpf"] == "12345678901"

    def test_no_corretor_is_assigned(self, client):
        """The payload names no broker, and guessing one hands a real
        customer to the wrong person."""
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        row = client.table("leads").select("*").execute().data[0]
        assert row.get("corretor_id") is None

    def test_smartlead_starts_null(self, client):
        """Enrichment is downstream of the durable write, so its absence is
        a degradation and never a lost lead."""
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        ledger = client.table("imovelweb_leads").select("*").execute().data[0]
        assert ledger.get("smartlead") is None


class TestSmartleadAttachment:
    def test_attaches_to_an_existing_ledger_row(self, client):
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        attached = imovelweb_ingest_service.attach_smartlead(
            client, ORG, "evt-0000000001", {"priceRange": "300k-400k"}
        )

        assert attached is True
        ledger = client.table("imovelweb_leads").select("*").execute().data[0]
        assert ledger["smartlead"]["priceRange"] == "300k-400k"

    def test_a_missing_row_is_false_not_an_exception(self, client):
        assert (
            imovelweb_ingest_service.attach_smartlead(client, ORG, "nope", {"a": 1})
            is False
        )

    def test_empty_enrichment_is_a_no_op(self, client):
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        assert (
            imovelweb_ingest_service.attach_smartlead(
                client, ORG, "evt-0000000001", {}
            )
            is False
        )


class TestBackfill:
    def test_projects_stored_ledger_rows(self, client):
        imovelweb_ingest_service.store_imovelweb_lead(client, ORG, _lead())

        result = imovelweb_ingest_service.backfill_imovelweb_leads(client, ORG)

        assert result["ingested"] == 1

    def test_is_idempotent(self, client):
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, _lead())

        result = imovelweb_ingest_service.backfill_imovelweb_leads(client, ORG)

        assert result["ingested"] == 0
        assert result["skipped_existing"] == 1

    def test_an_unmappable_row_is_reported_not_silently_skipped(self, client):
        imovelweb_ingest_service.store_imovelweb_lead(
            client, ORG, _lead(timestamp=None)
        )

        result = imovelweb_ingest_service.backfill_imovelweb_leads(client, ORG)

        assert len(result["errors"]) == 1
        assert result["errors"][0]["event_id"] == "evt-0000000001"


class TestPayloadIngest:
    def test_a_body_with_no_event_id_is_refused(self, client):
        with pytest.raises(ValueError, match="no usable eventId"):
            imovelweb_ingest_service.ingest_imovelweb_payload(
                client, ORG, {"eventType": "CONTACTO"}
            )
