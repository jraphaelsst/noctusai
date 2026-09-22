"""``POST /api/studio/agents/{key}/import`` (Agent Studio §D5, §F, §H7)."""
from __future__ import annotations

import copy

import pytest

from app.routers.studio_agents_router import compile_version
from app.studio.catalog import StoreKnowledgeCatalog
from app.studio.importer import AgentBundle, import_bundle
from tests.routers.conftest import seed_org_role
from tests.studio.rt.fakes import ReadOnlyProxy, WriteForbidden

BUNDLE = {
    "formato": "noctus.agent-bundle/v1",
    "agente": {"key": "isa", "nome": "Isa", "descricao": "Estrategista de conteúdo."},
    "versao": {"notas": "import inicial", "model": "claude-opus-5", "effort": "high", "max_turns": 30,
               "idioma": "pt-BR", "tool_policy": {"web_search": True, "knowledge": True}},
    "secoes": [
        {"chave": "identidade", "titulo": "Identidade", "ordem": 10, "conteudo": "Você é a Isa.", "ativo": True},
        {"chave": "estilo", "titulo": "Estilo", "ordem": 20, "conteudo": "Direta e prática."},
    ],
    "skills": [{"nome": "roteiro-reels", "descricao": "Roteiros de Reels.", "corpo": "Passo 1.", "ordem": 10,
                "arquivos": [{"caminho": "references/arquiteturas.md", "titulo": "Arq", "conteudo": "ARQ"}]}],
    "conhecimento": [{"slug": "audience", "nome": "Audiência", "tag": "AU", "descricao": "Pesquisas.", "ordem": 10,
                      "documentos": [
                          {"slug": "ganchos", "titulo": "Ganchos", "tipo": "fonte", "resumo": "r",
                           "proveniencia": {"autor": "Autor", "pagina": 12}, "conteudo": "Conteúdo A"},
                          {"slug": "ctas", "titulo": "CTAs", "tipo": "card", "conteudo": "Conteúdo B"},
                      ]}],
    "evals": [{"slug": "reels-basico", "titulo": "Reels", "entrada": "Crie um roteiro", "contexto": None,
               "criterios": {"deve": ["ter gancho"], "nao_deve": ["inventar dados"]}, "rubrica": None, "tags": ["reels"]}],
    "clientes": [{"slug": "loja", "nome": "Loja", "resumo": "Moda.", "entradas": [{"tipo": "marca", "titulo": "Tom", "conteudo": "leve"}]}],
}


def _import(rt, body=None, *, key="isa", dry_run=False):
    return rt.post(f"/api/studio/agents/{key}/import", params={"dry_run": str(dry_run).lower()}, json=body or BUNDLE)


