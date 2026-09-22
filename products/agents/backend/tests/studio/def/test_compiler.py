"""``compile_prompt`` (contract §C): layout, manifest offsets, on-demand layer,
warnings, determinism and hash sensitivity. Pure — no IO, no fixtures."""
from __future__ import annotations

import hashlib
import math
from dataclasses import replace
from uuid import UUID

import pytest

from app.studio.compiler import compile_prompt
from app.studio.models import (
    ClientBundle,
    ClientEntryData,
    CollectionSummary,
    CompileInput,
    SectionData,
    SkillData,
    SkillFileRef,
    VersionBundle,
)

SEC_A = UUID("00000000-0000-0000-0000-00000000000a")
SEC_B = UUID("00000000-0000-0000-0000-00000000000b")
CLIENT_ID = UUID("00000000-0000-0000-0000-0000000000c1")

POLICY = {"web_search": True, "knowledge": True}


def _version(**kw) -> VersionBundle:
    base = dict(
        model="claude-opus-5",
        effort="high",
        max_turns=40,
        idioma="pt-BR",
        tool_policy=dict(POLICY),
        secoes=(
            SectionData(id=SEC_B, chave="regras", titulo="Regras", ordem=20, conteudo="  Seja direta.  \n"),
            SectionData(id=SEC_A, chave="identidade", titulo="Identidade", ordem=10, conteudo="Você é uma estrategista."),
        ),
        skills=(
            SkillData(
                id=None, nome="roteiro-reels", descricao="Roteiros de reels.", corpo="Passo 1...", ordem=10,
                arquivos=(SkillFileRef(caminho="references/b.md", titulo="B", chars=40),
                          SkillFileRef(caminho="references/a.md", titulo=None, chars=9)),
            ),
            SkillData(id=None, nome="calendario", descricao="Calendário editorial.", corpo="Corpo", ordem=5),
        ),
    )
    base.update(kw)
    return VersionBundle(**base)


def _input(version=None, knowledge=(), client=None, policy=None) -> CompileInput:
    version = version or _version()
    return CompileInput(
        agent_nome="Agente",
        version=version,
        knowledge=tuple(knowledge),
        client=client,
        tool_policy=dict(policy if policy is not None else version.tool_policy),
    )


KNOWLEDGE = (
    CollectionSummary(slug="publico", nome="Público", tag="AU", descricao="Pesquisas de audiência", doc_count=12, ordem=20),
    CollectionSummary(slug="cases", nome="Cases", tag=None, descricao="", doc_count=1, ordem=10),
)


