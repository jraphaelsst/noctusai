"""Notificações — platform-admin surface over every owner-facing notification the products send.

  GET   /api/admin/notifications                    → catalog grouped by product, switch state, 30-day send stats
  GET   /api/admin/notifications/sends              → recent dispatch ledger (?product=&kind=&limit=)
  PATCH /api/admin/notifications/{product}          → {enabled} for every kind of the product
  PATCH /api/admin/notifications/{product}/{kind}   → {enabled} for one kind
  GET/POST /recipients · PATCH/DELETE /recipients/{id} → who receives the owner notices (NoctusAI line)
  POST  /api/admin/notifications/skill-scout        → one WhatsApp-only notice for a skill the skill-scout recommends
  GET   /api/admin/notifications/owner-line         → {configurada, instancia} (is the NoctusAI line set up here?)

Access: platform tier — `require_platform_admin_dep` on the router AND on every route (401 without a valid bearer,
403 for a non-admin). Code only, no vendor call. Products read the switch through the seed gate with a 60 s cache.
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import Depends, HTTPException, Path, Query, Response
from pydantic import Field

from noctusai_lib.api.access_tiers import make_router
from noctusai_lib.api.auth._blocking import run_blocking
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.primitives.timeutil import now_utc

from noctusai_lib.api.schemas import StrictHttpModel

from app.services import notification_catalog_service as svc
from app.services import owner_recipients_service as rec_svc
from app.services import skill_scout_notice_service as scout_svc
from app.services.trusted_auth import get_trusted_db, require_platform_admin_dep

router = make_router(
    tier="platform", guard=require_platform_admin_dep,
    prefix="/api/admin/notifications", tags=["Admin · Notificações"],
)

_SLUG = r"^[a-z0-9][a-z0-9-]{0,99}$"
_KIND = r"^[a-z0-9_]{1,80}$"


class SwitchBody(StrictHttpModel):
    enabled: bool


def _user_id(auth: AuthContext) -> Optional[str]:
    uid = getattr(auth, "user_id", None) or getattr(getattr(auth, "user", None), "id", None)
    return str(uid) if uid else None


class SkillScoutNotice(StrictHttpModel):
    nome: str = Field(..., min_length=1, max_length=120)
    resumo: str = Field(..., min_length=1, max_length=400)
    fonte_url: Optional[str] = Field(None, max_length=300)


class RecipientCreate(StrictHttpModel):
    numero: str = Field(..., min_length=1, max_length=40)
    nome: Optional[str] = Field(None, max_length=120)


class RecipientPatch(StrictHttpModel):
    ativo: Optional[bool] = None
    nome: Optional[str] = Field(None, max_length=120)


_RID = r"^[0-9a-fA-F-]{36}$"


def _err(status: int, code: str, message: str) -> HTTPException:
    # Seed "machine error" shape: the handler passes it through flat as {"detail": message, "code": code}.
    return HTTPException(status_code=status, detail={"detail": message, "code": code})


# Declared BEFORE the `/{product}` routes so `recipients` / `owner-line` are never read as a product slug.
@router.get("/owner-line")
async def get_owner_line(_: AuthContext = Depends(require_platform_admin_dep)):
    return {"data": rec_svc.owner_line_status()}


@router.post("/skill-scout")
async def post_skill_scout(
    body: SkillScoutNotice,
    _: AuthContext = Depends(require_platform_admin_dep),
):
    """WhatsApp only. The seed gate honours the owner's switch and records the outcome; `status` says what happened."""
    out = await run_blocking(
        lambda: scout_svc.avisar_novo_skill(nome=body.nome, resumo=body.resumo, fonte_url=body.fonte_url)
    )
    return {"data": {"status": out.status, "recipients": out.recipients, "delivered": out.delivered, "reason": out.reason}}


@router.get("/recipients")
async def list_recipients(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return {"data": {"items": await run_blocking(rec_svc.list_recipients, db)}}


@router.post("/recipients", status_code=201)
async def add_recipient(
    body: RecipientCreate,
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    try:
        item = await run_blocking(
            lambda: rec_svc.add_recipient(db, numero=body.numero, nome=body.nome, user_id=_user_id(auth))
        )
        return {"data": item}
    except rec_svc.ActorRequired:
        raise _err(403, "ator_desconhecido", "Não foi possível identificar o administrador.")
    except rec_svc.InvalidNumber:
        raise _err(422, "numero_invalido", "Número de telefone inválido.")
    except rec_svc.DuplicateNumber:
        raise _err(409, "numero_duplicado", "Este número já recebe os avisos.")


@router.patch("/recipients/{recipient_id}")
async def patch_recipient(
    body: RecipientPatch,
    recipient_id: str = Path(..., pattern=_RID),
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    try:
        item = await run_blocking(
            lambda: rec_svc.update_recipient(
                db, recipient_id=recipient_id, patch=body.model_dump(mode="json", exclude_unset=True),
                user_id=_user_id(auth),
            )
        )
        return {"data": item}
    except rec_svc.ActorRequired:
        raise _err(403, "ator_desconhecido", "Não foi possível identificar o administrador.")
    except rec_svc.RecipientNotFound:
        raise _err(404, "destinatario_nao_encontrado", "Destinatário não encontrado.")


@router.delete("/recipients/{recipient_id}", status_code=204)
async def delete_recipient(
    recipient_id: str = Path(..., pattern=_RID),
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    try:
        await run_blocking(lambda: rec_svc.delete_recipient(db, recipient_id=recipient_id, user_id=_user_id(auth)))
    except rec_svc.ActorRequired:
        raise _err(403, "ator_desconhecido", "Não foi possível identificar o administrador.")
    except rec_svc.RecipientNotFound:
        raise _err(404, "destinatario_nao_encontrado", "Destinatário não encontrado.")
    return Response(status_code=204)


@router.get("")
async def get_catalog(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return {"data": await run_blocking(svc.list_catalog, db, now_utc())}


@router.get("/sends")
async def get_sends(
    _: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
    product: Optional[str] = Query(None, pattern=_SLUG),
    kind: Optional[str] = Query(None, pattern=_KIND),
    limit: int = Query(50, ge=1, le=500),
):
    rows = await run_blocking(lambda: svc.list_sends(db, product=product, kind=kind, limit=limit))
    return {"data": rows}


async def _switch(db: Any, auth: AuthContext, product: str, kind: Optional[str], enabled: bool) -> dict:
    try:
        changed = await run_blocking(
            lambda: svc.set_enabled(db, product=product, kind=kind, enabled=enabled, user_id=_user_id(auth),
                                    now=now_utc())
        )
    except svc.KindNotFound:
        raise HTTPException(status_code=404, detail={"code": "notificacao_nao_encontrada",
                                                     "message": "Notificação não encontrada no catálogo."})
    return {"data": {"product": product, "kind": kind, "enabled": enabled, "changed": changed}}


@router.patch("/{product}")
async def switch_product(
    body: SwitchBody,
    product: str = Path(..., pattern=_SLUG),
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return await _switch(db, auth, product, None, body.enabled)


@router.patch("/{product}/{kind}")
async def switch_kind(
    body: SwitchBody,
    product: str = Path(..., pattern=_SLUG),
    kind: str = Path(..., pattern=_KIND),
    auth: AuthContext = Depends(require_platform_admin_dep),
    db: Any = Depends(get_trusted_db),
):
    return await _switch(db, auth, product, kind, body.enabled)
