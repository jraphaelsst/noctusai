"""The compiler's shared-skill extension point (Julia v2 A-SKILLS): pinned library skills join the skills
index and the on-demand layer, gate tools, and are hash-covered ONLY when present (a version without pins keeps
the hash it had). Skill text here is TEST DATA."""
from __future__ import annotations

from dataclasses import replace
from uuid import uuid4

from app.studio.compiler import compile_prompt, prompt_hash
from app.studio.models import (
    CompileInput,
    ConteudoBundle,
    FerramentaData,
    SectionData,
    SkillData,
    TextoData,
    VersionBundle,
)
from app.studio.skills_contract import SkillRef

TEXTOS = (
    TextoData("compilador.titulo_ferramentas", "Tools"),
    TextoData("compilador.ferramenta_linha.web_desativada", "- sem web"),
    TextoData("compilador.ferramenta_linha.conhecimento_desativada", "- sem kb"),
    TextoData("compilador.titulo_skills", "Skills"),
    TextoData("compilador.skills_intro", "Abra a skill antes de agir."),
    TextoData("compilador.ferramenta_linha.skills_ativada", "- skills ligadas"),
)
VID = uuid4()


def _inp(refs=(), skills=(), textos=TEXTOS, ferramentas=()) -> CompileInput:
    v = VersionBundle(
        model="m", effort="medium", max_turns=8, idioma="pt-BR", tool_policy={"web_search": False, "knowledge": False},
        secoes=(SectionData(None, "persona", "Persona", 10, "Atende."),), skills=tuple(skills), skill_refs=tuple(refs),
        conteudo=ConteudoBundle(textos=tuple(textos), ferramentas=tuple(ferramentas)), provider="openai",
    )
    return CompileInput(agent_nome="J", version=v, knowledge=(), client=None, tool_policy=dict(v.tool_policy))


def _ref(key="qualificar", vid=VID, para=("handoff",), desc="quando qualificar", **kw) -> SkillRef:
    return SkillRef(key, vid, tuple(para), descricao=desc, **kw)


def _codes(c):
    return {w.codigo for w in c.avisos if w.bloqueante}


def test_a_pinned_skill_is_in_the_index_and_the_on_demand_layer_not_its_body():
    c = compile_prompt(_inp([_ref(corpo_chars=400, arquivos=(("ref/a.md", 40),))], ferramentas=(FerramentaData("handoff", "Passa."),)))
    assert "# Skills" in c.texto and "- `qualificar` — quando qualificar" in c.texto
    assert "- skills ligadas" in c.texto  # the tools block states skills are on
    od = {(i.tipo, i.nome, i.caminho): i for i in c.sob_demanda}
    assert od[("skill", "qualificar", None)].gatilho == 'abrir_skill("qualificar")' and od[("skill", "qualificar", None)].chars == 400
    assert od[("arquivo_skill", "qualificar", "ref/a.md")].gatilho == 'ler_arquivo_skill("qualificar", "ref/a.md")'
    assert _codes(c) == set()


def test_required_skill_texts_apply_when_only_pinned_skills_exist():
    sem_intro = tuple(t for t in TEXTOS if t.chave != "compilador.skills_intro")
    assert "texto_ausente" in _codes(compile_prompt(_inp([_ref()], textos=sem_intro)))


def test_the_hash_covers_the_pin_its_version_and_its_gates():
    base = compile_prompt(_inp([_ref()])).hash
    assert base == compile_prompt(_inp([_ref()])).hash  # deterministic
    assert base != compile_prompt(_inp([_ref(vid=uuid4())])).hash       # another library version
    assert base != compile_prompt(_inp([_ref(para=("handoff", "x_y"))])).hash  # another gate
    assert base != compile_prompt(_inp([_ref(desc="outra")])).hash
    assert base != compile_prompt(_inp([])).hash                        # unpinned


def test_a_version_without_pins_keeps_its_hash():
    c = compile_prompt(_inp())
    legacy = compile_prompt(replace(_inp(), version=replace(_inp().version, conteudo=None)))
    assert c.hash.startswith("sha256:") and legacy.hash == prompt_hash(legacy.texto)
    from app.studio.compiler import hash_payload
    assert "skill_refs" not in hash_payload(c.texto, _inp().version.conteudo, _inp().version, None)


def test_pin_order_is_by_ordem_then_key_and_independent_of_input_order():
    a, b = _ref("zeta", ordem=1), _ref("alfa", vid=uuid4(), ordem=2)
    one, two = compile_prompt(_inp([a, b])), compile_prompt(_inp([b, a]))
    assert one.texto == two.texto and one.hash == two.hash
    assert one.texto.index("`zeta`") < one.texto.index("`alfa`")


def test_a_pin_clashing_with_the_agents_own_skill_is_blocking():
    own = SkillData(None, "qualificar", "d", "corpo")
    assert "skill_duplicada" in _codes(compile_prompt(_inp([_ref()], skills=[own])))


def test_a_pinned_skill_satisfies_a_tools_obrigatoria_skill():
    f = FerramentaData("handoff", "Passa.", obrigatoria_skill="qualificar")
    assert "skill_exigida_inexistente" not in _codes(compile_prompt(_inp([_ref()], ferramentas=(f,))))
    assert "skill_exigida_inexistente" in _codes(compile_prompt(_inp([], ferramentas=(f,))))


def test_a_gate_on_an_unknown_tool_and_an_empty_description_block():
    assert "ferramenta_desconhecida" in _codes(compile_prompt(_inp([_ref(para=("nao_existe",))])))
    assert "skill_sem_descricao" in _codes(compile_prompt(_inp([_ref(desc=" ")])))
