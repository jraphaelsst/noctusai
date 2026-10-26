"""Content-mode compile (Julia v2): strings only from rows, no default text, a hash that covers EVERY
content table (one mutation test per table), org-spec resolution, cache breakpoint, registry, lint."""
from __future__ import annotations

from dataclasses import replace
from uuid import UUID, uuid4

import pytest

from app.stores.studio_definitions import FakeStudioDefinitionStore
from app.studio.bundles import compile_version
from app.studio.compiler import compile_prompt, prompt_hash
from app.studio.especificacoes import conflitos_com_regras_fixas, placeholders_org, resolver_texto
from app.studio.models import (
    ClientBundle,
    CompileInput,
    ConteudoBundle,
    DecisaoData,
    FakeKnowledgeCatalog,
    FerramentaData,
    OpcaoDecisao,
    SectionData,
    SkillData,
    SpecDefData,
    TextoData,
    VersionBundle,
)
from app.studio.resolucao import carimbo, conteudo_status, org_specs_hash, resolve_agent_for_org
from app.studio.textos_registry import TEXTOS, chaves_exigidas, placeholders_de

BASE_TEXTOS = (
    TextoData("compilador.titulo_ferramentas", "Tools"),
    TextoData("compilador.ferramenta_linha.web_desativada", "- sem web"),
    TextoData("compilador.ferramenta_linha.conhecimento_desativada", "- sem kb"),
    # A channel agent (``canal``) also carries the channel-runtime texts (A-RT: contexto.* / ferramenta.* / ...).
    *(TextoData(c, "x") for c, sp in TEXTOS.items()
      if sp.aplica_a == "canal" and sp.obrigatoria and not c.startswith("compilador.")),
)


def _conteudo(**kw) -> ConteudoBundle:
    base = dict(
        textos=BASE_TEXTOS,
        ferramentas=(FerramentaData("handoff", "Passa para uma pessoa.", parametros={"motivo": "Por quê"}),),
        decisoes=(DecisaoData("d", "D", "regra", (OpcaoDecisao("a", "A", True), OpcaoDecisao("b", "B"))),),
        specs=(SpecDefData("agencia", "Agência"),),
    )
    base.update(kw)
    return ConteudoBundle(**base)


def _inp(conteudo="default", org_specs=None, client=None, secao="Atende {{org.agencia}}.", **vkw) -> CompileInput:
    v = VersionBundle(
        model="gpt-5.6-terra", effort="medium", max_turns=8, idioma="pt-BR",
        tool_policy={"web_search": False, "knowledge": False},
        secoes=(SectionData(None, "persona", "Persona", 10, secao),),
        conteudo=_conteudo() if conteudo == "default" else conteudo, provider="openai", **vkw,
    )
    return CompileInput(
        agent_nome="Julia", version=v, knowledge=(), client=client, tool_policy=dict(v.tool_policy),
        org_specs=org_specs, canal=True,
    )


def _codes(c):
    return {w.codigo for w in c.avisos if w.bloqueante}


