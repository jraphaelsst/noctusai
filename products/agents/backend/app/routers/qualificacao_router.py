"""Qualification standard API (Julia v2 CONTRACT §3, §8.2).

* ``/api/qualificacao/...`` — the platform-wide standard (the same for every org, owner decision
  Q2). Reads, writes and publish are NoctusAI platform admin only (``require_platform_admin``, 403
  ``platform_admin_required``): criteria, ``descricao_modelo``, weights and rules are platform IP.
  Org admins and SW only ever get the COMPUTED state (stage, score, faltando keys) via the channel route.
* ``GET /api/channels/leads/{lead_ref}/qualificacao`` — the computed state of one
  lead (channel token, ``agents:channel-status``), org-scoped by the token.

Seams (FastAPI dependencies, overridable in tests): ``get_padrao_store_dep``,
``get_lead_qualificacao_store_dep``.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response
from pydantic import Field

from app.dependencies import (
    require_admin,
    require_channel_status,
    require_channel_turn,
    require_platform_admin,
)
from app.qualificacao import engine
from app.qualificacao.identificacao import EncryptionNotConfigured, IdentificacaoService, RevelarNegado
from app.qualificacao.lead_store import LeadQualificacaoStore
from app.qualificacao.models import EventoImovel, LeadSinais
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
from noctusai_lib.api import StrictHttpModel
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


def get_identificacao_service_dep() -> IdentificacaoService:
    from app.config import settings
    from app.qualificacao.ident_store import get_identificacao_service

    return get_identificacao_service(settings)


def _service(padroes, leads, ident) -> QualificacaoService:
    return QualificacaoService(padroes, leads, identificacao=ident)


def get_qualificacao_service_dep(
    padroes=Depends(get_padrao_store_dep),
    leads=Depends(get_lead_qualificacao_store_dep),
    ident=Depends(get_identificacao_service_dep),
) -> QualificacaoService:
    """The qualification service over the three seams (a test overrides any of them) -- what the channel
    turn and the delete-by-lead route share."""
    return _service(padroes, leads, ident)


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
    ctx: AuthContext = Depends(require_platform_admin), store: PadraoStore = Depends(get_padrao_store_dep),
) -> dict[str, Any]:
    return {"items": [
        {"id": str(p.id), "chave": p.chave, "nome": p.nome, "descricao": p.descricao}
        for p in store.listar_padroes()
    ]}


@router.get("/api/qualificacao/padroes/{chave}/versoes")
async def listar_versoes(
    chave: str, ctx: AuthContext = Depends(require_platform_admin), store: PadraoStore = Depends(get_padrao_store_dep),
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
    versao_id: UUID, ctx: AuthContext = Depends(require_platform_admin), store: PadraoStore = Depends(get_padrao_store_dep),
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
    ident: IdentificacaoService = Depends(get_identificacao_service_dep),
) -> dict[str, Any]:
    """Computed state: stage + the rule ID that fired, total and per-axis scores, missing criterion KEYS, a
    suggested (never applied) discard, property events. Never weights, rule bodies, ``descricao_modelo``,
    literal quotes or identity values (platform IP / LGPD)."""
    service = _service(padroes, leads, ident)
    with _Mapped():
        q = service.obter_qualificacao(ctx.org_id, lead_ref)
    if q is None:
        raise _err(404, "lead_sem_qualificacao", "Lead sem qualificacao registrada.")
    e = q.estado
    return {
        "lead_ref": str(lead_ref), "versao_id": str(q.versao_id), "estagio": e.estagio, "regra_id": e.regra_id,
        "score": e.score, "scores": dict(e.scores),
        "descartado_sugerido": e.descartado_sugerido, "valores": e.valores, "faltando": list(e.faltando),
        "identificacao_faltando": list(e.identificacao_faltando) if e.pedir_identificacao else [],
        "pode_ofertar": e.pode_ofertar, "pode_concluir": e.pode_concluir, "hash": e.hash,
        "calculado_em": q.calculado_em.isoformat(),
        "eventos_imovel": [_evento_out(ev) for ev in q.eventos],
    }


class SinaisIn(StrictHttpModel):
    ultima_resposta_em: datetime | None = None
    respostas_count: int | None = Field(default=None, ge=0)
    eventos: dict[str, int] = Field(default_factory=dict)

    def to_sinais(self) -> LeadSinais:
        return LeadSinais(self.ultima_resposta_em, self.respostas_count, dict(self.eventos))


class ConfirmarDescarteIn(StrictHttpModel):
    ator_user_id: UUID
    motivo: str | None = Field(default=None, max_length=500)
    estagio: str | None = Field(default=None, max_length=64)
    sinais: SinaisIn | None = None


@router.post("/api/channels/leads/{lead_ref}/descarte/confirmar")
async def confirmar_descarte(
    lead_ref: UUID,
    body: ConfirmarDescarteIn,
    ctx: AuthContext = Depends(require_channel_turn),
    padroes: PadraoStore = Depends(get_padrao_store_dep),
    leads: LeadQualificacaoStore = Depends(get_lead_qualificacao_store_dep),
    ident: IdentificacaoService = Depends(get_identificacao_service_dep),
) -> dict[str, Any]:
    """LGPD art. 20: the engine only SUGGESTS ``descartado``; a human (``ator_user_id``) confirms here."""
    cache = leads.obter_estado(ctx.org_id, lead_ref)
    if cache is None:
        raise _err(404, "lead_sem_qualificacao", "Lead sem qualificacao registrada.")
    with _Mapped():
        r = _service(padroes, leads, ident).confirmar_terminal(
            ctx.org_id, lead_ref, cache.versao_id, ator_user_id=body.ator_user_id, estagio=body.estagio,
            motivo=body.motivo, sinais=body.sinais.to_sinais() if body.sinais else None,
        )
    if not r.ok:
        raise _err(409, r.codigo or "conflito", "Nada a confirmar.")
    return {"estagio": r.estado.estagio, "regra_id": r.estado.regra_id}


# ── lead identity: masked by default, clear text only for org owner/admin, audited ──

@router.get("/api/channels/leads/{lead_ref}/identificacao")
async def identificacao_mascarada(
    lead_ref: UUID,
    ctx: AuthContext = Depends(require_channel_status),
    ident: IdentificacaoService = Depends(get_identificacao_service_dep),
) -> dict[str, Any]:
    m = ident.mascarado(ctx.org_id, lead_ref)
    if m is None:
        raise _err(404, "lead_sem_identificacao", "Lead sem identificacao registrada.")
    return m


class RevelarIn(StrictHttpModel):
    motivo: str | None = Field(default=None, max_length=500)


@router.post("/api/qualificacao/leads/{lead_ref}/identificacao/revelar")
async def revelar_identificacao(
    lead_ref: UUID,
    body: RevelarIn,
    ctx: AuthContext = Depends(require_admin),
    ident: IdentificacaoService = Depends(get_identificacao_service_dep),
) -> dict[str, Any]:
    """Clear CPF/RG for an org owner/admin (human session). The access is audited BEFORE the value is returned."""
    if ctx.user_id is None:
        raise _err(403, "user_required", "Restricted to human users")
    try:
        return ident.revelar(ctx.org_id, lead_ref, ator_user_id=ctx.user_id, motivo=body.motivo)
    except RevelarNegado as exc:
        raise _err(404, "lead_sem_identificacao", "Lead sem identificacao registrada.") from exc
    except EncryptionNotConfigured as exc:
        raise _err(503, "encryption_not_configured", "Chave de cifra nao configurada.") from exc


def _evento_out(ev: EventoImovel) -> dict[str, Any]:
    return {
        "codigo_imovel": ev.codigo_imovel, "evento": ev.evento, "origem": ev.origem, "lote": ev.lote,
        "motivo": ev.motivo, "created_at": ev.created_at.isoformat() if ev.created_at else None,
    }


__all__ = ["router", "get_padrao_store_dep", "get_lead_qualificacao_store_dep", "get_identificacao_service_dep"]
