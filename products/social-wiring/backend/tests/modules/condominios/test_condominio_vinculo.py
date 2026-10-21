"""Migration 300 — the imóvel page's condomínio picker (search + create) and
the FK side of the master list (FK-first stats, merge re-points the FK).
Synthetic data only."""
from __future__ import annotations

from uuid import uuid4

import pytest

from tests.modules.condominios.conftest import ORG_ID, auth, scoped  # noqa: F401
from tests.modules.imovel_hub.conftest import dados_row, imovel_row, registry_row

BASE = "/api/condominios"
OUTRA_ORG = str(uuid4())


def cond(nome, norm, *, org=ORG_ID, status="validado", fundido=None, cidade="Cotia"):
    return {
        "id": str(uuid4()), "org_id": org, "nome": nome, "nome_normalizado": norm,
        "cidade": cidade, "bairro": None, "status_validacao": status, "fundido_em_id": fundido,
    }


@pytest.fixture
def lista(scoped):  # noqa: F811
    verde = cond("Residencial Vila Verde", "VILA VERDE")
    rows = [
        verde,
        cond("Vila Velha", "VILA VELHA"),
        cond("Chácara Ipê", "CHACARA IPE"),
        cond("Nova Vila", "NOVA VILA"),
        cond("Vila Fundida", "VILA FUNDIDA", status="descartado", fundido=verde["id"]),
        cond("Vila Descartada", "VILA DESCARTADA", status="descartado"),
        cond("Vila Alheia", "VILA ALHEIA", org=OUTRA_ORG),
    ]
    scoped.set_table_data("condominios", rows)
    scoped.set_table_data("condominio_aliases", [])
    scoped.set_table_data("condominio_eventos", [])
    return {r["nome"]: r for r in rows}


class TestBuscar:
    def test_contains_accent_insensitive_prefix_first_never_merged_discarded_or_alien(
        self, member_client, lista
    ):
        r = member_client.get(f"{BASE}/buscar", params={"q": "vila"}, headers=auth())
        assert r.status_code == 200, r.text
        nomes = [i["nome"] for i in r.json()["items"]]
        # prefix hits (by name, or by identity once "Residencial" is dropped)
        # first, alphabetical; then contains-only hits.
        assert nomes == ["Residencial Vila Verde", "Vila Velha", "Nova Vila"]

    def test_prefix_words_and_accents_ignored(self, member_client, lista):
        nomes = [i["nome"] for i in member_client.get(
            f"{BASE}/buscar", params={"q": "chacara ip"}, headers=auth()).json()["items"]]
        assert nomes == ["Chácara Ipê"]
        nomes = [i["nome"] for i in member_client.get(
            f"{BASE}/buscar", params={"q": "residencial vila verde"}, headers=auth()).json()["items"]]
        assert nomes == ["Residencial Vila Verde"]

    def test_empty_query_returns_nothing_and_limit_is_respected(self, member_client, lista):
        assert member_client.get(f"{BASE}/buscar", params={"q": "  "}, headers=auth()).json()["items"] == []
        r = member_client.get(f"{BASE}/buscar", params={"q": "v", "limite": 1}, headers=auth())
        assert len(r.json()["items"]) == 1

    def test_item_shape(self, member_client, lista):
        item = member_client.get(f"{BASE}/buscar", params={"q": "ipê"}, headers=auth()).json()["items"][0]
        assert set(item) == {"id", "nome", "cidade", "bairro", "status_validacao"}


