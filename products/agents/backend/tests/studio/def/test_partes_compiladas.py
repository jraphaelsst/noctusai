"""Per-part hashes (eval consolidation): the completeness invariant -- ANY input change that moves ``compiled_hash`` moves
at least one part -- plus the granularity the consolidation relies on (a section edit moves only that section)."""
from __future__ import annotations

import importlib
from dataclasses import replace

from app.studio.compiler import compile_prompt
from app.studio.models import (
    CompileInput, ConteudoBundle, DecisaoData, FerramentaData, OpcaoDecisao, SectionData, SkillData, SpecDefData, TextoData,
)
from app.studio.partes import PARTES_GLOBAIS

_base = importlib.import_module("tests.studio.def.test_compiler_conteudo")  # `def` is a keyword: no plain import
_inp = _base._inp


def _two_sections(**kw) -> CompileInput:
    inp = _inp(**kw)
    v = replace(inp.version, secoes=(
        SectionData(None, "persona", "Persona", 10, "Atende bem."), SectionData(None, "regras", "Regras", 20, "Seja breve.")),
        skills=(SkillData(None, "qualificar", "Qualifica", "corpo", 1),))
    return replace(inp, version=v)


def _moved(a: CompileInput, b: CompileInput) -> set[str]:
    ca, cb = compile_prompt(a), compile_prompt(b)
    assert ca.partes and cb.partes
    return {k for k in set(ca.partes) | set(cb.partes) if ca.partes.get(k) != cb.partes.get(k)}


def test_identical_compiles_have_identical_parts():
    assert compile_prompt(_two_sections()).partes == compile_prompt(_two_sections()).partes


def test_a_section_edit_moves_only_that_section():
    base = _two_sections()
    v = replace(base.version, secoes=(base.version.secoes[0], replace(base.version.secoes[1], conteudo="Seja longo.")))
    assert _moved(base, replace(base, version=v)) == {"secao:regras"}


def test_a_tool_edit_moves_only_that_tool():
    base = _two_sections()
    c = base.version.conteudo
    nova = ConteudoBundle(textos=c.textos, ferramentas=(replace(c.ferramentas[0], descricao="Outra."),), decisoes=c.decisoes, specs=c.specs)
    assert _moved(base, replace(base, version=replace(base.version, conteudo=nova))) == {"ferramenta:handoff"}


def test_a_skill_edit_moves_only_that_skill():
    base = _two_sections()
    sk = replace(base.version.skills[0], corpo="outro corpo")
    assert _moved(base, replace(base, version=replace(base.version, skills=(sk,)))) == {"skill:qualificar"}


def test_model_change_moves_a_global_part():
    base = _two_sections()
    assert _moved(base, replace(base, version=replace(base.version, model="claude-haiku-4-5"))) == {"modelo"}
    assert "modelo" in PARTES_GLOBAIS


def test_section_order_moves_the_global_structure_part():
    base = _two_sections()
    s0, s1 = base.version.secoes
    swapped = replace(base, version=replace(base.version, secoes=(replace(s0, ordem=30), s1)))
    assert "estrutura" in _moved(base, swapped)


def test_completeness_every_hash_covered_mutation_moves_some_part():
    base = _two_sections()
    v, c = base.version, base.version.conteudo
    mutations = {
        "texto": replace(base, version=replace(v, conteudo=replace(c, textos=c.textos + (TextoData("extra.chave", "x"),)))),
        "decisao": replace(base, version=replace(v, conteudo=replace(c, decisoes=(DecisaoData("d", "D", "outra", (OpcaoDecisao("a", "A", True),)),)))),
        "spec": replace(base, version=replace(v, conteudo=replace(c, specs=(SpecDefData("agencia", "Outra"),)))),
        "effort": replace(base, version=replace(v, effort="high")),
        "max_turns": replace(base, version=replace(v, max_turns=3)),
        "idioma": replace(base, version=replace(v, idioma="en")),
        "tool_policy": replace(base, version=replace(v, tool_policy={"web_search": True, "knowledge": False}),
                               tool_policy={"web_search": True, "knowledge": False}),
        "extras": replace(base, extras={"padrao": "v2"}),
        "secao_inativa->ativa": replace(base, version=replace(v, secoes=v.secoes + (SectionData(None, "nova", "Nova", 30, "n"),))),
    }
    for nome, mutado in mutations.items():
        h_base, h_mut = compile_prompt(base), compile_prompt(mutado)
        assert h_base.hash != h_mut.hash, f"{nome}: the mutation must move compiled_hash"
        assert _moved(base, mutado), f"{nome}: moved compiled_hash but NO part -- part hashes would miss a change"


def test_legacy_agent_uses_the_text_as_a_global_part():
    inp = _inp(conteudo=None)
    a = compile_prompt(inp)
    assert "texto_legado" in a.partes and "texto_legado" in PARTES_GLOBAIS
