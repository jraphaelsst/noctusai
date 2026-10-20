"""``GET /api/agents/catalogo`` -- the tiered agent catalogue (Julia v2 A-RT2; CONTRACT 0.4 visibility tiers).

Strict 401/403 on the boundary, an org-tier response limited to display fields, a platform-admin tier that adds
tool KEYS + versions (audited), One Chat (``runtime='external'``, role operador) listed, and an OpenAPI-shape
test that the org-tier schema carries no instruction-bearing field."""
from __future__ import annotations

import pytest

from app.dependencies import get_auth_context
from app.routers.catalogo_router import CatalogoAgenteAdminOut, CatalogoAgenteOut, get_catalogo_store_dep
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.stores.catalogo import CatalogoEntrada, FakeCatalogoStore
from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.stores.studio_definitions_conteudo import FerramentaInput
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, seed_org_role

URL = "/api/agents/catalogo"

#: Field names that carry instructions / rules / weights / content: none may exist in the ORG-tier schema.
PROIBIDOS = ("descricao", "texto", "regra", "peso", "conteudo")


@pytest.fixture
def cat(agents_client):
    from app.main import app

    store = FakeCatalogoStore([
        CatalogoEntrada("julia", "sdr", "Atende os leads.", ("Atendimento", "Sugestão de imóveis"), 10),
        CatalogoEntrada("one-chat", "operador", "Responde no WhatsApp.", ("Resposta automática",), 20),
        CatalogoEntrada("escondido", "x", "Não listar.", (), 99, visivel=False),
    ])
    studio = FakeStudioDefinitionStore()
    app.dependency_overrides[get_catalogo_store_dep] = lambda: store
    app.dependency_overrides[get_studio_definition_store_dep] = lambda: studio
    agents_client.catalogo, agents_client.studio = store, studio
    # in production the instance row of Julia lives in the same table the legacy store lists
    agents_client.stores.agents._ensure_one(
        DEFAULT_ORG_ID, key="julia", nome="Julia", runtime="llm", owner_product="social-wiring")
    try:
        yield agents_client
    finally:
        app.dependency_overrides.pop(get_catalogo_store_dep, None)
        app.dependency_overrides.pop(get_studio_definition_store_dep, None)


def _julia(cat):
    cat.studio.mark_platform_org(DEFAULT_ORG_ID)
    d = cat.studio.create_studio_agent(
        DEFAULT_ORG_ID, "julia", "Julia", None, runtime="llm", definition_scope="plataforma")
    draft = cat.studio.create_draft(DEFAULT_ORG_ID, d.id, None, d.id)
    cat.studio.replace_ferramentas(DEFAULT_ORG_ID, draft.id, [
        FerramentaInput("handoff", "SEGREDO: descricao da ferramenta", parametros={}),
        FerramentaInput("avaliar_lead", "SEGREDO 2", parametros={}),
    ])
    return d


class TestBoundary:
    def test_unauthenticated_is_401(self, cat):
        assert cat.raw().get(URL).status_code == 401

    def test_a_product_token_is_403_user_required(self, cat):
        from uuid import UUID, uuid4

        from app.main import app

        app.dependency_overrides[get_auth_context] = lambda: AuthContext(
            org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=["agents:channel-status"],
            raw_token="t", api_token_id=uuid4(), principal_agent_id=UUID(int=1), issuer="social-wiring")
        try:
            r = cat.raw().get(URL)
        finally:
            app.dependency_overrides.pop(get_auth_context, None)
        assert r.status_code == 403 and r.json()["code"] == "user_required"

    def test_a_non_member_role_is_403(self, cat):
        seed_org_role(cat, role="customer")
        assert cat.get(URL).status_code == 403

    def test_the_write_is_platform_admin_only(self, cat):
        body = {"papel": "sdr", "descricao_publica": "x", "capacidades": []}
        assert cat.raw().put(f"{URL}/julia", json=body).status_code == 401
        seed_org_role(cat, role="member")
        assert cat.put(f"{URL}/julia", json=body).status_code == 403
        cat.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": "owner", "role": "user"}])
        r = cat.put(f"{URL}/julia", json=body)
        assert r.status_code == 403 and r.json()["code"] == "platform_admin_required"