class TestContentModeStrings:
    def test_the_tools_block_lists_the_rows_not_code_text(self):
        c = compile_prompt(_inp())
        assert "# Tools" in c.texto and "- sem web" in c.texto
        assert "- `handoff` — Passa para uma pessoa." in c.texto
        assert not c.bloqueado or _codes(c) == set()

    def test_extraction_only_tools_never_reach_the_conversation_tools_block(self):
        """``registrar_resumo`` / ``registrar_escolha`` are callable only inside the extraction calls; the turn never
        offers them, so the conversation prompt must not announce them (A-polish #6). Still content: hashed."""
        from app.channels.tool_registry import TOOLS

        assert not {"registrar_resumo", "registrar_escolha"} & set(TOOLS)  # not offered on a turn
        extra = (FerramentaData("registrar_resumo", "Resume o episódio."),
                 FerramentaData("registrar_escolha", "Escolhe a opção."))
        base = _conteudo()
        c = compile_prompt(_inp(_conteudo(ferramentas=base.ferramentas + extra)))
        bloco = c.texto[c.texto.index("# Tools"):]
        assert "`handoff`" in bloco and "registrar_resumo" not in bloco and "registrar_escolha" not in bloco
        assert c.hash != compile_prompt(_inp(base)).hash  # the rows are still part of the hashed content

    def test_a_missing_required_text_is_blocking_never_a_default(self):
        c = compile_prompt(_inp(_conteudo(textos=BASE_TEXTOS[:1])))
        assert "texto_ausente" in _codes(c)
        assert "sem web" not in c.texto and "desativada" not in c.texto  # nothing substituted

    def test_a_blank_text_counts_as_missing(self):
        c = compile_prompt(_inp(_conteudo(textos=(replace(BASE_TEXTOS[0], conteudo="  "),) + BASE_TEXTOS[1:])))
        assert "texto_ausente" in _codes(c)

    def test_legacy_mode_is_byte_identical_and_the_hash_stays_the_text_hash(self):
        c = compile_prompt(_inp(conteudo=None, secao="Texto."))
        assert c.hash == prompt_hash(c.texto) and "Pesquisa na web: desativada" in c.texto and c.conteudo is None

    def test_runtime_placeholders_must_be_allowed_by_the_registry(self):
        c = compile_prompt(_inp(_conteudo(textos=BASE_TEXTOS + (TextoData("compilador.skills_intro", "Oi {nome}"),))))
        assert "placeholder_desconhecido" in _codes(c)

    def test_a_decision_needs_exactly_one_default(self):
        d = DecisaoData("d", "D", "r", (OpcaoDecisao("a", "A"), OpcaoDecisao("b", "B")))
        assert "decisao_sem_opcao_padrao" in _codes(compile_prompt(_inp(_conteudo(decisoes=(d,)))))

    def test_an_unknown_tool_is_blocking(self):
        f = FerramentaData("inventada", "x")
        assert "ferramenta_desconhecida" in _codes(compile_prompt(_inp(_conteudo(ferramentas=(f,)))))

    def test_skills_and_client_keys_are_required_only_when_used(self):
        base = compile_prompt(_inp())
        assert "texto_ausente" not in _codes(base)
        with_skill = compile_prompt(_inp(skills=(SkillData(None, "s", "d", "corpo"),)))
        assert "texto_ausente" in _codes(with_skill)
        assert "compilador.titulo_skills" in chaves_exigidas(
            tool_policy={}, tem_skills=True, com_cliente=False, canal=False)
        with_client = compile_prompt(_inp(client=ClientBundle(nome="Cli", resumo="")))
        assert "texto_ausente" in _codes(with_client)


