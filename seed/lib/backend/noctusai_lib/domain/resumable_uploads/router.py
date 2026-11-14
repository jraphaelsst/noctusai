"""HTTP surface of the resumable-upload seam (access tier `org`: the caller's own org, from the session).

    POST   {prefix}                    open  {filename, content_type, size_bytes, client_key?} -> session + parts
    GET    {prefix}/{id}               status: which parts the server already has (resume)
    PUT    {prefix}/{id}/parts/{n}     raw bytes of part n (1-based); idempotent
    POST   {prefix}/{id}/complete      assemble -> stored object (409 + `missing` when parts are absent)
    DELETE {prefix}/{id}               abort
"""
from __future__ import annotations

from typing import Any, Awaitable, Callable, Optional

from fastapi import APIRouter, Depends, HTTPException, Request

from noctusai_lib.api.access_tiers import access_tier
from noctusai_lib.api.schemas import StrictHttpModel

from .service import ResumableUploadService
from .types import MIB, UploadError, UploadSession

__all__ = ["OpenUploadBody", "create_resumable_upload_router", "part_path_pattern", "part_body_limit"]


class OpenUploadBody(StrictHttpModel):
    filename: str
    content_type: str = "application/octet-stream"
    size_bytes: int
    client_key: Optional[str] = None


def part_path_pattern(prefix: str) -> str:
    """`max_body_path_overrides` key for the part route (the default body cap is far below one part)."""
    return f"{prefix.rstrip('/')}/*/parts/*"


def part_body_limit(max_part_size: int = 16 * MIB) -> int:
    return max_part_size + 64 * 1024


def _err(exc: UploadError) -> HTTPException:
    return HTTPException(exc.http_status, {"code": exc.code, "detail": str(exc), **exc.extra})


def _out(s: UploadSession, parts: list) -> dict[str, Any]:
    return {
        "id": s.id, "status": s.status, "filename": s.filename, "size_bytes": s.size_bytes,
        "part_size": s.part_size, "total_parts": s.total_parts, "expires_at": s.expires_at.isoformat(),
        "object_key": s.object_key, "parts": [p.number for p in parts],
    }


def create_resumable_upload_router(*, get_auth_context: Callable[..., Awaitable[Any]],
                                   get_service: Callable[..., ResumableUploadService],
                                   prefix: str = "/api/uploads") -> APIRouter:
    router = APIRouter(prefix=prefix, tags=["Uploads"])

    async def _ctx(ctx=Depends(get_auth_context)):
        return ctx

    @router.post("", status_code=201)
    @access_tier("org", reason="session org; sessions are bound to org + object prefix")
    async def open_upload(body: OpenUploadBody, ctx=Depends(_ctx), svc: ResumableUploadService = Depends(get_service)):
        try:
            s = svc.open(org_id=str(ctx.org_id), user_id=None if ctx.user_id is None else str(ctx.user_id),
                         filename=body.filename, content_type=body.content_type, size_bytes=body.size_bytes,
                         client_key=body.client_key)
            _, parts = await svc.status(org_id=str(ctx.org_id), session_id=s.id)
        except UploadError as exc:
            raise _err(exc) from exc
        return _out(s, parts)

    @router.get("/{upload_id}")
    @access_tier("org", reason="session org")
    async def upload_status(upload_id: str, ctx=Depends(_ctx), svc: ResumableUploadService = Depends(get_service)):
        try:
            s, parts = await svc.status(org_id=str(ctx.org_id), session_id=upload_id)
        except UploadError as exc:
            raise _err(exc) from exc
        return _out(s, parts)

    @router.put("/{upload_id}/parts/{number}")
    @access_tier("org", reason="session org")
    async def put_part(upload_id: str, number: int, request: Request, ctx=Depends(_ctx),
                       svc: ResumableUploadService = Depends(get_service)):
        data = await request.body()
        try:
            info = await svc.put_part(org_id=str(ctx.org_id), session_id=upload_id, number=number, data=data)
        except UploadError as exc:
            raise _err(exc) from exc
        return {"number": info.number, "size": info.size}

    @router.post("/{upload_id}/complete")
    @access_tier("org", reason="session org")
    async def complete(upload_id: str, ctx=Depends(_ctx), svc: ResumableUploadService = Depends(get_service)):
        try:
            s = await svc.complete(org_id=str(ctx.org_id), session_id=upload_id)
        except UploadError as exc:
            raise _err(exc) from exc
        return _out(s, [])

    @router.delete("/{upload_id}", status_code=204)
    @access_tier("org", reason="session org")
    async def abort(upload_id: str, ctx=Depends(_ctx), svc: ResumableUploadService = Depends(get_service)):
        try:
            await svc.abort(org_id=str(ctx.org_id), session_id=upload_id)
        except UploadError as exc:
            raise _err(exc) from exc

    return router
