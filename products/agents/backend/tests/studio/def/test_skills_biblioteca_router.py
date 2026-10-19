"""Shared skill library API (Julia v2 A-SKILLS, migration 039): platform-only auth, the library
lifecycle (draft -> publish -> immutable -> new version), the pins on an agent draft, the
"new version available" indicator, the hash coverage of the pins, and the MCP token path.

Skill text below is TEST DATA ONLY: app/ carries no skill content (D3). Auth assertions are strict.
"""
from __future__ import annotations

from uuid import UUID

import pytest

from app.dependencies import get_auth_context
from app.routers.skills_biblioteca_router import get_skills_store_dep
from app.stores.skills_biblioteca import FakeSkillsBibliotecaStore
from app.studio.bundles import configure_skill_refs_provider
from noctusai_lib.api.auth.session import AuthContext
from tests.routers.conftest import DEFAULT_ORG_ID, DEFAULT_USER_ID

LIB = "/api/skills-biblioteca"
AGENT = "/api/studio/agents"
PLAT = "/api/studio/plataforma"


def _platform_admin(studio):
    studio.mock_supabase.set_table_data(
        "noctus_users",
        [{"id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": "admin", "org_role": "owner"}],
    )


@pytest.fixture
def lib(studio):
    """The platform org is the default org; ``julia``'s definition + draft exist; one Fake library
    store shared by the router AND the compile slot (the production wiring reads the same store)."""
    skills = FakeSkillsBibliotecaStore()
    studio.skills = skills
    studio.raw.app.dependency_overrides[get_skills_store_dep] = lambda: skills
    previous = configure_skill_refs_provider(lambda: skills)
    studio.store.mark_platform_org(DEFAULT_ORG_ID)
    _platform_admin(studio)
    assert studio.post(f"{PLAT}/agents", json={"key": "julia"}).status_code == 201
    try:
        yield studio
    finally:
        configure_skill_refs_provider(previous)


def _publicar_skill(lib, chave="qualificar", corpo="corpo de teste", desc="quando abrir"):
    """Create + fill + publish version 1 of a library skill; returns the version id."""
    assert lib.post(LIB, json={"chave": chave, "nome": chave.title()}).status_code == 201
    vid = lib.post(f"{LIB}/{chave}/versoes", json={}).json()["id"]
    r = lib.patch(f"{LIB}/versoes/{vid}", json={"descricao_modelo": desc, "corpo": corpo})
    assert r.status_code == 200, r.text
    r = lib.post(f"{LIB}/versoes/{vid}/publicar")
    assert r.status_code == 200, r.text
    return UUID(vid)


def _draft(lib):
    agent = lib.store.get_agent(DEFAULT_ORG_ID, "julia")
    return lib.store.get_draft(DEFAULT_ORG_ID, agent.id)


def _token_ctx(scopes=("studio:content-write",), issuer="noctus-platform"):
    return lambda: AuthContext(
        org_id=DEFAULT_ORG_ID, caller_kind="product", user_id=None, scopes=list(scopes),
        raw_token="tok", api_token_id=UUID(int=9), issuer=issuer,
    )


class TestPlatformOnly:
    def test_unauthenticated_is_401(self, lib):
        for method, url in (("get", LIB), ("post", LIB), ("get", f"{AGENT}/julia/draft/skills-biblioteca")):
            resp = getattr(lib.raw, method)(url, **({"json": {}} if method == "post" else {}))
            assert resp.status_code == 401, (method, url)

    def test_an_org_owner_who_is_not_a_platform_admin_is_403(self, lib):
        lib.as_org_admin_only()
        for method, url, body in (
            ("get", LIB, None), ("post", LIB, {"chave": "x1", "nome": "X"}),
            ("get", f"{AGENT}/julia/draft/skills-biblioteca", None),
            ("put", f"{AGENT}/julia/draft/skills-biblioteca/x1", {}),
        ):
            resp = getattr(lib, method)(url, **({"json": body} if body is not None else {}))
            assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required", (method, url)

    def test_a_plain_member_is_403(self, lib):
        lib.mock_supabase.set_table_data("noctus_users", [{
            "id": str(DEFAULT_USER_ID), "org_id": str(DEFAULT_ORG_ID), "role": "user", "org_role": "member",
        }])
        resp = lib.get(LIB)
        assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required"

    def test_a_token_needs_the_scope_and_the_platform_issuer(self, lib):
        app = lib.raw.app
        app.dependency_overrides[get_auth_context] = _token_ctx(scopes=("studio:publish",))
        resp = lib.raw.get(LIB)
        assert resp.status_code == 403 and resp.json()["code"] == "scope_missing"
        for issuer in (None, "social-wiring"):
            app.dependency_overrides[get_auth_context] = _token_ctx(issuer=issuer)
            resp = lib.raw.get(LIB)
            assert resp.status_code == 403 and resp.json()["code"] == "issuer_not_allowed"

    def test_the_content_token_writes_drafts_but_never_publishes(self, lib):
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx()
        assert lib.raw.post(LIB, json={"chave": "viaquota", "nome": "V"}).status_code == 201
        vid = lib.raw.post(f"{LIB}/viaquota/versoes", json={}).json()["id"]
        assert lib.raw.patch(
            f"{LIB}/versoes/{vid}", json={"descricao_modelo": "d", "corpo": "c"},
        ).status_code == 200
        resp = lib.raw.post(f"{LIB}/versoes/{vid}/publicar")
        assert resp.status_code == 403 and resp.json()["code"] == "user_required"
        assert lib.skills.obter_versao(UUID(vid)).meta.status == "rascunho"


