"""agents-unified CONTRACT §2-§5: the agent model schema, the unified listing / painel, the superadmin-only
internals (D31: 404, never 403, for everyone else), and the de-pinned legacy routes (persona by key)."""
from __future__ import annotations

import pytest

from app.routers.catalogo_router import get_catalogo_store_dep
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.schemas.studio_conteudo import FerramentaIn
from app.stores.catalogo import CatalogoEntrada, FakeCatalogoStore
from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.stores.studio_geracoes import AREAS
from app.studio.modelo import AREA_ROTULOS, PASSOS_ASSISTENTE, SECOES_PAGINA
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID, seed_org_role

MODELO = "/api/studio/modelo"
LISTA = "/api/agents/painel"
WIZARD = ["identidade", "papel", "personalidade", "conhecimento", "ferramentas", "canais", "regras", "rotinas",
          "revisao", "publicar"]


@pytest.fixture
def casa(agents_client):
    from app.main import app

    studio = FakeStudioDefinitionStore()
    catalogo = FakeCatalogoStore([CatalogoEntrada("one-chat", "operador", "Responde no WhatsApp.", ("Resposta",), 20)])
    app.dependency_overrides[get_studio_definition_store_dep] = lambda: studio
    app.dependency_overrides[get_catalogo_store_dep] = lambda: catalogo
    # an org Studio agent (pre-v2 content) and the org's instance of a platform definition
    studio.seed_agent(DEFAULT_ORG_ID, "isaia", nome="IsaIA")
    studio.seed_agent(DEFAULT_ORG_ID, "julia", nome="Julia", definition_scope="instancia", conteudo_modo="linhas",
                      runtime="llm", owner_product="social-wiring")
    # the pre-cutover code-defined chat agent (still a prod row until the Renata runbook retires it)
    agents_client.stores.agents.seed_legacy_chat_agent(DEFAULT_ORG_ID)
    agents_client.studio = studio
    try:
        yield agents_client
    finally:
        app.dependency_overrides.pop(get_studio_definition_store_dep, None)
        app.dependency_overrides.pop(get_catalogo_store_dep, None)


def _papel(client, *, org_role: str, platform: bool) -> None:
    client.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": org_role,
        "role": "admin" if platform else "user"}])


class TestBoundary:
    @pytest.mark.parametrize("url", [MODELO, LISTA, "/api/agents/bia/painel", "/api/agents/bia/painel/interno"])
    def test_unauthenticated_is_401(self, casa, url):
        assert casa.raw().get(url).status_code == 401

    @pytest.mark.parametrize("url", [MODELO, LISTA, "/api/agents/bia/painel"])
    def test_a_non_member_role_is_403(self, casa, url):
        seed_org_role(casa, role="customer")
        assert casa.get(url).status_code == 403

    def test_an_unknown_agent_is_404(self, casa):
        seed_org_role(casa, role="member")
        r = casa.get("/api/agents/nao-existe/painel")
        assert r.status_code == 404 and r.json()["code"] == "agent_not_found"


class TestInternalsAreSuperadminOnly:
    """D31: internals 404 (not 403) for anyone but a NoctusAI superadmin, including an org owner."""

    @pytest.mark.parametrize("org_role", ["member", "viewer", "admin", "owner"])
    @pytest.mark.parametrize("key", ["isaia", "julia", "bia"])
    def test_non_superadmin_gets_404(self, casa, org_role, key):
        _papel(casa, org_role=org_role, platform=False)
        r = casa.get(f"/api/agents/{key}/painel/interno")
        assert r.status_code == 404
        assert r.json()["code"] == "agent_not_found"

    def test_superadmin_reads_them_and_the_read_is_audited(self, casa):
        _papel(casa, org_role="owner", platform=True)
        r = casa.get("/api/agents/isaia/painel/interno")
        assert r.status_code == 200, r.text
        assert r.json()["origem"] == "org" and r.json()["definition_scope"] == "org"
        audit = [a for a in casa.studio.audit_log_all() if a.acao == "definicao_lida"]
        assert audit and audit[-1].depois["o_que"] == "painel_interno"

    def test_superadmin_unknown_key_is_still_404(self, casa):
        _papel(casa, org_role="owner", platform=True)
        assert casa.get("/api/agents/nao-existe/painel/interno").status_code == 404


