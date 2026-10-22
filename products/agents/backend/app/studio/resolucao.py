"""Resolving a platform-defined agent for an org (Julia v2, CONTRACT §2.6).

Julia is ONE definition for every org (Q2). The definition (versions, sections, textos, tool
descriptions, decisions, org-spec declarations) belongs to the ``plataforma`` agent row of the
platform org; each org has an INSTANCE row (activation / mode, LLM key, budget, tokens) and its
own SPEC VALUES. Everything that needs "Julia, for this org" — the channel turn, the compiled view,
the readiness status SW shows — resolves through :func:`resolve_agent_for_org` and compiles through
:func:`compile_for_org`; nobody re-derives the hop.

An agent that predates v2 (``definition_scope='org'``) resolves to itself — one code path, no
branch in the caller.
"""
from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from uuid import UUID

from app.stores.errors import NotFound
from app.stores.studio_definitions import StudioAgentRecord, VersionRecord
from app.studio.bundles import compile_version
from app.studio.models import ClientBundle, CompiledPrompt, KnowledgeCatalog

__all__ = [
    "AgenteResolvido",
    "ConteudoStatus",
    "resolve_agent_for_org",
    "compile_for_org",
    "conteudo_status",
    "Carimbo",
    "carimbo",
]


@dataclass(frozen=True)
class AgenteResolvido:
    #: The org's own row: ``ativo`` / mode, LLM key, budget, tokens, conversations.
    instancia: StudioAgentRecord
    #: Where the definition lives. ``is instancia`` for an ``org`` / ``plataforma`` row.
    definicao: StudioAgentRecord
    #: The resolved definition version (the ACTIVE one by default); ``None`` = nothing published.
    versao: VersionRecord | None
    #: The declarations of that version (``{{org.chave}}`` the definition uses).
    specs_declaradas: tuple
    #: This org's stored values.
    specs_org: tuple

    @property
    def valores(self) -> dict[str, str]:
        return {s.chave: s.valor for s in self.specs_org}

    @property
    def faltando(self) -> tuple[str, ...]:
        """Required declared specs this org has not filled (blank counts as not filled)."""
        v = self.valores
        return tuple(sorted(
            d.chave for d in self.specs_declaradas if d.obrigatoria and not v.get(d.chave, "").strip()
        ))


def resolve_agent_for_org(
    store, org_id: UUID, key: str, *, versao: UUID | str = "ativa",
) -> AgenteResolvido:
    """``(definition version, org instance, org specs)`` of agent ``key`` for ``org_id``.

    ``versao``: ``"ativa"`` (default — what a live turn runs), ``"rascunho"`` (the definition's
    draft — Studio previews it per org) or an explicit version id. Raises :class:`NotFound` when
    the org has no such agent (an instance row is created by ``plataforma.ensure_instancia`` / the admin)."""
    instancia = store.get_agent(org_id, key)
    if instancia.definition_scope == "instancia":
        definicao = store.get_agent_by_id(instancia.definition_agent_id)
    else:
        definicao = instancia
    if versao == "ativa":
        v = store.get_active_version(definicao.org_id, definicao.id)
    elif versao == "rascunho":
        v = store.get_draft(definicao.org_id, definicao.id)
    else:
        v = store.get_version(definicao.org_id, versao)
        if v.agent_id != definicao.id:
            raise NotFound(f"version {versao} does not belong to the definition of {key!r}")
    declaradas = tuple(store.list_spec_defs(definicao.org_id, v.id)) if v is not None else ()
    return AgenteResolvido(
        instancia=instancia, definicao=definicao, versao=v,
        specs_declaradas=declaradas, specs_org=tuple(store.list_org_specs(org_id, key)),
    )


def compile_for_org(
    store, catalog: KnowledgeCatalog, r: AgenteResolvido, client: ClientBundle | None = None, *,
    extras: dict | None = None, qualificacao=None,
) -> CompiledPrompt:
    """The definition compiled FOR this org: every ``{{org.chave}}`` replaced by the org's value,
    the hash covering exactly what the model receives. Requires a resolved version."""
    if r.versao is None:
        raise NotFound(f"agent {r.instancia.key!r} has no published version")
    return compile_version(
        store, catalog, r.definicao.org_id, r.definicao, r.versao, client,
        org_specs=r.valores, extras=extras, qualificacao=qualificacao,
    )


@dataclass(frozen=True)
class Carimbo:
    """The version tuple every assistant message is stamped with (A-THREAD stores it)."""

    definition_version_id: UUID
    compiled_hash: str
    org_specs_hash: str
    #: Pinned shared-skill versions (A-SKILLS fills it; empty until the library exists).
    skill_version_ids: tuple[UUID, ...] = ()


def org_specs_hash(r: AgenteResolvido) -> str:
    """Hash of the org's values for the specs the definition declares (so an unused leftover key
    never changes it); stable, order-independent."""
    v = r.valores
    payload = sorted([d.chave, v.get(d.chave, "")] for d in r.specs_declaradas)
    raw = json.dumps(payload, ensure_ascii=False, separators=(",", ":"))
    return "sha256:" + hashlib.sha256(raw.encode("utf-8")).hexdigest()


def carimbo(
    store, catalog: KnowledgeCatalog, r: AgenteResolvido, *, qualificacao=None,
    compiled: CompiledPrompt | None = None,
) -> Carimbo:
    """The version tuple. Pass the ``compiled`` prompt the model actually received (compiled WITH the
    pinned ``qualificacao``) so the stamp is the hash of what ran, not of a second compile."""
    compiled = compiled or compile_for_org(store, catalog, r, qualificacao=qualificacao)
    return Carimbo(r.versao.id, compiled.hash, org_specs_hash(r))


@dataclass(frozen=True)
class ConteudoStatus:
    """Readiness of an org's agent: what SW / Studio surface as ``conteudo_completo`` and what a
    turn answers 409 ``conteudo_incompleto`` with."""

    completo: bool
    sem_versao: bool
    specs_faltando: tuple[str, ...]
    avisos_bloqueantes: tuple[str, ...]


def conteudo_status(
    store, catalog: KnowledgeCatalog, r: AgenteResolvido, *, qualificacao=None,
    compiled: CompiledPrompt | None = None,
) -> ConteudoStatus:
    if r.versao is None:
        return ConteudoStatus(False, True, r.faltando, ())
    compiled = compiled or compile_for_org(store, catalog, r, qualificacao=qualificacao)
    bloqueantes = tuple(w.codigo for w in compiled.avisos if w.bloqueante)
    return ConteudoStatus(
        completo=not bloqueantes, sem_versao=False, specs_faltando=compiled.specs_faltando,
        avisos_bloqueantes=bloqueantes,
    )