class TestLibraryLifecycle:
    def test_draft_publish_immutable_and_new_version(self, lib):
        v1 = _publicar_skill(lib)
        again = lib.patch(f"{LIB}/versoes/{v1}", json={"corpo": "outro"})
        assert again.status_code == 409 and again.json()["code"] == "version_immutable"
        assert lib.put(f"{LIB}/versoes/{v1}/arquivos/ref.md", json={"conteudo": "x"}).status_code == 409
        assert lib.delete(f"{LIB}/versoes/{v1}").status_code == 409
        assert lib.post(f"{LIB}/versoes/{v1}/publicar").json()["code"] == "version_immutable"

        v2 = lib.post(f"{LIB}/qualificar/versoes", json={"copiar_de": str(v1), "notas": "v2"}).json()
        assert v2["versao"] == 2 and v2["corpo"] == "corpo de teste" and v2["status"] == "rascunho"
        dup = lib.post(f"{LIB}/qualificar/versoes", json={})
        assert dup.status_code == 409 and dup.json()["code"] == "draft_exists"
        lib.patch(f"{LIB}/versoes/{v2['id']}", json={"corpo": "corpo novo"})
        lib.post(f"{LIB}/versoes/{v2['id']}/publicar")
        statuses = {v["versao"]: v["status"] for v in lib.get(f"{LIB}/qualificar/versoes").json()["items"]}
        assert statuses == {1: "arquivada", 2: "publicada"}
        # the archived version is still readable and still says what it said
        assert lib.get(f"{LIB}/versoes/{v1}").json()["corpo"] == "corpo de teste"
        listing = lib.get(LIB).json()["items"]
        assert [(s["chave"], s["versao_publicada"], s["tem_rascunho"]) for s in listing] == [("qualificar", 2, False)]

    def test_publish_needs_a_description_and_a_body(self, lib):
        lib.post(LIB, json={"chave": "vazia", "nome": "Vazia"})
        vid = lib.post(f"{LIB}/vazia/versoes", json={}).json()["id"]
        resp = lib.post(f"{LIB}/versoes/{vid}/publicar")
        assert resp.status_code == 422 and resp.json()["code"] == "skill_incompleta"

    def test_files_belong_to_the_version(self, lib):
        lib.post(LIB, json={"chave": "comarq", "nome": "C"})
        vid = lib.post(f"{LIB}/comarq/versoes", json={}).json()["id"]
        lib.patch(f"{LIB}/versoes/{vid}", json={"descricao_modelo": "d", "corpo": "c"})
        put = lib.put(f"{LIB}/versoes/{vid}/arquivos/guias/a.md", json={"titulo": "A", "conteudo": "texto"})
        assert put.status_code == 200 and put.json()["arquivos"][0]["caminho"] == "guias/a.md"
        assert lib.put(f"{LIB}/versoes/{vid}/arquivos/..%2Fx", json={"conteudo": "x"}).status_code in (404, 422)
        assert lib.put(f"{LIB}/versoes/{vid}/arquivos/Mau.md", json={"conteudo": "x"}).status_code == 422
        assert lib.delete(f"{LIB}/versoes/{vid}/arquivos/guias/a.md").status_code == 204
        assert lib.delete(f"{LIB}/versoes/{vid}/arquivos/guias/a.md").status_code == 404

    def test_duplicate_key_and_bad_key(self, lib):
        _publicar_skill(lib, "unica")
        dup = lib.post(LIB, json={"chave": "unica", "nome": "x"})
        assert dup.status_code == 409 and dup.json()["code"] == "chave_taken"
        assert lib.post(LIB, json={"chave": "Maiuscula", "nome": "x"}).status_code == 422
        assert lib.get(f"{LIB}/nada/versoes").status_code == 404

    def test_errors_never_echo_content(self, lib):
        v1 = _publicar_skill(lib, corpo="SEGREDO-DE-PLATAFORMA")
        resp = lib.patch(f"{LIB}/versoes/{v1}", json={"corpo": "x"})
        assert "SEGREDO-DE-PLATAFORMA" not in resp.text


