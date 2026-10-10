"""``POST /api/meta/leadgen/simular`` — the staff-only lead rehearsal
(CONTRACT sw-lead-to-contract §1.4).

The REAL route, the REAL `LeadgenWebhookService.process_simulated`, the REAL
`upsert_lead` → `ingest_meta_lead` chain on the MockSupabaseClient; only the Graph
fetch is absent (that is the point of the endpoint)."""
from __future__ import annotations

import pytest

from noctusai_lib.testing.clients import TEST_USER_ID

URL = "/api/meta/leadgen/simular"
HOME_ORG = "00000000-0000-4000-8000-0000000000a9"
CAMPANHA = "00000000-0000-4000-8000-0000000000c1"
REG = "00000000-0000-4000-8000-0000000000e1"
CARD = "00000000-0000-4000-8000-00000000bb01"


@pytest.fixture
def staff_db(client):
    """The mock, with the caller made platform staff (trusted noctus_users row +
    platform home org), plus one campanha bound to ad AD1 → imóvel AAA1."""
    db = client.mock_supabase
    db.set_table_data("organizations", [{"id": HOME_ORG, "is_platform": True}])
    db.set_table_data(
        "noctus_users",
        [{"id": TEST_USER_ID, "org_id": HOME_ORG, "org_role": "owner", "role": "admin"}],
    )
    db.set_table_data("imovel_registry", [{"id": REG, "org_id": HOME_ORG, "codigo_canonical": "AAA1"}])
    db.set_table_data("campanhas", [{"id": CAMPANHA, "org_id": HOME_ORG, "nome": "C", "deleted_at": None}])
    db.set_table_data("campanha_imoveis", [{"campanha_id": CAMPANHA, "org_id": HOME_ORG, "imovel_ref_id": REG}])
    db.set_table_data(
        "campanha_veiculacoes",
        [{"id": "v1", "org_id": HOME_ORG, "campanha_id": CAMPANHA, "canal": "meta_ads",
          "nivel": "ad", "ref_codigo": "AD1"}],
    )
    return db


SIM_ID = "sim-fixed-0001"


class _SameStoreAdmin:
    """`client.schema("social_wiring")` on the real client is the SAME database,
    scoped; the mock hands back a separate empty store instead. This keeps one
    store so the upsert the service writes is the row the ingest later reads."""

    def __init__(self, db):
        self._db = db

    def schema(self, _name):
        return self

    def __getattr__(self, name):
        return getattr(self._db, name)


@pytest.fixture
def card(staff_db, client):
    """What migration 034's trigger spawns when the `meta_ads_leads` row lands
    (the mock has no triggers), plus the service wired with a known synthetic id
    through the real `get_leadgen_service` dependency seam."""
    from app.main import app
    from app.modules.meta_ads.routers.leadgen_router import get_leadgen_service
    from app.modules.meta_ads.services.leadgen_webhook_service import LeadgenWebhookService

    staff_db.set_table_data("atendimentos", [{
        "id": CARD, "org_id": HOME_ORG, "meta_ads_lead_id": SIM_ID, "lead_id": None,
        "cliente_id": None, "arquivado": False, "substituida_por": None,
        "created_at": "2026-07-10T12:00:06+00:00",
    }])
    ids = iter([SIM_ID] + [f"sim-extra-{n}" for n in range(20)])
    svc = LeadgenWebhookService(
        admin_supabase=_SameStoreAdmin(staff_db), sim_id_factory=lambda: next(ids)
    )
    app.dependency_overrides[get_leadgen_service] = lambda: svc
    yield staff_db
    app.dependency_overrides.pop(get_leadgen_service, None)


def _stored(db, table):
    return db.table(table).select("*").execute().data


def _body(**kw):
    return {"nome": "Maria Simulada", "telefone": "+5511977770000", **kw}


def test_without_a_token_is_401(client):
    resp = client.raw().post(URL, json=_body())
    assert resp.status_code == 401


def test_non_staff_is_403_not_platform_staff(client):
    db = client.mock_supabase
    db.set_table_data("organizations", [{"id": HOME_ORG, "is_platform": False}])
    db.set_table_data(
        "noctus_users",
        [{"id": TEST_USER_ID, "org_id": HOME_ORG, "org_role": "owner", "role": "admin"}],
    )
    resp = client.post(URL, json=_body())
    assert resp.status_code == 403
    assert resp.json()["code"] == "not_platform_staff"
    assert _stored(db, "meta_ads_leads") == []


def test_a_user_without_a_noctus_users_row_is_403(client):
    client.mock_supabase.set_table_data("noctus_users", [])
    resp = client.post(URL, json=_body())
    # No trusted row ⇒ the auth layer itself refuses (no org); never a 200.
    assert resp.status_code == 403


def test_unknown_body_fields_are_rejected(client, staff_db):
    resp = client.post(URL, json=_body(surprise=1))
    assert resp.status_code == 422


def test_staff_simulates_a_lead_end_to_end(client, card):
    resp = client.post(URL, json=_body(ad_id="AD1", respostas={"REF": "IGNORED9"}))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]

    assert data["meta_lead_id"] == SIM_ID
    assert data["lead_id"] and data["cliente_id"]
    assert data["atendimento_id"] == CARD
    # The ad-level campanha links AAA1; the REF answer names an imóvel OUTSIDE
    # it, which the lead named itself, so it is linked too (origem='lead').
    assert data["imoveis"] == [
        {"codigo": "AAA1", "origem": "campanha"},
        {"codigo": "IGNORED9", "origem": "lead"},
    ]

    (meta_row,) = _stored(card, "meta_ads_leads")
    assert meta_row["id"] == SIM_ID
    assert meta_row["simulado"] is True
    assert meta_row["full_name"] == "Maria Simulada"
    assert meta_row["ad_id"] == "AD1"
    assert meta_row["answers"]["REF"] == "IGNORED9"

    (lead,) = card.table("leads").select("*").execute().data
    assert lead["id"] == data["lead_id"]
    # The timeline's touch label reads leads.origem_raw.
    assert lead["origem_raw"] == "Lead simulado"
    (touch,) = card.table("cliente_touches").select("*").execute().data
    assert touch["origem_label"] == "Lead simulado"
    links = card.table("atendimento_imoveis").select("*").execute().data
    assert sorted((l["codigo"], l["origem"]) for l in links) == [
        ("AAA1", "campanha"), ("IGNORED9", "lead"),
    ]


def test_without_a_campanha_hit_the_ref_answer_links_as_lead(client, card):
    card.set_table_data("imovel_registry", [
        {"id": REG, "org_id": HOME_ORG, "codigo_canonical": "AAA1"},
        {"id": "00000000-0000-4000-8000-0000000000e2", "org_id": HOME_ORG, "codigo_canonical": "REF9"},
    ])
    resp = client.post(URL, json=_body(ad_id="UNKNOWN", respostas={"REF": "REF9"}))
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["imoveis"] == [{"codigo": "REF9", "origem": "lead"}]


def test_no_hit_and_no_ref_is_imovel_pendente(client, card):
    resp = client.post(URL, json=_body())
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["imoveis"] == []
    assert card.table("atendimento_imoveis").select("*").execute().data == []


def test_each_simulation_gets_its_own_synthetic_id(client, card):
    a = client.post(URL, json=_body(nome="Ana")).json()["data"]
    b = client.post(URL, json=_body(nome="Bia", telefone="+5511966660000")).json()["data"]
    assert a["meta_lead_id"] != b["meta_lead_id"]
    assert len(_stored(card, "meta_ads_leads")) == 2
