"""Skill texts accept ``{{org.chave}}`` placeholders, resolved FOR THE ORG with the same resolver as the prompt
sections (A-polish #10): the version's own skills AND pinned library skills, body and reference files, at the moment
the model opens them; and the compiler's spec-usage check sees what a pinned skill uses."""
from __future__ import annotations

import asyncio
from dataclasses import replace
from uuid import UUID

from noctusai_lib.integrations.llm import FakeProvider

from app.channels.tool_registry import SkillsComSpecs
from app.stores.studio_definitions_conteudo import SpecDefInput
from app.studio.compiler import compile_prompt
from app.studio.skills_contract import SkillRef
from tests.channels.conftest import turn_body
from tests.channels.julia_v2 import PLAT_ORG
from tests.channels.test_julia_v2_e2e import call, say, step, tool_results


class _Fonte:
    async def abrir(self, nome):
        return {"nome": nome, "descricao": "Para {{org.agencia}}.", "corpo": "Fale da {{org.agencia}}.", "arquivos": []}

    async def ler_arquivo(self, nome, caminho):
        return {"caminho": caminho, "titulo": "Tabela {{org.agencia}}", "conteudo": "Regiões: {{org.regioes}}"}

    def obrigatoria_para(self):
        return {"x": ["oferecer_imoveis"]}


def test_the_wrapper_resolves_every_model_visible_field_and_keeps_the_gates():
    s = SkillsComSpecs(_Fonte(), {"agencia": "Aurora", "regioes": "Moema"})
    aberta = asyncio.run(s.abrir("ofertar"))
    assert (aberta["descricao"], aberta["corpo"], aberta["nome"]) == ("Para Aurora.", "Fale da Aurora.", "ofertar")
    arq = asyncio.run(s.ler_arquivo("ofertar", "ref.md"))
    assert (arq["titulo"], arq["conteudo"], arq["caminho"]) == ("Tabela Aurora", "Regiões: Moema", "ref.md")
    assert s.obrigatoria_para() == {"x": ["oferecer_imoveis"]}


def test_an_org_turn_opens_the_skill_with_the_orgs_values(chan):
    from tests.studio.rt.fakes import publish

    studio = chan.rt.studio
    chan.seed_agent(publish=False)
    d = studio.get_platform_definition("julia")
    draft = studio.get_draft(PLAT_ORG, d.id)
    [sk] = [s for s in studio.list_skills(PLAT_ORG, draft.id) if s.nome == "qualificar-lead"]
    studio.update_skill(PLAT_ORG, sk.id, {"corpo": "Apresente a {{org.agencia}} e pergunte o prazo."})
    studio.replace_spec_defs(PLAT_ORG, draft.id, [SpecDefInput("agencia", "Agência")])
    publish(studio, PLAT_ORG, d, draft.id, UUID(int=7))
    studio.upsert_org_specs(chan.org_id, "julia", {"agencia": "Imobiliária Aurora"})
    chan.use_provider(FakeProvider(tool_responses=[step(call("abrir_skill", nome="qualificar-lead")), say("Oi! Prazo?")]))
    body = chan.turn(turn_body("Oi", ids=["s1"])).json()
    assert body["status"] == "respondido", body
    [aberta] = [r for r in tool_results(chan.provider) if r.get("nome") == "qualificar-lead"]
    assert aberta["corpo"] == "Apresente a Imobiliária Aurora e pergunte o prazo."
    assert "{{org." not in str(tool_results(chan.provider))


def test_a_pinned_library_skill_counts_its_placeholders_for_the_spec_check():
    import importlib

    _inp = importlib.import_module("tests.studio.def.test_compiler_conteudo")._inp

    ref = SkillRef("ofertar", UUID(int=3), descricao="Quando ofertar na {{org.agencia}}.", corpo_chars=10,
                   placeholders=("agencia", "regioes"))
    base = _inp(secao="Sem placeholder.")
    c = compile_prompt(replace(base, version=replace(base.version, skill_refs=(ref,))))
    codigos = {w.codigo for w in c.avisos}
    assert "spec_nao_usada" not in codigos            # agencia is used by the pinned skill
    assert "spec_nao_declarada" in codigos            # regioes is used by it and never declared
    org = compile_prompt(replace(base, version=replace(base.version, skill_refs=(ref,)), org_specs={"agencia": "Aurora"}))
    assert "`ofertar` — Quando ofertar na Aurora." in org.texto  # the index line is resolved for the org
