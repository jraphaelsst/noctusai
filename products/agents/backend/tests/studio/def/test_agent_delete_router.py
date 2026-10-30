"""Agent lifecycle (S1): ``DELETE /api/studio/agents/{key}`` + the empty-shell creation of a platform definition.

Contract: 204 on success; 409 ``{code, message, detail}`` (flat on the wire: the seed exception handler passes a dict detail through verbatim) with code in publicado / tem_instancias / tem_conversas /
tem_canal / ativo; 404 ``agente_nao_encontrado``; unauthenticated is a strict 401, an org admin that is not a platform
admin a 403, a content token WITHOUT ``studio:agent-delete`` a 403 ``scope_missing``. The audit rows outlive the agent
(``agent_id`` None + an ``agente_excluido`` tombstone). The Fake enforces the same guards as ``agents.excluir_agente``.
"""
from __future__ import annotations

from tests.julia_body import JULIA_BODY

from uuid import UUID

import pytest

from app.dependencies import SCOPE_STUDIO_AGENT_DELETE, get_auth_context
from app.stores.studio_definitions import EXCLUSAO_CODIGOS
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

BASE = "/api/studio/agents"
PLAT = "/api/studio/plataforma"


def _platform_admin(studio):
    studio.mock_supabase.set_table_data(
        "noctus_users", [{"id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": "admin", "org_role": "owner"}],
    )


def _token(studio, scopes, issuer="noctus-platform"):
    studio.raw.app.dependency_overrides[get_auth_context] = lambda: AuthContext(
        org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=list(scopes),
        raw_token="tok", api_token_id=UUID(int=9), issuer=issuer,
    )
    return studio.raw


@pytest.fixture
def shell(studio):
    """An empty, off, never-published agent of the caller's org (the thing the owner wants to delete)."""
    agent = studio.store.create_studio_agent(DEFAULT_ORG_ID, "casca", "Casca", None)
    studio.store.create_draft(DEFAULT_ORG_ID, agent.id, None, DEFAULT_USER_ID)
    return studio


class TestDeleteAuth:
    def test_unauthenticated_is_strict_401(self, shell):
        assert shell.raw.delete(f"{BASE}/casca").status_code == 401

    def test_an_org_admin_that_is_not_a_platform_admin_is_403(self, shell):
        shell.as_org_admin_only()
        resp = shell.delete(f"{BASE}/casca")
        assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"
        assert shell.store.get_agent(DEFAULT_ORG_ID, "casca")

    def test_a_member_is_403(self, shell):
        shell.as_role("member")
        assert shell.delete(f"{BASE}/casca").status_code == 403

    def test_a_content_token_without_the_delete_scope_is_403(self, shell):
        raw = _token(shell, ["studio:content-write"])
        resp = raw.delete(f"{BASE}/casca")
        assert resp.status_code == 403 and resp.json()["code"] == "scope_missing"
        assert shell.store.get_agent(DEFAULT_ORG_ID, "casca")

    def test_the_delete_scope_with_a_foreign_issuer_is_403(self, shell):
        raw = _token(shell, [SCOPE_STUDIO_AGENT_DELETE], issuer="social-wiring")
        resp = raw.delete(f"{BASE}/casca")
        assert resp.status_code == 403 and resp.json()["code"] == "issuer_not_allowed"


