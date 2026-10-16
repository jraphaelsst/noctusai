"""Lais wave 10 -- Relatorios: dedup, % math, month boundaries in Sao Paulo time, A7 + org isolation,
strict == 401. Mock DB seams only; fixtures carry no personal data."""
from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import MagicMock, patch
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.services import lais_relatorios_service as svc

from tests.support.lais_world import CONNECTION_ID, ORG_ID, OTHER_ORG_ID, OWNER_ID, World

URL = "/api/lais/relatorios"
H = {"Authorization": "Bearer test-token"}
MES = "2026-10"
DENTRO = "2026-10-10T12:00:00+00:00"
OUTRO_USER = "00000000-0000-4000-8000-0000000000d9"


def _mundo(*, org=ORG_ID):
    w = World()
    w.seed_connection()
    for t in ("lais_visitas", "imoveis"):
        w.sw.set_table_data(t, [])
    return w


def _lead(w, slots, *, op="compra", quando=DENTRO, org=ORG_ID, responsavel=None, conexao=CONNECTION_ID):
    cid = str(uuid4())
    w.sw.table("lais_contatos").insert({
        "id": cid, "org_id": org, "connection_id": conexao, "chat_id": f"{cid}@c.us", "operacao": op,
        "slots": slots, "responsavel_user_id": responsavel}).execute()
    w.sw.table("lais_interacoes").insert({
        "id": str(uuid4()), "org_id": org, "contato_id": cid, "iniciada_at": quando, "operacao": op, "slots": {}}).execute()
    return cid


def _visita(w, cid, codigo, quando=DENTRO, org=ORG_ID):
    w.sw.table("lais_visitas").insert({"id": str(uuid4()), "org_id": org, "contato_id": cid, "codigo_imovel": codigo,
                                      "created_at": quando, "status": "solicitada"}).execute()


def _imovel(w, codigo, categoria, *, fin=("venda",), venda=500000, locacao=None, org=ORG_ID, exibir=True):
    w.sw.table("imoveis").insert({"org_id": org, "codigo": codigo, "codigo_norm": codigo.upper(), "categoria": categoria,
                                  "finalidades": list(fin), "valor_venda": venda, "valor_locacao": locacao,
                                  "exibir_no_site": exibir}).execute()


def _scene(override_settings_factory, w, role="owner"):
    w.core.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role}])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app

        bind_consent_module_to_mock(w.root)
        from app.config import settings as _s
        from app.dependencies import get_settings

        stub = _s.model_copy(update={})
        app.dependency_overrides[get_settings] = lambda: stub
        try:
            tc = TestClient(app)
            yield lambda **q: tc.get(URL, params=q, headers=H)
        finally:
            app.dependency_overrides.pop(get_settings, None)


@pytest.fixture
def mundo():
    return _mundo()


@pytest.fixture
def admin(mundo, override_settings_factory):
    yield from _scene(override_settings_factory, mundo, "owner")


@pytest.fixture
def override_settings_factory():
    yield None


class TestPuro:
    def test_month_bounds_are_sao_paulo_midnight(self):
        ini, fim = svc.limites_mes("2026-10")
        assert ini == datetime(2026, 10, 1, 3, 0, tzinfo=timezone.utc)  # BRT = UTC-3
        assert fim == datetime(2026, 11, 1, 3, 0, tzinfo=timezone.utc)
        assert svc.limites_mes("2026-12")[1] == datetime(2027, 1, 1, 3, 0, tzinfo=timezone.utc)

    @pytest.mark.parametrize("txt,esperado", [("500 mil", 500000), ("R$ 1,2 milhão", 1200000), ("2.500", 2500),
                                              ("até 4k", 4000), ("R$ 350.000,00", 350000), ("sem ideia", None)])
    def test_parse_preco(self, txt, esperado):
        assert svc.parse_preco(txt) == esperado

    def test_bad_mes(self):
        with pytest.raises(Exception):
            svc.limites_mes("2026-13")


