"""Lais wave 1 -- Conhecimento (lais-build-contract section 3): routes, optimistic lock, golden
render, contexto provider, recesso first-turn message, endereco_iptu switch on the tools route.

Auth tests assert strict `== 401` / `== 403`. No personal data in fixtures."""
from __future__ import annotations

from datetime import date, datetime, timezone
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient

from noctusai_lib.testing import (
    TEST_USER_ID,
    MockSupabaseClient,
    MockUser,
    MockUserResponse,
    bind_consent_module_to_mock,
)

from app.services import lais_conhecimento_service as svc
from app.services import lais_contexto_service as ctxsvc

URL = "/api/lais/conhecimento"
ORG = "test-org-123"
GOLDEN = Path(__file__).resolve().parent / "golden" / "lais_conhecimento.md"


def _client_for(org_role):
    mock_sb = MockSupabaseClient()
    mock_sb.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG, org_role=org_role)))
    mock_sb.set_table_data("noctus_users", [{"id": TEST_USER_ID, "org_id": ORG, "org_role": org_role}])
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=mock_sb),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=mock_sb),
    ):
        from app.dependencies import get_scoped_admin_client
        from app.main import app

        bind_consent_module_to_mock(mock_sb)
        c = TestClient(app, raise_server_exceptions=True)
        c.sw = get_scoped_admin_client("social_wiring")
        yield c


@pytest.fixture
def admin():
    yield from _client_for("owner")


@pytest.fixture
def member():
    yield from _client_for(None)


def _h():
    return {"Authorization": "Bearer test-token"}


# one valid `dados` per section (exercises every field of the contract table)
DOCS = {"pessoais": ["RG", "CPF"], "renda": ["Contra-cheque"], "endereco": ["Conta de luz"], "adicionais": ""}
VALIDOS = {
    "politicas": {"assinatura": "digital", "chaves": "outro", "chaves_outro": "Retirar na portaria"},
    "telefones": [{"setor": "Vendas", "telefone": "5511900000001", "principal": True},
                  {"setor": "Locação", "telefone": "5511900000002", "principal": False}],
    "exibir_atendente": {"ativo": True},
    "recesso": {"ativo": True, "inicio": "2026-12-20", "fim": "2027-01-05", "mensagem": "Voltamos em janeiro."},
    "venda_info": {"atende": True, "nomenclatura_corretor": "Consultor"},
    "venda_documentos": DOCS,
    "venda_financiamento": {"acompanha": True, "servicos": ["despachantes", "bancos"], "custos": ["Taxa de engenharia"],
                            "detalhes": "Parceria com dois bancos."},
    "locacao_info": {"atende": True, "nomenclatura_corretor": "Locador"},
    "locacao_documentos": {**DOCS, "endereco": ["Conta de luz", "Matrícula"]},
    "locacao_processo": {"prazo_residencial": [12, 30], "prazo_comercial": [60], "multa": "tres_alugueis",
                         "isencao": "mediante_proposta"},
    "locacao_garantias": {
        "caucao": {"aceita": True, "oferecer": True, "min_alugueis": 3},
        "seguro_fianca": {"aceita": True, "oferecer": False, "seguradoras": ["Seguradora A"]},
        "fiador": {"aceita": True, "oferecer": False, "nome_limpo": True, "imovel_quitado": True, "localizacao": "mesma_cidade"},
        "titulo": {"aceita": True, "oferecer": False, "alugueis": "até 12", "inclui_encargos": True},
        "outras": {"aceita": True, "opcoes": ["Fiança bancária"], "sem_garantia": True},
    },
    "perfil_whatsapp": {"nome_exibicao": "Julia", "descricao": "Ajudo você a comprar ou alugar.", "sobre": "Disponível 24h",
                        "endereco": "Rua Exemplo, 1", "email": "contato@exemplo.test", "site": "https://exemplo.test",
                        "link_imovel": "{site}/imovel/{codigo}"},
    "endereco_iptu": {"endereco_completo": True, "usar_iptu": True},
}


class TestAuth:
    def test_get_without_token_is_exactly_401(self, admin):
        assert admin.get(URL).status_code == 401

    def test_preview_without_token_is_exactly_401(self, admin):
        assert admin.get(f"{URL}/preview").status_code == 401

    def test_put_without_token_is_exactly_401(self, admin):
        assert admin.put(f"{URL}/politicas", json={"dados": {}, "versao": 0}).status_code == 401

    def test_member_can_read(self, member):
        assert member.get(URL, headers=_h()).status_code == 200
        assert member.get(f"{URL}/preview", headers=_h()).status_code == 200

    def test_member_write_is_exactly_403_and_nothing_is_stored(self, member):
        r = member.put(f"{URL}/endereco_iptu", json={"dados": VALIDOS["endereco_iptu"], "versao": 0}, headers=_h())
        assert r.status_code == 403
        assert member.sw.table(svc.TABLE).select("*").execute().data == []