class TestDelete:
    def test_a_platform_admin_deletes_an_empty_shell_and_the_audit_survives(self, shell):
        _platform_admin(shell)
        agent = shell.store.get_agent(DEFAULT_ORG_ID, "casca")
        shell.store.update_agent(DEFAULT_ORG_ID, "casca", {"publicacao_limiar": 0.9}, actor=DEFAULT_USER_ID)
        resp = shell.delete(f"{BASE}/casca")
        assert resp.status_code == 204 and resp.content == b""
        assert shell.get(f"{BASE}/casca").status_code == 404
        rows = shell.store.audit_log_all()
        assert rows and all(r.agent_id is None for r in rows), "every audit row loses the id, none is dropped"
        assert {r.agent_key for r in rows} == {"casca"}
        tomb = [r for r in rows if r.acao == "agente_excluido"]
        assert len(tomb) == 1 and tomb[0].antes["key"] == "casca" and tomb[0].antes["id"] == str(agent.id)
        assert any(r.acao == "limiar_alterado" for r in rows)
        assert shell.store.list_audit_log(DEFAULT_ORG_ID, agent.id) == []

    def test_the_token_with_the_scope_deletes(self, shell):
        raw = _token(shell, ["studio:content-write", SCOPE_STUDIO_AGENT_DELETE])
        assert raw.delete(f"{BASE}/casca").status_code == 204
        tomb = [r for r in shell.store.audit_log_all() if r.acao == "agente_excluido"]
        assert len(tomb) == 1 and tomb[0].actor == UUID(int=9)

    def test_an_unknown_key_is_404(self, shell):
        _platform_admin(shell)
        resp = shell.delete(f"{BASE}/nao-existe")
        assert resp.status_code == 404 and resp.json()["code"] == "agente_nao_encontrado"

    def test_another_orgs_agent_is_404_not_403(self, shell):
        shell.store.create_studio_agent(UUID(int=77), "alheio", "Alheio", None)
        _platform_admin(shell)
        assert shell.delete(f"{BASE}/alheio").status_code == 404

    def test_the_draft_and_its_content_go_with_the_agent(self, shell):
        _platform_admin(shell)
        agent = shell.store.get_agent(DEFAULT_ORG_ID, "casca")
        draft = shell.store.get_draft(DEFAULT_ORG_ID, agent.id)
        shell.store.replace_sections(DEFAULT_ORG_ID, draft.id, [])
        assert shell.delete(f"{BASE}/casca").status_code == 204
        assert shell.store.list_versions(DEFAULT_ORG_ID, agent.id) == []