class TestImoveis:
    def test_percent_math_and_shelf(self, mundo, admin):
        w = mundo
        for tipo in ("casa", "casa", "Apartamento", "apartamento"):
            _lead(w, {"tipo_imovel": tipo})
        _lead(w, {"tipo_imovel": "Casas"})  # plural folds into casa
        _lead(w, {})  # no tipo -> not in the denominator
        for i, cat in enumerate(["Casa", "Apartamento", "Apartamento", "Apartamento"]):
            _imovel(w, f"X{i}", cat)
        _imovel(w, "ALUG", "Casa", fin=("aluguel",))   # other operacao -> not on this shelf
        _imovel(w, "OCULTO", "Casa", exibir=False)    # hidden from the site -> not stock
        r = admin(operacao="compra", mes=MES, aba="imoveis")
        assert r.status_code == 200
        d = r.json()["data"]
        assert d["total_leads"] == 6
        por = {t["tipo"]: t for t in d["tipos"]}
        assert por["Casa"] == {"tipo": "Casa", "pct_leads": 60.0, "pct_prateleira": 25.0}
        assert por["Apartamento"]["pct_leads"] == 40.0 and por["Apartamento"]["pct_prateleira"] == 75.0
        assert d["tipos"][0]["tipo"] == "Casa"

    def test_top_imoveis_deduplicated(self, mundo, admin):
        w = mundo
        _imovel(w, "AP0123", "Apartamento", venda=450000)
        a, b = _lead(w, {}), _lead(w, {})
        _visita(w, a, "AP0123")
        _visita(w, a, "ap0123")        # same lead, other spelling -> still ONE
        _visita(w, a, "AP0123 ")
        _visita(w, b, "AP0123")
        _visita(w, b, "ZZ9")           # unknown to the catalogue -> kept, no tipo/price
        w.sw.table("lais_acoes_aplicadas").insert({"id": str(uuid4()), "org_id": ORG_ID, "contato_id": b, "lote_hash": "h",
                                                   "seq": 1, "tipo": "pedido_visita", "payload": {"codigo": "AP0123"},
                                                   "created_at": DENTRO}).execute()
        d = admin(operacao="compra", mes=MES, aba="imoveis").json()["data"]
        assert d["top_imoveis"] == [
            {"codigo": "AP0123", "tipo": "Apartamento", "preco": 450000.0, "leads": 2},
            {"codigo": "ZZ9", "tipo": None, "preco": None, "leads": 1},
        ]

    def test_aluguel_uses_locacao_price(self, mundo, admin):
        w = mundo
        _imovel(w, "L1", "Casa", fin=("aluguel",), venda=None, locacao=3200)
        _visita(w, _lead(w, {}, op="aluguel"), "L1")
        d = admin(operacao="aluguel", mes=MES, aba="imoveis").json()["data"]
        assert d["top_imoveis"][0]["preco"] == 3200.0


class TestMes:
    def test_boundaries_in_sao_paulo_time(self, mundo, admin):
        w = mundo
        _lead(w, {"tipo_imovel": "casa"}, quando="2026-10-01T02:59:59+00:00")   # 23:59:59 Sep 30 BRT -> September
        _lead(w, {"tipo_imovel": "casa"}, quando="2026-10-01T03:00:00+00:00")   # 00:00 Oct 1 BRT -> October
        _lead(w, {"tipo_imovel": "casa"}, quando="2026-11-01T02:59:59+00:00")   # last second of October
        _lead(w, {"tipo_imovel": "casa"}, quando="2026-11-01T03:00:00+00:00")   # November
        assert admin(operacao="compra", mes="2026-10", aba="imoveis").json()["data"]["total_leads"] == 2
        assert admin(operacao="compra", mes="2026-09", aba="imoveis").json()["data"]["total_leads"] == 1

    def test_operacao_filter(self, mundo, admin):
        _lead(mundo, {}, op="aluguel")
        assert admin(operacao="compra", mes=MES, aba="imoveis").json()["data"]["total_leads"] == 0

    def test_visit_outside_month_not_counted(self, mundo, admin):
        _imovel(mundo, "A1", "Casa")
        c = _lead(mundo, {})
        _visita(mundo, c, "A1", quando="2026-09-20T12:00:00+00:00")
        assert admin(operacao="compra", mes=MES, aba="imoveis").json()["data"]["top_imoveis"] == []

    def test_validation(self, admin):
        assert admin(operacao="x", mes=MES, aba="imoveis").status_code == 422
        assert admin(operacao="compra", mes="2026-13", aba="imoveis").status_code == 422
        assert admin(operacao="compra", mes=MES, aba="y").status_code == 422


