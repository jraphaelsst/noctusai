"""Julia > Contatos por setor + Conhecimento editor (Lais study, owner decisions 2026-11-17).

Seams: mock DB + `FakeAgentsClient` injected through the routes' own `Depends(get_agents_client_factory)` (same scene as
`test_julia_especificacoes`); nothing of ours is patched. Auth: strict `== 401` without a session, `== 403` for a member (and,
for the knowledge PUT, for an org admin who is not a platform admin). No real personal data: numbers are fictitious."""
from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import EspecificacoesResposta, FakeAgentsClient
from app.services import julia_contatos_setoriais_service as setoriais
from app.services import julia_conhecimento_specs_service as conhec
from tests.support.julia_world import ADMIN_ID, MEMBER_ID, ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
CONTATOS = "/api/julia/contatos-setoriais"
CONHEC = "/api/julia/conhecimento-editor"
DONO_FONE = "+5511900000001"


class Scene:
    def __init__(self, tc, w):
        self.tc, self.w = tc, w

    def req(self, m, url, body=None):
        return getattr(self.tc, m)(url, headers=H, **({"json": body} if body is not None else {}))

    def eventos(self, tipo="configuracao_alterada"):
        return [e for e in self.w.rows("julia_eventos") if e["tipo"] == tipo]


