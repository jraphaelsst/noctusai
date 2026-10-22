"""Shared skill library API (Julia v2 CONTRACT D7/D8, section 4.2; migration 039).

One standardised, versioned library of skills used the same way by every agent (owner requirement:
agents use skills instead of their own judgement). A skill body is platform IP, so EVERY route here
is platform-only (``require_platform_content_admin``): a NoctusAI platform admin (403
``platform_admin_required`` for anyone else, 401 unauthenticated) or the platform-issued
``studio:content-write`` token of the ``noctus.agents.content`` MCP tool. That token writes DRAFTS
only: publishing a skill version stays a human platform-admin act (403 ``user_required``).

* ``/api/skills-biblioteca`` -- the library: skills, their versions, drafts, reference files, publish.
* ``/api/studio/agents/{key}/draft/skills-biblioteca`` -- pin / re-pin / unpin a library version on an
  agent DRAFT (``obrigatoria_para`` = the tools that refuse until the skill was opened in the thread),
  with the "new version available" indicator per pin. A pin change invalidates and re-stamps the
  draft's ``compiled_hash`` (the pins are hash-covered).

Error bodies carry machine codes and fixed texts, never row content. Every response model is an
explicit allowlist. Seam: ``get_skills_store_dep``.
"""
from __future__ import annotations

import re
from datetime import datetime
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from app.dependencies import get_skills_store_dep, require_platform_content_admin
from app.routers.studio_agents_router import (
    _refresh_draft_hash,
    actor_id,
    audit_definition_read,
    get_knowledge_catalog_dep,
    get_studio_definition_store_dep,
    resolve_agent,
    resolve_draft,
    resolve_version,
)
from app.stores._db_errors import StudioConflict, VersionImmutable
from app.stores.errors import NotFound
from app.stores.skills_biblioteca import (
    SKILL_CHAVE_RE,
    RefRecord,
    SkillsBibliotecaStore,
    SkillVersao,
    SkillVersaoMeta,
)
from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(tags=["skills-biblioteca"])

_CHAVE = r"^[a-z0-9]+(-[a-z0-9]+)*$"
_TOOL_RE = re.compile(r"^[a-z][a-z0-9_]{1,63}$")


# ── schemas (request: strict; response: explicit allowlists) ────────────────


class SkillCreate(StrictHttpModel):
    chave: str = Field(pattern=_CHAVE, max_length=64)
    nome: str = Field(min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=1024)


class SkillPatch(StrictHttpModel):
    nome: str | None = Field(default=None, min_length=1, max_length=200)
    descricao: str | None = Field(default=None, max_length=1024)


class RascunhoCreate(StrictHttpModel):
    notas: str | None = Field(default=None, max_length=2000)
    copiar_de: UUID | None = None


class VersaoPatch(StrictHttpModel):
    descricao_modelo: str | None = Field(default=None, max_length=1024)
    corpo: str | None = Field(default=None, max_length=60_000)
    notas: str | None = Field(default=None, max_length=2000)


class ArquivoPut(StrictHttpModel):
    titulo: str | None = Field(default=None, max_length=200)
    conteudo: str = Field(max_length=120_000)


class RefPut(StrictHttpModel):
    #: Library version NUMBER to pin; omitted = the skill's current ``publicada`` version.
    versao: int | None = Field(default=None, ge=1)
    obrigatoria_para: list[str] = Field(default_factory=list, max_length=32)
    ordem: int = Field(default=0, ge=0, le=10_000)


class SkillOut(StrictHttpModel):
    id: UUID
    chave: str
    nome: str
    descricao: str | None
    versao_publicada: int | None = None
    tem_rascunho: bool = False


class SkillsOut(StrictHttpModel):
    items: list[SkillOut]


class VersaoMetaOut(StrictHttpModel):
    id: UUID
    versao: int
    status: str
    notas: str | None
    publicada_em: datetime | None


class VersoesOut(StrictHttpModel):
    items: list[VersaoMetaOut]


class ArquivoOut(StrictHttpModel):
    caminho: str
    titulo: str | None
    conteudo: str


