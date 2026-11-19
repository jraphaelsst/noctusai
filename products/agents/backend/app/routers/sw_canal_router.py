"""Staff view of the onboarding channel to social-wiring (owner 2026-11-18): is it connected, and does it work?

``GET  /api/studio/plataforma/sw-canal``         credential state (provisionado / ausente / expirado / erro), scope, expiry,
                                                 last successful call and last error. READ-ONLY: it never provisions.
``POST /api/studio/plataforma/sw-canal/testar``  provisions the token if it is due, then makes a harmless read-only
                                                 authenticated call (``whoami``) to social-wiring and reports the result.

Platform admin only. The token is provisioned and rotated by agents itself (:mod:`app.onboarding.sw_canal`); no route here
can set, import, reveal or return it -- the response models have no field that could carry it.
"""
from __future__ import annotations

import logging
from datetime import datetime
from functools import lru_cache

from fastapi import Depends, Response
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth.session import AuthContext
from pydantic import BaseModel

from app.dependencies import require_platform_admin
from app.onboarding.sw_canal import CanalStatus, SwCanal, get_sw_canal
from app.routers.studio_agents_router import http_error
from app.stores.sw_canal_eventos import EventoCanal

logger = logging.getLogger(__name__)

router = make_router(tier="platform", guard=require_platform_admin, tags=["onboarding"])

_BASE = "/api/studio/plataforma/sw-canal"


@lru_cache(maxsize=1)
def _canal_do_processo() -> SwCanal:
    from app.config import settings

    return get_sw_canal(settings)


def get_sw_canal_dep() -> SwCanal:
    """DI seam: the process-wide channel (one lock per process); tests override."""
    return _canal_do_processo()


class EventoOut(BaseModel):
    em: datetime
    evento: str
    codigo: str | None = None
    motivo: str | None = None


class CanalStatusOut(BaseModel):
    estado: str
    escopo: str
    emissor: str
    expira_em: datetime | None = None
    dias_restantes: int | None = None
    ultima_chamada_ok: EventoOut | None = None
    ultimo_erro: EventoOut | None = None
    codigo: str | None = None
    motivo: str | None = None


class TesteOut(BaseModel):
    ok: bool
    codigo: str | None = None
    motivo: str
    status: CanalStatusOut


def _evento(e: EventoCanal | None) -> EventoOut | None:
    return None if e is None else EventoOut(em=e.em, evento=e.evento, codigo=e.codigo, motivo=e.mensagem)


def _out(s: CanalStatus) -> CanalStatusOut:
    return CanalStatusOut(
        estado=s.estado, escopo=s.escopo, emissor=s.emissor, expira_em=s.expira_em, dias_restantes=s.dias_restantes,
        ultima_chamada_ok=_evento(s.ultima_chamada_ok), ultimo_erro=_evento(s.ultimo_erro), codigo=s.codigo, motivo=s.mensagem)


@router.get(_BASE, response_model=CanalStatusOut)
def get_status(
    response: Response, ctx: AuthContext = Depends(require_platform_admin), canal: SwCanal = Depends(get_sw_canal_dep),
) -> CanalStatusOut:
    response.headers["Cache-Control"] = "no-store"
    try:
        return _out(canal.status())
    except Exception as exc:
        logger.error("agents.sw_canal.status_failed error=%s", type(exc).__name__)
        raise http_error(502, "status_indisponivel", "Não foi possível ler o estado da conexão.") from exc


@router.post(f"{_BASE}/testar", response_model=TesteOut)
def post_testar(
    response: Response, ctx: AuthContext = Depends(require_platform_admin), canal: SwCanal = Depends(get_sw_canal_dep),
) -> TesteOut:
    response.headers["Cache-Control"] = "no-store"
    try:
        teste, status = canal.testar(ctx.org_id, ctx.user_id)
    except Exception as exc:
        logger.error("agents.sw_canal.test_failed error=%s", type(exc).__name__)
        raise http_error(502, "teste_indisponivel", "Não foi possível testar a conexão.") from exc
    return TesteOut(ok=teste.ok, codigo=teste.codigo, motivo=teste.mensagem, status=_out(status))
