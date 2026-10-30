"""Renata cutover (agents-unified): history transfer, retirement of the code-defined rows, and the dynamic chat
destination the legacy `/bia` URLs resolve to. Superadmin-only writes: 404 (never 403) for anyone else, a strict
401 without a credential."""
from __future__ import annotations

import pytest

from app.dependencies import get_credential_service_dep
from app.routers.agentes_cutover_router import get_cutover_store_dep
from app.routers.studio_agents_router import get_studio_definition_store_dep
from app.stores.cutover import FakeCutoverStore
from app.stores.studio_definitions import FakeStudioDefinitionStore
from tests.credentials.conftest import build_kit
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

TRANSFERIR = "/api/agents/bia/transferir-historico"
ARQUIVAR = "/api/agents/bia/arquivar"
DESTINO = "/api/agents/painel/destino-chat"


def _papel(client, *, org_role: str = "owner", platform: bool) -> None:
    client.mock_supabase.set_table_data("noctus_users", [{
        "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "org_role": org_role,
        "role": "admin" if platform else "user"}])


@pytest.fixture
def corte(agents_client):
    from app.main import app

    stores = agents_client.stores
    studio = FakeStudioDefinitionStore()
    legado = stores.agents.seed_legacy_chat_agent(DEFAULT_ORG_ID)
    renata = studio.seed_agent(DEFAULT_ORG_ID, "renata", nome="Renata")
    kit = build_kit(academia_agent_id=str(legado.id))
    cutover = FakeCutoverStore(
        agents=stores.agents, studio=studio, conversations=stores.conversations, messages=stores.messages,
        approvals=stores.approvals,
    )
    app.dependency_overrides[get_studio_definition_store_dep] = lambda: studio
    app.dependency_overrides[get_cutover_store_dep] = lambda: cutover
    app.dependency_overrides[get_credential_service_dep] = lambda: kit.service
    # history on the legacy agent: two conversations, three messages
    c1 = stores.conversations.create(DEFAULT_ORG_ID, legado.id, DEFAULT_USER_ID, "a")
    c2 = stores.conversations.create(DEFAULT_ORG_ID, legado.id, DEFAULT_USER_ID, "b")
    for cid, texto in ((c1.id, "oi"), (c1.id, "ola"), (c2.id, "tchau")):
        stores.messages.add(DEFAULT_ORG_ID, cid, "user", texto)
    agents_client.studio, agents_client.kit = studio, kit
    agents_client.legado, agents_client.renata = legado, renata
    agents_client.conversas = (c1.id, c2.id)
    try:
        yield agents_client
    finally:
        for dep in (get_studio_definition_store_dep, get_cutover_store_dep, get_credential_service_dep):
            app.dependency_overrides.pop(dep, None)


class TestBoundary:
    @pytest.mark.parametrize("method,url,body", [
        ("post", TRANSFERIR, {"target_key": "renata"}), ("post", ARQUIVAR, {}), ("get", DESTINO, None),
    ])
    def test_unauthenticated_is_strict_401(self, corte, method, url, body):
        kw = {"json": body} if body is not None else {}
        assert getattr(corte.raw(), method)(url, **kw).status_code == 401

    @pytest.mark.parametrize("org_role", ["member", "admin", "owner"])
    @pytest.mark.parametrize("url,body", [(TRANSFERIR, {"target_key": "renata"}), (ARQUIVAR, {})])
    def test_a_non_superadmin_gets_404_never_403(self, corte, org_role, url, body):
        _papel(corte, org_role=org_role, platform=False)
        r = corte.post(url, json={**body, "dry_run": False})
        assert r.status_code == 404 and r.json()["code"] == "agent_not_found"
        # and nothing moved
        assert all(corte.stores.conversations.get(DEFAULT_ORG_ID, c).agent_id == corte.legado.id
                   for c in corte.conversas)

    def test_an_unknown_body_field_is_422(self, corte):
        _papel(corte, platform=True)
        assert corte.post(TRANSFERIR, json={"target_key": "renata", "x": 1}).status_code == 422