class TestImport:
    def test_first_import_creates_everything_and_never_publishes(self, rt):
        resp = _import(rt)
        assert resp.status_code == 200, resp.text
        out = resp.json()
        assert out["dry_run"] is False and out["agente"] == {"criado": True}
        assert (out["rascunho"]["secoes"], out["rascunho"]["skills"], out["rascunho"]["arquivos"]) == (2, 1, 1)
        assert out["conhecimento"] == {"colecoes_criadas": 1, "documentos_criados": 2, "documentos_atualizados": 0, "documentos_inalterados": 0}
        assert out["evals"] == {"criados": 1, "atualizados": 0}
        assert out["clientes"] == {"criados": 1}

        agent = rt.studio.get_agent(rt.org_id, "isa")
        assert agent.definition_mode == "studio"
        assert rt.studio.get_active_version(rt.org_id, agent.id) is None  # never publishes
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        assert str(draft.id) == out["rascunho"]["version_id"]
        assert (draft.model, draft.max_turns, draft.notas) == ("claude-opus-5", 30, "import inicial")
        assert [s.chave for s in rt.studio.list_sections(rt.org_id, draft.id)] == ["identidade", "estilo"]
        # compiled_hash refreshed = the compile of the draft as imported.
        compiled = compile_version(rt.studio, StoreKnowledgeCatalog(rt.knowledge), rt.org_id, agent, draft)
        assert draft.compiled_hash == compiled.hash
        doc = rt.knowledge.get_document_by_slug(rt.org_id, agent.id, "ganchos")
        assert doc.proveniencia == {"autor": "Autor", "pagina": 12}

    def test_reimport_is_idempotent(self, rt):
        first = _import(rt).json()
        agent = rt.studio.get_agent(rt.org_id, "isa")
        doc = rt.knowledge.get_document_by_slug(rt.org_id, agent.id, "ganchos")
        revisions = len(rt.knowledge.list_revisions(rt.org_id, agent.id, doc.id))
        hash_before = rt.studio.get_draft(rt.org_id, agent.id).compiled_hash

        second = _import(rt).json()
        assert second["agente"] == {"criado": False}
        assert second["rascunho"]["version_id"] == first["rascunho"]["version_id"]
        assert second["conhecimento"] == {"colecoes_criadas": 0, "documentos_criados": 0, "documentos_atualizados": 0, "documentos_inalterados": 2}
        assert second["evals"] == {"criados": 0, "atualizados": 0}
        assert second["clientes"] == {"criados": 0}
        assert len(rt.knowledge.list_revisions(rt.org_id, agent.id, doc.id)) == revisions
        assert rt.studio.get_draft(rt.org_id, agent.id).compiled_hash == hash_before
        client = rt.studio.list_clients(rt.org_id, agent.id)[0]
        assert len(rt.studio.list_client_entries(rt.org_id, client.id)) == 1

    def test_changed_content_updates_and_replaces_the_draft(self, rt):
        _import(rt)
        body = copy.deepcopy(BUNDLE)
        body["secoes"] = [body["secoes"][0]]
        body["conhecimento"][0]["documentos"][0]["conteudo"] = "Conteúdo A v2"
        body["evals"][0]["titulo"] = "Reels v2"
        out = _import(rt, body).json()
        assert out["conhecimento"]["documentos_atualizados"] == 1
        assert out["conhecimento"]["documentos_inalterados"] == 1
        assert out["evals"] == {"criados": 0, "atualizados": 1}
        agent = rt.studio.get_agent(rt.org_id, "isa")
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        assert [s.chave for s in rt.studio.list_sections(rt.org_id, draft.id)] == ["identidade"]

    def test_existing_agent_without_draft_gets_one_from_active_and_active_is_untouched(self, rt):
        agent, v1 = rt.make_agent(secoes=[("antiga", "Antiga", "texto publicado")])
        out = _import(rt).json()
        assert out["agente"] == {"criado": False}
        draft = rt.studio.get_draft(rt.org_id, agent.id)
        assert draft.based_on_version_id == v1.id
        assert [s.chave for s in rt.studio.list_sections(rt.org_id, v1.id)] == ["antiga"]
        assert rt.studio.get_active_version(rt.org_id, agent.id).id == v1.id

    def test_dry_run_plans_with_zero_writes(self, rt):
        out = _import(rt, dry_run=True).json()
        assert out["dry_run"] is True and out["agente"] == {"criado": True}
        assert out["conhecimento"]["documentos_criados"] == 2
        with pytest.raises(Exception):
            rt.studio.get_agent(rt.org_id, "isa")

    def test_dry_run_on_existing_agent_calls_no_write_method(self, rt):
        _import(rt)
        body = copy.deepcopy(BUNDLE)
        body["conhecimento"][0]["documentos"][0]["conteudo"] = "mudou"
        reads = {"list_agents", "get_draft", "list_collections", "find_document_by_slug", "list_cases", "list_clients"}
        out = import_bundle(
            AgentBundle.model_validate(body), org_id=rt.org_id, key="isa", user_id=rt.user_id, dry_run=True,
            definitions=ReadOnlyProxy(rt.studio, reads), knowledge=ReadOnlyProxy(rt.knowledge, reads),
            evals=ReadOnlyProxy(rt.evals, reads), catalog=None,
        )
        assert out["conhecimento"]["documentos_atualizados"] == 1
        assert out["rascunho"]["version_id"] is not None

    def test_dry_run_counts_an_archived_document_as_existing(self, rt):
        _import(rt)
        agent = rt.studio.get_agent(rt.org_id, "isa")
        doc = rt.knowledge.get_document_by_slug(rt.org_id, agent.id, "ganchos")
        rt.knowledge.update_document(rt.org_id, agent.id, doc.id, author_id=rt.user_id, ativo=False)
        out = _import(rt, dry_run=True).json()
        assert out["conhecimento"]["documentos_criados"] == 0
        assert out["conhecimento"]["documentos_inalterados"] == 2

    def test_slug_living_in_another_collection_is_a_409(self, rt):
        _import(rt)
        body = copy.deepcopy(BUNDLE)
        body["conhecimento"].append({"slug": "outra", "nome": "Outra", "documentos": [
            body["conhecimento"][0]["documentos"].pop(0)]})
        resp = _import(rt, body)
        assert resp.status_code == 409
        assert resp.json()["code"] == "slug_in_other_collection"

    def test_the_read_only_proxy_really_refuses_writes(self, rt):
        with pytest.raises(WriteForbidden):
            ReadOnlyProxy(rt.studio, set()).create_studio_agent(rt.org_id, "x", "X", None)