class TestPins:
    def test_pin_defaults_to_the_published_version_and_stamps_the_hash(self, lib):
        _publicar_skill(lib)
        sem = _draft(lib).compiled_hash
        resp = lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={"obrigatoria_para": ["handoff"]})
        assert resp.status_code == 200, resp.text
        item = resp.json()["items"][0]
        assert item["skill"] == "qualificar" and item["versao"] == 1 and item["obrigatoria_para"] == ["handoff"]
        assert item["nova_versao"] is None
        com = _draft(lib).compiled_hash
        assert com and com != sem  # the pin is hash-covered, and re-stamped
        got = lib.get(f"{AGENT}/julia/draft/skills-biblioteca").json()
        assert [i["skill"] for i in got["items"]] == ["qualificar"]

    def test_the_compiled_prompt_lists_the_pinned_skill_and_gates(self, lib):
        _publicar_skill(lib, desc="abra ao qualificar")
        lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={})
        from app.studio.bundles import compile_version
        agent = lib.store.get_agent(DEFAULT_ORG_ID, "julia")
        compiled = compile_version(lib.store, lib.catalog, DEFAULT_ORG_ID, agent, _draft(lib))
        assert "`qualificar` — abra ao qualificar" in compiled.texto
        assert any(i.tipo == "skill" and i.nome == "qualificar" and i.gatilho == 'abrir_skill("qualificar")'
                   for i in compiled.sob_demanda)

    def test_new_version_available_indicator_and_repin(self, lib):
        v1 = _publicar_skill(lib)
        lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={})
        v2 = lib.post(f"{LIB}/qualificar/versoes", json={"copiar_de": str(v1)}).json()["id"]
        lib.patch(f"{LIB}/versoes/{v2}", json={"corpo": "nova"})
        lib.post(f"{LIB}/versoes/{v2}/publicar")
        item = lib.get(f"{AGENT}/julia/draft/skills-biblioteca").json()["items"][0]
        assert item["versao"] == 1 and item["nova_versao"] == 2 and item["nova_versao_id"] == v2
        before = _draft(lib).compiled_hash
        item = lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={}).json()["items"][0]
        assert item["versao"] == 2 and item["nova_versao"] is None
        assert _draft(lib).compiled_hash != before
        # pin the archived v1 again explicitly (rollback)
        item = lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={"versao": 1}).json()["items"][0]
        assert item["versao"] == 1 and item["nova_versao"] == 2

    def test_a_draft_skill_version_cannot_be_pinned(self, lib):
        lib.post(LIB, json={"chave": "rasc", "nome": "R"})
        lib.post(f"{LIB}/rasc/versoes", json={})
        resp = lib.put(f"{AGENT}/julia/draft/skills-biblioteca/rasc", json={"versao": 1})
        assert resp.status_code == 409 and resp.json()["code"] == "versao_nao_publicada"
        none = lib.put(f"{AGENT}/julia/draft/skills-biblioteca/rasc", json={})
        assert none.status_code == 404  # no published version to default to

    def test_obrigatoria_para_is_shape_checked(self, lib):
        _publicar_skill(lib)
        for bad in (["Handoff"], ["a b"], [""], ["x" * 70]):
            resp = lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={"obrigatoria_para": bad})
            assert resp.status_code == 422, bad

    def test_unpin(self, lib):
        _publicar_skill(lib)
        lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={})
        with_pin = _draft(lib).compiled_hash
        resp = lib.delete(f"{AGENT}/julia/draft/skills-biblioteca/qualificar")
        assert resp.status_code == 200 and resp.json()["items"] == []
        assert _draft(lib).compiled_hash != with_pin
        assert lib.delete(f"{AGENT}/julia/draft/skills-biblioteca/qualificar").status_code == 404

    def test_pins_of_a_published_version_are_readable_by_version_id(self, lib):
        _publicar_skill(lib)
        lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={})
        draft = _draft(lib)
        got = lib.get(f"{AGENT}/julia/versions/{draft.id}/skills-biblioteca")
        assert got.status_code == 200 and got.json()["version_id"] == str(draft.id)
        assert lib.get(f"{AGENT}/julia/versions/{UUID(int=3)}/skills-biblioteca").status_code == 404

    def test_a_token_pin_is_audited_as_an_mcp_write(self, lib):
        _publicar_skill(lib)
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx()
        resp = lib.raw.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={})
        assert resp.status_code == 200, resp.text
        agent = lib.store.get_agent(DEFAULT_ORG_ID, "julia")
        rows = [a for a in lib.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "conteudo_editado_mcp"]
        assert len(rows) == 1 and rows[0].depois["kind"] == "skill_ref" and rows[0].actor == UUID(int=9)

    def test_an_unknown_gated_tool_blocks_the_compile(self, lib):
        _publicar_skill(lib)
        lib.put(f"{AGENT}/julia/draft/skills-biblioteca/qualificar", json={"obrigatoria_para": ["ferramenta_que_nao_existe"]})
        from app.studio.bundles import compile_version
        agent = lib.store.get_agent(DEFAULT_ORG_ID, "julia")
        compiled = compile_version(lib.store, lib.catalog, DEFAULT_ORG_ID, agent, _draft(lib))
        assert any(w.codigo == "ferramenta_desconhecida" and w.bloqueante for w in compiled.avisos)


