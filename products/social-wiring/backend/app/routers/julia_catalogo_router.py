"""Julia > Catálogo -- which catalog Julia's listing tools read (julia-v3, CONTRACT 12.7; migration 314).

  GET /api/julia/catalogo-fonte    org admin   {data: {fonte, fontes, padrao, updated_by, updated_at}}
  PUT /api/julia/catalogo-fonte    org admin   {fonte: "vista" | "espelho"} -> the same envelope

`vista` = Julia reads Vista live; `espelho` = the `imoveis` mirror (the default for an org with no row). Strict 401 without
a session, 403 for a non-admin; 422 `invalid_field` for an unknown key, 422 `fonte_invalida` for another value.
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
from typing import Any, Literal, Optional

from fastapi import APIRouter, Depends, Request

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import julia_catalogo_service as svc

router = APIRouter(prefix="/api/julia/catalogo-fonte", tags=["julia-catalogo"])


def get_catalogo_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


def get_catalogo_core() -> Any:
    """DI seam: the core client (admin check)."""
    return get_core_client()


class FonteIn(StrictHttpModel):
    fonte: Literal["vista", "espelho"]


@router.get("")
def ler_fonte(
    request: Request = None, auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_catalogo_client),
    core: Any = Depends(get_catalogo_core),
) -> dict[str, Any]:
    require_org_admin_for(core, auth, request, "A fonte do catálogo da Julia")
    return {"data": svc.obter_config(client, coerce_org_uuid(auth[2]))}


@router.put("")
def salvar_fonte(
    corpo: FonteIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
    client: Any = Depends(get_catalogo_client), core: Any = Depends(get_catalogo_core),
) -> dict[str, Any]:
    require_org_admin_for(core, auth, request, "A fonte do catálogo da Julia")
    user = auth[0]
    user_id: Optional[str] = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return {"data": svc.salvar_fonte(client, coerce_org_uuid(auth[2]), corpo.fonte, user_id)}


__all__ = ["router"]
