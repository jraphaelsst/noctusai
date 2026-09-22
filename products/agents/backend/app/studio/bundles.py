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
    KnowledgeCatalog,
    SectionData,
    SkillData,
    SkillFileRef,
    VersionBundle,
)

__all__ = ["version_bundle", "client_bundle", "compile_version"]


def version_bundle(store, org_id: UUID, version: VersionRecord) -> VersionBundle:
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
    version: VersionRecord, client: ClientBundle | None = None,
) -> CompiledPrompt:
    bundle = version_bundle(store, org_id, version)
    knowledge = tuple(catalog.collection_summaries(org_id, agent.id))
    return compile_prompt(CompileInput(
        agent_nome=agent.nome,
        version=bundle,
        knowledge=knowledge,
        client=client,
        tool_policy=bundle.tool_policy,
    ))
