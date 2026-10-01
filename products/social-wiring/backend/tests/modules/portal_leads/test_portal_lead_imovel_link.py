"""OLX / imovelweb ingest → the imóvel-link step (contract §3.5).

Both paths already parse the código and `registrar_imovel` it; the link step
(`vincular_lead_seguro`) is reached through the `vincular=` DI seam, so the
test asserts the call (and its arguments) without patching either module."""
from __future__ import annotations

import copy
from uuid import UUID

import pytest

from noctusai_lib.integrations.imovelweb import IMOVELWEB_SAMPLE_BODIES, parse_imovelweb_callback
from noctusai_lib.integrations.olx import OLX_SAMPLE_LEAD, parse_olx_lead_webhook

from app.modules.leads.services import dimensions_service
from app.modules.portal_leads.services import imovelweb_ingest_service, olx_ingest_service
from tests.modules.portal_leads.conftest import ORG_A

ORG = UUID(ORG_A)


class Espiao:
    def __init__(self):
        self.chamadas = []

    def __call__(self, client, org_id, **kw):
        self.chamadas.append((org_id, kw))
        return None


@pytest.fixture
def client(mock_db):
    scoped = mock_db.schema("social_wiring")
    dimensions_service.ensure_default_dimensions(scoped, ORG)
    scoped.set_table_data("imovel_registry", [])
    return scoped


def test_olx_ingest_links_the_created_lead(client):
    lead = parse_olx_lead_webhook(copy.deepcopy(OLX_SAMPLE_LEAD))
    espiao = Espiao()
    out = olx_ingest_service.ingest_olx_lead(client, ORG, lead, vincular=espiao)
    assert out["created"] is True
    assert [(o, kw["lead_id"], kw["contexto"]) for o, kw in espiao.chamadas] == [
        (ORG, out["lead"]["id"], "olx_ingest")
    ]


def test_olx_re_delivery_does_not_relink(client):
    lead = parse_olx_lead_webhook(copy.deepcopy(OLX_SAMPLE_LEAD))
    espiao = Espiao()
    olx_ingest_service.ingest_olx_lead(client, ORG, lead, vincular=espiao)
    olx_ingest_service.ingest_olx_lead(client, ORG, lead, vincular=espiao)
    assert len(espiao.chamadas) == 1


def test_imovelweb_ingest_links_the_created_lead(client):
    body = copy.deepcopy(IMOVELWEB_SAMPLE_BODIES["EN2"])
    lead = parse_imovelweb_callback(body, language="EN2")
    espiao = Espiao()
    out = imovelweb_ingest_service.ingest_imovelweb_lead(client, ORG, lead, vincular=espiao)
    assert out["created"] is True
    assert [(kw["lead_id"], kw["contexto"]) for _o, kw in espiao.chamadas] == [
        (out["lead"]["id"], "imovelweb_ingest")
    ]


def test_the_real_link_step_converges_through_the_sweep(client):
    """Default (un-spied) path end to end: the card the DB trigger spawns
    after the insert is linked by the reconcile, código registered by the
    ingest itself."""
    from app.modules.imovel_hub import atendimento_imoveis_service as svc

    lead = parse_olx_lead_webhook(copy.deepcopy(OLX_SAMPLE_LEAD))
    out = olx_ingest_service.ingest_olx_lead(client, ORG, lead)
    client.table("atendimentos").insert(
        {"id": "00000000-0000-4000-8000-00000000dd01", "org_id": ORG_A,
         "lead_id": out["lead"]["id"], "cliente_id": None, "arquivado": False,
         "substituida_por": None, "created_at": "2026-07-01T00:00:00+00:00"}
    ).execute()
    assert svc.reconcile(client, ORG)["vinculos_criados"] == 1
    (juncao,) = client.table("atendimento_imoveis").select("*").execute().data
    assert juncao["codigo"] == "A40171" and juncao["origem"] == "lead"