class TestDeleteGuards:
    """Each 409: the body carries ``code`` + ``message`` and nothing was deleted."""

    def _assert_409(self, studio, code):
        resp = studio.delete(f"{BASE}/casca")
        assert resp.status_code == 409, resp.text
        body = resp.json()  # flat, like every Studio error: the seed handler passes {detail, code, ...} through verbatim
        assert body["code"] == code and body["message"] and body["detail"] == body["message"]
        assert studio.store.get_agent(DEFAULT_ORG_ID, "casca"), "a refused delete deletes nothing"
        assert not [r for r in studio.store.audit_log_all() if r.acao == "agente_excluido"]

    def test_codes_are_exactly_the_contract(self):
        assert EXCLUSAO_CODIGOS == ("publicado", "tem_instancias", "tem_conversas", "tem_canal", "ativo")

    def test_publicado(self, shell):
        _platform_admin(shell)
        agent = shell.store.get_agent(DEFAULT_ORG_ID, "casca")
        draft = shell.store.get_draft(DEFAULT_ORG_ID, agent.id)
        h = "sha256:" + "a" * 64
        shell.store.set_compiled_hash(DEFAULT_ORG_ID, draft.id, h)
        shell.store.publish_version(
            DEFAULT_ORG_ID, draft.id, DEFAULT_USER_ID, None, "publicação de teste para o guard",
            expected_hash=h, texto="t", manifest=[],
        )
        self._assert_409(shell, "publicado")

    def test_tem_instancias(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        _platform_admin(studio)
        definition = studio.store.create_studio_agent(
            DEFAULT_ORG_ID, "julia", "Julia", None, definition_scope="plataforma",
        )
        studio.store.create_draft(DEFAULT_ORG_ID, definition.id, None, DEFAULT_USER_ID)
        studio.store.grant_definition_org(definition.id, UUID(int=77))  # 050: closed definition -> grant
        studio.store.create_studio_agent(
            UUID(int=77), "julia", "Julia", None, definition_scope="instancia", definition_agent_id=definition.id,
        )
        resp = studio.delete(f"{BASE}/julia")
        assert resp.status_code == 409
        assert resp.json()["code"] == "tem_instancias"

    def test_tem_conversas(self, shell):
        _platform_admin(shell)
        shell.store.mark_agent_has_messages(shell.store.get_agent(DEFAULT_ORG_ID, "casca").id)
        self._assert_409(shell, "tem_conversas")

    def test_tem_canal(self, shell):
        _platform_admin(shell)
        shell.store.mark_agent_has_channel(shell.store.get_agent(DEFAULT_ORG_ID, "casca").id)
        self._assert_409(shell, "tem_canal")

    def test_ativo(self, shell):
        _platform_admin(shell)
        shell.store.update_agent(DEFAULT_ORG_ID, "casca", {"ativo": True})
        self._assert_409(shell, "ativo")


class TestEmptyShellCreation:
    """Creation never requires content; only PUBLISH is gated by completeness."""

    def test_the_content_token_creates_an_empty_platform_definition_and_audits_it_once(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        raw = _token(studio, ["studio:content-write"])
        first = raw.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert first.status_code == 201, first.text
        assert first.json()["definition_scope"] == "plataforma"
        agent = studio.store.get_agent(DEFAULT_ORG_ID, "julia")
        draft = studio.store.get_draft(DEFAULT_ORG_ID, agent.id)
        assert studio.store.list_sections(DEFAULT_ORG_ID, draft.id) == [], "no text is required to create"
        dup = raw.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert dup.status_code == 409 and dup.json()["code"] == "agente_ja_existe", "a create never lands on an existing key"
        again = raw.post(f"{PLAT}/agents", json={**JULIA_BODY, "reutilizar": True})
        assert again.status_code == 201 and again.json()["id"] == first.json()["id"]
        criado = [a for a in studio.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "agente_criado"]
        assert len(criado) == 1, "audited when it creates, not on the reuse hit nor the refused duplicate"

    def test_a_token_without_the_scope_cannot_create(self, studio):
        studio.store.mark_platform_org(DEFAULT_ORG_ID)
        raw = _token(studio, ["studio:publish"])
        resp = raw.post(f"{PLAT}/agents", json=JULIA_BODY)
        assert resp.status_code == 403 and resp.json()["code"] == "scope_missing"

    def test_unauthenticated_is_strict_401(self, studio):
        assert studio.raw.post(f"{PLAT}/agents", json=JULIA_BODY).status_code == 401


class TestMintWithDelete:
    def _minting(self, studio):
        from app.channels.token_audit import FakeTokenAudit
        from app.dependencies import get_product_token_admin_dep, get_token_audit_dep
        from noctusai_lib.api.auth.session import FakeProductTokenAdmin

        admin, audit = FakeProductTokenAdmin(), FakeTokenAudit()
        studio.raw.app.dependency_overrides[get_product_token_admin_dep] = lambda: admin
        studio.raw.app.dependency_overrides[get_token_audit_dep] = lambda: audit
        return admin

    def test_default_has_no_delete_scope(self, studio):
        admin = self._minting(studio)
        ok = studio.post(f"{PLAT}/content-token", json={"label": "mcp"})
        assert ok.status_code == 201 and ok.json()["scopes"] == ["studio:content-write"]
        assert admin.rows["agents"][0]["scopes"] == ["studio:content-write"]

    def test_permitir_exclusao_adds_the_scope_and_the_list_shows_it(self, studio):
        admin = self._minting(studio)
        ok = studio.post(f"{PLAT}/content-token", json={"label": "mcp", "permitir_exclusao": True})
        assert ok.status_code == 201
        assert ok.json()["scopes"] == ["studio:content-write", SCOPE_STUDIO_AGENT_DELETE]
        assert admin.rows["agents"][0]["scopes"] == ["studio:content-write", SCOPE_STUDIO_AGENT_DELETE]
        itens = studio.get(f"{PLAT}/content-tokens").json()["itens"]
        assert SCOPE_STUDIO_AGENT_DELETE in itens[0]["scopes"]
