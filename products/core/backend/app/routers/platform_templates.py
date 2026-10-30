"""Admin > Templates -- `/api/admin/templates` (DB-backed, versioned, platform-admin only).

Kinds: design_system | agent | message | document | repo_workflow, optionally scoped to a product
(``product`` NULL = platform-wide). Edit = new version (a draft is edited in place; touching an
active/archived version spawns draft N+1); ``activate`` archives the previous active version.
``/sources`` is the read-only "Fontes" catalogue of template-like assets that live outside the DB.
The filesystem scaffold browser moved to `/api/admin/template-scaffolds` (routers/templates.py).
"""
from __future__ import annotations

import logging
import uuid
from typing import Optional

import anyio
from fastapi import APIRouter, Depends, Header, HTTPException, Query, Request

from noctusai_lib.config.cors_registry import parse_products_registry

from app.dependencies import get_current_admin
from app.schemas.platform_templates import TemplateCreate, TemplateUpdate
from app.services import audit_service
from app.services.platform_templates import service as svc
from app.services.platform_templates.repository import (
    PLATFORM_SCOPE, FrozenVersion, NotFound, SupabasePlatformTemplateRepo, VersionConflict,
)
from app.services.platform_templates.sources import list_sources

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/admin/templates", tags=["Admin · Templates"])


def get_service() -> svc.PlatformTemplateService:
    """FastAPI dependency (override in tests via ``app.dependency_overrides``)."""
    from app.database import get_admin_client

    return svc.PlatformTemplateService(SupabasePlatformTemplateRepo(get_admin_client()))


def _run(fn, *args, **kwargs):
    return anyio.to_thread.run_sync(lambda: fn(*args, **kwargs))


def _http(exc: Exception) -> HTTPException:
    if isinstance(exc, NotFound):
        return HTTPException(404, "Template nao encontrado")
    if isinstance(exc, svc.TemplateInvalid):
        return HTTPException(422, "; ".join(exc.errors))
    if isinstance(exc, (VersionConflict, FrozenVersion)):
        return HTTPException(409, "Conflito de versao: recarregue e tente de novo")
    raise exc


async def _audit(user, request: Request, action: str, row: dict) -> None:
    await audit_service.log(
        user_id=user.id, org_id=None, action=action, resource_type="platform_template",
        resource_id=str(row.get("id")),
        details={"kind": row.get("kind"), "product": row.get("product"), "key": row.get("key"),
                 "version": row.get("version")},
        request=request,
    )


@router.get("")
async def list_templates(
    product: Optional[str] = Query(None, max_length=64, description="slug, or `_platform` for platform-wide"),
    kind: Optional[str] = Query(None),
    q: Optional[str] = Query(None, max_length=200),
    status: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    await get_current_admin(authorization)
    if (kind and kind not in svc.KINDS) or (status and status not in svc.STATUSES):
        raise HTTPException(422, "kind/status invalido")
    rows = await _run(service.list, product=product, kind=kind, q=q, status=status)
    return {"data": rows}


@router.get("/meta")
async def templates_meta(
    authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    """Navigation tree: kinds -> scopes (platform + product slugs) with template and source counts."""
    await get_current_admin(authorization)
    rows = await _run(service.list)
    display = {e["slug"]: e["display"] for e in parse_products_registry()}
    tree: dict[str, dict[str, dict[str, int]]] = {k: {} for k in svc.KINDS}
    for r in rows:
        scope = r["product"] or PLATFORM_SCOPE
        tree[r["kind"]].setdefault(scope, {"templates": 0, "sources": 0})["templates"] += 1
    for s in list_sources():
        scope = s["product"] or PLATFORM_SCOPE
        tree[s["kind"]].setdefault(scope, {"templates": 0, "sources": 0})["sources"] += 1
    return {"data": {
        "kinds": [{"key": k, "label": svc.KIND_LABELS[k],
                   "scopes": [{"scope": sc, "label": "Plataforma" if sc == PLATFORM_SCOPE else display.get(sc, sc), **n}
                              for sc, n in sorted(tree[k].items(), key=lambda kv: (kv[0] != PLATFORM_SCOPE, kv[0]))]}
                  for k in svc.KINDS],
        "formats": list(svc.FORMATS),
        "products": [{"slug": s, "label": display[s]} for s in sorted(display)],
        "platform_scope": PLATFORM_SCOPE,
    }}


@router.get("/sources")
async def templates_sources(
    product: Optional[str] = Query(None, max_length=64),
    kind: Optional[str] = Query(None),
    authorization: Optional[str] = Header(None),
):
    """"Fontes": read-only discovery entries (template-like assets that live outside the DB)."""
    await get_current_admin(authorization)
    if kind and kind not in svc.KINDS:
        raise HTTPException(422, "kind invalido")
    scope = None if product in (None, "") else (None if product == PLATFORM_SCOPE else product)
    rows = [s for s in list_sources(kind=kind) if product in (None, "") or s["product"] == scope]
    return {"data": rows}


@router.post("", status_code=201)
async def create_template(
    body: TemplateCreate, request: Request, authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    user, _ = await get_current_admin(authorization)
    try:
        row = await _run(service.create, product=body.product, kind=body.kind, key=body.key, title=body.title,
                         description=body.description, fmt=body.format, body=body.body, user_id=user.id)
    except (svc.TemplateInvalid, VersionConflict) as exc:
        raise _http(exc) from exc
    await _audit(user, request, "create", row)
    return {"data": row}


@router.get("/{template_id}")
async def get_template(
    template_id: uuid.UUID, authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    await get_current_admin(authorization)
    try:
        return {"data": await _run(service.get, str(template_id))}
    except NotFound as exc:
        raise _http(exc) from exc


@router.get("/{template_id}/history")
async def template_history(
    template_id: uuid.UUID, authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    await get_current_admin(authorization)
    try:
        return {"data": await _run(service.history, str(template_id))}
    except NotFound as exc:
        raise _http(exc) from exc


@router.patch("/{template_id}")
async def update_template(
    template_id: uuid.UUID, body: TemplateUpdate, request: Request, authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    user, _ = await get_current_admin(authorization)
    try:
        row = await _run(service.update, str(template_id), fields=body.model_dump(exclude_none=True), user_id=user.id)
    except (NotFound, svc.TemplateInvalid, VersionConflict, FrozenVersion) as exc:
        raise _http(exc) from exc
    await _audit(user, request, "update", row)
    return {"data": row}


@router.post("/{template_id}/activate")
async def activate_template(
    template_id: uuid.UUID, request: Request, authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    user, _ = await get_current_admin(authorization)
    try:
        row = await _run(service.activate, str(template_id), user_id=user.id)
    except (NotFound, svc.TemplateInvalid) as exc:
        raise _http(exc) from exc
    await _audit(user, request, "activate", row)
    return {"data": row}


@router.post("/{template_id}/archive")
async def archive_template(
    template_id: uuid.UUID, request: Request, authorization: Optional[str] = Header(None),
    service: svc.PlatformTemplateService = Depends(get_service),
):
    user, _ = await get_current_admin(authorization)
    try:
        row = await _run(service.archive, str(template_id), user_id=user.id)
    except NotFound as exc:
        raise _http(exc) from exc
    await _audit(user, request, "archive", row)
    return {"data": row}