class TestLayout:
    def test_sections_first_by_ordem_then_auto_blocks(self):
        out = compile_prompt(_input(knowledge=KNOWLEDGE))
        heads = [line for line in out.texto.split("\n") if line.startswith("# ")]
        assert heads == ["# Identidade", "# Regras", "# Skills", "# Base de conhecimento", "# Ferramentas"]

    def test_exact_section_block_and_separator(self):
        out = compile_prompt(_input())
        assert out.texto.startswith("# Identidade\n\nVocê é uma estrategista.\n\n# Regras\n\nSeja direta.\n\n# Skills")
        assert not out.texto.endswith("\n")

    def test_skills_block_exact_text_ordered_by_ordem(self):
        out = compile_prompt(_input())
        expected = (
            "# Skills\n\n"
            "Skills são procedimentos especializados. Quando o pedido corresponder à descrição de uma skill,\n"
            "chame `abrir_skill` com o nome dela ANTES de responder e siga as instruções que ela devolver.\n"
            "Arquivos de referência de uma skill são lidos com `ler_arquivo_skill`.\n\n"
            "- `calendario` — Calendário editorial.\n"
            "- `roteiro-reels` — Roteiros de reels."
        )
        assert expected in out.texto

    def test_knowledge_block_exact_text_ordered_by_ordem(self):
        out = compile_prompt(_input(knowledge=KNOWLEDGE))
        expected = (
            "# Base de conhecimento\n\n"
            "Use `kb_buscar` para encontrar documentos e `kb_ler` para ler um documento pelo slug.\n"
            "Cite a origem com a tag da coleção (ex.: [AU]) quando usar um conteúdo.\n\n"
            "- `cases` — Cases (1 documento)\n"
            "- `publico` [AU] — Público: Pesquisas de audiência (12 documentos)"
        )
        assert expected in out.texto

    def test_no_skills_block_without_active_skills(self):
        v = _version(skills=(SkillData(id=None, nome="x", descricao="d", corpo="c", ativo=False),))
        out = compile_prompt(_input(version=v))
        assert "# Skills" not in out.texto
        assert "- Skills:" not in out.texto

    def test_no_knowledge_block_when_policy_off_or_empty(self):
        off = compile_prompt(_input(knowledge=KNOWLEDGE, policy={"web_search": True, "knowledge": False}))
        assert "# Base de conhecimento" not in off.texto
        assert "- Base de conhecimento: desativada." in off.texto
        empty = compile_prompt(_input(knowledge=()))
        assert "# Base de conhecimento" not in empty.texto

    def test_tools_block_states_each_family(self):
        out = compile_prompt(_input(policy={"web_search": False, "knowledge": True}))
        tools = out.texto[out.texto.index("# Ferramentas"):]
        assert tools == (
            "# Ferramentas\n\n"
            "- Pesquisa na web: desativada — não há acesso à web nesta conversa.\n"
            "- Base de conhecimento: ativada (`kb_buscar`, `kb_ler`).\n"
            "- Skills: ativadas (`abrir_skill`, `ler_arquivo_skill`)."
        )

    def test_client_block_groups_entries_in_fixed_order_and_drops_archived(self):
        client = ClientBundle(
            id=CLIENT_ID, nome="Marca X", resumo="  Resumo da marca.  ",
            entradas=(
                ClientEntryData(tipo="nota", titulo="N1", conteudo="nota"),
                ClientEntryData(tipo="marca", titulo="Tom", conteudo="leve"),
                ClientEntryData(tipo="trava", titulo="Nunca", conteudo="preço", status="arquivado"),
                ClientEntryData(tipo="marca", titulo="Cores", conteudo=""),
            ),
        )
        out = compile_prompt(_input(client=client))
        assert out.texto.endswith(
            "# Cliente em foco: Marca X\n\nResumo da marca.\n\n"
            "## Marca\n- **Tom** — leve\n- **Cores**\n\n"
            "## Notas\n- **N1** — nota"
        )
        assert "Nunca" not in out.texto
        assert out.manifest[-1].origem.id == CLIENT_ID

    def test_on_demand_layer_never_in_texto(self):
        v = _version(skills=(SkillData(id=None, nome="s", descricao="d", corpo="CORPO-SECRETO-DA-SKILL"),))
        out = compile_prompt(_input(version=v))
        assert "CORPO-SECRETO-DA-SKILL" not in out.texto


class TestManifest:
    def test_offsets_slice_exactly_each_block(self):
        client = ClientBundle(id=CLIENT_ID, nome="C", resumo="R")
        out = compile_prompt(_input(knowledge=KNOWLEDGE, client=client))
        assert [m.chave for m in out.manifest] == [
            "identidade", "regras", "skills", "base-de-conhecimento", "ferramentas", "cliente",
        ]
        for m in out.manifest:
            block = out.texto[m.inicio : m.fim]
            assert block.startswith("# ")
            assert m.chars == len(block) == m.fim - m.inicio
            assert m.tokens == math.ceil(m.chars / 4)
        # contiguous with exactly "\n\n" between blocks, covering the whole text
        assert out.manifest[0].inicio == 0
        assert out.manifest[-1].fim == len(out.texto)
        for prev, nxt in zip(out.manifest, out.manifest[1:]):
            assert out.texto[prev.fim : nxt.inicio] == "\n\n"

    def test_origins(self):
        out = compile_prompt(_input())
        by = {m.chave: m for m in out.manifest}
        assert by["identidade"].origem.tipo == "secao"
        assert by["identidade"].origem.id == SEC_A
        assert by["identidade"].origem.campo == "conteudo"
        assert by["skills"].origem.tipo == "auto" and by["skills"].origem.id is None
        assert by["ferramentas"].origem.campo == "tool_policy"

    def test_manifest_json_shape(self):
        out = compile_prompt(_input())
        item = out.manifest_json()[0]
        assert set(item) == {"chave", "titulo", "origem", "inicio", "fim", "chars", "tokens"}
        assert set(item["origem"]) == {"tipo", "id", "campo"}
        assert item["origem"]["id"] == str(SEC_A)