class TestCriar:
    def test_member_creates_sugerido_with_alias_and_event(self, member_client, lista, scoped):  # noqa: F811
        r = member_client.post(BASE, json={"nome": "  Reserva   do Vianna ", "cidade": "Cotia"}, headers=auth())
        assert r.status_code == 200, r.text
        b = r.json()
        assert b["criado"] is True and b["nome"] == "Reserva do Vianna" and b["status_validacao"] == "sugerido"
        row = next(c for c in scoped.table("condominios")._data if c["id"] == b["id"])
        assert row["org_id"] == ORG_ID and row["nome_normalizado"] == "RESERVA DO VIANNA"
        assert any(a["condominio_id"] == b["id"] and a["alias_normalizado"] == "RESERVA DO VIANNA"
                   for a in scoped.table("condominio_aliases")._data)
        assert any(e["condominio_id"] == b["id"] and e["tipo"] == "sugerido"
                   for e in scoped.table("condominio_eventos")._data)

    def test_dedupes_by_normalized_name(self, member_client, lista, scoped):  # noqa: F811
        antes = len(scoped.table("condominios")._data)
        b = member_client.post(BASE, json={"nome": "Condomínio Vila Velha"}, headers=auth()).json()
        assert b["criado"] is False and b["id"] == lista["Vila Velha"]["id"]
        assert len(scoped.table("condominios")._data) == antes

    def test_merged_name_returns_the_destination(self, member_client, lista):
        b = member_client.post(BASE, json={"nome": "Vila Fundida"}, headers=auth()).json()
        assert b["criado"] is False and b["id"] == lista["Residencial Vila Verde"]["id"]

    def test_discarded_name_is_409(self, member_client, lista):
        assert member_client.post(BASE, json={"nome": "Vila Descartada"}, headers=auth()).status_code == 409

    def test_another_orgs_name_does_not_dedupe(self, member_client, lista):
        b = member_client.post(BASE, json={"nome": "Vila Alheia"}, headers=auth()).json()
        assert b["criado"] is True and b["id"] != lista["Vila Alheia"]["id"]

    @pytest.mark.parametrize("body", [{}, {"nome": ""}, {"nome": "Condomínio"}, {"nome": "X", "extra": 1}])
    def test_invalid_body_is_refused(self, member_client, lista, body):
        assert member_client.post(BASE, json=body, headers=auth()).status_code in (400, 422)


@pytest.mark.parametrize("metodo, path", [("get", f"{BASE}/buscar?q=vila"), ("post", BASE)])
def test_new_routes_are_strict_401(anon_client, metodo, path):
    kw = {"json": {"nome": "Vila"}} if metodo == "post" else {}
    assert getattr(anon_client, metodo)(path, **kw).status_code == 401


class TestFkNoMestre:
    def _imoveis(self, scoped, verde_id):  # noqa: F811
        scoped.set_table_data("imovel_registry", [registry_row("A1"), registry_row("A2"), registry_row("A3")])
        scoped.set_table_data("imoveis", [
            {**imovel_row("A1"), "codigo_norm": "A1", "empreendimento": "Outro Nome"},
            {**imovel_row("A2"), "codigo_norm": "A2", "empreendimento": "Vila Verde"},
            {**imovel_row("A3"), "codigo_norm": "A3", "empreendimento": "Vila Verde"},
        ])
        scoped.set_table_data("imovel_dados", [
            dados_row("A1", condominio_id=verde_id, casa_de_rua=False),
            dados_row("A3", casa_de_rua=True),
        ])
        scoped.set_table_data("condominio_aliases", [{
            "id": str(uuid4()), "org_id": ORG_ID, "condominio_id": verde_id, "alias": "Vila Verde",
            "alias_normalizado": "VILA VERDE", "origem": "manual",
        }])

    def test_stats_count_fk_first_and_casa_de_rua_never_matches_by_name(self, admin_client, lista, scoped):  # noqa: F811
        verde = lista["Residencial Vila Verde"]["id"]
        self._imoveis(scoped, verde)
        itens = admin_client.get(BASE, headers=auth()).json()["items"]
        # A1 by FK (its CRM name differs), A2 by alias; A3 is a casa de rua.
        assert next(i for i in itens if i["id"] == verde)["imoveis_count"] == 2

    def test_merge_moves_attached_imoveis_and_undo_moves_them_back(self, admin_client, lista, scoped):  # noqa: F811
        verde, velha = lista["Residencial Vila Verde"]["id"], lista["Vila Velha"]["id"]
        self._imoveis(scoped, velha)
        r = admin_client.post(f"{BASE}/{velha}/fundir", json={"destino_id": verde}, headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["imoveis_movidos"] == 1
        a1 = next(d for d in scoped.table("imovel_dados")._data if d["codigo"] == "A1")
        assert a1["condominio_id"] == verde
        assert admin_client.post(f"{BASE}/{velha}/desfazer-fusao", headers=auth()).status_code == 200
        a1 = next(d for d in scoped.table("imovel_dados")._data if d["codigo"] == "A1")
        assert a1["condominio_id"] == velha