class VersaoOut(StrictHttpModel):
    id: UUID
    skill: str
    versao: int
    status: str
    notas: str | None
    publicada_em: datetime | None
    descricao_modelo: str
    corpo: str
    arquivos: list[ArquivoOut]


class RefOut(StrictHttpModel):
    skill: str
    skill_versao_id: UUID
    versao: int
    obrigatoria_para: list[str]
    ordem: int
    #: The current published version when newer than the pinned one (Studio: "new version available").
    nova_versao: int | None = None
    nova_versao_id: UUID | None = None


class RefsOut(StrictHttpModel):
    version_id: UUID
    items: list[RefOut]


# ── helpers ─────────────────────────────────────────────────────────────────


def _err(status: int, code: str, detail: str) -> HTTPException:
    return HTTPException(status_code=status, detail={"detail": detail, "code": code})


class _Mapped:
    """Typed store errors -> HTTP codes. No message from the store (a DB error text can carry the
    failing row) is ever echoed."""

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if ev is None:
            return False
        if isinstance(ev, NotFound):
            raise _err(404, "not_found", "Nao encontrado.") from ev
        if isinstance(ev, VersionImmutable):
            raise _err(409, "version_immutable", "A versao publicada e imutavel.") from ev
        if isinstance(ev, StudioConflict):
            raise _err(409, ev.code, "Conflito.") from ev
        if isinstance(ev, ValueError):
            raise _err(422, "invalid_field", "Valor invalido.") from ev
        return False


def _versao_meta_out(v: SkillVersaoMeta) -> VersaoMetaOut:
    return VersaoMetaOut(id=v.id, versao=v.versao, status=v.status, notas=v.notas, publicada_em=v.publicada_em)


def _versao_out(v: SkillVersao) -> VersaoOut:
    return VersaoOut(
        id=v.meta.id, skill=v.skill_chave, versao=v.meta.versao, status=v.meta.status, notas=v.meta.notas,
        publicada_em=v.meta.publicada_em, descricao_modelo=v.descricao_modelo, corpo=v.corpo,
        arquivos=[ArquivoOut(caminho=a.caminho, titulo=a.titulo, conteudo=a.conteudo) for a in v.arquivos],
    )


def _ref_out(r: RefRecord) -> RefOut:
    return RefOut(
        skill=r.skill_chave, skill_versao_id=r.skill_versao_id, versao=r.versao,
        obrigatoria_para=list(r.obrigatoria_para), ordem=r.ordem, nova_versao=r.nova_versao,
        nova_versao_id=r.nova_versao_id,
    )


def _rascunho(store: SkillsBibliotecaStore, versao_id: UUID) -> SkillVersao:
    v = store.obter_versao(versao_id)
    if v.meta.status != "rascunho":
        raise VersionImmutable()
    return v


def _check_chave(chave: str) -> None:
    if not SKILL_CHAVE_RE.match(chave) or len(chave) > 64:
        raise _err(422, "invalid_field", "Valor invalido.")


# ── library: skills ─────────────────────────────────────────────────────────


