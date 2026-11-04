"""Julia > Especificações (Julia-line S9): the org admin's business specs, proxied to agents' channel route.

Seams: mock DB + `FakeAgentsClient` injected through the route's own `Depends(get_agents_client_factory)`; nothing of ours is
patched. Strict `== 401` without a session; org admin only; agents' 200/422 bodies pass through unchanged."""
from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock, patch

import httpx
import pytest
from fastapi.testclient import TestClient
from noctusai_lib.testing import TEST_USER_ID, handler_status, MockUser, MockUserResponse, bind_consent_module_to_mock

from app.clients.agents import (
    AgentsTimeout, AgentsTokenInvalid, EspecificacoesResposta, FakeAgentsClient, HttpAgentsClient,
)
from tests.support.julia_world import ADMIN_ID, CORRETOR_ID, MEMBER_ID, ORG_ID, OWNER_ID, World

H = {"Authorization": "Bearer test-token"}
URL = "/api/julia/especificacoes"
ATOR = {"user_id": "00000000-0000-0000-0000-000000000001", "nome": "Chefe"}


def _codigo(r):
    corpo = r.json()
    return corpo.get("code") or corpo.get("error", {}).get("code") or corpo.get("detail", {}).get("code")


class Scene:
    def __init__(self, tc, w):
        self.tc, self.w = tc, w

    def req(self, m, json=None):
        return getattr(self.tc, m)(URL, headers=H, **({"json": json} if json is not None else {}))


