"""The channel turn's skill source over the shared library (A-RT's ``SkillFonte`` interface): it opens the
PINNED version, never the latest; the pins' tool gates reach ``obrigatoria_para``; no pins = the version's own
skills. Skill text is TEST DATA."""
from __future__ import annotations

import asyncio
from uuid import uuid4

from app.channels.tool_registry import SkillsDaVersao
from app.stores.skills_biblioteca import FakeSkillsBibliotecaStore
from app.studio.skills_fonte import FonteDaBiblioteca, skills_factory

ADMIN, ORG, AV = uuid4(), uuid4(), uuid4()


def _lib():
    st = FakeSkillsBibliotecaStore()
    s = st.criar_skill("qualificar-lead", "Q", None)
    v1 = st.criar_rascunho(s.id, None, None)
    st.salvar_rascunho(v1, {"descricao_modelo": "quando", "corpo": "corpo UM"})
    st.salvar_arquivo(v1, "ref/a.md", "A", "arquivo um")
    st.publicar(v1, ADMIN)
    st.fixar_ref(ORG, AV, v1, ["avaliar_lead"], 0)
    v2 = st.criar_rascunho(s.id, None, v1)
    st.salvar_rascunho(v2, {"corpo": "corpo DOIS"})
    st.publicar(v2, ADMIN)
    return st


def run(coro):
    return asyncio.run(coro)


def test_it_opens_the_pinned_version_never_the_latest():
    f = FonteDaBiblioteca(_lib(), AV)
    out = run(f.abrir("qualificar-lead"))
    assert out["corpo"] == "corpo UM" and out["arquivos"] == [{"caminho": "ref/a.md", "titulo": "A"}]
    assert run(f.ler_arquivo("qualificar-lead", "ref/a.md"))["conteudo"] == "arquivo um"
    assert run(f.ler_arquivo("qualificar-lead", "x.md"))["erro"] == "arquivo_inexistente"
    assert run(f.abrir("outra"))["erro"] == "skill_inexistente"


def test_the_pins_gates_become_obrigatoria_para():
    assert dict(FonteDaBiblioteca(_lib(), AV).obrigatoria_para()) == {"qualificar-lead": ["avaliar_lead"]}


def test_unknown_skills_fall_back_to_the_versions_own_and_gates_merge():
    class Propria:
        async def abrir(self, nome):
            return {"nome": nome, "corpo": "propria"}

        async def ler_arquivo(self, nome, caminho):
            return {"erro": "arquivo_inexistente"}

        def obrigatoria_para(self):
            return {"propria": ["handoff"], "qualificar-lead": ["registrar_perfil"]}

    f = FonteDaBiblioteca(_lib(), AV, Propria())
    assert run(f.abrir("propria"))["corpo"] == "propria"
    assert run(f.abrir("qualificar-lead"))["corpo"] == "corpo UM"
    assert dict(f.obrigatoria_para()) == {"propria": ["handoff"], "qualificar-lead": ["registrar_perfil", "avaliar_lead"]}


def test_the_factory_serves_the_library_only_when_the_version_pins_any():
    lib = _lib()
    fac = skills_factory(lambda: lib)
    assert isinstance(fac(None, ORG, uuid4(), AV), FonteDaBiblioteca)
    assert isinstance(fac(None, ORG, uuid4(), uuid4()), SkillsDaVersao)