class TestSectionsViaContentToken:
    """The MCP tool writes sections with the platform content token (previously org-admin only)."""

    def test_the_token_replaces_sections_and_is_audited(self, lib):
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx()
        resp = lib.raw.put(f"{AGENT}/julia/draft/sections", json={"secoes": [
            {"chave": "persona", "titulo": "T", "ordem": 1, "conteudo": "c", "ativo": True},
        ]})
        assert resp.status_code == 200, resp.text
        agent = lib.store.get_agent(DEFAULT_ORG_ID, "julia")
        rows = [a for a in lib.store.list_audit_log(DEFAULT_ORG_ID, agent.id) if a.acao == "conteudo_editado_mcp"]
        assert len(rows) == 1 and rows[0].depois["kind"] == "secao" and rows[0].depois["chaves"] == ["persona"]

    def test_a_token_with_another_issuer_or_scope_is_403(self, lib):
        body = {"secoes": []}
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx(issuer="social-wiring")
        assert lib.raw.put(f"{AGENT}/julia/draft/sections", json=body).json()["code"] == "issuer_not_allowed"
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx(scopes=("studio:publish",))
        assert lib.raw.put(f"{AGENT}/julia/draft/sections", json=body).json()["code"] == "scope_missing"


class TestDraftAndContentReadsForTheMcpTool:
    """The MCP tool diffs against the current rows: the draft read and the four content reads accept the
    platform content token; every other caller is refused (an org owner is not a platform admin)."""

    def test_platform_admin_and_content_token_read_the_draft(self, lib):
        lib.put(f"{AGENT}/julia/draft/sections", json={"secoes": [
            {"chave": "persona", "titulo": "T", "ordem": 1, "conteudo": "c", "ativo": True}]})
        body = lib.get(f"{AGENT}/julia/draft").json()
        assert body["id"] == str(_draft(lib).id) and [s["chave"] for s in body["secoes"]] == ["persona"]
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx()
        as_token = lib.raw.get(f"{AGENT}/julia/draft")
        assert as_token.status_code == 200 and as_token.json()["id"] == body["id"]
        reads = lib.raw.get(f"{AGENT}/julia/versions/{body['id']}/textos")
        assert reads.status_code == 200
        agent = lib.store.get_agent(DEFAULT_ORG_ID, "julia")
        assert any(a.acao == "definicao_lida" and a.actor == UUID(int=9) for a in lib.store.list_audit_log(DEFAULT_ORG_ID, agent.id))

    def test_an_org_owner_who_is_not_a_platform_admin_cannot(self, lib):
        draft_id = _draft(lib).id
        lib.as_org_admin_only()
        for url in (f"{AGENT}/julia/draft", f"{AGENT}/julia/versions/{draft_id}/textos"):
            resp = lib.get(url)
            assert resp.status_code == 403 and resp.json()["code"] == "platform_admin_required", url

    def test_a_token_of_another_issuer_cannot(self, lib):
        lib.raw.app.dependency_overrides[get_auth_context] = _token_ctx(issuer="social-wiring")
        resp = lib.raw.get(f"{AGENT}/julia/draft")
        assert resp.status_code == 403 and resp.json()["code"] == "issuer_not_allowed"
