"""Lais / Julia agent surface (contract section 5) -- privacy-notice endpoints.

Slice P ships only the aviso endpoints; slice W1 adds the rest of the router.

  GET  /api/public/lais/privacidade/{slug}   public, no auth, rate-limited
  GET  /api/lais/agente/aviso                org member
  PUT  /api/lais/agente/aviso                core org role owner/admin

# NOC-REMEDIATE[seed-promotion]: per-org public privacy notice -- promote to the seed as `org_privacy_notice` (router + table + default template) when the 2nd consumer (store/igig) needs it — 2026-10-14
"""
# No `from __future__ import annotations`: this module carries
# `@limiter.limit` (check_slowapi_with_pep563).
import logging
from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_role
from noctusai_lib.primitives.exceptions import AppException

from app.config import settings
from app.dependencies import (
    coerce_org_uuid,
    get_core_client,
    get_current_user_org,
    get_scoped_admin_client,
)
from app.rate_limit import limiter
from app.services import lais_aviso_service as svc

logger = logging.getLogger(__name__)

router = APIRouter(tags=["lais-agente"])


class _Secao(StrictHttpModel):
    n: str = Field(min_length=1, max_length=8)
    title: str = Field(min_length=1, max_length=200)
    blocks: list[dict[str, Any]]


class AvisoUpdate(StrictHttpModel):
    titulo: str = Field(min_length=1, max_length=200)
    empresa_nome: str = Field(min_length=1, max_length=200)
    contato_email: Optional[str] = Field(default=None, max_length=200)
    contato_whatsapp: Optional[str] = Field(default=None, max_length=40)
    secoes: list[_Secao] = Field(min_length=1, max_length=40)
    mensagem_inicial: str = Field(min_length=1, max_length=1000)


def _validar_blocos(secoes: list[_Secao]) -> None:
    for s in secoes:
        for b in s.blocks:
            ok = (
                (set(b) == {"p"} and isinstance(b["p"], str))
                or (set(b) == {"ul"} and isinstance(b["ul"], list)
                    and all(isinstance(i, str) for i in b["ul"]))
            )
            if not ok:
                raise AppException(
                    "secoes_invalidas",
                    "Cada bloco deve ser {p: texto} ou {ul: [textos]}.",
                    status_code=422,
                )


def _admin_row(auth: tuple) -> tuple[dict[str, Any], Any, Any]:
    user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_scoped_admin_client("social_wiring")
    row = svc.obter_ou_criar(client, get_core_client(), org_id)
    return row, client, (user, org_id)


def _saida_admin(row: dict[str, Any]) -> dict[str, Any]:
    return {**row, "incompleto": svc.incompleto(row)}


@router.get("/api/public/lais/privacidade/{slug}")
@limiter.limit(settings.webhook_rate_limit)
def get_aviso_publico(slug: str, request: Request) -> dict[str, Any]:
    """Public notice by slug. Returns ONLY the notice fields (never org ids,
    users or settings)."""
    row = svc.buscar_por_slug(get_scoped_admin_client("social_wiring"), slug)
    if row is None:
        raise HTTPException(status_code=404, detail="Aviso não encontrado")
    return {"data": svc.somente_publico(row)}


@router.get("/api/lais/agente/aviso")
def get_aviso(auth: tuple = Depends(get_current_user_org)) -> dict[str, Any]:
    row, _client, _ctx = _admin_row(auth)
    return {"data": _saida_admin(row)}


@router.put("/api/lais/agente/aviso")
def put_aviso(payload: AvisoUpdate, auth: tuple = Depends(get_current_user_org)) -> dict[str, Any]:
    user, _token, _raw = auth
    require_org_admin_role(get_core_client(), getattr(user, "id", None), "Aviso de privacidade")
    if not svc.contem_link(payload.mensagem_inicial):
        raise AppException(
            "link_obrigatorio",
            "A mensagem inicial deve conter {link} (link do aviso de privacidade).",
            status_code=422,
        )
    _validar_blocos(payload.secoes)
    row, client, (_u, org_id) = _admin_row(auth)
    dados = payload.model_dump()
    dados["secoes"] = [s.model_dump() for s in payload.secoes]
    novo = svc.atualizar(client, org_id, row, dados, getattr(user, "id", None))
    return {"data": _saida_admin(novo)}


__all__ = ["router"]