class TestRoundTrip:
    def test_never_saved_returns_defaults_for_every_section(self, admin):
        d = admin.get(URL, headers=_h()).json()["data"]
        assert set(d["secoes"]) == set(svc.SECOES)
        assert all(v["versao"] == 0 and v["updated_at"] is None for v in d["secoes"].values())
        assert d["secoes"]["telefones"]["dados"] == []
        assert d["secoes"]["endereco_iptu"]["dados"] == {"endereco_completo": False, "usar_iptu": False}
        assert d["preview_md"] == "" and len(d["hash"]) == 64

    @pytest.mark.parametrize("secao", svc.SECOES)
    def test_each_section_saves_and_reads_back(self, admin, secao):
        r = admin.put(f"{URL}/{secao}", json={"dados": VALIDOS[secao], "versao": 0}, headers=_h())
        assert r.status_code == 200, r.text
        data = r.json()["data"]
        assert data["secao"] == secao and data["versao"] == 1 and data["dados"] == VALIDOS[secao]
        lido = admin.get(URL, headers=_h()).json()["data"]["secoes"][secao]
        assert lido["dados"] == VALIDOS[secao] and lido["versao"] == 1 and lido["updated_at"]

    def test_perfil_nome_exibicao_is_read_only(self, admin):
        corpo = {**VALIDOS["perfil_whatsapp"], "nome_exibicao": "Outro Nome"}
        r = admin.put(f"{URL}/perfil_whatsapp", json={"dados": corpo, "versao": 0}, headers=_h())
        assert r.status_code == 200 and r.json()["data"]["dados"]["nome_exibicao"] == "Julia"


class TestOptimisticLock:
    def test_stale_versao_is_409_versao_conflito_and_changes_nothing(self, admin):
        u = f"{URL}/politicas"
        assert admin.put(u, json={"dados": {"assinatura": "digital"}, "versao": 0}, headers=_h()).status_code == 200
        assert admin.put(u, json={"dados": {"assinatura": "fisico"}, "versao": 1}, headers=_h()).json()["data"]["versao"] == 2
        r = admin.put(u, json={"dados": {"assinatura": "digital_fisico"}, "versao": 1}, headers=_h())
        assert r.status_code == 409
        assert r.json()["error"]["code"] == "versao_conflito" and r.json()["error"]["details"]["versao_atual"] == 2
        assert admin.get(URL, headers=_h()).json()["data"]["secoes"]["politicas"]["dados"]["assinatura"] == "fisico"

    def test_first_save_with_a_nonzero_versao_is_409(self, admin):
        r = admin.put(f"{URL}/politicas", json={"dados": {}, "versao": 3}, headers=_h())
        assert r.status_code == 409 and r.json()["error"]["code"] == "versao_conflito"

    def test_second_first_save_loses(self, admin):
        u = f"{URL}/exibir_atendente"
        assert admin.put(u, json={"dados": {"ativo": True}, "versao": 0}, headers=_h()).status_code == 200
        assert admin.put(u, json={"dados": {"ativo": False}, "versao": 0}, headers=_h()).status_code == 409


