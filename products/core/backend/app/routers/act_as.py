"""Superadmin act-as-org endpoints (round 2) — ``/api/admin/orgs`` + ``/api/admin/act-as*``.

SUPERADMIN = ``public.noctus_users.role == 'admin'`` read from the trusted row
(``get_current_admin``); a non-admin is 403, no token 401. The act-as session
itself is enforced downstream by the seed's effective-org resolver — this
router only starts / ends / lists sessions.

KB § PATTERNS/backend/tenancy-license-and-act-as.md
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Header, Query, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.config.product_urls import resolve_product_url
from noctusai_lib.domain.licensing import (
    license_rows_valid,
    org_has_license_for_product_id,
    org_sem_licenca,
)
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

from fastapi import HTTPException

from app.database import get_admin_client
from app.dependencies import create_sso_token, get_current_admin
from app.services import act_as_service, audit_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin", tags=["Admin · Act-as"])

_IN_BATCH = 100


class ActAsStartBody(StrictHttpModel):
    org_id: str = Field(..., min_length=1)
    product_slug: str = Field(..., min_length=1)
    reason: Optional[str] = Field(None, max_length=500)


def _client_ip(request: Request) -> Optional[str]:
    fwd = request.headers.get("x-forwarded-for")
    if fwd:
        return fwd.split(",")[0].strip()
    return request.client.host if request.client else None


def _batched(values: list, size: int = _IN_BATCH):
    for i in range(0, len(values), size):
        yield values[i : i + size]


def _fetch_all(db, table: str, columns: str, **eq) -> list[dict]:
    def page(start: int, end: int):
        q = db.table(table).select(columns)
        for col, val in eq.items():
            q = q.eq(col, val)
        return q.order("id").range(start, end).execute().data

    return list(iter_paged_rows(page, label=table))


@router.get("/orgs")
async def list_orgs(authorization: Optional[str] = Header(None)) -> list[dict]:
    """Every org with its owner e-mail and the products it holds a VALID license for."""
    await get_current_admin(authorization)
    db = get_admin_client()
    orgs = _fetch_all(db, "organizations", "id, nome, slug")
    owners = _fetch_all(db, "noctus_users", "id, email, org_id", org_role="owner")
    products = {p["id"]: p for p in _fetch_all(db, "products", "id, slug, nome, url_base, ativo")}
    licenses = _fetch_all(db, "licenses", "id, org_id, product_id, fim", status="active")

    owner_by_org: dict[str, str] = {}
    for o in owners:
        owner_by_org.setdefault(o["org_id"], o["email"])
    lic_by_org: dict[str, list[dict]] = {}
    for lic in licenses:
        if license_rows_valid([lic]):
            lic_by_org.setdefault(lic["org_id"], []).append(lic)

    out = []
    for org in orgs:
        licensed, seen = [], set()
        for lic in lic_by_org.get(org["id"], []):
            prod = products.get(lic["product_id"])
            if prod is None or prod["id"] in seen or prod.get("ativo") is False:
                continue
            seen.add(prod["id"])
            licensed.append({
                "slug": prod["slug"],
                "nome": prod["nome"],
                "url_base": resolve_product_url(prod["slug"], db_url_base=prod.get("url_base")),
            })
        licensed.sort(key=lambda p: p["slug"])
        out.append({
            "id": org["id"],
            "nome": org["nome"],
            "slug": org["slug"],
            "owner_email": owner_by_org.get(org["id"]),
            "licensed_products": licensed,
        })
    return out


@router.post("/act-as")
async def start_act_as(
    request: Request, body: ActAsStartBody, authorization: Optional[str] = Header(None)
) -> dict:
    """Enter ``product_slug`` AS ``org_id``. The target org must hold the license."""
    user, _token = await get_current_admin(authorization)
    db = get_admin_client()

    org = db.table("organizations").select("id").eq("id", body.org_id).limit(1).execute()
    if not org.data:
        raise HTTPException(status_code=404, detail="Organização não encontrada")
    product = (
        db.table("products").select("id, slug, url_base").eq("slug", body.product_slug).limit(1).execute()
    )
    if not product.data:
        raise HTTPException(status_code=404, detail="Produto não encontrado")
    prod = product.data[0]
    if not org_has_license_for_product_id(db, body.org_id, prod["id"]):
        raise org_sem_licenca()

    session = act_as_service.start_session(
        user.id,
        body.org_id,
        body.product_slug,
        reason=body.reason,
        ip=_client_ip(request),
        user_agent=request.headers.get("user-agent"),
        db=db,
    )
    # Audit is superadmin-only: org_id stays NULL so the customer's own
    # org-scoped audit read never sees it (target org rides in `details`).
    await audit_service.log(
        user.id, None, "act_as.start", "act_as_session", session["id"],
        {"target_org_id": body.org_id, "product_slug": body.product_slug,
         "has_reason": bool(body.reason)},
        request,
    )

    # Same mint path as POST /api/sso/token, superadmin identity; the token's
    # org is the TARGET so /api/sso/session's license re-check passes on it.
    sso_token = create_sso_token(
        user_id=user.id,
        org_id=body.org_id,
        product_slug=body.product_slug,
        email=user.email,
        role="admin",
        org_role="owner",
    )
    url_base = resolve_product_url(body.product_slug, db_url_base=prod.get("url_base"))
    return {"session_id": session["id"], "redirect_url": f"{url_base}/sso?token={sso_token}"}


@router.delete("/act-as/current")
async def end_act_as(request: Request, authorization: Optional[str] = Header(None)) -> dict:
    """End the superadmin's live act-as session ("Sair"). Idempotent."""
    user, _token = await get_current_admin(authorization)
    ended = act_as_service.end_live_session(user.id, "exit")
    if ended:
        await audit_service.log(
            user.id, None, "act_as.end", "act_as_session", ended["id"],
            {"target_org_id": ended.get("target_org_id"), "ended_by": "exit"},
            request,
        )
    return {"ended": ended is not None}


@router.get("/act-as/history")
async def act_as_history(
    limit: int = Query(50, ge=1, le=200), authorization: Optional[str] = Header(None)
) -> dict:
    """Recent act-as sessions, newest first — from ``act_as_sessions`` itself."""
    await get_current_admin(authorization)
    db = get_admin_client()
    rows = (
        db.table("act_as_sessions")
        .select("id, superadmin_id, target_org_id, entry_product_slug, reason, started_at, ended_at, ended_by")
        .order("started_at", desc=True)
        .limit(limit)
        .execute()
        .data
        or []
    )
    emails: dict[str, str] = {}
    for chunk in _batched(sorted({r["superadmin_id"] for r in rows})):
        for u in db.table("noctus_users").select("id, email").in_("id", chunk).execute().data or []:
            emails[u["id"]] = u["email"]
    nomes: dict[str, str] = {}
    for chunk in _batched(sorted({r["target_org_id"] for r in rows})):
        for o in db.table("organizations").select("id, nome").in_("id", chunk).execute().data or []:
            nomes[o["id"]] = o["nome"]
    return {
        "items": [
            {
                "session_id": r["id"],
                "superadmin_email": emails.get(r["superadmin_id"]),
                "target_org_id": r["target_org_id"],
                "target_org_nome": nomes.get(r["target_org_id"]),
                "entry_product_slug": r["entry_product_slug"],
                "reason": r.get("reason"),
                "started_at": r["started_at"],
                "ended_at": r.get("ended_at"),
                "ended_by": r.get("ended_by"),
            }
            for r in rows
        ]
    }