def _scene(role, *, plataforma=True, dono_fone=DONO_FONE, agents="fake"):
    w = World()
    w.seed_connection(user_id=OWNER_ID)
    w.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Dono Exemplo", "telefone": dono_fone},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin", "nome": "Adriana"},
        {"id": TEST_USER_ID, "org_id": ORG_ID, "org_role": role, "nome": "Chefe"},
        {"id": MEMBER_ID, "org_id": ORG_ID, "org_role": "member", "nome": "Marcos"},
    ])
    w.root.auth.get_user = MagicMock(return_value=MockUserResponse(MockUser(org_id=ORG_ID, org_role=role)))
    with (
        patch("noctusai_seed.database.DatabaseModule.get_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_core_client", return_value=w.root),
        patch("noctusai_seed.database.DatabaseModule.get_admin_client", return_value=w.admin),
    ):
        from app.main import app
        from app.dependencies import get_platform_admin_check
        from app.routers.julia_conhecimento_editor_router import get_conhecimento_editor_client
        from app.routers.julia_contatos_setoriais_router import get_contatos_setoriais_client
        from app.routers.whatsapp_connections_router import get_agents_client_factory

        bind_consent_module_to_mock(w.root)
        w.agents = FakeAgentsClient() if agents == "fake" else agents
        if w.agents is not None:
            w.agents.especificacoes_declaradas.update({
                setoriais.SPEC_CHAVE: "contatos", "conhecimento_venda": "texto_longo",
                "conhecimento_locacao": "texto_longo", "conhecimento_politicas": "texto_longo",
            })
        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: w.agents)
        app.dependency_overrides[get_platform_admin_check] = lambda: (lambda uid: plataforma)
        app.dependency_overrides[get_contatos_setoriais_client] = lambda: w.sw
        app.dependency_overrides[get_conhecimento_editor_client] = lambda: w.sw
        yield Scene(TestClient(app), w)
        for dep in (get_agents_client_factory, get_platform_admin_check, get_contatos_setoriais_client, get_conhecimento_editor_client):
            app.dependency_overrides.pop(dep, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def org_admin():
    """An org owner who is NOT a platform admin."""
    yield from _scene("owner", plataforma=False)


@pytest.fixture
def member():
    yield from _scene("member", plataforma=False)


@pytest.fixture
def desconectado():
    yield from _scene("owner", agents=None)


def _contato(**over):
    return {"setor": "juridico", "finalidade": "Dúvidas jurídicas e contratos", "nome": "Dra. Exemplo", "telefone": "(11) 98888-7777", **over}


# ── auth (strict) ──────────────────────────────────────────────────────────────────
@pytest.mark.parametrize("url,metodo,corpo", [
    (CONTATOS, "get", None), (CONTATOS, "put", {"contatos": []}),
    (CONHEC, "get", None), (CONHEC, "put", {"valores": {"conhecimento_venda": "x"}}),
])
def test_no_session_is_exactly_401(admin, url, metodo, corpo):
    r = getattr(admin.tc, metodo)(url, **({"json": corpo} if corpo is not None else {}))
    assert r.status_code == 401


@pytest.mark.parametrize("url,metodo,corpo", [
    (CONTATOS, "get", None), (CONTATOS, "put", {"contatos": [_contato()]}),
    (CONHEC, "get", None), (CONHEC, "put", {"valores": {"conhecimento_venda": "x"}}),
])
def test_a_member_is_exactly_403_and_agents_is_never_written(member, url, metodo, corpo):
    r = member.req(metodo, url, corpo)
    assert r.status_code == 403
    assert member.w.agents.especificacoes_salvas == [] and member.eventos() == []


# ── sector contacts ─────────────────────────────────────────────────────────────────
class TestContatosSetoriais:
    def test_get_derives_the_owner_from_the_profile_and_lists_nothing_else(self, admin):
        d = admin.req("get", CONTATOS).json()["data"]
        assert d["dono"]["telefone"] == DONO_FONE and d["dono"]["nome"] == "Dono Exemplo" and d["dono"]["origem"] == "perfil"
        assert d["contatos"] == [] and d["legado"] == [] and d["declarada"] is True
        assert "juridico" in d["setores"] and d["maximo"] == 10

    def test_an_owner_without_a_number_yields_no_derived_entry(self):
        for s in _scene("owner", dono_fone=None):
            assert s.req("get", CONTATOS).json()["data"]["dono"] is None

    def test_put_writes_only_the_contatos_oficiais_spec_owner_first_with_e164_phones(self, admin):
        r = admin.req("put", CONTATOS, {"contatos": [_contato()]})
        assert r.status_code == 200
        [(chave_agente, valores)] = admin.w.agents.especificacoes_salvas
        assert chave_agente == "julia" and set(valores) == {setoriais.SPEC_CHAVE}
        lista = json.loads(valores[setoriais.SPEC_CHAVE])
        assert [c["telefone"] for c in lista] == [DONO_FONE, "+5511988887777"]
        assert lista[0]["setor"] == setoriais.SETOR_DONO and lista[1]["setor"] == "juridico"
        corpo = r.json()["data"]
        assert [c["telefone"] for c in corpo["contatos"]] == ["+5511988887777"] and corpo["dono"]["telefone"] == DONO_FONE
        [ator] = admin.w.agents.especificacoes_atores
        assert ator["user_id"] == TEST_USER_ID

    def test_get_after_put_round_trips_without_duplicating_the_owner(self, admin):
        admin.req("put", CONTATOS, {"contatos": [_contato()]})
        d = admin.req("get", CONTATOS).json()["data"]
        assert [c["nome"] for c in d["contatos"]] == ["Dra. Exemplo"] and d["dono"]["nome"] == "Dono Exemplo"

    def test_each_save_records_one_measurable_event_without_names_or_numbers(self, admin):
        admin.req("put", CONTATOS, {"contatos": [_contato()]})
        [ev] = admin.eventos()
        assert ev["payload"] == {"area": "contatos_setoriais", "chaves": ["contatos_oficiais"], "total": 2, "com_dono": True, "ator": TEST_USER_ID}
        assert "98888" not in json.dumps(ev) and "Dra." not in json.dumps(ev)

    def test_saving_an_empty_list_keeps_only_the_owner(self, admin):
        admin.req("put", CONTATOS, {"contatos": []})
        [(_, valores)] = admin.w.agents.especificacoes_salvas
        assert [c["telefone"] for c in json.loads(valores[setoriais.SPEC_CHAVE])] == [DONO_FONE]

    @pytest.mark.parametrize("over,codigo", [
        ({"telefone": "abc"}, "telefone_invalido"), ({"telefone": "123"}, "telefone_invalido"),
        ({"setor": "vendas"}, "setor_invalido"), ({"setor": ""}, "setor_invalido"),
        ({"finalidade": "ab"}, "finalidade_invalida"), ({"nome": "  "}, "nome_invalido"),
        ({"setor": setoriais.SETOR_DONO, "finalidade": setoriais.FINALIDADE_DONO}, "finalidade_reservada"),
    ])
    def test_an_invalid_entry_is_422_with_a_typed_code_and_nothing_is_saved(self, admin, over, codigo):
        r = admin.req("put", CONTATOS, {"contatos": [_contato(**over)]})
        assert r.status_code == 422 and r.json()["error"]["code"] == codigo
        assert admin.w.agents.especificacoes_salvas == [] and admin.eventos() == []

    def test_a_duplicate_phone_and_an_overflow_are_422(self, admin):
        assert admin.req("put", CONTATOS, {"contatos": [_contato(), _contato(nome="Outra")]}).json()["error"]["code"] == "telefone_duplicado"
        muitos = [_contato(telefone=f"(11) 9{i:04d}-0000") for i in range(10)]
        assert admin.req("put", CONTATOS, {"contatos": muitos}).json()["error"]["code"] == "contatos_excede"

    def test_the_body_cannot_name_another_spec_an_org_or_an_actor(self, admin):
        for corpo in ({"contatos": [], "valores": {"agencia": "x"}}, {"contatos": [], "org_id": "x"}, {"contatos": [], "ator": {"user_id": "z"}}):
            assert admin.req("put", CONTATOS, corpo).status_code == 422
        assert admin.w.agents.especificacoes_salvas == []

    def test_a_member_cannot_save_contacts_403_before_any_call_to_agents(self, member):
        r = member.req("put", CONTATOS, {"contatos": [_contato()]})
        assert r.status_code == 403 and member.w.agents.especificacoes_salvas == [] and member.eventos() == []

    def test_the_acting_user_and_role_reach_agents(self, org_admin):
        assert org_admin.req("put", CONTATOS, {"contatos": [_contato()]}).status_code == 200
        assert org_admin.w.agents.especificacoes_atores[-1]["papel"] == "admin"

    def test_a_legacy_comma_value_is_shown_not_dropped(self, admin):
        admin.w.agents.especificacoes_valores[setoriais.SPEC_CHAVE] = "+5511911112222, +5511933334444"
        d = admin.req("get", CONTATOS).json()["data"]
        assert d["legado"] == ["+5511911112222", "+5511933334444"] and d["contatos"] == []

    def test_a_key_agents_does_not_declare_yet_is_reported_not_hidden(self, admin):
        admin.w.agents.especificacoes_declaradas.pop(setoriais.SPEC_CHAVE)
        assert admin.req("get", CONTATOS).json()["data"]["declarada"] is False

    def test_not_connected_is_409(self, desconectado):
        assert desconectado.req("get", CONTATOS).status_code == 409


# ── knowledge editor ────────────────────────────────────────────────────────────────
class TestConhecimentoEditor:
    def test_get_lists_the_three_keys_with_values_and_a_legacy_suggestion(self, admin):
        admin.w.agents.especificacoes_valores["conhecimento_venda"] = "Aceitamos financiamento."
        d = admin.req("get", CONHEC).json()["data"]
        assert [i["chave"] for i in d["itens"]] == list(conhec.CHAVES) and d["max_chars"] == 4000
        venda = d["itens"][0]
        assert venda["valor"] == "Aceitamos financiamento." and venda["declarada"] is True

    def test_member_reads_nothing_and_cannot_write_knowledge_403(self, member):
        r = member.req("put", CONHEC, {"valores": {"conhecimento_venda": "x"}})
        assert r.status_code == 403 and member.w.agents.especificacoes_salvas == []

    def test_org_admin_who_is_not_a_platform_admin_writes_knowledge(self, org_admin):
        r = org_admin.req("put", CONHEC, {"valores": {"conhecimento_venda": "x"}})
        assert r.status_code == 200 and org_admin.w.agents.especificacoes_atores[-1]["papel"] == "admin"

    def test_org_admin_writes_only_the_three_keys_and_records_an_event_without_text(self, admin):
        r = admin.req("put", CONHEC, {"valores": {"conhecimento_venda": " Texto de vendas. ", "conhecimento_politicas": ""}})
        assert r.status_code == 200
        assert admin.w.agents.especificacoes_salvas == [("julia", {"conhecimento_venda": "Texto de vendas.", "conhecimento_politicas": ""})]
        [ev] = admin.eventos()
        assert ev["payload"]["area"] == "conhecimento" and ev["payload"]["chaves"] == ["conhecimento_politicas", "conhecimento_venda"]
        assert "Texto de vendas" not in json.dumps(ev)

    @pytest.mark.parametrize("valores,codigo", [
        ({"agencia": "x"}, "chave_invalida"), ({}, "sem_alteracao"), ({"conhecimento_venda": "x" * 4001}, "texto_longo_demais"),
    ])
    def test_a_foreign_key_empty_body_or_oversized_text_is_422(self, admin, valores, codigo):
        r = admin.req("put", CONHEC, {"valores": valores})
        assert r.status_code == 422 and r.json()["error"]["code"] == codigo and admin.w.agents.especificacoes_salvas == []

    def test_agents_refusal_is_passed_as_a_typed_422(self, admin):
        admin.w.agents.especificacoes_script.append(EspecificacoesResposta(422, {"code": "spec_nao_declarada", "detail": "não declarada"}))
        r = admin.req("put", CONHEC, {"valores": {"conhecimento_venda": "x"}})
        assert r.status_code == 422 and r.json()["error"]["code"] == "spec_nao_declarada" and admin.eventos() == []


class TestDividirPorChave:
    def test_splits_the_legacy_markdown_into_the_three_keys(self):
        md = "## Aviso de recesso\nx\n\n## Informações gerais\n- a\n\n## Vendas\n- v\n\n## Locação\n- l"
        out = conhec.dividir_por_chave(md)
        assert set(out) == set(conhec.CHAVES)
        assert out["conhecimento_politicas"].count("##") == 2 and out["conhecimento_venda"].startswith("## Vendas")

    def test_empty_markdown_yields_nothing(self):
        assert conhec.dividir_por_chave("") == {}