class TestOrgTier:
    @pytest.mark.parametrize("role", ["member", "viewer", "admin"])
    def test_display_level_fields_only(self, cat, role):
        # an org admin who is NOT a platform admin must still get the org tier
        cat.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": role, "role": "user"}])
        r = cat.get(URL)
        assert r.status_code == 200, r.text
        body = r.json()
        assert [a["key"] for a in body] == ["one-chat", "julia"] or [a["key"] for a in body] == ["julia", "one-chat"]
        for item in body:
            assert set(item) == {"key", "nome", "papel", "descricao_publica", "runtime", "capacidades"}
        por = {a["key"]: a for a in body}
        assert por["one-chat"]["runtime"] == "external" and por["one-chat"]["papel"] == "operador"
        assert por["julia"]["capacidades"] == ["Atendimento", "Sugestão de imóveis"]
        assert "escondido" not in por and "bia" not in por  # a row decides who is listed
        # the order is the catalogue's (julia 10, one-chat 20)
        assert [a["key"] for a in body] == ["julia", "one-chat"]

    def test_julia_is_the_leads_agent_and_one_chat_stays_separate(self, cat):
        cat.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": "member", "role": "user"}])
        por = {a["key"]: a for a in cat.get(URL).json()}
        assert por["julia"]["papel"] == "sdr" and por["one-chat"]["papel"] == "operador"

    def test_the_org_tier_never_sees_tool_keys_or_versions_even_if_the_store_has_them(self, cat):
        _julia(cat)
        cat.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": "owner", "role": "user"}])
        raw = cat.get(URL).text
        assert "SEGREDO" not in raw and "handoff" not in raw and "ferramentas" not in raw and "versoes" not in raw


class TestPlatformAdminTier:
    def test_adds_tool_keys_and_versions_never_descriptions_and_audits_the_read(self, cat):
        d = _julia(cat)
        seed_org_role(cat, role="owner")  # owner/admin are platform admins in this harness
        r = cat.get(URL)
        assert r.status_code == 200, r.text
        por = {a["key"]: a for a in r.json()}
        assert por["julia"]["versoes"] == [{"versao": 1, "status": "rascunho"}] and por["julia"]["versao_ativa"] is None
        # no active version yet -> no tool keys; publish-less draft is not "what runs"
        assert por["julia"]["ferramentas"] == []
        assert por["one-chat"]["ferramentas"] == [] and por["one-chat"]["versoes"] == []
        assert "SEGREDO" not in r.text
        assert d is not None

    def test_with_an_active_version_the_active_tool_keys_are_listed(self, cat):
        d = _julia(cat)
        draft = cat.studio.get_draft(DEFAULT_ORG_ID, d.id)
        from dataclasses import replace

        cat.studio._versions[draft.id] = replace(draft, status="ativa")
        seed_org_role(cat, role="owner")
        por = {a["key"]: a for a in cat.get(URL).json()}
        assert por["julia"]["ferramentas"] == ["avaliar_lead", "handoff"] and por["julia"]["versao_ativa"] == 1
        audit = cat.studio.list_audit_log(DEFAULT_ORG_ID, d.id)
        assert any(a.acao == "definicao_lida" for a in audit)

    def test_put_updates_the_rows_the_org_tier_then_shows(self, cat):
        seed_org_role(cat, role="owner")
        r = cat.put(f"{URL}/julia", json={
            "papel": "sdr", "descricao_publica": "Nova descrição.", "capacidades": ["A", " B ", ""], "ordem": 5})
        assert r.status_code == 204
        cat.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": "member", "role": "user"}])
        julia = next(a for a in cat.get(URL).json() if a["key"] == "julia")
        assert julia["descricao_publica"] == "Nova descrição." and julia["capacidades"] == ["A", "B"]


class TestOpenApiShape:
    def test_the_org_tier_schema_has_no_instruction_bearing_field(self):
        props = set(CatalogoAgenteOut.model_json_schema()["properties"])
        assert props == {"key", "nome", "papel", "descricao_publica", "runtime", "capacidades"}
        # `descricao_publica` is the ONE description-like field and it is a DB row, not an instruction
        for nome in props:
            if nome == "descricao_publica":
                continue
            assert not any(p in nome for p in PROIBIDOS), nome

    def test_the_published_openapi_org_tier_component_carries_no_forbidden_field(self):
        from app.main import app

        schemas = app.openapi()["components"]["schemas"]
        org = schemas["CatalogoAgenteOut"]["properties"]
        assert not [n for n in org if n != "descricao_publica" and any(p in n for p in PROIBIDOS)]
        assert "ferramentas" not in org and "versoes" not in org
        admin = schemas["CatalogoAgenteAdminOut"]["properties"]
        assert {"ferramentas", "versoes", "versao_ativa"} <= set(admin)
        assert not [n for n in admin if n != "descricao_publica" and any(p in n for p in PROIBIDOS)]
        assert CatalogoAgenteAdminOut.model_fields.keys() >= CatalogoAgenteOut.model_fields.keys()
