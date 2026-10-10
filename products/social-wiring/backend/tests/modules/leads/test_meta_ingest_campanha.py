"""Meta lead → campanha → imóveis at intake (CONTRACT sw-lead-to-contract §1.2/§1.3).

The imóvel comes from the CAMPAIGN first (ad → adset → campaign → form), the form's
`REF` answer is the fallback, and neither ⇒ `imovel_pendente`. The cliente is
attached synchronously. Real services against the MockSupabaseClient — nothing of
ours is patched."""
from __future__ import annotations

from uuid import UUID

import pytest

from app.modules.leads.services import dimensions_service, meta_ingest_service
from tests.modules.leads.conftest import ORG_A

ORG = UUID(ORG_A)
CARD = "00000000-0000-4000-8000-00000000bb01"

META = {
    "id": "meta-lead-9",
    "org_id": ORG_A,
    "full_name": "Maria Meta",
    "phone": "+5511977771111",
    "created_time": "2026-07-10T12:00:00+00:00",
    "campaign_name": "Camp A",
    "ad_id": "AD1",
    "adset_id": "ADSET1",
    "campaign_id": "CAMP1",
    "form_id": "FORM1",
    "answers": {"REF": "REF777"},
}

REG = {  # imovel_registry id → código
    "00000000-0000-4000-8000-0000000000e1": "AAA1",
    "00000000-0000-4000-8000-0000000000e2": "BBB2",
    "00000000-0000-4000-8000-0000000000e3": "CCC3",
    "00000000-0000-4000-8000-0000000000e4": "REF777",
}
CAMPANHAS = {
    "00000000-0000-4000-8000-0000000000c1": ("ad-camp", ["e1"], None),
    "00000000-0000-4000-8000-0000000000c2": ("adset-camp", ["e2"], None),
    "00000000-0000-4000-8000-0000000000c3": ("campaign-camp", ["e3", "e1"], None),
    "00000000-0000-4000-8000-0000000000c4": ("form-camp", ["e2"], None),
}


def _eid(n: str) -> str:
    return f"00000000-0000-4000-8000-0000000000{n}"


def _seed(db, *, veiculacoes, campanhas=None):
    db.set_table_data(
        "imovel_registry",
        [{"id": i, "org_id": ORG_A, "codigo_canonical": c} for i, c in REG.items()],
    )
    camp = campanhas or CAMPANHAS
    db.set_table_data(
        "campanhas",
        [{"id": cid, "org_id": ORG_A, "nome": n, "deleted_at": d} for cid, (n, _i, d) in camp.items()],
    )
    db.set_table_data(
        "campanha_imoveis",
        [
            {"campanha_id": cid, "org_id": ORG_A, "imovel_ref_id": _eid(i)}
            for cid, (_n, imoveis, _d) in camp.items()
            for i in imoveis
        ],
    )
    db.set_table_data(
        "campanha_veiculacoes",
        [
            {"id": f"v{n}", "org_id": ORG_A, "campanha_id": cid, "canal": "meta_ads",
             "nivel": nivel, "ref_codigo": ref}
            for n, (cid, nivel, ref) in enumerate(veiculacoes)
        ],
    )


def _links(db):
    return sorted(
        (r["codigo"], r["origem"])
        for r in db.table("atendimento_imoveis").select("*").execute().data
        if r.get("deleted_at") is None
    )


@pytest.fixture
def db(http_client, leads_client):
    dimensions_service.ensure_default_dimensions(leads_client, ORG)
    leads_client.set_table_data("meta_ads_leads", [dict(META)])
    leads_client.set_table_data(
        "atendimentos",
        [{
            "id": CARD, "org_id": ORG_A, "meta_ads_lead_id": META["id"], "lead_id": None,
            "cliente_id": None, "arquivado": False, "substituida_por": None,
            "created_at": "2026-07-10T12:00:06+00:00",
        }],
    )
    return leads_client


def C(n):  # campanha id
    return f"00000000-0000-4000-8000-0000000000c{n}"