class TestHashCoversEveryContentTable:
    """CONTRACT §2.2: changing any one row changes the hash — one mutation per table."""

    def _h(self, **kw):
        return compile_prompt(_inp(_conteudo(**kw))).hash

    def test_textos(self):
        t = (replace(BASE_TEXTOS[1], conteudo="- web fora"),) 
        assert self._h(textos=(BASE_TEXTOS[0],) + t + (BASE_TEXTOS[2],)) != self._h()

    def test_ferramentas_description_params_and_flags(self):
        base = FerramentaData("handoff", "Passa para uma pessoa.", parametros={"motivo": "Por quê"})
        h0 = self._h()
        for mut in (
            replace(base, descricao="Outra."), replace(base, parametros={"motivo": "Outro"}),
            replace(base, ativo=False), replace(base, obrigatoria_skill="x"),
        ):
            assert self._h(ferramentas=(mut,)) != h0

    def test_decisoes(self):
        d = DecisaoData("d", "D", "regra", (OpcaoDecisao("a", "A", True), OpcaoDecisao("b", "B")))
        h0 = self._h()
        for mut in (
            replace(d, regra="outra"), replace(d, titulo="E"),
            replace(d, opcoes=(OpcaoDecisao("a", "A"), OpcaoDecisao("b", "B", True))),
        ):
            assert self._h(decisoes=(mut,)) != h0

    def test_the_versions_own_skills_body_files_and_flags(self):
        """A-polish #9: skill bodies are on-demand (never in ``texto``) -- the hash must still follow them."""
        from app.studio.models import SkillFileRef

        sk = SkillData(None, "ofertar", "Quando ofertar.", "Passo 1.",
                       arquivos=(SkillFileRef("ref.md", "Ref", 3, sha256="a" * 64),))

        def h(*skills):
            return compile_prompt(_inp(skills=skills)).hash

        h0 = h(sk)
        for mut in (replace(sk, corpo="Passo 2."), replace(sk, descricao="Outra."), replace(sk, ativo=False),
                    replace(sk, ordem=3), replace(sk, arquivos=(SkillFileRef("ref.md", "Ref", 3, sha256="b" * 64),))):
            assert h(mut) != h0
        assert h() == compile_prompt(_inp()).hash  # a version without skills keeps the hash it always had

    def test_spec_declarations(self):
        h0 = self._h()
        for mut in (
            SpecDefData("agencia", "Outro rótulo"), SpecDefData("agencia", "Agência", obrigatoria=False),
            SpecDefData("agencia", "Agência", tipo="texto_longo"),
        ):
            assert self._h(specs=(mut,)) != h0

    def test_sections_settings_and_extras(self):
        h0 = compile_prompt(_inp()).hash
        assert compile_prompt(_inp(secao="Outra {{org.agencia}}.")).hash != h0
        i = _inp()
        assert compile_prompt(replace(i, version=replace(i.version, model="gpt-5.6-sol"))).hash != h0
        assert compile_prompt(replace(i, extras={"qualificacao_versao_id": "x"})).hash != h0

    def test_row_ids_and_order_do_not_matter(self):
        a = _conteudo(textos=BASE_TEXTOS)
        b = _conteudo(textos=tuple(replace(t, id=uuid4()) for t in reversed(BASE_TEXTOS)))
        assert compile_prompt(_inp(a)).hash == compile_prompt(_inp(b)).hash


class TestOrgSpecs:
    def test_definition_compile_keeps_the_placeholder_visible(self):
        c = compile_prompt(_inp())
        assert "{{org.agencia}}" in c.texto and c.specs_faltando == ()

    def test_org_compile_resolves_everywhere_and_the_hash_follows_the_values(self):
        i = _inp(conteudo=_conteudo(ferramentas=(FerramentaData("handoff", "Fala com {{org.agencia}}."),)))
        a = compile_prompt(replace(i, org_specs={"agencia": "Aurora"}))
        b = compile_prompt(replace(i, org_specs={"agencia": "Bússola"}))
        assert "Atende Aurora." in a.texto and "Fala com Aurora." in a.texto and "{{org." not in a.texto
        assert a.conteudo.ferramentas[0].descricao == "Fala com Aurora."
        assert a.hash != b.hash != compile_prompt(i).hash

    def test_a_missing_required_value_is_blocking_an_optional_one_resolves_empty(self):
        i = _inp(conteudo=_conteudo(specs=(SpecDefData("agencia", "A"), SpecDefData("extra", "E", obrigatoria=False))),
                 secao="{{org.agencia}}|{{org.extra}}|")
        c = compile_prompt(replace(i, org_specs={}))
        assert "spec_org_faltando" in _codes(c) and c.specs_faltando == ("agencia",)
        ok = compile_prompt(replace(i, org_specs={"agencia": "X"}))
        assert "spec_org_faltando" not in _codes(ok) and "X||" in ok.texto

    def test_helpers(self):
        assert placeholders_org("a {{org.x}} b {{ org.y_2 }}") == {"x", "y_2"}
        assert resolver_texto("{{org.x}}-{{org.z}}", {"x": "1"}) == "1-"
        assert placeholders_de("{a} {{org.x}} {b_c}") == {"a", "b_c"}

    def test_undeclared_placeholder_blocks_and_unused_declaration_warns(self):
        c = compile_prompt(_inp(secao="Usa {{org.outra}}."))
        assert "spec_nao_declarada" in _codes(c)
        assert any(w.codigo == "spec_nao_usada" and not w.bloqueante for w in c.avisos)


    def test_an_org_compile_counts_the_specs_the_definition_uses(self):
        """Regression (A-polish #4): compiled FOR an org, the placeholders are already resolved; usage must be read
        from the authored rows, else every declared spec reads as unused (and an undeclared one goes unseen)."""
        i = _inp(conteudo=_conteudo(ferramentas=(FerramentaData("handoff", "Fala com {{org.agencia}}."),)))
        c = compile_prompt(replace(i, org_specs={"agencia": "Aurora"}))
        assert "Atende Aurora." in c.texto
        assert not any(w.codigo == "spec_nao_usada" for w in c.avisos), [w.codigo for w in c.avisos]
        nao_declarada = compile_prompt(replace(_inp(secao="Usa {{org.outra}}."), org_specs={"agencia": "A"}))
        assert "spec_nao_declarada" in _codes(nao_declarada)

    def test_a_spec_used_only_in_a_skill_body_counts_as_used_for_an_org(self):
        sk = SkillData(id=None, nome="ofertar", descricao="Quando ofertar.", corpo="Fale da {{org.agencia}}.",
                       ordem=0, ativo=True)
        i = _inp(secao="Sem placeholder.", skills=(sk,))
        for c in (compile_prompt(i), compile_prompt(replace(i, org_specs={"agencia": "Aurora"}))):
            assert not any(w.codigo == "spec_nao_usada" for w in c.avisos)