class TestRefusals:
    @pytest.mark.parametrize(
        "mutate,path_fragment",
        [
            (lambda b: b["skills"][0]["arquivos"][0].update(extra=1), ["skills", 0, "arquivos", 0, "extra"]),
            (lambda b: b.update(desconhecido=True), ["desconhecido"]),
            (lambda b: b["versao"]["tool_policy"].update(web_search="true"), ["versao", "tool_policy", "web_search"]),
            (lambda b: b["versao"].update(model="gpt-4o"), ["versao", "model"]),
            (lambda b: b["skills"][0]["arquivos"][0].update(caminho="references/../segredo.md"), ["skills", 0, "arquivos", 0, "caminho"]),
            (lambda b: b["secoes"][0].update(chave="Nao Slug"), ["secoes", 0, "chave"]),
            (lambda b: b["conhecimento"][0]["documentos"][0]["proveniencia"].update(site="x"), ["proveniencia", "site"]),
        ],
    )
    def test_strict_validation_names_the_json_path(self, rt, mutate, path_fragment):
        body = copy.deepcopy(BUNDLE)
        mutate(body)
        resp = _import(rt, body)
        assert resp.status_code == 422
        assert all(str(p) in resp.text for p in path_fragment)
        with pytest.raises(Exception):
            rt.studio.get_agent(rt.org_id, "isa")

    def test_duplicate_keys_in_the_bundle(self, rt):
        body = copy.deepcopy(BUNDLE)
        body["secoes"].append(dict(body["secoes"][0]))
        assert _import(rt, body).status_code == 422

    def test_key_mismatch(self, rt):
        resp = _import(rt, key="outro")
        assert resp.status_code == 422
        assert resp.json()["code"] == "key_mismatch"

    @pytest.mark.parametrize("key", ["julia", "one-chat"])
    def test_reserved_keys_are_refused(self, rt, key):
        body = copy.deepcopy(BUNDLE)
        body["agente"]["key"] = key
        resp = _import(rt, body, key=key)
        assert resp.status_code == 409
        assert resp.json()["code"] == "not_studio_agent"

    def test_legacy_agent_is_never_converted(self, rt):
        rt.studio.add_legacy_agent(rt.org_id, "isa", "Isa")
        resp = _import(rt)
        assert resp.status_code == 409
        assert resp.json()["code"] == "not_studio_agent"
        assert rt.studio.get_agent(rt.org_id, "isa").definition_mode == "legacy"

    def test_member_is_forbidden(self, rt):
        seed_org_role(rt.client, role="member")
        assert _import(rt).status_code == 403

    def test_unauthenticated_is_401(self, rt):
        resp = rt.client.raw().post("/api/studio/agents/isa/import", json=BUNDLE)
        assert resp.status_code == 401

    def test_body_cap_is_raised_for_import_only(self, rt):
        big = copy.deepcopy(BUNDLE)
        big["conhecimento"][0]["documentos"] = [
            {"slug": f"grande-{i}", "titulo": "G", "tipo": "fonte", "conteudo": "x" * 700_000} for i in range(3)
        ]  # ~2.1 MB body
        assert _import(rt, big).status_code == 200  # > 1 MB default, < 25 MB
        agent_key = "isa"
        resp = rt.put(
            f"/api/studio/agents/{agent_key}/draft/sections",
            json={"secoes": [{"chave": "a", "titulo": "A", "ordem": 1, "conteudo": "x" * (2 * 1024 * 1024), "ativo": True}]},
        )
        assert resp.status_code == 413