ALL_LEVELS = [
    (C(1), "ad", "AD1"),
    (C(2), "adset", "ADSET1"),
    (C(3), "campaign", "CAMP1"),
    (C(4), "form", "FORM1"),
]


class TestResolutionOrder:
    def test_ad_beats_everything_below_it(self, db):
        _seed(db, veiculacoes=ALL_LEVELS)
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"]["nivel"] == "ad"
        # REF777 is outside the campanha: the lead named it, so it is linked too.
        assert _links(db) == [("AAA1", "campanha"), ("REF777", "lead")]
        assert out["imoveis"] == [
            {"codigo": "AAA1", "origem": "campanha"},
            {"codigo": "REF777", "origem": "lead"},
        ]

    def test_adset_beats_campaign_and_form(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[1:])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"]["nivel"] == "adset"
        assert _links(db) == [("BBB2", "campanha"), ("REF777", "lead")]

    def test_campaign_links_every_imovel_of_the_campanha(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[2:])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"]["nivel"] == "campaign"
        assert _links(db) == [("AAA1", "campanha"), ("CCC3", "campanha"), ("REF777", "lead")]
        assert {i["codigo"] for i in out["imoveis"]} == {"AAA1", "CCC3", "REF777"}

    def test_form_hit_wins_and_ref_outside_is_added_as_lead(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[3:])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"]["nivel"] == "form"
        assert _links(db) == [("BBB2", "campanha"), ("REF777", "lead")]

    def test_ref_is_the_fallback_with_origem_lead(self, db):
        _seed(db, veiculacoes=[])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"] is None
        assert _links(db) == [("REF777", "lead")]
        assert out["imoveis"] == [{"codigo": "REF777", "origem": "lead"}]

    def test_an_id_registered_at_another_nivel_does_not_match(self, db):
        # The ad id registered as an 'adset' must not resolve the lead's ad.
        _seed(db, veiculacoes=[(C(1), "adset", "AD1")])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"] is None

    def test_another_orgs_veiculacao_never_resolves(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[:1])
        rows = db.table("campanha_veiculacoes").select("*").execute().data
        db.set_table_data("campanha_veiculacoes", [{**r, "org_id": "someone-else"} for r in rows])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"] is None


class TestNoHit:
    def test_no_ref_and_no_campanha_is_imovel_pendente(self, db):
        _seed(db, veiculacoes=[])
        sem_ref = {**META, "answers": {}}
        db.set_table_data("meta_ads_leads", [sem_ref])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, sem_ref)
        assert out["created"] is True and out["imoveis"] == []
        assert _links(db) == []

    def test_a_deleted_campanha_never_resolves(self, db):
        deleted = dict(CAMPANHAS)
        deleted[C(1)] = ("ad-camp", ["e1"], "2026-09-01T00:00:00+00:00")
        _seed(db, veiculacoes=ALL_LEVELS[:1], campanhas=deleted)
        sem_ref = {**META, "answers": {}}
        db.set_table_data("meta_ads_leads", [sem_ref])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, sem_ref)
        assert out["campanha"] is None and _links(db) == []

    def test_a_deleted_campanha_falls_through_to_the_next_level(self, db):
        deleted = dict(CAMPANHAS)
        deleted[C(1)] = ("ad-camp", ["e1"], "2026-09-01T00:00:00+00:00")
        _seed(db, veiculacoes=ALL_LEVELS, campanhas=deleted)
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"]["nivel"] == "adset"

    def test_a_campanha_without_imoveis_is_no_hit_not_a_guess(self, db):
        empty = {C(1): ("ad-camp", [], None)}
        _seed(db, veiculacoes=ALL_LEVELS[:1], campanhas=empty)
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["campanha"] is None
        assert _links(db) == [("REF777", "lead")]


class TestClienteAtIntake:
    def test_the_titular_exists_before_ingest_returns(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[:1])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["cliente_id"]
        (cliente,) = db.table("clientes").select("*").execute().data
        assert cliente["id"] == out["cliente_id"] and cliente["nome"] == "Maria Meta"
        # the touch the card timeline reads exists too
        assert db.table("cliente_touches").select("*").execute().data
        assert out["atendimento_id"] == CARD