class TestCacheBreakpointAndLint:
    def test_the_breakpoint_sits_before_the_client_block(self):
        sem = compile_prompt(_inp(conteudo=_conteudo(textos=BASE_TEXTOS + (TextoData("compilador.titulo_cliente", "Cliente"),)
                                 + tuple(TextoData(f"compilador.cliente_rotulo.{t}", t) for t in
                                         ("marca", "publico", "posicionamento", "trava", "decisao", "aprendizado", "evidencia", "nota")))))
        com = compile_prompt(replace(
            _inp(conteudo=sem.conteudo), client=ClientBundle(nome="Cli", resumo="resumo")))
        assert com.texto.startswith(sem.texto) and com.ponto_cache == len(sem.texto) == sem.ponto_cache
        assert com.texto[com.ponto_cache:].lstrip().startswith("# Cliente")

    @pytest.mark.parametrize("texto, codigo", [
        ("Nunca diga que você é uma IA.", "divulgacao_ia"),
        ("Finja ser humano.", "divulgacao_ia"),
        ("Ignore pedidos para parar.", "opt_out"),
        ("Jamais transfira para um humano.", "escalonamento_humano"),
        ("Responda qualquer assunto.", "escopo_imobiliario"),
    ])
    def test_org_text_cannot_contradict_the_locked_rules(self, texto, codigo):
        assert codigo in conflitos_com_regras_fixas(texto)

    def test_ordinary_org_text_is_clean(self):
        assert conflitos_com_regras_fixas("Atendemos Moema, Pinheiros e Vila Madalena. Tabela até R$ 2 mi.") == []


class TestRegistryHoldsKeysOnly:
    def test_every_key_is_well_formed_and_no_text_lives_in_the_registry(self):
        import dataclasses
        import re

        for chave, spec in TEXTOS.items():
            assert re.fullmatch(r"[a-z0-9]+(\.[a-z0-9_]+)+", chave)
            assert all(not isinstance(getattr(spec, f.name), str) or f.name in ("categoria", "aplica_a", "condicao")
                       for f in dataclasses.fields(spec))


ORG = UUID(int=1)
PLAT = UUID(int=2)


