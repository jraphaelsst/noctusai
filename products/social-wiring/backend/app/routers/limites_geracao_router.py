"""GET/PUT /api/settings/limites-geracao -- the org's daily generation limits (geracao-contract.md §9.4.1).

Tier ``org`` (``get_current_user_org``: strict 401 without a session). The read is open to every member -- a
person who hits a limit should be able to see it; the write is org owner/admin only (``require_org_admin_for``,
the trusted ``noctus_users`` row, 403 otherwise). Same envelope as ``/api/settings/documento-retencao``: a plain
response model carrying the WHOLE list, so the screen writes one answer into its cache.

Values resolve through ``app.modules.media_creation.limites_geracao`` (org_settings -> platform_settings -> env ->
config); the write is the ``cs_limite_geracao_definir`` RPC (override + event, one transaction, migration 361).
"""
from __future__ import annotations

import logging
from typing import Literal, Optional

from fastapi import Depends, HTTPException, Request
from pydantic import BaseModel, Field, StrictInt, field_validator

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.config.credentials import resolve_org_credential

from app.config import SocialWiringSettings
from app.dependencies import coerce_org_uuid, get_admin_client, get_core_client, get_current_user_org, get_settings
from app.modules.media_creation import limites_geracao as lg

logger = logging.getLogger(__name__)
router = make_router(
    tier="org", guard=get_current_user_org, prefix="/api/settings/limites-geracao",
    tags=["settings — limites diários"],
)


class LimiteGeracao(BaseModel):
    """One row of the "Limites diários" screen: the effective value, the default a reset restores, the ceiling."""

    chave: str
    rotulo: str
    descricao: str
    escopo: Literal["usuario", "marca", "org"]
    valor: int
    padrao: int
    maximo: int
    personalizado: bool


class LimitesGeracaoLista(BaseModel):
    items: list[LimiteGeracao]
    total: int


class LimitesGeracaoUpdate(StrictHttpModel):
    """``{"limites": {"<chave>": <int> | null}}`` -- ``null`` restores the default. Validated whole before any write:
    an unknown key, a non-integer, or a value outside ``[1, maximo]`` is a 422 and nothing changes."""

    limites: dict[str, Optional[StrictInt]] = Field(..., min_length=1, max_length=len(lg.LIMITES))

    @field_validator("limites")
    @classmethod
    def _dentro_dos_limites(cls, v: dict[str, Optional[int]]) -> dict[str, Optional[int]]:
        try:
            return lg.validar_alteracoes(v)
        except lg.LimiteInvalido as exc:
            raise ValueError(str(exc)) from exc


def _lista(org_id: str, cfg: SocialWiringSettings) -> LimitesGeracaoLista:
    items = [LimiteGeracao(**i) for i in lg.listar(org_id, cfg, ler_org=resolve_org_credential)]
    return LimitesGeracaoLista(items=items, total=len(items))


@router.get("", response_model=LimitesGeracaoLista)
def get_limites_geracao(
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> LimitesGeracaoLista:
    """Every daily limit of this org (any member may read)."""
    _user, _token, raw_org = auth
    return _lista(str(coerce_org_uuid(raw_org)), cfg)


@router.put("", response_model=LimitesGeracaoLista)
def update_limites_geracao(
    payload: LimitesGeracaoUpdate,
    request: Request,
    auth: tuple = Depends(get_current_user_org),
    cfg: SocialWiringSettings = Depends(get_settings),
) -> LimitesGeracaoLista:
    """Owner/admin: set (or, with ``null``, restore) one or more limits; answers the whole list."""
    user, _token, raw_org = auth
    require_org_admin_for(get_core_client(), auth, request, "Os limites diários")
    org_id = str(coerce_org_uuid(raw_org))
    try:
        lg.definir(get_admin_client(), org_id, payload.limites, getattr(user, "id", None))
    except lg.LimiteInvalido as exc:  # the schema already validated; kept so a refusal can never become a 500
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return _lista(org_id, cfg)


__all__ = ["router"]
