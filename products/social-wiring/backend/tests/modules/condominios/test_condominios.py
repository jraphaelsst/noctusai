"""Condomínios module: suggest (idempotent, validated rows untouched), list
stats, merge (+ event + undo), role gates, cross-org isolation, strict 401."""
from __future__ import annotations

from uuid import UUID, uuid4

import pytest

from tests.modules.condominios.conftest import ORG_ID, auth, scoped  # noqa: F401

BASE = "/api/condominios"
OUTRA_ORG = str(uuid4())


def imovel(cod, emp, cidade="Cotia", bairro="Granja Viana", valor=1_000_000, area=200, lat=None, lng=None, org=ORG_ID):
    return {
        "org_id": org, "codigo": cod, "codigo_norm": cod.upper(), "empreendimento": emp,
        "cidade": cidade, "bairro": bairro, "status": "Venda", "valor_venda": valor,
        "area_privativa": area, "area_total": None, "latitude": lat, "longitude": lng,
    }


@pytest.fixture
def com_imoveis(scoped):
    rows = [
        imovel("A1", "Vila Verde", valor=1_000_000, area=200, lat=-23.6, lng=-46.8),
        imovel("A2", "VILA VERDE", valor=2_000_000, area=200, lat=-23.8, lng=-46.9),
        imovel("A3", "Condominio Vila Verde", valor=1_500_000, area=100),
        imovel("B1", "Chácara Ipê", valor=900_000, area=90),
        imovel("C1", "Cond Vila Verde", cidade="Carapicuíba"),
        imovel("X1", "Vila Verde", org=OUTRA_ORG),
    ]
    for r in rows:
        scoped.table("imoveis").insert(r).execute()
    return scoped


def condominios(scoped):
    return scoped.table("condominios")._data


def aliases(scoped):
    return scoped.table("condominio_aliases")._data


def eventos(scoped):
    return scoped.table("condominio_eventos")._data


class TestSugerir:
    def test_cria_sugeridos_com_aliases_e_centroide(self, admin_client, com_imoveis):
        r = admin_client.post(f"{BASE}/sugerir", headers=auth())
        assert r.status_code == 200, r.text
        cs = [c for c in condominios(com_imoveis) if c["org_id"] == ORG_ID]
        assert sorted((c["nome"], c["cidade"]) for c in cs) == [
            ("Chácara Ipê", "Cotia"), ("Cond Vila Verde", "Carapicuíba"), ("Vila Verde", "Cotia")
        ]
        cotia = next(c for c in cs if c["cidade"] == "Cotia" and c["nome"] == "Vila Verde")
        assert cotia["status_validacao"] == "sugerido"
        assert cotia["latitude"] == pytest.approx(-23.7) and cotia["longitude"] == pytest.approx(-46.85)
        assert {a["alias_normalizado"] for a in aliases(com_imoveis) if a["condominio_id"] == cotia["id"]} == {
            "VILA VERDE", "CONDOMINIO VILA VERDE"}
        assert all(c["org_id"] == ORG_ID for c in cs)  # other org's imovel never leaks in

    def test_idempotente_e_validado_intocado(self, admin_client, com_imoveis):
        admin_client.post(f"{BASE}/sugerir", headers=auth())
        cotia = next(c for c in condominios(com_imoveis) if c["cidade"] == "Cotia" and c["nome"] == "Vila Verde")
        assert admin_client.patch(f"{BASE}/{cotia['id']}", json={"seguranca_nivel": 4, "tipo": "horizontal"},
                                  headers=auth()).status_code == 200
        assert admin_client.post(f"{BASE}/{cotia['id']}/validar", headers=auth()).status_code == 200
        antes = {c["id"]: dict(c) for c in condominios(com_imoveis)}
        n_alias = len(aliases(com_imoveis))
        # a NEW spelling of the validated one appears; re-suggest
        com_imoveis.table("imoveis").insert(imovel("A9", "Cond. Vila Verde", lat=-10.0, lng=-10.0)).execute()
        r = admin_client.post(f"{BASE}/sugerir", headers=auth())
        assert r.json()["condominios_criados"] == 0
        assert len(condominios(com_imoveis)) == len(antes)
        assert len(aliases(com_imoveis)) == n_alias + 1
        depois = next(c for c in condominios(com_imoveis) if c["id"] == cotia["id"])
        for campo in ("nome", "status_validacao", "seguranca_nivel", "tipo", "latitude", "longitude", "validado_em"):
            assert depois[campo] == antes[cotia["id"]][campo], campo
        # and a third run is a no-op
        r = admin_client.post(f"{BASE}/sugerir", headers=auth())
        assert r.json()["aliases_novos"] == 0

    def test_membro_comum_leva_403(self, member_client, scoped):
        assert member_client.post(f"{BASE}/sugerir", headers=auth()).status_code == 403
        assert condominios(scoped) == []