class TestSobDemanda:
    def test_skills_files_and_collections(self):
        out = compile_prompt(_input(knowledge=KNOWLEDGE))
        rows = [(i.tipo, i.nome, i.caminho) for i in out.sob_demanda]
        assert rows == [
            ("skill", "calendario", None),
            ("skill", "roteiro-reels", None),
            ("arquivo_skill", "roteiro-reels", "references/a.md"),
            ("arquivo_skill", "roteiro-reels", "references/b.md"),
            ("colecao", "cases", None),
            ("colecao", "publico", None),
        ]
        skill = out.sob_demanda[1]
        assert skill.chars == len("Passo 1...") and skill.tokens == math.ceil(len("Passo 1...") / 4)
        assert skill.gatilho == 'abrir_skill("roteiro-reels")'
        assert out.sob_demanda[3].chars == 40 and out.sob_demanda[3].tokens == 10
        assert set(out.sob_demanda[0].to_dict()) == {"tipo", "nome", "caminho", "chars", "tokens", "gatilho"}

    def test_no_collections_when_knowledge_off(self):
        out = compile_prompt(_input(knowledge=KNOWLEDGE, policy={"web_search": True, "knowledge": False}))
        assert not [i for i in out.sob_demanda if i.tipo == "colecao"]


class TestWarnings:
    @staticmethod
    def _codes(out):
        return {(w.codigo, w.bloqueante) for w in out.avisos}

    def test_clean_input_has_no_warnings(self):
        out = compile_prompt(_input())
        assert out.avisos == []
        assert out.bloqueado is False

    def test_empty_active_section_is_skipped_and_blocking(self):
        v = _version(secoes=(
            SectionData(id=SEC_A, chave="identidade", titulo="Identidade", ordem=1, conteudo="ok"),
            SectionData(id=SEC_B, chave="vazia", titulo="Vazia", ordem=2, conteudo="   \n"),
        ))
        out = compile_prompt(_input(version=v))
        assert "# Vazia" not in out.texto
        assert ("secao_vazia", True) in self._codes(out)
        assert out.bloqueado

    def test_inactive_empty_section_is_not_a_warning(self):
        v = _version(secoes=(
            SectionData(id=SEC_A, chave="identidade", titulo="Identidade", ordem=1, conteudo="ok"),
            SectionData(id=SEC_B, chave="off", titulo="Off", ordem=2, conteudo="", ativo=False),
        ))
        assert compile_prompt(_input(version=v)).avisos == []

    def test_zero_active_sections_blocks(self):
        out = compile_prompt(_input(version=_version(secoes=())))
        assert ("sem_secoes", True) in self._codes(out)

    def test_skill_without_corpo_blocks(self):
        v = _version(skills=(SkillData(id=None, nome="s", descricao="d", corpo="  "),))
        assert ("skill_sem_corpo", True) in self._codes(compile_prompt(_input(version=v)))

    def test_duplicates_block(self):
        v = _version(
            secoes=(
                SectionData(id=None, chave="a", titulo="A", ordem=1, conteudo="x"),
                SectionData(id=None, chave="a", titulo="A2", ordem=2, conteudo="y"),
            ),
            skills=(
                SkillData(id=None, nome="s", descricao="d", corpo="c"),
                SkillData(id=None, nome="s", descricao="d", corpo="c"),
            ),
        )
        codes = self._codes(compile_prompt(_input(version=v)))
        assert ("chave_duplicada", True) in codes
        assert ("skill_duplicada", True) in codes

    def test_long_prompt_is_a_non_blocking_warning(self):
        v = _version(secoes=(SectionData(id=None, chave="a", titulo="A", ordem=1, conteudo="x" * 50000),))
        out = compile_prompt(_input(version=v))
        assert out.tokens_estimados > 12000
        assert ("prompt_extenso", False) in self._codes(out)
        assert not out.bloqueado

    @pytest.mark.parametrize("titulo", ["Skills", "ferramentas", "Base de Conhecimento", "Cliente em foco: X"])
    def test_section_title_duplicating_an_auto_title_warns(self, titulo):
        v = _version(secoes=(SectionData(id=None, chave="a", titulo=titulo, ordem=1, conteudo="x"),))
        out = compile_prompt(_input(version=v))
        assert ("titulo_reservado", False) in self._codes(out)
        assert not out.bloqueado


