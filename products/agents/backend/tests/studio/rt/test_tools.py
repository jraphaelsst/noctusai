"""The studio MCP tools (Agent Studio §E3 + security review of wave 1):
server-side binding, active skills of the pinned version only, exact
``caminho``, knowledge-off ⇒ not registered, bounded inputs/outputs, and
errors as payloads."""
from __future__ import annotations

import json
from uuid import uuid4

import pytest

from app.stores.studio_definitions import SectionInput
from app.stores.studio_knowledge import CollectionInput, DocumentInput, FakeStudioKnowledgeStore
from app.studio.tools import MAX_RESULT_CHARS, studio_allowed_tools, studio_tool_specs
from tests.studio.rt.fakes import FakeStudioStore

pytestmark = pytest.mark.asyncio

ORG = uuid4()
USER = uuid4()


def _payload(result):
    text = result["content"][0]["text"]
    assert len(text) <= MAX_RESULT_CHARS
    return json.loads(text)


class _World:
    def __init__(self, *, knowledge_enabled=True, big_corpo=False):
        self.defs = FakeStudioStore()
        self.kb = FakeStudioKnowledgeStore()
        self.agent = self.defs.create_studio_agent(ORG, "isa", "Isa", None)
        v = self.defs.create_draft(ORG, self.agent.id, None, USER)
        self.defs.replace_sections(ORG, v.id, [SectionInput(chave="a", titulo="A", ordem=1, conteudo="x")])
        corpo = "PASSO " * 9000 if big_corpo else "Passo 1: faça o roteiro."
        self.roteiro = self.defs.create_skill(ORG, v.id, nome="roteiro-reels", descricao="Roteiros", corpo=corpo)
        self.defs.upsert_skill_file(ORG, self.roteiro.id, caminho="references/arquiteturas.md", titulo="Arq", conteudo="ARQ")
        self.defs.create_skill(ORG, v.id, nome="desligada", descricao="off", corpo="nunca", ativo=False)
        self.v1 = self.defs.publish_version(ORG, v.id, USER, None, "publicação de teste do BE-RT")
        # A newer draft with a skill the pinned v1 does NOT have.
        v2 = self.defs.create_draft(ORG, self.agent.id, self.v1.id, USER)
        self.defs.create_skill(ORG, v2.id, nome="so-no-rascunho", descricao="d", corpo="c")
        col = self.kb.create_collection(ORG, self.agent.id, CollectionInput(slug="audience", nome="Audiência", tag="AU"))
        paragraphs = "\n\n".join(("P%d " % i) + ("a" * 8000) for i in range(3))
        self.kb.create_document(
            ORG, self.agent.id, col.id,
            DocumentInput(slug="guia-longo", titulo="Guia de ganchos", tipo="fonte", conteudo=paragraphs, resumo="ganchos"),
            author_id=USER,
        )
        self.specs = {
            s.name: s
            for s in studio_tool_specs(
                org_id=ORG, agent_id=self.agent.id, version_id=self.v1.id,
                knowledge_enabled=knowledge_enabled, definitions=self.defs, knowledge=self.kb,
            )
        }

    async def call(self, name, **args):
        return _payload(await self.specs[name].handler(args))


class TestSkills:
    async def test_abrir_skill_returns_body_and_file_list(self):
        w = _World()
        out = await w.call("abrir_skill", nome="roteiro-reels")
        assert out["corpo"] == "Passo 1: faça o roteiro."
        assert out["arquivos"] == [{"caminho": "references/arquiteturas.md", "titulo": "Arq"}]

    async def test_unknown_or_inactive_skill_lists_only_active_ones_of_the_pinned_version(self):
        w = _World()
        for nome in ("nao-existe", "desligada", "so-no-rascunho"):
            out = await w.call("abrir_skill", nome=nome)
            assert out == {"erro": "skill_inexistente", "disponiveis": ["roteiro-reels"]}

    async def test_ler_arquivo_skill_is_an_exact_path_match(self):
        w = _World()
        ok = await w.call("ler_arquivo_skill", nome="roteiro-reels", caminho="references/arquiteturas.md")
        assert ok["conteudo"] == "ARQ"
        for caminho in ("arquiteturas.md", "references/../references/arquiteturas.md", "REFERENCES/arquiteturas.md"):
            out = await w.call("ler_arquivo_skill", nome="roteiro-reels", caminho=caminho)
            assert out == {"erro": "arquivo_inexistente", "disponiveis": ["references/arquiteturas.md"]}

    async def test_file_of_an_inactive_skill_is_unreachable(self):
        w = _World()
        out = await w.call("ler_arquivo_skill", nome="desligada", caminho="x.md")
        assert out["erro"] == "skill_inexistente"

    async def test_oversize_body_is_cut_explicitly_under_the_cap(self):
        w = _World(big_corpo=True)
        out = await w.call("abrir_skill", nome="roteiro-reels")
        assert out["truncado"] is True and "aviso" in out
        assert out["corpo"].startswith("PASSO ")