class TestValidation:
    def test_unknown_section_is_422_secao_invalida(self, admin):
        r = admin.put(f"{URL}/nao_existe", json={"dados": {}, "versao": 0}, headers=_h())
        assert r.status_code == 422 and r.json()["error"]["code"] == "secao_invalida"

    @pytest.mark.parametrize("secao,dados", [
        ("politicas", {"assinatura": "carta"}),
        ("politicas", {"assinatura": "digital", "extra": 1}),                       # forbid
        ("politicas", {"assinatura": "digital", "chaves_outro": "x"}),             # outro text without outro
        ("telefones", [{"setor": "A", "telefone": "5511900000001", "principal": False}]),   # no principal
        ("telefones", [{"setor": "A", "telefone": "abc", "principal": True}]),
        ("telefones", [{"setor": f"S{i}", "telefone": "5511900000001", "principal": i == 0} for i in range(11)]),
        ("recesso", {"ativo": True}),                                                # active needs a period
        ("recesso", {"ativo": False, "inicio": "2026-12-20", "fim": "2026-12-01"}),
        ("recesso", {"ativo": False, "mensagem": "x" * 501}),
        ("venda_info", {"atende": True, "nomenclatura_corretor": "x" * 41}),
        ("venda_financiamento", {"servicos": ["tarot"]}),
        ("locacao_processo", {"prazo_residencial": [13]}),
        ("locacao_processo", {"multa": "metade"}),
        ("locacao_garantias", {"fiador": {"localizacao": "mesmo_pais"}}),
        ("perfil_whatsapp", {"sobre": "x" * 140}),
        ("perfil_whatsapp", {"email": "sem-arroba"}),
        ("perfil_whatsapp", {"link_imovel": "{site}/imovel/"}),
        ("endereco_iptu", {"endereco_completo": "talvez"}),
        ("endereco_iptu", []),
    ])
    def test_bad_dados_is_422_invalid_field(self, admin, secao, dados):
        r = admin.put(f"{URL}/{secao}", json={"dados": dados, "versao": 0}, headers=_h())
        assert r.status_code == 422 and r.json()["error"]["code"] == "invalid_field", r.text
        assert admin.sw.table(svc.TABLE).select("*").execute().data == []

    def test_body_with_unknown_field_is_422(self, admin):
        assert admin.put(f"{URL}/politicas", json={"dados": {}, "versao": 0, "x": 1}, headers=_h()).status_code == 422


def _seed_all(client, org=ORG) -> None:
    for secao in svc.SECOES:
        client.table(svc.TABLE).insert({"org_id": str(org), "secao": secao, "dados": svc.validar(secao, VALIDOS[secao]), "versao": 1}).execute()


class TestRender:
    def test_golden(self):
        db = MockSupabaseClient()
        _seed_all(db)
        md = svc.render_md(db, ORG, hoje=date(2026, 12, 25))
        if not GOLDEN.exists():  # pragma: no cover -- first run authors it; reviewed in the diff
            GOLDEN.parent.mkdir(exist_ok=True)
            GOLDEN.write_text(md + "\n", encoding="utf-8")
        assert md + "\n" == GOLDEN.read_text(encoding="utf-8")

    def test_deterministic_and_hash_changes_with_content(self):
        db = MockSupabaseClient()
        _seed_all(db)
        a, b = svc.render_md(db, ORG, hoje=date(2026, 1, 1)), svc.render_md(db, ORG, hoje=date(2026, 1, 1))
        assert a == b and svc.hash_md(a) == svc.hash_md(b)
        db.table(svc.TABLE).update({"dados": svc.validar("venda_info", {"atende": False})}).eq("secao", "venda_info").execute()
        assert svc.hash_md(svc.render_md(db, ORG, hoje=date(2026, 1, 1))) != svc.hash_md(a)

    def test_recesso_notice_only_inside_the_period(self):
        db = MockSupabaseClient()
        _seed_all(db)
        assert "Aviso de recesso" in svc.render_md(db, ORG, hoje=date(2026, 12, 20))
        assert "Aviso de recesso" in svc.render_md(db, ORG, hoje=date(2027, 1, 5))
        assert "Aviso de recesso" not in svc.render_md(db, ORG, hoje=date(2026, 12, 19))
        assert "Aviso de recesso" not in svc.render_md(db, ORG, hoje=date(2027, 1, 6))

    def test_preview_route_matches_the_render(self, admin):
        from app.dependencies import coerce_org_uuid

        org = coerce_org_uuid(ORG)  # the route resolves the org through the same coercion
        _seed_all(admin.sw, org)
        d = admin.get(f"{URL}/preview", headers=_h()).json()["data"]
        assert d["markdown"] and d["markdown"] == svc.render_md(admin.sw, org) and d["hash"] == svc.hash_md(d["markdown"])


class TestContextoProvider:
    def test_registered_at_import_in_the_conhecimento_slot(self):
        assert dict(ctxsvc.PROVIDERS)["conhecimento"] is svc.contexto_provider
        assert [n for n, _ in ctxsvc.PROVIDERS].count("conhecimento") == 1

    def test_montar_carries_the_markdown_and_a_save_changes_the_hash(self):
        db = MockSupabaseClient()
        contato = {"slots": {}, "operacao": None}
        agora = datetime(2026, 6, 1, 12, tzinfo=timezone.utc)
        antes = ctxsvc.montar(db, ORG, contato, agora=agora, ferramentas_habilitadas=False)
        assert antes["conhecimento_md"] == ""
        _seed_all(db)
        depois = ctxsvc.montar(db, ORG, contato, agora=agora, ferramentas_habilitadas=False)
        assert "## Vendas" in depois["conhecimento_md"] and "## Locação" in depois["conhecimento_md"]
        assert depois["hash"] != antes["hash"]