class TestDeterminismAndHash:
    def test_same_input_same_text_and_hash(self):
        a = compile_prompt(_input(knowledge=KNOWLEDGE))
        b = compile_prompt(_input(knowledge=tuple(reversed(KNOWLEDGE))))
        assert a.texto == b.texto and a.hash == b.hash

    def test_input_row_order_does_not_matter(self):
        v = _version()
        shuffled = replace(v, secoes=tuple(reversed(v.secoes)), skills=tuple(reversed(v.skills)))
        assert compile_prompt(_input(version=v)).hash == compile_prompt(_input(version=shuffled)).hash

    def test_hash_format(self):
        out = compile_prompt(_input())
        assert out.hash == "sha256:" + hashlib.sha256(out.texto.encode("utf-8")).hexdigest()
        assert out.tokens_estimados == math.ceil(len(out.texto) / 4)

    def test_draft_uuids_never_reach_the_text(self):
        out = compile_prompt(_input())
        assert str(SEC_A) not in out.texto
        with_other_ids = _version(secoes=tuple(replace(s, id=None) for s in _version().secoes))
        assert compile_prompt(_input(version=with_other_ids)).hash == out.hash

    @pytest.mark.parametrize(
        "mutate",
        [
            lambda v: replace(v, secoes=(replace(v.secoes[0], conteudo="Outra coisa."), v.secoes[1])),
            lambda v: replace(v, secoes=(replace(v.secoes[0], titulo="Outras regras"), v.secoes[1])),
            lambda v: replace(v, secoes=(replace(v.secoes[0], ordem=1), v.secoes[1])),
            lambda v: replace(v, secoes=(replace(v.secoes[0], ativo=False), v.secoes[1])),
            lambda v: replace(v, skills=(replace(v.skills[0], descricao="Nova descrição."), v.skills[1])),
            lambda v: replace(v, skills=(v.skills[0],)),
        ],
    )
    def test_any_field_change_changes_the_hash(self, mutate):
        base = _version()
        assert compile_prompt(_input(version=base)).hash != compile_prompt(_input(version=mutate(base))).hash

    def test_policy_knowledge_and_client_change_the_hash(self):
        base = compile_prompt(_input(knowledge=KNOWLEDGE)).hash
        assert compile_prompt(_input(knowledge=KNOWLEDGE, policy={"web_search": False, "knowledge": True})).hash != base
        more_docs = (replace(KNOWLEDGE[0], doc_count=13), KNOWLEDGE[1])
        assert compile_prompt(_input(knowledge=more_docs)).hash != base
        client = ClientBundle(id=CLIENT_ID, nome="C", resumo="R")
        assert compile_prompt(_input(knowledge=KNOWLEDGE, client=client)).hash != base