class TestListaEStats:
    def test_contagem_e_preco_m2_mediano(self, admin_client, com_imoveis):
        admin_client.post(f"{BASE}/sugerir", headers=auth())
        itens = admin_client.get(BASE, headers=auth()).json()["items"]
        vv = next(i for i in itens if i["nome"] == "Vila Verde" and i["cidade"] == "Cotia")
        assert vv["imoveis_count"] == 3 and vv["aliases_count"] == 2
        # 5000, 10000, 15000 -> median 10000
        assert vv["preco_m2_mediano"] == 10000
        assert itens[0]["imoveis_count"] == 3  # sorted by imoveis desc
        f = admin_client.get(BASE, params={"cidade": "carapicuíba"}, headers=auth()).json()
        assert [i["cidade"] for i in f["items"]] == ["Carapicuíba"]
        f = admin_client.get(BASE, params={"status": "validado"}, headers=auth()).json()
        assert f["items"] == []

    def test_manual_empreendimento_vence_o_espelho(self, admin_client, com_imoveis):
        admin_client.post(f"{BASE}/sugerir", headers=auth())
        com_imoveis.table("imovel_dados").insert(
            {"org_id": ORG_ID, "codigo": "b1", "empreendimento_manual": "vila  verde",
         "empreendimento_manual_confirmado_em": "2026-10-14T00:00:00+00:00"}).execute()
        itens = admin_client.get(BASE, headers=auth()).json()["items"]
        vv = next(i for i in itens if i["nome"] == "Vila Verde" and i["cidade"] == "Cotia")
        assert vv["imoveis_count"] == 4


class TestFundir:
    def _dois(self, admin_client, com_imoveis):
        admin_client.post(f"{BASE}/sugerir", headers=auth())
        cs = {(c["nome"], c["cidade"]): c for c in condominios(com_imoveis)}
        return cs[("Vila Verde", "Cotia")], cs[("Chácara Ipê", "Cotia")]

    def test_fusao_repoe_aliases_gera_evento_e_e_reversivel(self, admin_client, com_imoveis):
        destino, origem = self._dois(admin_client, com_imoveis)
        r = admin_client.post(f"{BASE}/{origem['id']}/fundir", json={"destino_id": destino["id"]}, headers=auth())
        assert r.status_code == 200, r.text
        assert r.json()["aliases_movidos"] == 1
        assert {a["condominio_id"] for a in aliases(com_imoveis) if "IPÊ" in a["alias_normalizado"]} == {destino["id"]}
        o = next(c for c in condominios(com_imoveis) if c["id"] == origem["id"])
        assert o["status_validacao"] == "descartado" and o["fundido_em_id"] == destino["id"]
        tipos = [e["tipo"] for e in eventos(com_imoveis)]
        assert tipos.count("merge") == 2
        ev = next(e for e in eventos(com_imoveis) if e["tipo"] == "merge" and e["condominio_id"] == destino["id"])
        assert ev["ator"] is not None
        itens = admin_client.get(BASE, headers=auth()).json()["items"]
        assert next(i for i in itens if i["id"] == destino["id"])["imoveis_count"] == 4

        r = admin_client.post(f"{BASE}/{origem['id']}/desfazer-fusao", headers=auth())
        assert r.status_code == 200, r.text
        assert {a["condominio_id"] for a in aliases(com_imoveis) if "IPÊ" in a["alias_normalizado"]} == {origem["id"]}
        o = next(c for c in condominios(com_imoveis) if c["id"] == origem["id"])
        assert o["status_validacao"] == "sugerido" and o["fundido_em_id"] is None

    def test_fundir_em_si_mesmo_e_rejeitado(self, admin_client, com_imoveis):
        destino, _ = self._dois(admin_client, com_imoveis)
        r = admin_client.post(f"{BASE}/{destino['id']}/fundir", json={"destino_id": destino["id"]}, headers=auth())
        assert r.status_code in (400, 422)

    def test_membro_comum_nao_funde_nem_valida(self, member_client, scoped):
        a, b = str(uuid4()), str(uuid4())
        assert member_client.post(f"{BASE}/{a}/fundir", json={"destino_id": b}, headers=auth()).status_code == 403
        assert member_client.post(f"{BASE}/{a}/validar", headers=auth()).status_code == 403
        assert member_client.post(f"{BASE}/{a}/descartar", headers=auth()).status_code == 403
        assert member_client.post(f"{BASE}/{a}/aliases", json={"alias": "x"}, headers=auth()).status_code == 403