class TestRecessoPrimeiroTurno:
    NOW = datetime(2026, 12, 25, 15, tzinfo=timezone.utc)

    def _db(self):
        db = MockSupabaseClient()
        _seed_all(db)
        return db

    def test_first_turn_inside_the_period_returns_the_org_message(self):
        msg = svc.mensagem_recesso_primeiro_turno(
            self._db(), ORG, {"ultimo_outbound_at": None}, {"iniciada_at": "2026-12-25T14:00:00+00:00"}, agora=self.NOW)
        assert msg == "Voltamos em janeiro."

    def test_a_later_turn_of_the_same_interacao_gets_none(self):
        msg = svc.mensagem_recesso_primeiro_turno(
            self._db(), ORG, {"ultimo_outbound_at": "2026-12-25T14:05:00+00:00"},
            {"iniciada_at": "2026-12-25T14:00:00+00:00"}, agora=self.NOW)
        assert msg is None

    def test_an_outbound_from_a_previous_interacao_does_not_count(self):
        msg = svc.mensagem_recesso_primeiro_turno(
            self._db(), ORG, {"ultimo_outbound_at": "2026-12-01T10:00:00+00:00"},
            {"iniciada_at": "2026-12-25T14:00:00+00:00"}, agora=self.NOW)
        assert msg == "Voltamos em janeiro."

    def test_outside_the_period_or_inactive_gets_none(self):
        args = ({"ultimo_outbound_at": None}, {"iniciada_at": "2026-06-01T14:00:00+00:00"})
        assert svc.mensagem_recesso_primeiro_turno(self._db(), ORG, *args, agora=datetime(2026, 6, 1, 15, tzinfo=timezone.utc)) is None
        db = self._db()
        db.table(svc.TABLE).update({"dados": svc.validar("recesso", {"ativo": False})}).eq("secao", "recesso").execute()
        assert svc.mensagem_recesso_primeiro_turno(db, ORG, *args, agora=self.NOW) is None

    def test_empty_message_falls_back_to_a_default_naming_the_period(self):
        db = self._db()
        db.table(svc.TABLE).update({"dados": svc.validar("recesso", {**VALIDOS["recesso"], "mensagem": ""})}).eq("secao", "recesso").execute()
        msg = svc.mensagem_recesso_primeiro_turno(db, ORG, {}, {"iniciada_at": "2026-12-25T14:00:00+00:00"}, agora=self.NOW)
        assert "20/12/2026" in msg and "05/01/2027" in msg


class TestEnderecoIptuPolicy:
    def test_default_is_withheld(self):
        assert svc.politica_endereco_iptu(MockSupabaseClient(), ORG) == {"endereco_completo": False, "usar_iptu": False}

    def test_saved_policy_is_read(self):
        db = MockSupabaseClient()
        _seed_all(db)
        assert svc.politica_endereco_iptu(db, ORG) == {"endereco_completo": True, "usar_iptu": True}

    def test_detalhes_imovel_honours_the_switch(self):
        from uuid import UUID
        from app.services import lais_ferramentas_service as tools

        org = UUID("00000000-0000-4000-8000-0000000000aa")
        db = MockSupabaseClient()
        db.set_table_data("imoveis", [{
            "org_id": str(org), "codigo": "CA1", "codigo_norm": "CA1", "titulo": "Casa CA1", "categoria": "Casa",
            "status": "Venda", "finalidades": ["venda"], "bairro": "Granja Viana", "cidade": "Cotia", "uf": "SP",
            "valor_venda": 900000, "valor_condominio": 1200, "valor_iptu": 450, "dormitorios": 3, "descricao_web": "x",
            "caracteristicas": [], "exibir_no_site": True, "logradouro": "Rua Teste", "numero": "10",
            "data_atualizacao": "2026-10-01"}])
        antes = tools.detalhes_imovel(db, org, {"codigo": "CA1"})
        assert antes["iptu"] is None and antes["endereco"] == "Granja Viana, Cotia"
        db.table(svc.TABLE).insert({"org_id": str(org), "secao": "endereco_iptu", "versao": 1,
                                    "dados": {"endereco_completo": True, "usar_iptu": True}}).execute()
        depois = tools.detalhes_imovel(db, org, {"codigo": "CA1"})
        assert depois["iptu"] == 450 and depois["endereco"] == "Rua Teste 10, Granja Viana, Cotia"