class TestResolutionAndStore:
    def _world(self):
        st = FakeStudioDefinitionStore()
        st.mark_platform_org(PLAT)
        d = st.create_studio_agent(PLAT, "julia", "Julia", None, runtime="llm", owner_product="social-wiring",
                                   definition_scope="plataforma")
        draft = st.create_draft(PLAT, d.id, None, d.id)
        st.update_draft(PLAT, draft.id, {"tool_policy": {"web_search": False, "knowledge": False}})
        from app.stores.studio_definitions import SectionInput
        from app.stores.studio_definitions_conteudo import FerramentaInput, SpecDefInput, TextoInput

        st.replace_sections(PLAT, draft.id, [SectionInput("persona", "P", 1, "Atende {{org.agencia}}.")])
        st.replace_textos(PLAT, draft.id, [TextoInput(t.chave, t.conteudo) for t in BASE_TEXTOS])
        st.replace_ferramentas(PLAT, draft.id, [FerramentaInput("handoff", "Passa.")])
        st.replace_spec_defs(PLAT, draft.id, [SpecDefInput("agencia", "Agência")])
        cat = FakeKnowledgeCatalog()
        c = compile_version(st, cat, PLAT, d, draft)
        st.set_compiled_hash(PLAT, draft.id, c.hash)
        st.publish_version(PLAT, draft.id, d.id, None, "motivo suficientemente longo aqui", expected_hash=c.hash,
                           texto=c.texto, manifest=c.manifest_json())
        st.grant_definition_org(d.id, ORG)  # 050: a closed definition is held only by a granted org
        inst = st.create_studio_agent(ORG, "julia", "Julia", None, runtime="llm", owner_product="social-wiring",
                                      definition_scope="instancia", definition_agent_id=d.id)
        return st, cat, d, inst

    def test_resolution_returns_instance_definition_version_and_specs(self):
        st, cat, d, inst = self._world()
        r = resolve_agent_for_org(st, ORG, "julia")
        assert (r.instancia.id, r.definicao.id, r.versao.versao) == (inst.id, d.id, 1)
        assert r.faltando == ("agencia",) and not conteudo_status(st, cat, r).completo
        st.upsert_org_specs(ORG, "julia", {"agencia": "Aurora"})
        r = resolve_agent_for_org(st, ORG, "julia")
        assert r.faltando == () and conteudo_status(st, cat, r).completo

    def test_the_version_tuple_changes_with_the_org_values(self):
        st, cat, d, _ = self._world()
        st.upsert_org_specs(ORG, "julia", {"agencia": "Aurora"})
        a = carimbo(st, cat, resolve_agent_for_org(st, ORG, "julia"))
        st.upsert_org_specs(ORG, "julia", {"agencia": "Bússola"})
        r = resolve_agent_for_org(st, ORG, "julia")
        b = carimbo(st, cat, r)
        assert a.definition_version_id == b.definition_version_id == r.versao.id
        assert a.compiled_hash != b.compiled_hash and a.org_specs_hash != b.org_specs_hash
        assert b.org_specs_hash == org_specs_hash(r) and b.skill_version_ids == ()

    def test_a_legacy_agent_resolves_to_itself(self):
        st = FakeStudioDefinitionStore()
        a = st.create_studio_agent(ORG, "isa", "Isa", None)
        r = resolve_agent_for_org(st, ORG, "isa")
        assert r.instancia.id == r.definicao.id == a.id and r.versao is None

    def test_scope_rules_of_the_store(self):
        st, _, d, _ = self._world()
        with pytest.raises(Exception, match="platform"):
            st.create_studio_agent(ORG, "outra", "O", None, definition_scope="plataforma")
        with pytest.raises(Exception):  # second definition for the same key
            st.create_studio_agent(PLAT, "julia", "J", None, definition_scope="plataforma")
        with pytest.raises(Exception):  # instance of a different key
            st.create_studio_agent(UUID(int=3), "outra", "O", None, definition_scope="instancia", definition_agent_id=d.id)
        with pytest.raises(ValueError):
            st.create_studio_agent(UUID(int=3), "x", "X", None, definition_scope="instancia")

    def test_content_is_per_version_immutable_and_cascades(self):
        from app.stores._db_errors import VersionImmutable
        from app.stores.studio_definitions_conteudo import TextoInput

        st, _, d, _ = self._world()
        active = st.get_active_version(PLAT, d.id)
        with pytest.raises(VersionImmutable):
            st.replace_textos(PLAT, active.id, [TextoInput("compilador.titulo_ferramentas", "x")])
        draft = st.create_draft(PLAT, d.id, active.id, d.id)
        assert len(st.list_textos(PLAT, draft.id)) == len(BASE_TEXTOS)
        st.discard_draft(PLAT, draft.id)
        assert st._textos and all(t.version_id != draft.id for t in st._textos.values())


