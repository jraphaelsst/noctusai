"""Qualification standard API (Julia v2 CONTRACT §3, §8.2).

* ``/api/qualificacao/...`` — the platform-wide standard. Reads: any org member
  (the standard is the same for every org, owner decision Q2). Writes + publish:
  NoctusAI platform admin only (``require_platform_admin``); there is no per-org
  fork and no "Personalizar".
* ``GET /api/channels/leads/{lead_ref}/qualificacao`` — the computed state of one
  lead (channel token, ``agents:channel-status``), org-scoped by the token.

Seams (FastAPI dependencies, overridable in tests): ``get_padrao_store_dep``,
``get_lead_qualificacao_store_dep``.
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response

from app.dependencies import require_channel_status, require_member, require_platform_admin
from app.qualificacao import engine
from app.qualificacao.lead_store import LeadQualificacaoStore
from app.qualificacao.models import EventoImovel
from app.qualificacao.schemas import (
    CriterioIn,
    EstagioIn,
    ParametrosIn,
    PadraoCreate,
    RascunhoCreate,
    VersaoPatch,
    versao_out,
)
from app.qualificacao.service import QualificacaoService
from app.qualificacao.store import PadraoStore
from app.stores._db_errors import StudioConflict, VersionImmutable
from app.stores.errors import NotFound
from noctusai_lib.api.auth.session import AuthContext

router = APIRouter(tags=["qualificacao"])


def get_padrao_store_dep() -> PadraoStore:
    from app.config import settings
    from app.qualificacao.store import get_padrao_store

    return get_padrao_store(settings)


def get_lead_qualificacao_store_dep() -> LeadQualificacaoStore:
    from app.config import settings
    from app.qualificacao.lead_store import get_lead_qualificacao_store

    return get_lead_qualificacao_store(settings)


def _err(status: int, code: str, detail: str, **extra: Any) -> HTTPException:
    return HTTPException(status_code=status, detail={"detail": detail, "code": code, **extra})


def _actor(ctx: AuthContext) -> UUID:
    if ctx.user_id is None:
        raise _err(403, "user_required", "Restricted to human users")
    return ctx.user_id


class _Mapped:
    """Context manager: typed store errors -> HTTP codes."""

    def __enter__(self):
        return self

    def __exit__(self, et, ev, tb):
        if ev is None:
            return False
        if isinstance(ev, NotFound):
            raise _err(404, "not_found", str(ev)) from ev
        if isinstance(ev, VersionImmutable):
            raise _err(409, "version_immutable", "A versao publicada e imutavel.") from ev
        if isinstance(ev, StudioConflict):
            raise _err(409, ev.code, str(ev)) from ev
        if isinstance(ev, ValueError):
            raise _err(422, "invalid_field", str(ev)) from ev
        return False


def _draft(store: PadraoStore, versao_id: UUID):
    """The version, 409 ``version_immutable`` unless it is a draft."""
    v = store.obter_versao(versao_id)
    if v.status != "rascunho":
        raise VersionImmutable()
    return v


# ── reads (any org member) ──────────────────────────────────────────────────

@router.get("/api/qualificacao/padroes")
async def listar_padroes(
    ctx: AuthContext = Depends(require_member), store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    return {"items": [
        {"id": str(p.id), "chave": p.chave, "nome": p.nome, "descricao": p.descricao}
        for p in store.listar_padroes()
    ]}


@router.get("/api/qualificacao/padroes/{chave}/versoes")
async def listar_versoes(
    chave: str, ctx: AuthContext = Depends(require_member), store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        padrao = store.obter_padrao(chave)
        versoes = store.listar_versoes(padrao.id)
    return {"items": [
        {"id": str(v.id), "versao": v.versao, "status": v.status, "notas": v.notas,
         "publicada_em": v.publicada_em.isoformat() if v.publicada_em else None}
        for v in versoes
    ]}


@router.get("/api/qualificacao/versoes/{versao_id}")
async def obter_versao(
    versao_id: UUID, ctx: AuthContext = Depends(require_member), store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        return versao_out(store.obter_versao(versao_id))


# ── writes (platform admin) ─────────────────────────────────────────────────

@router.post("/api/qualificacao/padroes", status_code=201)
async def criar_padrao(
    body: PadraoCreate, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        p = store.criar_padrao(body.chave, body.nome, body.descricao)
    return {"id": str(p.id), "chave": p.chave, "nome": p.nome, "descricao": p.descricao}


@router.post("/api/qualificacao/padroes/{chave}/versoes", status_code=201)
async def criar_rascunho(
    chave: str, body: RascunhoCreate, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        padrao = store.obter_padrao(chave)
        vid = store.criar_rascunho(padrao.id, body.notas, body.copiar_de)
        return versao_out(store.obter_versao(vid))


@router.patch("/api/qualificacao/versoes/{versao_id}")
async def atualizar_versao(
    versao_id: UUID, body: VersaoPatch, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        _draft(store, versao_id)
        store.atualizar_notas(versao_id, body.notas)
        return versao_out(store.obter_versao(versao_id))


@router.delete("/api/qualificacao/versoes/{versao_id}", status_code=204)
async def descartar_rascunho(
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> Response:
    with _Mapped():
        _draft(store, versao_id)
        store.descartar_rascunho(versao_id)
    return Response(status_code=204)


@router.put("/api/qualificacao/versoes/{versao_id}/criterios/{chave}")
async def salvar_criterio(
    versao_id: UUID, chave: str, body: CriterioIn, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", chave):
        raise _err(422, "invalid_field", "chave invalida")
    with _Mapped():
        _draft(store, versao_id)
        store.salvar_criterio(versao_id, body.to_def(chave))
        return versao_out(store.obter_versao(versao_id))


@router.delete("/api/qualificacao/versoes/{versao_id}/criterios/{chave}")
async def remover_criterio(
    versao_id: UUID, chave: str, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        _draft(store, versao_id)
        store.remover_criterio(versao_id, chave)
        return versao_out(store.obter_versao(versao_id))


@router.put("/api/qualificacao/versoes/{versao_id}/estagios/{chave}")
async def salvar_estagio(
    versao_id: UUID, chave: str, body: EstagioIn, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    import re

    if not re.fullmatch(r"[a-z][a-z0-9_]{1,63}", chave):
        raise _err(422, "invalid_field", "chave invalida")
    with _Mapped():
        _draft(store, versao_id)
        store.salvar_estagio(versao_id, body.to_def(chave))
        return versao_out(store.obter_versao(versao_id))


@router.delete("/api/qualificacao/versoes/{versao_id}/estagios/{chave}")
async def remover_estagio(
    versao_id: UUID, chave: str, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        _draft(store, versao_id)
        store.remover_estagio(versao_id, chave)
        return versao_out(store.obter_versao(versao_id))


@router.put("/api/qualificacao/versoes/{versao_id}/parametros")
async def salvar_parametros(
    versao_id: UUID, body: ParametrosIn, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        _draft(store, versao_id)
        store.salvar_parametros(versao_id, body.to_def())
        return versao_out(store.obter_versao(versao_id))


def _erros_de_publicacao(store: PadraoStore, versao_id: UUID) -> list[dict[str, str]]:
    v = store.obter_versao(versao_id)
    erros = engine.validar_versao(v)
    if not store.tem_parametros(versao_id):
        erros.append({"code": "parametros_ausentes", "path": "parametros", "detail": "defina os parametros"})
    return erros


@router.post("/api/qualificacao/versoes/{versao_id}/validar")
async def validar_versao(
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    with _Mapped():
        _draft(store, versao_id)
        erros = _erros_de_publicacao(store, versao_id)
    return {"ok": not erros, "erros": erros}


@router.post("/api/qualificacao/versoes/{versao_id}/publicar")
async def publicar_versao(
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_admin),
    store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    actor = _actor(ctx)
    with _Mapped():
        _draft(store, versao_id)
        erros = _erros_de_publicacao(store, versao_id)
        if erros:
            raise _err(422, "regras_invalidas", "A versao nao pode ser publicada.", erros=erros)
        store.publicar(versao_id, actor)
        return versao_out(store.obter_versao(versao_id))


# ── org-read: the computed state of one lead (channel token) ────────────────

@router.get("/api/channels/leads/{lead_ref}/qualificacao")
async def obter_qualificacao_lead(
    lead_ref: UUID,
    ctx: AuthContext = Depends(require_channel_status),
    padroes: PadraoStore = Depends(get_padrao_store_dep),
    leads: LeadQualificacaoStore = Depends(get_lead_qualificacao_store_dep),
) -> dict[str, Any]:
    service = QualificacaoService(padroes, leads)
    with _Mapped():
        q = service.obter_qualificacao(ctx.org_id, lead_ref)
    if q is None:
        raise _err(404, "lead_sem_qualificacao", "Lead sem qualificacao registrada.")
    e = q.estado
    return {
        "lead_ref": str(lead_ref), "versao_id": str(q.versao_id), "estagio": e.estagio, "score": e.score,
        "scores": dict(e.scores), "valores": e.valores, "faltando": list(e.faltando), "pode_ofertar": e.pode_ofertar,
        "pode_concluir": e.pode_concluir, "hash": e.hash,
        "calculado_em": q.calculado_em.isoformat(),
        "eventos_imovel": [_evento_out(ev) for ev in q.eventos],
    }


def _evento_out(ev: EventoImovel) -> dict[str, Any]:
    return {
        "codigo_imovel": ev.codigo_imovel, "evento": ev.evento, "origem": ev.origem, "lote": ev.lote,
        "motivo": ev.motivo, "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


__all__ = ["router", "get_padrao_store_dep", "get_lead_qualificacao_store_dep"]
