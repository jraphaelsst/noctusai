"""Bundle builders + the one compile call site (Agent Studio contract §A4, §C).

Store rows → the compiler's pure input (:class:`VersionBundle`,
:class:`ClientBundle`) → :func:`compile_prompt`. The inspector / publish
routes (``studio_agents_router``), the runtime spec (``app.studio.spec``),
the eval runner and the importer all compile through
:func:`compile_version` — one composition path, never re-implemented.
"""
from __future__ import annotations

import hashlib
import logging
from typing import Any, Callable
from uuid import UUID

from app.stores.errors import NotFound
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
from app.studio.skills_contract import SkillRef, SkillsRuntime

logger = logging.getLogger(__name__)

__all__ = [
    "version_bundle", "conteudo_bundle", "client_bundle", "compile_version",
    "configure_skill_refs_provider", "skill_refs_of", "configure_padrao_reader", "qualificacao_da_versao",
]

# The shared skill library (Julia v2 D7/D8). Every compile site (publish hash, inspector, runtime,
# evals) reaches the pins through THIS slot, so the hash can never differ by call site. A provider
# (not an instance): the store is resolved at call time, never bound at import. ``None`` = no
# library wired (every pre-v2 test/app path): no pins. ``install_studio_seams`` wires production.
_skill_refs_provider: Callable[[], SkillsRuntime] | None = None


def configure_skill_refs_provider(provider: Callable[[], SkillsRuntime] | None) -> Callable[[], SkillsRuntime] | None:
    """Wire (or clear, with ``None``) the library reader; returns the previous provider so a test
    can restore it."""
    global _skill_refs_provider
    previous, _skill_refs_provider = _skill_refs_provider, provider
    return previous


def skill_refs_of(version_id: UUID) -> tuple[SkillRef, ...]:
    """The library pins of a version ("()" when no library is wired). A reader failure propagates."""
    if _skill_refs_provider is None:
        return ()
    return tuple(_skill_refs_provider().skill_refs_for(version_id))


#: The qualification-standard reader (``PadraoStore``: ``obter_versao(id)`` / ``obter_versao_publicada(chave)``).
#: A module slot populated at startup by ``install_studio_seams`` (the studio compile call sites are many and
#: none of them carries a standards store); unset = a compile without the standard (legacy / unit tests).
_padrao_reader: Any = None


def configure_padrao_reader(reader: Any) -> None:
    global _padrao_reader
    _padrao_reader = reader


def qualificacao_da_versao(agent: StudioAgentRecord, version: VersionRecord):
    """The standard block input a platform-defined agent's version compiles with: its PINNED standard version,
    else the newest PUBLISHED version of the agent's standard -- the same rule the channel turn applies
    (``padrao_do_turno``), so the hash a studio eval/publish judges is the hash a turn runs. ``None`` for an
    agent without a standard or when no reader is configured."""
    reader = _padrao_reader
    if reader is None:
        return None
    from app.qualificacao.prompt import qualificacao_data
    from app.studio.plataforma import padrao_de

    chave = padrao_de(agent)
    if chave is None:
        return None
    pin = getattr(version, "qualificacao_versao_id", None)
    try:
        padrao = reader.obter_versao(pin) if pin is not None else reader.obter_versao_publicada(chave)
    except NotFound:
        logger.warning("agents.studio.compile.padrao_ausente agent=%s pin=%s", agent.key, pin)
        return None
    return qualificacao_data(padrao)


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
            SkillFileRef(
                caminho=f.caminho, titulo=f.titulo, chars=len(f.conteudo),
                sha256=hashlib.sha256(f.conteudo.encode("utf-8")).hexdigest(),
            )
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
        # Pins exist only on content-mode (platform-defined) versions; a legacy agent keeps the
        # pre-v2 compiler and its hash byte for byte.
        skill_refs=skill_refs_of(version.id) if conteudo else (),
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
    if qualificacao is None:
        qualificacao = qualificacao_da_versao(agent, version)
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