class TestCrud:
    def test_validar_descartar_renomear_alias(self, admin_client, com_imoveis):
        admin_client.post(f"{BASE}/sugerir", headers=auth())
        c = next(c for c in condominios(com_imoveis) if c["nome"] == "Vila Verde" and c["cidade"] == "Cotia")
        cid = c["id"]
        r = admin_client.post(f"{BASE}/{cid}/validar", headers=auth())
        assert r.json()["status_validacao"] == "validado" and r.json()["validado_em"]
        assert admin_client.post(f"{BASE}/{cid}/validar", headers=auth()).status_code == 409
        assert admin_client.post(f"{BASE}/{cid}/renomear", json={"nome": "Vila Verde Residencial"},
                                 headers=auth()).json()["nome"] == "Vila Verde Residencial"
        r = admin_client.post(f"{BASE}/{cid}/aliases", json={"alias": " vila  verde ii "}, headers=auth())
        assert r.status_code == 200 and r.json()["alias_normalizado"] == "VILA VERDE II"
        assert admin_client.post(f"{BASE}/{cid}/aliases", json={"alias": "VILA VERDE II"}, headers=auth()).status_code == 409
        det = admin_client.get(f"{BASE}/{cid}", headers=auth()).json()
        assert any(a["alias_normalizado"] == "VILA VERDE II" for a in det["aliases"])
        assert {"validate", "rename", "alias_add"} <= {e["tipo"] for e in det["eventos"]}
        aid = r.json()["id"]
        assert admin_client.delete(f"{BASE}/{cid}/aliases/{aid}", headers=auth()).status_code == 200
        assert admin_client.post(f"{BASE}/{cid}/descartar", headers=auth()).json()["status_validacao"] == "descartado"

    def test_membro_edita_atributos_e_tipo_invalido_422(self, member_client, scoped):
        row = scoped.table("condominios").insert(
            {"id": str(uuid4()), "org_id": ORG_ID, "nome": "X", "nome_normalizado": "X", "cidade": "Cotia"}).execute().data[0]
        r = member_client.patch(f"{BASE}/{row['id']}", json={"area_lazer": "piscina"}, headers=auth())
        assert r.status_code == 200 and r.json()["area_lazer"] == "piscina"
        assert member_client.patch(f"{BASE}/{row['id']}", json={"tipo": "castelo"}, headers=auth()).status_code == 422
        assert member_client.patch(f"{BASE}/{row['id']}", json={"seguranca_nivel": 9}, headers=auth()).status_code == 422

    def test_isolamento_entre_orgs(self, admin_client, scoped):
        alheio = scoped.table("condominios").insert(
            {"id": str(uuid4()), "org_id": OUTRA_ORG, "nome": "ALHEIO", "nome_normalizado": "ALHEIO"}).execute().data[0]
        assert admin_client.get(BASE, headers=auth()).json()["items"] == []
        assert admin_client.get(f"{BASE}/{alheio['id']}", headers=auth()).status_code == 404
        assert admin_client.post(f"{BASE}/{alheio['id']}/validar", headers=auth()).status_code == 404
        assert admin_client.patch(f"{BASE}/{alheio['id']}", json={"area_lazer": "x"}, headers=auth()).status_code == 404


def test_toda_rota_exige_auth_401_estrito(anon_client):
    from app.modules.condominios import register

    caminhos = {
        (m.lower(), r.path)
        for router in register().routers for r in router.routes
        for m in getattr(r, "methods", set()) if m.lower() in {"get", "post", "patch", "delete"}
    }
    assert caminhos
    for metodo, path in sorted(caminhos):
        concreto = path.replace("{condominio_id}", str(uuid4())).replace("{alias_id}", str(uuid4()))
        kw = {"json": {}} if metodo in {"post", "patch"} else {}
        resp = getattr(anon_client, metodo)(concreto, **kw)
        assert resp.status_code == 401, f"{metodo.upper()} {concreto} -> {resp.status_code}"