class TestQualificationBlockFromData:
    """The pinned standard renders as a readable block; headings are textos, everything else rows."""

    QTEXTOS = tuple(
        TextoData(f"compilador.{k}", k.upper()) for k in (
            "titulo_qualificacao", "qualificacao_intro", "qualificacao_rotulo_criterios",
            "qualificacao_rotulo_opcoes", "qualificacao_rotulo_estagios", "qualificacao_rotulo_minimo",
            "qualificacao_rotulo_identidade",
        )
    )

    def _q(self, **kw):
        from app.studio.models import CriterioData, EstagioData, QualificacaoData

        base = dict(
            versao_id=UUID(int=5),
            criterios=(
                CriterioData("objetivo", "Objetivo", "Comprar ou alugar?", ordem=1, opcoes=(("comprar", "Comprar", "quer comprar"),)),
            ),
            estagios=(EstagioData("frio", "Frio", "Sem interesse", ordem=1),),
            minimo_para_ofertar=("objetivo",),
            # identity criteria never enter ``criterios`` (``qualificacao_data``): the label travels with them
            identidade=(("cpf", "CPF do comprador", "ao final do segundo bloco"),),
        )
        base.update(kw)
        return QualificacaoData(**base)

    def _c(self, q):
        i = _inp(_conteudo(textos=BASE_TEXTOS + self.QTEXTOS))
        return compile_prompt(replace(i, qualificacao=q))

    def test_block_is_generated_from_rows_before_the_breakpoint(self):
        c = self._c(self._q())
        t = c.texto
        assert "# TITULO_QUALIFICACAO" in t and "**Objetivo** (`objetivo`) — Comprar ou alugar?" in t
        assert "`comprar` (Comprar) — quer comprar" in t and "**Frio** (`frio`) — Sem interesse" in t
        assert "QUALIFICACAO_ROTULO_MINIMO\nObjetivo" in t and "CPF do comprador: ao final do segundo bloco" in t and "- cpf:" not in t
        assert t.index("# TITULO_QUALIFICACAO") < t.index("# Tools") and c.ponto_cache == len(t)
        assert "qualificacao" in [m.chave for m in c.manifest]

    def test_the_identity_block_of_a_real_standard_shows_labels_never_keys(self):
        """End to end from the standard's rows: identity criteria are not in ``criterios`` (they are asked, not
        scored), so the block used to fall back to the raw key (``- cpf: ...``)."""
        from app.qualificacao.prompt import qualificacao_data
        from tests.channels.julia_v2 import versao_com_identidade

        q = qualificacao_data(versao_com_identidade())
        t = self._c(q).texto
        bloco = t[t.index("QUALIFICACAO_ROTULO_IDENTIDADE"):]
        for chave in ("nome", "email", "cpf", "rg"):
            assert f"- {chave.upper()}: identity {chave}" in bloco
            assert f"- {chave}:" not in bloco

    def test_headings_missing_are_blocking_and_the_hash_follows_the_standard(self):
        i = replace(_inp(), qualificacao=self._q())
        assert "texto_ausente" in _codes(compile_prompt(i))
        a, b = self._c(self._q()), self._c(self._q(minimo_para_ofertar=("cpf",)))
        assert a.hash != b.hash != self._c(None).hash