class TestListing:
    def test_one_card_per_agent_with_data_driven_origin(self, casa):
        _papel(casa, org_role="member", platform=False)
        r = casa.get(LISTA)
        assert r.status_code == 200, r.text
        por = {a["key"]: a for a in r.json()["items"]}
        assert set(por) == {"bia", "one-chat", "isaia", "julia"}
        assert r.json()["total"] == 4
        assert por["bia"]["origem"] == "legado" and por["julia"]["origem"] == "instancia"
        assert por["isaia"]["origem"] == "org"
        assert por["one-chat"]["papel"] == "operador" and por["one-chat"]["capacidades"] == ["Resposta"]
        # One Chat with no connection: the owning product's state is unknown, said so
        assert por["one-chat"]["estado_externo"] is None and por["one-chat"]["aviso"]

    def test_a_member_sees_only_public_sections_and_cannot_toggle(self, casa):
        _papel(casa, org_role="member", platform=False)
        por = {a["key"]: a for a in casa.get(LISTA).json()["items"]}
        assert por["bia"]["secoes"] == ["visao-geral", "conversar"]
        assert por["one-chat"]["secoes"] == ["visao-geral"]
        assert por["julia"]["secoes"] == ["visao-geral"]
        assert por["isaia"]["secoes"] == ["visao-geral", "conversar"]
        assert not any(a["pode_alternar"] for a in por.values())

    def test_an_org_admin_gets_the_org_sections_never_the_internal_ones(self, casa):
        _papel(casa, org_role="admin", platform=False)
        por = {a["key"]: a for a in casa.get(LISTA).json()["items"]}
        assert por["bia"]["secoes"] == ["visao-geral", "conversar", "persona"]
        assert por["julia"]["secoes"] == ["visao-geral", "especificacoes-org", "controles", "conversas"]
        assert por["bia"]["pode_alternar"] and not por["julia"]["pode_alternar"]
        internas = {s.id for s in SECOES_PAGINA if s.tier == "plataforma"}
        assert not any(set(a["secoes"]) & internas for a in por.values())

    def test_a_superadmin_gets_the_content_areas(self, casa):
        _papel(casa, org_role="owner", platform=True)
        por = {a["key"]: a for a in casa.get(LISTA).json()["items"]}
        assert {"prompt", "skills", "configuracoes", "versoes", "compilado"} <= set(por["isaia"]["secoes"])
        assert "textos" not in por["isaia"]["secoes"]  # a pre-v2 (legado content) agent has no text rows
        assert "compilado" in por["julia"]["secoes"] and "prompt" not in por["julia"]["secoes"]

    def test_the_card_carries_no_instruction_bearing_field(self, casa):
        _papel(casa, org_role="owner", platform=True)
        item = casa.get("/api/agents/isaia/painel").json()
        assert not {"texto", "conteudo", "regra", "prompt", "versoes", "compiled_hash"} & set(item)


class TestModelo:
    def test_member_gets_the_page_map_without_the_internal_structure(self, casa):
        _papel(casa, org_role="member", platform=False)
        body = casa.get(MODELO).json()
        assert body["tier"] == "membro" and body["areas"] == [] and body["assistente"] is None
        assert {s["tier"] for s in body["secoes"]} == {"membro"}

    def test_superadmin_gets_the_seven_areas_and_the_ten_wizard_steps(self, casa):
        _papel(casa, org_role="owner", platform=True)
        body = casa.get(MODELO).json()
        assert body["conteudo_modo"] == "linhas"
        assert [a["id"] for a in body["areas"]] == list(AREAS)
        assert [p["id"] for p in body["assistente"]["passos"]] == WIZARD
        ferramentas = next(a for a in body["areas"] if a["id"] == "ferramentas")
        assert [c["chave"] for c in ferramentas["campos"]] == list(FerramentaIn.model_fields)
        assert "handoff" in ferramentas["enumeracao"]["opcoes"]


class TestModelIsDerived:
    """Presentation-only tables are guarded against the derived sets (derive, don't sync by hand)."""

    def test_every_area_has_a_title_and_a_section(self):
        assert set(AREA_ROTULOS) == set(AREAS)
        assert {s.area for s in SECOES_PAGINA if s.area} == set(AREAS)

    def test_wizard_has_ten_steps_with_real_create_fields(self):
        from app.schemas.studio_geracao import Briefing
        from app.schemas.studio_plataforma import PlataformaAgentCreateRequest

        assert [p.id for p in PASSOS_ASSISTENTE] == WIZARD
        modelos = {"plataforma": PlataformaAgentCreateRequest, "briefing": Briefing}
        for passo in PASSOS_ASSISTENTE:
            for modelo, campo in passo.campos:
                assert campo in modelos[modelo].model_fields, (passo.id, campo)
            assert set(passo.areas) <= set(AREAS)


class TestPersonaByKey:
    def test_the_academia_agent_still_answers_at_its_path(self, casa):
        seed_org_role(casa, role="owner")
        # the AGENT resolves (no persona row yet is its own 404 message, never "agent not found")
        r = casa.get("/api/agents/bia/persona")
        assert r.status_code == 404 and r.json()["detail"] == "Nenhuma persona ativa configurada."

    @pytest.mark.parametrize("key", ["one-chat", "isaia", "nao-existe"])
    def test_a_key_that_is_not_a_legacy_chat_agent_is_404(self, casa, key):
        seed_org_role(casa, role="owner")
        r = casa.get(f"/api/agents/{key}/persona")
        assert r.status_code == 404
        assert r.json()["detail"] == "Agente não encontrado."
