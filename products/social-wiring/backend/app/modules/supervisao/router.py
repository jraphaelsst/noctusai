"""Supervisão (Maya) routes -- maya-blocks CONTRACT §4.3 / §4.4 / §4.5.

  GET /api/supervisao/scorecards?dia=YYYY-MM-DD    owner          {dia, supervisao_ativa, scorecards}
  GET /api/supervisao/handoffs?status&de_bloco&para_bloco&desde&ate&limit&cursor
                                                   owner/admin    {itens, proximo_cursor}
  GET /api/supervisao/config                       owner          {supervisao_ativa, horas_para_assumir, updated_at, updated_by}
  PUT /api/supervisao/config                       owner          same (state after)

No session = strict 401; the org is the session's selected org; roles come from the trusted `noctus_users` row
via the seed `is_org_admin_for` / `require_org_admin_for`;
owner-only routes answer an admin/member with 403 `exclusivo_proprietario`. Read-only toward leads: nothing here sends or touches a lead/card/chat.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import ADMIN_ORG_ROLES, is_org_admin_for, require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.modules.supervisao import service as svc

router = APIRouter(prefix="/api/supervisao", tags=["supervisao"])

SO_DONO = frozenset({"owner"})
#: Stable 403 code for an owner-only route (the FE shows "exclusiva do proprietário" on it).
CODIGO_SO_DONO = "exclusivo_proprietario"


def get_supervisao_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class ConfigIn(StrictHttpModel):
    supervisao_ativa: bool
    horas_para_assumir: int = Field(ge=1, le=168)


def exigir_dono(auth: tuple, request: Optional[Request], contexto: str) -> None:
    """Owner-only gate on the trusted `noctus_users` row of the SELECTED org (seed `is_org_admin_for` with
    `admin_roles={"owner"}`); an admin/member gets 403 `exclusivo_proprietario`."""
    if not is_org_admin_for(get_core_client(), auth, request, admin_roles=SO_DONO):
        raise AppException(CODIGO_SO_DONO, f"{contexto}: exclusiva do proprietário da organização.", status_code=403)


def _org(auth: tuple) -> UUID:
    return coerce_org_uuid(auth[2])


@router.get("/scorecards")
def scorecards(
    request: Request = None,
    dia: Optional[str] = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_supervisao_client),
) -> dict[str, Any]:
    exigir_dono(auth, request, "Os scorecards da supervisão")
    agora = svc.agora_utc()
    d = svc.parse_dia(dia, agora=agora)
    org = _org(auth)
    # History is kept (CONTRACT §4.5): "off" only stops the nightly job from computing new rows, it never hides
    # the stored ones.
    return {"dia": d.isoformat(), "supervisao_ativa": svc.ler_config(client, org)["supervisao_ativa"],
            "scorecards": svc.listar_scorecards(client, org, d)}


@router.get("/handoffs")
def handoffs(
    request: Request = None,
    status: Optional[str] = None,
    de_bloco: Optional[str] = None,
    para_bloco: Optional[str] = None,
    desde: Optional[str] = None,
    ate: Optional[str] = None,
    limit: Optional[str] = None,
    cursor: Optional[str] = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_supervisao_client),
) -> dict[str, Any]:
    require_org_admin_for(get_core_client(), auth, request, "Os handoffs da supervisão", admin_roles=ADMIN_ORG_ROLES)
    limite: Optional[int] = None
    if limit is not None:
        try:
            limite = int(limit)
        except ValueError:
            limite = 0  # rejected below as filtro_invalido, same envelope as every other bad filter
    return svc.listar_handoffs(client, _org(auth), agora=svc.agora_utc(), status=status, de_bloco=de_bloco,
                               para_bloco=para_bloco, desde=desde, ate=ate, limit=limite, cursor=cursor)


@router.get("/config")
def get_config(
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_supervisao_client),
) -> dict[str, Any]:
    exigir_dono(auth, request, "A configuração da supervisão")
    return svc.ler_config(client, _org(auth))


@router.put("/config")
def put_config(
    corpo: ConfigIn,
    request: Request = None,
    auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_supervisao_client),
) -> dict[str, Any]:
    exigir_dono(auth, request, "A configuração da supervisão")
    return svc.salvar_config(client, _org(auth), supervisao_ativa=corpo.supervisao_ativa,
                             horas_para_assumir=corpo.horas_para_assumir, por=getattr(auth[0], "id", None))