class TestRefVersusCampanha:
    """Owner ruling: one link per (atendimento, código)."""

    def _ref(self, db, codigo):
        ml = {**META, "answers": {"REF": codigo}}
        db.set_table_data("meta_ads_leads", [ml])
        return ml

    def test_ref_inside_the_campanha_is_a_single_campanha_link(self, db):
        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        _seed(db, veiculacoes=ALL_LEVELS[:1])  # ad → AAA1
        ml = self._ref(db, "aaa1")
        out = meta_ingest_service.ingest_meta_lead(db, ORG, ml)
        assert _links(db) == [("AAA1", "campanha")]
        assert out["imoveis"] == [{"codigo": "AAA1", "origem": "campanha"}]
        # the clientes sweep's reconcile adds nothing (no origem='lead' twin)
        rel = svc.reconcile(db, ORG)
        assert rel["vinculos_criados"] == 0
        assert _links(db) == [("AAA1", "campanha")]

    def test_ref_outside_the_campanha_adds_one_lead_link(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[2:])  # campaign → CCC3, AAA1
        ml = self._ref(db, "REF777")
        meta_ingest_service.ingest_meta_lead(db, ORG, ml)
        assert _links(db) == [("AAA1", "campanha"), ("CCC3", "campanha"), ("REF777", "lead")]

    def test_reconcile_is_idempotent_on_the_pair_for_any_origem(self, db):
        from app.modules.imovel_hub import atendimento_imoveis_service as svc

        _seed(db, veiculacoes=ALL_LEVELS[:1])
        meta_ingest_service.ingest_meta_lead(db, ORG, self._ref(db, "AAA1"))
        assert svc.reconcile(db, ORG)["vinculos_criados"] == 0
        assert svc.reconcile(db, ORG)["vinculos_criados"] == 0
        assert len(db.table("atendimento_imoveis").select("*").execute().data) == 1


class TestInteressesOnCampanhaHit:
    def test_every_campanha_imovel_becomes_a_cliente_interesse(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[2:])  # AAA1, CCC3
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        rows = db.table("cliente_imovel_interesses").select("*").execute().data
        by = {r["codigo"]: r for r in rows}
        assert {"AAA1", "CCC3"} <= set(by)
        assert all(r["cliente_id"] == out["cliente_id"] for r in rows)
        assert by["AAA1"]["meta_ads_lead_id"] == META["id"]

    def test_re_ingest_does_not_duplicate_interesses(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[2:])
        meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        n = len(db.table("cliente_imovel_interesses").select("*").execute().data)
        meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert len(db.table("cliente_imovel_interesses").select("*").execute().data) == n


class TestIdempotent:
    def test_re_ingest_duplicates_neither_leads_nor_links(self, db):
        _seed(db, veiculacoes=ALL_LEVELS[2:])
        first = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        again = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert first["created"] is True and again["created"] is False
        assert len(db.table("leads").select("*").execute().data) == 1
        assert len(db.table("clientes").select("*").execute().data) == 1
        assert _links(db) == [("AAA1", "campanha"), ("CCC3", "campanha"), ("REF777", "lead")]
        assert len(db.table("atendimento_imoveis").select("*").execute().data) == 3


class TestSimuladoLabel:
    def test_simulated_row_shows_lead_simulado_on_the_timeline_label(self, db):
        _seed(db, veiculacoes=[])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, {**META, "simulado": True})
        assert out["lead"]["origem_raw"] == "Lead simulado · Camp A"
        (touch,) = db.table("cliente_touches").select("*").execute().data
        assert touch["origem_label"].startswith("Lead simulado")

    def test_real_row_keeps_the_campaign_name(self, db):
        _seed(db, veiculacoes=[])
        out = meta_ingest_service.ingest_meta_lead(db, ORG, dict(META))
        assert out["lead"]["origem_raw"] == "Camp A"