class TestBairros:
    def test_ranking_and_desempenho(self, mundo, admin):
        w = mundo
        _imovel(w, "P1", "Apartamento", venda=700000)
        a = _lead(w, {"bairro_desejado": "Pinheiros, Vila Madalena", "tipo_imovel": "apartamento", "faixa_preco": "500 mil", "quartos": "2"})
        b = _lead(w, {"bairro_desejado": "pinheiros", "tipo_imovel": "casa", "faixa_preco": "R$ 900 mil", "quartos": "3 quartos"})
        _lead(w, {"bairro_desejado": "Pinheiros e Itaim", "tipo_imovel": "apartamento", "faixa_preco": "700 mil", "quartos": "2"})
        _visita(w, a, "P1")
        _visita(w, b, "P1")
        d = admin(operacao="compra", mes=MES, aba="bairros").json()["data"]
        assert d["top_bairros"][0] == {"bairro": "Pinheiros", "leads": 3}
        assert {x["bairro"] for x in d["top_bairros"]} == {"Pinheiros", "Vila Madalena", "Itaim"}
        assert d["bairros_disponiveis"] == ["Itaim", "Pinheiros", "Vila Madalena"]
        p = d["desempenho"]
        assert p["bairro"] == "Pinheiros" and p["mediana_preco"] == 700000.0 and p["melhor_quartos"] == 2
        assert p["pct_por_tipo"] == [{"tipo": "Apartamento", "pct": 66.7}, {"tipo": "Casa", "pct": 33.3}]
        assert p["mais_buscados"] == [{"codigo": "P1", "tipo": "Apartamento", "preco": 700000.0, "leads": 2}]
        v = admin(operacao="compra", mes=MES, aba="bairros", bairro="Itaim").json()["data"]["desempenho"]
        assert v["bairro"] == "Itaim" and v["mais_buscados"] == []
        assert admin(operacao="compra", mes=MES, aba="bairros", bairro="Inexistente").json()["data"]["desempenho"] is None

    def test_empty(self, admin):
        d = admin(operacao="compra", mes=MES, aba="bairros").json()["data"]
        assert d["top_bairros"] == [] and d["desempenho"] is None


class TestAcesso:
    def test_org_isolation(self, mundo, admin):
        w = mundo
        _lead(w, {"tipo_imovel": "casa"}, org=OTHER_ORG_ID)
        _imovel(w, "O1", "Casa", org=OTHER_ORG_ID)
        d = admin(operacao="compra", mes=MES, aba="imoveis").json()["data"]
        assert d["total_leads"] == 0 and d["tipos"] == []

    def test_member_sees_only_own_contatos(self, mundo, override_settings_factory):
        w = mundo
        _lead(w, {"tipo_imovel": "casa"}, responsavel=TEST_USER_ID)
        _lead(w, {"tipo_imovel": "casa"}, responsavel=OUTRO_USER)
        _lead(w, {"tipo_imovel": "casa"})  # unassigned -> the connection owner's (OWNER_ID), not this member
        gen = _scene(override_settings_factory, w, "member")
        get = next(gen)
        assert get(operacao="compra", mes=MES, aba="imoveis").json()["data"]["total_leads"] == 1
        gen.close()

    def test_owner_sees_all(self, mundo, admin):
        for _ in range(3):
            _lead(mundo, {}, responsavel=OUTRO_USER)
        assert admin(operacao="compra", mes=MES, aba="imoveis").json()["data"]["total_leads"] == 3


class TestAuth:
    def test_no_token_is_401(self, admin):
        from app.main import app
        assert TestClient(app).get(URL, params={"operacao": "compra", "mes": MES, "aba": "imoveis"}).status_code == 401