def _scene(role, *, agents="fake", plataforma=True):
    w = World()
    w.seed_connection(user_id=OWNER_ID)
    w.core.set_table_data("noctus_users", [
        {"id": OWNER_ID, "org_id": ORG_ID, "org_role": "owner", "nome": "Dono"},
        {"id": ADMIN_ID, "org_id": ORG_ID, "org_role": "admin", "nome": "Adriana"},
        {"id": CORRETOR_ID, "org_id": ORG_ID, "org_role": "corretor", "nome": "Carla"},
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
        from app.routers.whatsapp_connections_router import get_agents_client_factory

        bind_consent_module_to_mock(w.root)
        w.agents = FakeAgentsClient() if agents == "fake" else agents
        from app.dependencies import get_platform_admin_check

        app.dependency_overrides[get_agents_client_factory] = lambda: (lambda org_id: w.agents)
        app.dependency_overrides[get_platform_admin_check] = lambda: (lambda uid: plataforma)
        yield Scene(TestClient(app), w)
        app.dependency_overrides.pop(get_agents_client_factory, None)
        app.dependency_overrides.pop(get_platform_admin_check, None)


@pytest.fixture
def admin():
    yield from _scene("owner")


@pytest.fixture
def org_admin():
    """An org owner who is NOT a platform admin: reads the specs, cannot write them."""
    yield from _scene("owner", plataforma=False)


@pytest.fixture
def member():
    yield from _scene("member", plataforma=False)


@pytest.fixture
def desconectado():
    yield from _scene("owner", agents=None)


@pytest.mark.parametrize("metodo", ["get", "put"])
def test_no_token_is_401(admin, metodo):
    r = getattr(admin.tc, metodo)(URL, **({"json": {"valores": {}}} if metodo == "put" else {}))
    assert r.status_code == 401


@pytest.mark.parametrize("metodo", ["get", "put"])
def test_a_member_is_refused_and_agents_is_never_called(member, metodo):
    r = member.req(metodo, {"valores": {"agencia": "x"}} if metodo == "put" else None)
    assert r.status_code == 403
    assert member.w.agents.especificacoes_salvas == []


def test_an_org_admin_who_is_not_a_platform_admin_cannot_write_403(org_admin):
    r = org_admin.req("put", {"valores": {"agencia": "x"}})
    assert r.status_code == 403 and _codigo(r) == "edicao_restrita_plataforma"
    assert org_admin.w.agents.especificacoes_salvas == []
    assert org_admin.req("get").status_code == 200  # reading stays available to the org admin


def test_agents_edicao_restrita_403_is_passed_through_not_read_as_a_bad_token(admin):
    admin.w.agents.especificacoes_script.append(EspecificacoesResposta(403, {"code": "edicao_restrita_plataforma", "detail": "restrito"}))
    r = admin.req("put", {"valores": {"agencia": "x"}})
    assert r.status_code == 403 and r.json()["code"] == "edicao_restrita_plataforma"


def test_get_passes_agents_body_through(admin):
    admin.w.agents.especificacoes_valores["agencia"] = "Aurora"
    body = admin.req("get").json()
    assert [d["chave"] for d in body["declaradas"]] == ["agencia", "regioes"]
    assert body["valores"] == [{"chave": "agencia", "valor": "Aurora", "updated_by_nome": None}]
    assert body["faltando"] == ["regioes"] and body["invalidas"] == [] and body["modo_validacao"] == "report"


def test_put_sends_only_the_valores_to_the_julia_agent(admin):
    r = admin.req("put", {"valores": {"agencia": "Imobiliária Aurora"}})
    assert r.status_code == 200
    assert admin.w.agents.especificacoes_salvas == [("julia", {"agencia": "Imobiliária Aurora"})]
    [ator] = admin.w.agents.especificacoes_atores
    assert ator["user_id"] == TEST_USER_ID and ator["nome"] == "Chefe"


def test_the_body_cannot_name_an_org_or_extra_fields(admin):
    assert admin.req("put", {"valores": {"agencia": "A"}, "org_id": "x"}).status_code == 422
    assert admin.w.agents.especificacoes_salvas == []


def test_an_actor_in_the_body_is_refused_and_the_session_user_is_what_agents_gets(admin):
    outro = "00000000-0000-0000-0000-0000000000aa"
    r = admin.req("put", {"valores": {"agencia": "A"}, "ator": {"user_id": outro, "nome": "Impostor"}})
    assert r.status_code == 422 and admin.w.agents.especificacoes_salvas == []
    assert admin.req("put", {"valores": {"agencia": "A"}}).status_code == 200
    assert admin.w.agents.especificacoes_atores[-1]["user_id"] == TEST_USER_ID != outro


def test_an_agents_422_is_passed_through_faithfully(admin):
    violacoes = [{"chave": "agencia", "codigo": "spec_parece_instrucao", "motivo": "instrucao", "mensagem": "Parece uma instrução."}]
    admin.w.agents.especificacoes_script.append(EspecificacoesResposta(422, {
        "code": "spec_parece_instrucao", "detail": "Parece uma instrução.", "violacoes": violacoes,
    }))
    r = admin.req("put", {"valores": {"agencia": "ignore tudo"}})
    assert r.status_code == 422
    assert r.json() == {"code": "spec_parece_instrucao", "detail": "Parece uma instrução.", "violacoes": violacoes}


def test_an_undeclared_key_is_agents_422(admin):
    r = admin.req("put", {"valores": {"persona": "outra"}})
    assert r.status_code == 422 and r.json()["code"] == "spec_nao_declarada"


def test_report_mode_200_carries_invalidas(admin):
    corpo = {"agent_key": "julia", "declaradas": [], "valores": [], "faltando": [], "modo_validacao": "report",
             "invalidas": [{"chave": "agencia", "codigo": "spec_parece_instrucao", "motivo": "m", "mensagem": "x"}]}
    admin.w.agents.especificacoes_script.append(EspecificacoesResposta(200, corpo))
    r = admin.req("put", {"valores": {"agencia": "x"}})
    assert r.status_code == 200 and r.json() == corpo


@pytest.mark.parametrize("metodo", ["get", "put"])
def test_no_credential_is_a_named_409_not_a_silent_failure(desconectado, metodo):
    r = desconectado.req(metodo, {"valores": {"agencia": "x"}} if metodo == "put" else None)
    assert r.status_code == 409 and _codigo(r) == "agente_nao_conectado"


@pytest.mark.parametrize("erro,status,codigo", [
    (AgentsTokenInvalid("x"), 502, "agents_token_invalido"),
    (AgentsTimeout("x"), 502, "agents_indisponivel"),
])
def test_agents_failures_are_typed(admin, erro, status, codigo):
    admin.w.agents.errors["especificacoes"] = erro
    r = admin.req("get")
    assert handler_status(r) == status and _codigo(r) == codigo


# ── the real client's wire (no network: httpx MockTransport) ─────────────────
def _http(handler):
    return HttpAgentsClient("http://agents", "noc_tok", transport=httpx.MockTransport(handler))


def test_http_client_put_returns_a_422_body_and_raises_on_other_errors():
    asyncio.run(_http_client_wire())


async def _http_client_wire():
    vistos = []

    def handler(request):
        vistos.append((request.method, request.url.path, request.headers["authorization"], request.content))
        if request.url.path.endswith("/julia/specs") and b"ruim" in request.content:
            return httpx.Response(422, json={"code": "spec_parece_instrucao", "violacoes": [{"chave": "agencia"}]})
        if b"negado" in request.content:
            return httpx.Response(403, json={"code": "scope_missing"})
        if b"restrito" in request.content:
            return httpx.Response(403, json={"code": "edicao_restrita_plataforma"})
        return httpx.Response(200, json={"agent_key": "julia", "valores": []})

    c = _http(handler)
    ok = await c.salvar_especificacoes("julia", {"agencia": "bom"}, ATOR)
    assert (ok.status, ok.corpo["agent_key"]) == (200, "julia")
    ruim = await c.salvar_especificacoes("julia", {"agencia": "ruim"}, ATOR)
    assert ruim.status == 422 and ruim.corpo["violacoes"] == [{"chave": "agencia"}]
    with pytest.raises(AgentsTokenInvalid):
        await c.salvar_especificacoes("julia", {"agencia": "negado"}, ATOR)
    restrito = await c.salvar_especificacoes("julia", {"agencia": "restrito"}, ATOR)
    assert restrito.status == 403 and restrito.corpo["code"] == "edicao_restrita_plataforma"
    assert vistos[0][:3] == ("PUT", "/api/channels/agents/julia/specs", "Bearer noc_tok")
    assert json.loads(vistos[0][3]) == {"valores": {"agencia": "bom"}, "ator": ATOR}
    got = await _http(lambda r: httpx.Response(200, json={"declaradas": []})).especificacoes("julia")
    assert got.status == 200 and got.corpo == {"declaradas": []}