class TestTransfer:
    def test_dry_run_is_the_default_and_only_counts(self, corte):
        _papel(corte, platform=True)
        r = corte.post(TRANSFERIR, json={"target_key": "renata"})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["dry_run"] is True and body["executado"] is False
        assert (body["conversas"], body["mensagens"]) == (2, 3)
        assert body["credencial_academia"] == "seria_repontado"
        assert all(corte.stores.conversations.get(DEFAULT_ORG_ID, c).agent_id == corte.legado.id
                   for c in corte.conversas)
        assert not [a for a in corte.studio.audit_log_all() if a.acao == "historico_transferido"]
        assert corte.kit.service.academia_agent_id() == corte.legado.id

    def test_real_run_moves_history_audits_and_repoints_the_academia_principal(self, corte):
        _papel(corte, platform=True)
        r = corte.post(TRANSFERIR, json={"target_key": "renata", "dry_run": False})
        assert r.status_code == 200, r.text
        body = r.json()
        assert body["executado"] is True and (body["conversas"], body["mensagens"]) == (2, 3)
        assert body["target_agent_id"] == str(corte.renata.id)
        assert body["credencial_academia"] == "repontado"
        for c in corte.conversas:
            conv = corte.stores.conversations.get(DEFAULT_ORG_ID, c)
            assert conv.agent_id == corte.renata.id
            assert len(corte.stores.messages.list(DEFAULT_ORG_ID, c)) >= 1  # memory travels with the conversation
        [audit] = [a for a in corte.studio.audit_log_all() if a.acao == "historico_transferido"]
        assert audit.agent_id == corte.renata.id and audit.actor == DEFAULT_USER_ID
        assert audit.antes["de_key"] == "bia" and audit.depois["conversas"] == 2
        assert corte.kit.service.academia_agent_id() == corte.renata.id

    def test_it_is_idempotent(self, corte):
        _papel(corte, platform=True)
        assert corte.post(TRANSFERIR, json={"target_key": "renata", "dry_run": False}).json()["executado"] is True
        again = corte.post(TRANSFERIR, json={"target_key": "renata", "dry_run": False})
        assert again.status_code == 200
        body = again.json()
        assert body["executado"] is False and body["conversas"] == 0
        assert body["credencial_academia"] == "ja_aponta"
        assert len([a for a in corte.studio.audit_log_all() if a.acao == "historico_transferido"]) == 1

    def test_the_target_must_be_a_studio_agent_of_the_org(self, corte):
        _papel(corte, platform=True)
        corte.studio.add_legacy_agent(DEFAULT_ORG_ID, "velho", "Velho")
        r = corte.post(TRANSFERIR, json={"target_key": "velho", "dry_run": False})
        assert r.status_code == 409 and r.json()["code"] == "destino_invalido"
        assert corte.post(TRANSFERIR, json={"target_key": "nao-existe"}).status_code == 404

    def test_the_source_must_be_a_code_defined_agent(self, corte):
        _papel(corte, platform=True)
        assert corte.post("/api/agents/nao-existe/transferir-historico",
                          json={"target_key": "renata"}).status_code == 404

    def test_the_principal_is_left_alone_when_it_names_another_agent(self, corte):
        _papel(corte, platform=True)
        corte.kit.service.set_value("academia_agent_id", "00000000-0000-0000-0000-0000000000aa")
        body = corte.post(TRANSFERIR, json={"target_key": "renata", "dry_run": False}).json()
        assert body["executado"] is True and body["credencial_academia"] == "nao_aplicavel"
        assert str(corte.kit.service.academia_agent_id()) == "00000000-0000-0000-0000-0000000000aa"


class TestArchive:
    def test_refused_while_the_row_owns_history(self, corte):
        _papel(corte, platform=True)
        r = corte.post(ARQUIVAR, json={"dry_run": False})
        assert r.status_code == 409 and r.json()["code"] == "historico_pendente"
        assert corte.stores.agents.get_by_key(DEFAULT_ORG_ID, "bia").definition_mode == "legacy"

    def test_after_the_transfer_the_key_is_freed_and_audited(self, corte):
        _papel(corte, platform=True)
        corte.post(TRANSFERIR, json={"target_key": "renata", "dry_run": False})
        dry = corte.post(ARQUIVAR, json={})
        assert dry.status_code == 200 and dry.json()["executado"] is False and dry.json()["linhas"] == 1
        r = corte.post(ARQUIVAR, json={"dry_run": False})
        assert r.status_code == 200, r.text
        assert r.json()["executado"] is True
        # archived rows leave every listing; the row itself survives under a freed key
        listed = {a.key for a in corte.stores.agents.list(DEFAULT_ORG_ID)}
        assert "bia" not in listed and not any(k.startswith("bia-arquivado-") for k in listed)
        [arquivado] = [r for (o, k), r in corte.stores.agents._rows.items()
                       if o == DEFAULT_ORG_ID and k.startswith("bia-arquivado-")]
        assert arquivado["definition_mode"] == "arquivado" and arquivado["ativo"] is False
        assert arquivado["id"] == corte.legado.id
        assert [a for a in corte.studio.audit_log_all() if a.acao == "agente_arquivado"]
        # a second retire finds nothing (the key is free) and the old chat URLs follow the principal
        assert corte.post(ARQUIVAR, json={"dry_run": False}).status_code == 404
        assert corte.get(DESTINO).json() == {"key": "renata", "origem": "academia"}


class TestChatDestination:
    def test_follows_the_academia_principal_when_it_is_this_orgs_agent(self, corte):
        _papel(corte, org_role="member", platform=False)
        corte.kit.service.set_value("academia_agent_id", str(corte.renata.id))
        assert corte.get(DESTINO).json() == {"key": "renata", "origem": "academia"}

    def test_falls_back_to_the_orgs_code_defined_chat_agent(self, corte):
        _papel(corte, org_role="member", platform=False)
        assert corte.get(DESTINO).json() == {"key": "bia", "origem": "legado"}

    def test_404_when_the_org_has_neither(self, corte):
        _papel(corte, org_role="member", platform=False)
        corte.kit.service.set_value("academia_agent_id", "00000000-0000-0000-0000-0000000000aa")
        _papel(corte, platform=True)
        assert corte.post(TRANSFERIR, json={"target_key": "renata", "dry_run": False}).json()["executado"]
        assert corte.post(ARQUIVAR, json={"dry_run": False}).json()["executado"]
        _papel(corte, org_role="member", platform=False)
        r = corte.get(DESTINO)
        assert r.status_code == 404 and r.json()["code"] == "agent_not_found"
