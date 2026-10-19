"""Bundle builders + the one compile call site (Agent Studio contract §A4, §C).

Store rows → the compiler's pure input (:class:`VersionBundle`,
:class:`ClientBundle`) → :func:`compile_prompt`. The inspector / publish
routes (``studio_agents_router``), the runtime spec (``app.studio.spec``),
the eval runner and the importer all compile through
:func:`compile_version` — one composition path, never re-implemented.
"""
from __future__ import annotations

from uuid import UUID

from app.stores.studio_definitions import StudioAgentRecord, VersionRecord
from app.studio.compiler import compile_prompt
from app.studio.models import (
    ClientBundle,
    ClientEntryData,
    CompiledPrompt,
    CompileInput,
    ConteudoBundle,
    DecisaoData,
    FerramentaData,
    KnowledgeCatalog,
    OpcaoDecisao,
    SectionData,
    SkillData,
    SkillFileRef,
    SpecDefData,
    TextoData,
    VersionBundle,
)

__all__ = ["version_bundle", "conteudo_bundle", "client_bundle", "compile_version"]


def conteudo_bundle(store, org_id: UUID, version: VersionRecord) -> ConteudoBundle:
    """The version's four content tables as the compiler's pure input (Julia v2)."""
    return ConteudoBundle(
        textos=tuple(
            TextoData(chave=t.chave, conteudo=t.conteudo, id=t.id) for t in store.list_textos(org_id, version.id)
        ),
        ferramentas=tuple(
            FerramentaData(
                ferramenta=f.ferramenta, descricao=f.descricao, ativo=f.ativo, parametros=dict(f.parametros),
                obrigatoria_skill=f.obrigatoria_skill, id=f.id,
            )
            for f in store.list_ferramentas(org_id, version.id)
        ),
        decisoes=tuple(
            DecisaoData(
                chave=d.chave, titulo=d.titulo, regra=d.regra, id=d.id,
                opcoes=tuple(
                    OpcaoDecisao(valor=o["valor"], rotulo=o["rotulo"], padrao=bool(o["padrao"])) for o in d.opcoes
                ),
            )
            for d in store.list_decisoes(org_id, version.id)
        ),
        specs=tuple(
            SpecDefData(
                chave=sp.chave, rotulo=sp.rotulo, descricao=sp.descricao, tipo=sp.tipo,
                obrigatoria=sp.obrigatoria, exemplo=sp.exemplo, id=sp.id,
            )
            for sp in store.list_spec_defs(org_id, version.id)
        ),
    )


def version_bundle(store, org_id: UUID, version: VersionRecord, *, conteudo: bool = False) -> VersionBundle:
    secoes = store.list_sections(org_id, version.id)
    skills = store.list_skills(org_id, version.id)
    files_by_skill: dict[UUID, list[SkillFileRef]] = {}
    for f in store.list_version_skill_files(org_id, version.id):
        files_by_skill.setdefault(f.skill_id, []).append(
            SkillFileRef(caminho=f.caminho, titulo=f.titulo, chars=len(f.conteudo))
        )
    return VersionBundle(
        model=version.model,
        effort=version.effort,
        max_turns=version.max_turns,
        idioma=version.idioma,
        tool_policy=dict(version.tool_policy),
        secoes=tuple(
            SectionData(id=s.id, chave=s.chave, titulo=s.titulo, ordem=s.ordem, conteudo=s.conteudo, ativo=s.ativo)
            for s in secoes
        ),
        skills=tuple(
            SkillData(
                id=s.id, nome=s.nome, descricao=s.descricao, corpo=s.corpo, ordem=s.ordem,
                ativo=s.ativo, arquivos=tuple(files_by_skill.get(s.id, [])),
            )
            for s in skills
        ),
        version_id=version.id,
        versao=version.versao,
        conteudo=conteudo_bundle(store, org_id, version) if conteudo else None,
        provider=version.provider,
    )


def client_bundle(store, org_id: UUID, client) -> ClientBundle:
    entries = store.list_client_entries(org_id, client.id)
    return ClientBundle(
        id=client.id,
        nome=client.nome,
        resumo=client.resumo,
        entradas=tuple(
            ClientEntryData(tipo=e.tipo, titulo=e.titulo, conteudo=e.conteudo, status=e.status)
            for e in entries
        ),
    )


def compile_version(
    store, catalog: KnowledgeCatalog, org_id: UUID, agent: StudioAgentRecord,
    version: VersionRecord, client: ClientBundle | None = None, *,
    org_specs: dict[str, str] | None = None, extras: dict | None = None, qualificacao=None,
) -> CompiledPrompt:
    """THE one compile call site. ``org_id`` is the org that OWNS ``version``'s rows (the
    definition's org for a platform-defined agent). ``agent.conteudo_modo == 'linhas'`` selects
    content mode (every string a row, hash over every content table); ``org_specs`` compiles the
    definition FOR an org (see ``app.studio.resolucao.compile_for_org``)."""
    bundle = version_bundle(store, org_id, version, conteudo=agent.conteudo_modo == "linhas")
    knowledge = tuple(catalog.collection_summaries(org_id, agent.id))
    return compile_prompt(CompileInput(
        agent_nome=agent.nome,
        version=bundle,
        knowledge=knowledge,
        client=client,
        tool_policy=bundle.tool_policy,
        org_specs=org_specs,
        extras=extras,
        canal=agent.owner_product is not None,
        qualificacao=qualificacao,
    ))
