"""Julia > "post do Instagram" of a listing (Lais study S6): which listing an Instagram post/reel advertises, so a lead who
pastes the post link gets the listing (`julia_imovel_instagram`).

  GET    /api/julia/post-instagram-imovel?codigo_imovel   member  {data:[{id,shortcode,codigo_imovel,permalink,created_at}]}
  PUT    /api/julia/post-instagram-imovel {url,codigo_imovel}  admin  {data: row}   (upsert by (org, shortcode))
  DELETE /api/julia/post-instagram-imovel/{id}            admin   {data:{id}}
Errors: 422 `url_instagram_invalida` (not a /p/ | /reel/ post link).
"""
# No `from __future__ import annotations`: FastAPI body/param models are resolved from the signature.
from typing import Any, Optional
from uuid import UUID

from fastapi import Depends, Query, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org, get_scoped_admin_client
from app.services import julia_imovel_instagram as svc

router = make_router(tier="org", guard=get_current_user_org, prefix="/api/julia/post-instagram-imovel", tags=["julia-post-instagram"])
_COLS = "id, shortcode, codigo_imovel, permalink, created_at"


def get_post_instagram_client() -> Any:
    """DI seam: the schema-scoped service-role client (tests override)."""
    return get_scoped_admin_client("social_wiring")


class PostIn(StrictHttpModel):
    url: str = Field(min_length=10, max_length=500)
    codigo_imovel: str = Field(min_length=1, max_length=40)


@router.get("")
async def listar(
    codigo_imovel: Optional[str] = Query(default=None, max_length=40),
    auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_post_instagram_client),
) -> dict[str, Any]:
    org = coerce_org_uuid(auth[2])

    def _go() -> Any:
        q = client.table(svc.T).select(_COLS).eq("org_id", str(org))
        if codigo_imovel:
            q = q.eq("codigo_imovel", codigo_imovel.strip())
        return q.order("created_at", desc=True).limit(200).execute().data or []
    return {"data": await run_blocking(_go)}


@router.put("")
async def salvar(
    body: PostIn, request: Request,
    auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_post_instagram_client),
) -> dict[str, Any]:
    await run_blocking(require_org_admin_for, get_core_client(), auth, request, "O vínculo do post do Instagram")
    org = coerce_org_uuid(auth[2])
    codes, _ = svc.analisar(body.url)
    if len(codes) != 1:
        raise AppException("url_instagram_invalida", "Informe o link de um post ou reel do Instagram (/p/... ou /reel/...).", status_code=422)
    url = body.url.strip()
    linha = {"org_id": str(org), "shortcode": codes[0], "codigo_imovel": body.codigo_imovel.strip(),
             "permalink": url.split("?")[0] if url.lower().startswith("https://") else None, "created_by": str(auth[0].id)}
    res = await run_blocking(lambda: client.table(svc.T).upsert(linha, on_conflict="org_id,shortcode").execute().data)
    return {"data": (res or [linha])[0]}


@router.delete("/{linha_id}")
async def remover(
    linha_id: UUID, request: Request,
    auth: tuple = Depends(get_current_user_org), client: Any = Depends(get_post_instagram_client),
) -> dict[str, Any]:
    await run_blocking(require_org_admin_for, get_core_client(), auth, request, "O vínculo do post do Instagram")
    org = coerce_org_uuid(auth[2])
    await run_blocking(lambda: client.table(svc.T).delete().eq("org_id", str(org)).eq("id", str(linha_id)).execute())
    return {"data": {"id": str(linha_id)}}