class TestKnowledge:
    async def test_kb_buscar_uses_the_store_search(self):
        w = _World()
        out = await w.call("kb_buscar", consulta="ganchos")
        assert [r["slug"] for r in out["resultados"]] == ["guia-longo"]
        assert set(out["resultados"][0]) == {"slug", "titulo", "colecao", "tag", "tipo", "trecho"}

    async def test_kb_buscar_bounds(self):
        w = _World()
        assert (await w.call("kb_buscar", consulta="  "))["erro"] == "consulta_vazia"
        assert (await w.call("kb_buscar", consulta="x" * 513))["erro"] == "consulta_muito_longa"
        assert (await w.call("kb_buscar", consulta="ganchos", limite="muitos"))["erro"] == "limite_invalido"

    async def test_kb_buscar_clamps_limite(self):
        seen = []

        class SpyKb(FakeStudioKnowledgeStore):
            def search(self, org_id, agent_id, query, *, colecao=None, limite=8):
                seen.append(limite)
                return []

        specs = {
            s.name: s for s in studio_tool_specs(
                org_id=ORG, agent_id=uuid4(), version_id=uuid4(), knowledge_enabled=True,
                definitions=FakeStudioStore(), knowledge=SpyKb(),
            )
        }
        await specs["kb_buscar"].handler({"consulta": "a", "limite": 500})
        await specs["kb_buscar"].handler({"consulta": "a", "limite": -3})
        assert seen == [20, 1]

    async def test_kb_ler_pages_and_errors(self):
        w = _World()
        p1 = await w.call("kb_ler", slug="guia-longo")
        assert (p1["parte"], p1["total_partes"], p1["tag"], p1["colecao"]) == (1, 2, "AU", "audience")
        assert len(json.dumps(p1, ensure_ascii=False)) <= MAX_RESULT_CHARS
        assert (await w.call("kb_ler", slug="guia-longo", parte=0))["parte"] == 1  # clamped
        assert await w.call("kb_ler", slug="guia-longo", parte=9) == {"erro": "parte_inexistente", "total_partes": 2}
        assert await w.call("kb_ler", slug="nao-existe") == {"erro": "documento_inexistente"}

    async def test_knowledge_off_means_the_kb_tools_do_not_exist(self):
        w = _World(knowledge_enabled=False)
        assert set(w.specs) == {"abrir_skill", "ler_arquivo_skill"}
        assert "mcp__studio__kb_buscar" not in studio_allowed_tools(knowledge=False, web_search=True)


async def test_a_store_failure_is_a_payload_never_an_exception():
    class Boom(FakeStudioStore):
        def list_skills(self, org_id, version_id):
            raise RuntimeError("db exploded: secret detail")

    specs = {
        s.name: s for s in studio_tool_specs(
            org_id=ORG, agent_id=uuid4(), version_id=uuid4(), knowledge_enabled=True,
            definitions=Boom(), knowledge=FakeStudioKnowledgeStore(),
        )
    }
    out = _payload(await specs["abrir_skill"].handler({"nome": "x"}))
    assert out == {"erro": "falha_interna"}


async def test_model_arguments_cannot_redirect_the_bound_ids():
    """Extra arguments naming ids/orgs are ignored — the closure's ids win."""
    w = _World()
    out = await w.call("abrir_skill", nome="so-no-rascunho", version_id=str(uuid4()), org_id=str(uuid4()))
    assert out["erro"] == "skill_inexistente"
