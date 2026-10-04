"""`POST /api/public/ask/{app_slug}` — anonymous, stateless, text-free.

Hardening (projects/limiar-open-question §5.3):
- OFF unless `PUBLIC_ASK_ENABLED` (404 otherwise); only `limiar` is registered.
- 2 KB body cap (`max_body_path_overrides` in main.py → 413 before parsing).
- The body is parsed HERE, not by FastAPI's body binding, so a malformed input
  yields `400 {"code":"entrada_invalida"}` with NO input echoed — FastAPI's own
  422 body repeats `input`. Scoped to this router; no global handler changes.
- Per-IP 5/min + 30/day (seed limiter, `client_ip_key`); the seed 429 body is generic.
- Audit: the seed `AuditMiddleware` records only method/route template/status/
  path params (never a body); request logging records path + status. Neither
  sees the text, and the no-log proof test pins that.
"""
# NOTE: no `from __future__ import annotations` — slowapi-decorated routes lose their
# type resolution under postponed annotations (see app/routers/conversations_router.py).
import json
import logging
from dataclasses import dataclass
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse
from pydantic import Field, ValidationError

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.rate_limit import client_ip_key

from app.config import settings
from app.rate_limit import limiter

from . import limiar
from .service import AskRequest, PublicAskService

logger = logging.getLogger(__name__)

MAX_BODY_BYTES = 2048
BODY_LIMIT_PATTERN = "/api/public/ask/*"
RATE_LIMIT = "5/minute;30/day"

router = APIRouter(prefix="/api/public/ask", tags=["public-ask"])


class AskBody(StrictHttpModel):
    tema: Literal[
        "filhos-adultos",
        "relacionamento",
        "rotina-e-tempo",
        "trabalho-e-projetos",
        "amizades",
        "quem-sou-hoje",
        "planos-e-interesses",
        "outro-assunto",
    ]
    texto: str = Field(min_length=1, max_length=600)
    versao_triagem: str = Field(min_length=1, max_length=64)


@dataclass(frozen=True)
class PublicAskConfig:
    enabled: bool


def get_public_ask_config_dep() -> PublicAskConfig:
    """DI seam — tests override it (never a settings monkeypatch)."""
    return PublicAskConfig(enabled=settings.public_ask_enabled)


def get_public_ask_service_dep() -> PublicAskService:
    from .wiring import build_default_service

    return build_default_service()


def _not_found() -> HTTPException:
    return HTTPException(status_code=404, detail="Recurso não encontrado.")


async def require_enabled(cfg: PublicAskConfig = Depends(get_public_ask_config_dep)) -> None:
    if not cfg.enabled:
        raise _not_found()


def _entrada_invalida() -> JSONResponse:
    return JSONResponse(status_code=400, content={"code": "entrada_invalida"})


@router.post("/{app_slug}", dependencies=[Depends(require_enabled)])
@limiter.limit(RATE_LIMIT, key_func=client_ip_key)
async def ask(
    request: Request,
    app_slug: str,
    service: PublicAskService = Depends(get_public_ask_service_dep),
) -> JSONResponse:
    if app_slug != limiar.APP_SLUG:
        raise _not_found()
    raw = await request.body()
    if len(raw) > MAX_BODY_BYTES:
        return JSONResponse(status_code=413, content={"code": "entrada_invalida"})
    try:
        body = AskBody.model_validate(json.loads(raw))
    except (ValueError, ValidationError):  # json errors are ValueErrors; never echoed
        return _entrada_invalida()
    if not body.texto.strip():
        return _entrada_invalida()
    try:
        result = await service.ask(
            AskRequest(tema=body.tema, texto=body.texto, versao_triagem=body.versao_triagem)
        )
    except Exception as exc:  # last resort: fail-closed editorial, never an error page
        logger.error("public_ask.unexpected type=%s", type(exc).__name__)
        result = service.editorial_fallback()
    return JSONResponse(status_code=200, content=result)


__all__ = ["router", "AskBody", "BODY_LIMIT_PATTERN", "MAX_BODY_BYTES"]
