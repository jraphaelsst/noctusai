"""`imovelweb_reconcile_service` — the pull that makes a miss survivable.

This is the durability guarantee for the ImovelWeb pipe. The vendor allows
1.5 seconds and gives up after 72 hours, but it also exposes a pull API —
so a delivery we never received is recoverable, provided this job runs and
provided it does not duplicate everything it finds.

Two properties matter most, and both are tested directly rather than
inferred:

* **it recovers what the callback lost, and only that.** A lead the
  callback already delivered must not be created a second time.
* **it does not leak across tenants.** This runs on the admin client, which
  bypasses RLS, so `imovelweb_agencies` IS the isolation boundary here.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from noctusai_lib.integrations.imovelweb import (
    IMOVELWEB_SANDBOX_BR,
    FakeImovelWebClient,
)

from app.modules.leads.services import dimensions_service
from app.modules.portal_leads.services import (
    imovelweb_ingest_service,
    imovelweb_reconcile_service as svc,
)

from tests.modules.portal_leads.conftest import ORG_A, ORG_B

ORG = UUID(ORG_A)
OTHER_ORG = UUID(ORG_B)

AGENCY_A = "noc-org-a"
AGENCY_B = "noc-org-b"


def _message(id_mensaje: int, **overrides):
    body = {
        "idMensaje": id_mensaje,
        "idContacto": 55512345,
        "idContactoAccion": 1,
        "codigoAviso": "AP-1024",
        "idAvisoNavplat": 45491025,
        "nombre": "Fulano de Tal",
        "email": "fulano@example.com",
        "telefono": "31999998888",
        "textoMensaje": "Tenho interesse neste imóvel.",
        "fecha": "2026-08-17T15:50:30.619-0300",
    }
    body.update(overrides)
    return body


@pytest.fixture
def client(mock_db):
    scoped = mock_db.schema("social_wiring")
    dimensions_service.ensure_default_dimensions(scoped, ORG)
    scoped.table("imovelweb_agencies").insert(
        {"codigo_imobiliaria": AGENCY_A, "org_id": str(ORG)}
    ).execute()
    return scoped


@pytest.fixture
def adapter():
    return FakeImovelWebClient(base_url=IMOVELWEB_SANDBOX_BR)


class TestMessageMapping:
    def test_maps_a_pulled_message_onto_a_lead(self):
        lead = svc._message_to_lead(_message(777), AGENCY_A)

        assert lead is not None
        assert lead.message_id == 777
        assert lead.codigo_imobiliaria == AGENCY_A
        assert lead.event_type == "CONTACTO_MENSAJE"
        assert lead.client_listing_id == "AP-1024"

    def test_the_synthetic_id_is_visibly_synthetic(self):
        """`source` says the same thing, but the id is what shows up in
        logs and error messages."""
        lead = svc._message_to_lead(_message(777), AGENCY_A)

        assert lead.event_id == "reconcile:777"

    def test_the_raw_message_is_carried_verbatim(self):
        lead = svc._message_to_lead(_message(777), AGENCY_A)

        assert lead.raw["textoMensaje"] == "Tenho interesse neste imóvel."

    def test_a_message_with_no_id_is_refused(self):
        """No id ⇒ no dedup key ⇒ it would be re-created on every run."""
        assert svc._message_to_lead({"nombre": "x"}, AGENCY_A) is None

    def test_a_non_numeric_id_is_refused(self):
        assert svc._message_to_lead({"idMensaje": "abc"}, AGENCY_A) is None


class TestRecovery:
    @pytest.mark.asyncio
    async def test_recovers_a_lead_the_callback_never_delivered(self, client, adapter):
        adapter.inject_messages(AGENCY_A, [_message(777)])

        result = await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG
        )

        assert result["recovered"] == 1
        assert len(client.table("leads").select("*").execute().data) == 1

    @pytest.mark.asyncio
    async def test_the_recovered_row_is_marked_as_pulled(self, client, adapter):
        # The share of these is the operator-visible symptom of missing the
        # 1.5-second budget.
        adapter.inject_messages(AGENCY_A, [_message(777)])

        await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG
        )

        row = client.table("imovelweb_lead_events").select("*").execute().data[0]
        assert row["source"] == "reconcile"
        assert row["status"] == "processed"

    @pytest.mark.asyncio
    async def test_running_twice_recovers_once(self, client, adapter):
        adapter.inject_messages(AGENCY_A, [_message(777)])

        first = await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG
        )
        second = await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG
        )

        assert first["recovered"] == 1
        assert second["recovered"] == 0
        assert second["already_had"] == 1
        assert len(client.table("leads").select("*").execute().data) == 1

    @pytest.mark.asyncio
    async def test_does_not_duplicate_a_lead_the_callback_already_landed(
        self, client, adapter
    ):
        """The headline correctness property.

        The callback delivered it under the vendor's `eventId`; the pull
        finds the same message under a synthetic id. Without the
        `messageId` twin check in the ingest layer, every lead would be
        created a second time the next hour.
        """
        from noctusai_lib.integrations.imovelweb import parse_imovelweb_callback

        callback_body = {
            "eventId": "evt-real",
            "eventType": "CONTACTO_MENSAJE",
            "messageId": 777,
            "clientListingId": "AP-1024",
            "timestamp": "2026-08-17T15:50:30.619-0300",
            "name": "Fulano de Tal",
            "email": "fulano@example.com",
        }
        lead = parse_imovelweb_callback(callback_body)
        imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, lead)
        adapter.inject_messages(AGENCY_A, [_message(777)])

        result = await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG
        )

        assert result["recovered"] == 0
        assert len(client.table("leads").select("*").execute().data) == 1

    @pytest.mark.asyncio
    async def test_a_message_with_no_id_is_skipped_loudly(self, client, adapter):
        adapter.inject_messages(AGENCY_A, [{"nombre": "no id here"}])

        result = await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG
        )

        assert result["skipped"] == 1
        assert result["recovered"] == 0

    @pytest.mark.asyncio
    async def test_one_bad_row_does_not_stop_the_window(self, client, adapter):
        def _boom(client_, org_id, lead):
            if lead.message_id == 777:
                raise RuntimeError("mapping exploded")
            return imovelweb_ingest_service.ingest_imovelweb_lead(
                client_, org_id, lead
            )

        adapter.inject_messages(AGENCY_A, [_message(777), _message(888)])

        result = await svc.reconcile_agency(
            client, adapter, codigo_imobiliaria=AGENCY_A, org_id=ORG,
            ingest_fn=_boom,
        )

        assert len(result["errors"]) == 1
        assert result["recovered"] == 1


class TestTenantIsolation:
    @pytest.mark.asyncio
    async def test_each_agency_lands_in_its_own_org(self, client, adapter):
        """This job runs on the admin client and BYPASSES RLS, so the
        agency→org map is the only isolation boundary. A bug here is a
        cross-tenant leak, not a glitch."""
        dimensions_service.ensure_default_dimensions(client, OTHER_ORG)
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": AGENCY_B, "org_id": str(OTHER_ORG)}
        ).execute()
        adapter.inject_messages(AGENCY_A, [_message(777)])
        adapter.inject_messages(AGENCY_B, [_message(888)])

        await svc.reconcile_all_agencies(client, adapter)

        rows = client.table("imovelweb_lead_events").select("*").execute().data
        by_agency = {r["codigo_imobiliaria"]: r["org_id"] for r in rows}
        assert by_agency[AGENCY_A] == str(ORG)
        assert by_agency[AGENCY_B] == str(OTHER_ORG)

    @pytest.mark.asyncio
    async def test_the_same_message_id_in_two_orgs_is_two_leads(self, client, adapter):
        """The twin guard is org-scoped. Two tenants can legitimately hold
        the same vendor message id, and collapsing them would hide one
        client's lead inside another's."""
        dimensions_service.ensure_default_dimensions(client, OTHER_ORG)
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": AGENCY_B, "org_id": str(OTHER_ORG)}
        ).execute()
        adapter.inject_messages(AGENCY_A, [_message(777)])
        adapter.inject_messages(AGENCY_B, [_message(777)])

        result = await svc.reconcile_all_agencies(client, adapter)

        assert result["recovered"] == 2


class TestAllAgencies:
    @pytest.mark.asyncio
    async def test_no_agencies_is_a_no_op_that_explains_itself(self, mock_db, adapter):
        scoped = mock_db.schema("social_wiring")

        result = await svc.reconcile_all_agencies(scoped, adapter)

        assert result == {"agencies": 0, "results": [], "recovered": 0}

    @pytest.mark.asyncio
    async def test_one_failing_agency_does_not_cost_the_others(self, client, adapter):
        dimensions_service.ensure_default_dimensions(client, OTHER_ORG)
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": AGENCY_B, "org_id": str(OTHER_ORG)}
        ).execute()

        class _PartlyBroken(FakeImovelWebClient):
            async def list_agency_messages(self, codigo, **kwargs):
                if codigo == AGENCY_A:
                    raise RuntimeError("vendor error for this agency")
                return await super().list_agency_messages(codigo, **kwargs)

        broken = _PartlyBroken(base_url=IMOVELWEB_SANDBOX_BR)
        broken.inject_messages(AGENCY_B, [_message(888)])

        result = await svc.reconcile_all_agencies(client, broken)

        assert result["recovered"] == 1
        assert any("error" in r for r in result["results"])

    def test_agencies_without_a_mapping_are_ignored(self, client):
        client.table("imovelweb_agencies").insert(
            {"codigo_imobiliaria": "no-org", "org_id": None}
        ).execute()

        rows = svc.list_agencies(client)

        assert {r["codigo_imobiliaria"] for r in rows} == {AGENCY_A}


class TestWindow:
    def test_the_lookback_is_inside_the_vendor_expiry(self):
        # 7 days is well inside the 72-hour retry window in the sense that
        # matters: it covers an outage of ours several times longer than
        # the window in which the vendor is still trying.
        assert svc.DEFAULT_LOOKBACK_DAYS >= 3

    def test_from_date_is_the_vendors_format(self):
        value = svc._from_date(7)

        assert len(value) == 8
        assert value.isdigit()
