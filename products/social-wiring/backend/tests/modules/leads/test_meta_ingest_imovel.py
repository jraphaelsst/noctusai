"""Meta Lead-Ads → atendimento + imóvel + interesse (owner decision D1).

Verified fact (migrations 034/090): a Meta lead ALREADY spawned its funnel card
(`spawn_funil_card` fires on `meta_ads_leads` insert; the mapped `leads` row's
trigger attaches to that card). What never happened: the card was never LINKED
to the imóvel — `answers.REF` was read by nothing and the mapped `leads` row
carried no código. These tests pin the fix."""
from __future__ import annotations

from uuid import UUID

import pytest

from app.modules.leads.services import dimensions_service, meta_ingest_service
from tests.modules.leads.conftest import ORG_A

ORG = UUID(ORG_A)

META = {
    "id": "meta-lead-1",
    "org_id": ORG_A,
    "full_name": "Maria Meta",
    "phone": "+5511977771111",
    "created_time": "2026-07-10T12:00:00+00:00",
    "created_at": "2026-07-10T12:00:05+00:00",
    "campaign_name": "Camp A",
    "answers": {"REF": "ONE9441"},
    "codigo_imovel": "ONE9441",
    "codigo_imovel_norm": "ONE9441",
}


@pytest.fixture
def scoped(http_client, leads_client):
    dimensions_service.ensure_default_dimensions(leads_client, ORG)
    leads_client.set_table_data("imovel_registry", [])
    leads_client.set_table_data("meta_ads_leads", [dict(META)])
    return leads_client


def spawned_card(scoped, **extra):
    """The row migration 034's trigger writes when `meta_ads_leads` is inserted."""
    row = {
        "id": "00000000-0000-4000-8000-00000000bb01",
        "org_id": ORG_A,
        "meta_ads_lead_id": META["id"],
        "lead_id": None,
        "cliente_id": None,
        "arquivado": False,
        "substituida_por": None,
        "created_at": "2026-07-10T12:00:06+00:00",
    }
    row.update(extra)
    scoped.set_table_data("atendimentos", [row])
    return row


class TestPayloadCarriesTheCodigo:
    def test_ref_becomes_the_leads_codigo_imovel(self):
        payload = meta_ingest_service.map_meta_lead_to_lead_payload(
            {**META, "codigo_imovel": None}, origem_source_id="src"
        )
        assert payload["codigo_imovel"] == "ONE9441"

    def test_the_180_column_wins_over_the_raw_answer(self):
        payload = meta_ingest_service.map_meta_lead_to_lead_payload(
            {**META, "codigo_imovel": " one1 ", "answers": {"REF": "ONE2"}}, origem_source_id="s"
        )
        assert payload["codigo_imovel"] == "one1"

    @pytest.mark.parametrize("answers", [{}, {"REF": ""}, {"REF": "   "}, None])
    def test_no_ref_is_none_never_a_blank_string(self, answers):
        payload = meta_ingest_service.map_meta_lead_to_lead_payload(
            {**META, "codigo_imovel": None, "answers": answers}, origem_source_id="s"
        )
        assert payload["codigo_imovel"] is None


class TestIngestLinksTheCard:
    def test_meta_lead_gets_registry_junction_and_the_lead_carries_the_codigo(self, scoped):
        card = spawned_card(scoped)
        out = meta_ingest_service.ingest_meta_lead(scoped, ORG, dict(META))
        assert out["created"] is True
        assert out["lead"]["codigo_imovel"] == "ONE9441"

        assert [r["codigo_canonical"] for r in scoped.table("imovel_registry").select("*").execute().data] == ["ONE9441"]
        (juncao,) = scoped.table("atendimento_imoveis").select("*").execute().data
        assert juncao["atendimento_id"] == card["id"]
        assert (juncao["codigo"], juncao["origem"], juncao["principal"]) == ("ONE9441", "lead", True)

    def test_interesse_is_written_once_a_cliente_is_attached(self, scoped):
        card = spawned_card(scoped, cliente_id="00000000-0000-4000-8000-00000000cc01")
        scoped.set_table_data("clientes", [{"id": card["cliente_id"], "org_id": ORG_A, "nome": "Maria"}])
        meta_ingest_service.ingest_meta_lead(scoped, ORG, dict(META))
        (interesse,) = scoped.table("cliente_imovel_interesses").select("*").execute().data
        assert interesse["cliente_id"] == card["cliente_id"] and interesse["origem"] == "lead"
        assert interesse["meta_ads_lead_id"] == META["id"]
        assert interesse["created_at"] == META["created_time"]  # the true submission time

    def test_without_a_cliente_yet_the_sweep_completes_the_interesse(self, scoped):
        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        card = spawned_card(scoped)
        meta_ingest_service.ingest_meta_lead(scoped, ORG, dict(META))
        assert scoped.table("cliente_imovel_interesses").select("*").execute().data == []
        # the person-layer sweep attaches the cliente …
        scoped.table("atendimentos").update({"cliente_id": "00000000-0000-4000-8000-00000000cc02"}).eq("id", card["id"]).execute()
        out = svc.reconcile(scoped, ORG)
        assert out["interesses_criados"] == 1 and out["vinculos_criados"] == 0

    def test_a_meta_lead_without_ref_is_accepted_and_stays_imovel_pendente(self, scoped):
        spawned_card(scoped)
        sem_ref = {**META, "answers": {}, "codigo_imovel": None, "codigo_imovel_norm": None}
        scoped.set_table_data("meta_ads_leads", [sem_ref])
        out = meta_ingest_service.ingest_meta_lead(scoped, ORG, sem_ref)
        assert out["created"] is True and out["lead"].get("codigo_imovel") is None
        assert scoped.table("atendimento_imoveis").select("*").execute().data == []

    def test_re_ingest_is_a_noop(self, scoped):
        spawned_card(scoped)
        meta_ingest_service.ingest_meta_lead(scoped, ORG, dict(META))
        again = meta_ingest_service.ingest_meta_lead(scoped, ORG, dict(META))
        assert again["created"] is False
        assert len(scoped.table("atendimento_imoveis").select("*").execute().data) == 1