@router.get("/api/skills-biblioteca", response_model=SkillsOut)
def listar_skills(
    ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> SkillsOut:
    items = []
    for s in store.listar_skills():
        versoes = store.listar_versoes(s.id)
        pub = next((v.versao for v in versoes if v.status == "publicada"), None)
        items.append(SkillOut(
            id=s.id, chave=s.chave, nome=s.nome, descricao=s.descricao, versao_publicada=pub,
            tem_rascunho=any(v.status == "rascunho" for v in versoes),
        ))
    return SkillsOut(items=items)


@router.post("/api/skills-biblioteca", status_code=201, response_model=SkillOut)
def criar_skill(
    body: SkillCreate, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> SkillOut:
    with _Mapped():
        s = store.criar_skill(body.chave, body.nome, body.descricao)
    return SkillOut(id=s.id, chave=s.chave, nome=s.nome, descricao=s.descricao)


@router.patch("/api/skills-biblioteca/{chave}", response_model=SkillOut)
def atualizar_skill(
    chave: str, body: SkillPatch, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> SkillOut:
    _check_chave(chave)
    with _Mapped():
        s = store.atualizar_skill(
            chave, body.nome, body.descricao, "descricao" in body.model_fields_set,
        )
    return SkillOut(id=s.id, chave=s.chave, nome=s.nome, descricao=s.descricao)


# ── library: versions ───────────────────────────────────────────────────────


@router.get("/api/skills-biblioteca/{chave}/versoes", response_model=VersoesOut)
def listar_versoes(
    chave: str, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> VersoesOut:
    _check_chave(chave)
    with _Mapped():
        skill = store.obter_skill(chave)
        return VersoesOut(items=[_versao_meta_out(v) for v in store.listar_versoes(skill.id)])


@router.post("/api/skills-biblioteca/{chave}/versoes", status_code=201, response_model=VersaoOut)
def criar_rascunho(
    chave: str, body: RascunhoCreate, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> VersaoOut:
    _check_chave(chave)
    with _Mapped():
        skill = store.obter_skill(chave)
        vid = store.criar_rascunho(skill.id, body.notas, body.copiar_de)
        return _versao_out(store.obter_versao(vid))


@router.get("/api/skills-biblioteca/versoes/{versao_id}", response_model=VersaoOut)
def obter_versao(
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> VersaoOut:
    with _Mapped():
        return _versao_out(store.obter_versao(versao_id))


@router.patch("/api/skills-biblioteca/versoes/{versao_id}", response_model=VersaoOut)
def atualizar_versao(
    versao_id: UUID, body: VersaoPatch, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> VersaoOut:
    campos = body.model_dump(exclude_unset=True)
    if any(campos.get(k) is None and k in campos for k in ("descricao_modelo", "corpo")):
        raise _err(422, "invalid_field", "Valor invalido.")
    with _Mapped():
        _rascunho(store, versao_id)
        store.salvar_rascunho(versao_id, campos)
        return _versao_out(store.obter_versao(versao_id))


@router.delete("/api/skills-biblioteca/versoes/{versao_id}", status_code=204)
def descartar_rascunho(
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> Response:
    with _Mapped():
        _rascunho(store, versao_id)
        store.descartar_rascunho(versao_id)
    return Response(status_code=204)


@router.put("/api/skills-biblioteca/versoes/{versao_id}/arquivos/{caminho:path}", response_model=VersaoOut)
def salvar_arquivo(
    versao_id: UUID, caminho: str, body: ArquivoPut, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> VersaoOut:
    with _Mapped():
        _rascunho(store, versao_id)
        store.salvar_arquivo(versao_id, caminho, body.titulo, body.conteudo)
        return _versao_out(store.obter_versao(versao_id))


@router.delete("/api/skills-biblioteca/versoes/{versao_id}/arquivos/{caminho:path}", status_code=204)
def remover_arquivo(
    versao_id: UUID, caminho: str, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> Response:
    with _Mapped():
        _rascunho(store, versao_id)
        store.remover_arquivo(versao_id, caminho)
    return Response(status_code=204)


@router.post("/api/skills-biblioteca/versoes/{versao_id}/publicar", response_model=VersaoOut)
def publicar_versao(
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    store: SkillsBibliotecaStore = Depends(get_skills_store_dep),
) -> VersaoOut:
    """Draft -> published (the previous published version is archived; pins keep pointing at it).
    A human platform-admin act: the MCP content token never publishes (403 ``user_required``)."""
    if ctx.user_id is None:
        raise _err(403, "user_required", "Restrito a usuarios humanos.")
    with _Mapped():
        v = _rascunho(store, versao_id)
        if not v.corpo.strip() or not v.descricao_modelo.strip():
            raise _err(422, "skill_incompleta", "A skill precisa de descricao e corpo.")
        store.publicar(versao_id, ctx.user_id)
        return _versao_out(store.obter_versao(versao_id))


# ── pins on an agent version ────────────────────────────────────────────────


def _audit_pin(store, ctx: AuthContext, agent, version_id: UUID, antes: list[str], depois: list[str]) -> None:
    """A pin change made with a product token (the MCP path) is audit-logged: who, what, where."""
    if ctx.caller_kind != "product":
        return
    store.append_audit(
        agent.org_id, agent.id, actor_id(ctx), "conteudo_editado_mcp",
        {"kind": "skill_ref", "version_id": str(version_id), "chaves": antes},
        {"kind": "skill_ref", "version_id": str(version_id), "chaves": depois},
    )


@router.get("/api/studio/agents/{key}/versions/{version_id}/skills-biblioteca", response_model=RefsOut)
def listar_refs_da_versao(
    key: str, version_id: UUID, ctx: AuthContext = Depends(require_platform_content_admin),
    skills: SkillsBibliotecaStore = Depends(get_skills_store_dep),
    store=Depends(get_studio_definition_store_dep),
) -> RefsOut:
    agent = resolve_agent(store, ctx.org_id, key)
    v = resolve_version(store, ctx.org_id, agent, version_id)
    audit_definition_read(store, ctx, agent, "skills-biblioteca", v.id)
    return RefsOut(version_id=v.id, items=[_ref_out(r) for r in skills.listar_refs(v.id)])


@router.get("/api/studio/agents/{key}/draft/skills-biblioteca", response_model=RefsOut)
def listar_refs_do_rascunho(
    key: str, ctx: AuthContext = Depends(require_platform_content_admin),
    skills: SkillsBibliotecaStore = Depends(get_skills_store_dep),
    store=Depends(get_studio_definition_store_dep),
) -> RefsOut:
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    audit_definition_read(store, ctx, agent, "skills-biblioteca", draft.id)
    return RefsOut(version_id=draft.id, items=[_ref_out(r) for r in skills.listar_refs(draft.id)])


@router.put("/api/studio/agents/{key}/draft/skills-biblioteca/{skill}", response_model=RefsOut)
def fixar_ref(
    key: str, skill: str, body: RefPut, ctx: AuthContext = Depends(require_platform_content_admin),
    skills: SkillsBibliotecaStore = Depends(get_skills_store_dep),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> RefsOut:
    _check_chave(skill)
    if any(not _TOOL_RE.match(t) for t in body.obrigatoria_para):
        raise _err(422, "invalid_field", "Valor invalido.")
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    antes = [r.skill_chave for r in skills.listar_refs(draft.id)]
    with _Mapped():
        lib = skills.obter_skill(skill)
        versoes = skills.listar_versoes(lib.id)
        if body.versao is None:
            alvo = next((v for v in versoes if v.status == "publicada"), None)
        else:
            alvo = next((v for v in versoes if v.versao == body.versao), None)
        if alvo is None:
            raise NotFound("versao")
        if alvo.status == "rascunho":
            # A draft is mutable: pinning it would defeat the immutability of a published agent version.
            raise _err(409, "versao_nao_publicada", "Fixe uma versao publicada da skill.")
        skills.fixar_ref(draft.org_id, draft.id, alvo.id, list(body.obrigatoria_para), body.ordem)
    depois = [r.skill_chave for r in skills.listar_refs(draft.id)]
    _audit_pin(store, ctx, agent, draft.id, antes, depois)
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return RefsOut(version_id=draft.id, items=[_ref_out(r) for r in skills.listar_refs(draft.id)])


@router.delete("/api/studio/agents/{key}/draft/skills-biblioteca/{skill}", response_model=RefsOut)
def remover_ref(
    key: str, skill: str, ctx: AuthContext = Depends(require_platform_content_admin),
    skills: SkillsBibliotecaStore = Depends(get_skills_store_dep),
    store=Depends(get_studio_definition_store_dep), catalog=Depends(get_knowledge_catalog_dep),
) -> RefsOut:
    _check_chave(skill)
    agent = resolve_agent(store, ctx.org_id, key)
    draft = resolve_draft(store, ctx.org_id, agent)
    antes = [r.skill_chave for r in skills.listar_refs(draft.id)]
    with _Mapped():
        skills.remover_ref(draft.id, skill)
    depois = [r.skill_chave for r in skills.listar_refs(draft.id)]
    _audit_pin(store, ctx, agent, draft.id, antes, depois)
    _refresh_draft_hash(store, catalog, ctx.org_id, agent, draft.id)
    return RefsOut(version_id=draft.id, items=[_ref_out(r) for r in skills.listar_refs(draft.id)])


__all__ = ["router", "get_skills_store_dep"]
