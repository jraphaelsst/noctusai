"""`editorial_router(...)` — mountable HTTP surface for the editorial workflow.

A factory (mirrors ``pipeline_stages_router``): the seed cannot know the product's
auth dependency, its store, or its permission names, so those are injected.

Routes (under the caller's prefix):
    GET   ""                        queue by state (paged): ?state=&kind=&page=&page_size=
    POST  ""                        create item (version 1, author = actor)
    GET   "/{item_id}"              item + versions + events
    POST  "/{item_id}/versions"     new draft version (the ``edit`` action; author = actor)
    POST  "/{item_id}/transitions"  {action, motivo} — submit / approve_* / publish / send_back / archive
    GET   "/{item_id}/diff"         ?from_n=&to_n= structured content diff

Security model (PROJECT.md §11, Phase 0 findings):
- Permission grants are USER-GLOBAL (no org dimension), so the router ALSO requires the
  actor to be a member of the org it acts in (``EditorialContext.org_id`` is None ⇒ 403
  ``org_membership_required``) and every store read/write is scoped to that org.
- Grants are derived SERVER-SIDE from the permissions organ for the authenticated user.
  They are never read from the request (bodies are ``StrictHttpModel`` ⇒ an extra
  ``grants`` field is a 422).
- Separation of duties is decided by ``decide_transition`` (and re-checked by the DB
  function); its machine ``Code`` surfaces as ``detail.code``.
"""
from __future__ import annotations

from dataclasses import dataclass, fields, is_dataclass
from datetime import datetime
from enum import Enum
from typing import Any, Callable, Mapping
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.domain.editorial.store import (
    EditorialConflict,
    EditorialDenied,
    EditorialNotFound,
    EditorialStore,
)
from noctusai_lib.domain.editorial.workflow import Action, Code, Grant

# Denial code -> HTTP status. Authorization-shaped refusals are 403, state/ordering
# refusals are 409, malformed-request refusals are 422.
_STATUS_BY_CODE: dict[str, int] = {
    Code.ACTOR_REQUIRED.value: 401,
    Code.MISSING_GRANT.value: 403,
    Code.SELF_APPROVAL.value: 403,
    Code.SAME_APPROVER.value: 403,
    Code.ILLEGAL_TRANSITION.value: 409,
    Code.SECURITY_SIGNOFF_MISSING.value: 409,
    Code.MOTIVO_REQUIRED.value: 422,
    Code.CONTENT_REQUIRED.value: 422,
    Code.UNKNOWN_ACTION.value: 422,
}

_VERSION_ACTIONS = {Action.CREATE.value, Action.EDIT.value}


class ItemCreate(StrictHttpModel):
    kind: str = Field(..., min_length=1, max_length=80)
    ref: str = Field(..., min_length=1, max_length=200)
    content: dict[str, Any]


class VersionCreate(StrictHttpModel):
    content: dict[str, Any]


class TransitionBody(StrictHttpModel):
    action: str = Field(..., min_length=1, max_length=40)
    motivo: str | None = Field(default=None, max_length=2000)


@dataclass(frozen=True)
class EditorialContext:
    """What every handler needs, however the product supplies it.

    ``org_id`` is the org the actor is a VERIFIED MEMBER of for this request, or
    ``None`` when they are not (the router answers 403). ``user_id`` is the actor.
    """

    org_id: UUID | None
    user_id: UUID | None


def _jsonable(x: Any) -> Any:
    if isinstance(x, Enum):
        return x.value
    if isinstance(x, (UUID, datetime)):
        return str(x) if isinstance(x, UUID) else x.isoformat()
    if is_dataclass(x) and not isinstance(x, type):
        return {f.name: _jsonable(getattr(x, f.name)) for f in fields(x)}
    if isinstance(x, Mapping):
        return {k: _jsonable(v) for k, v in x.items()}
    if isinstance(x, (list, tuple)):
        return [_jsonable(v) for v in x]
    return x


def diff_content(before: Any, after: Any, path: str = "") -> list[dict[str, Any]]:
    """Structured diff of two JSON values: ``[{path, op, before, after}]`` with
    ``op`` in ``added | removed | changed``. Dicts recurse by key; lists and
    scalars compare whole (an array diff is a ``changed`` at the array's path)."""
    if isinstance(before, Mapping) and isinstance(after, Mapping):
        out: list[dict[str, Any]] = []
        for k in sorted(set(before) | set(after), key=str):
            p = f"{path}.{k}" if path else str(k)
            if k not in before:
                out.append({"path": p, "op": "added", "before": None, "after": after[k]})
            elif k not in after:
                out.append({"path": p, "op": "removed", "before": before[k], "after": None})
            else:
                out.extend(diff_content(before[k], after[k], p))
        return out
    if before != after:
        return [{"path": path, "op": "changed", "before": before, "after": after}]
    return []


def editorial_router(
    *,
    auth_dependency: Callable[..., Any],
    resolve_context: Callable[[Any], EditorialContext],
    get_store: Callable[[], EditorialStore],
    get_permission_repo: Callable[[], Any],
    success_response: Callable[[Any], Any],
    permission_names: Mapping[Grant, str] | None = None,
    prefix: str = "",
    tags: list[str] | None = None,
) -> APIRouter:
    """Build the editorial router for one consumer.

    Args:
        auth_dependency: product auth dep (whatever it returns; 401 on no token).
        resolve_context: maps its value to an ``EditorialContext`` (org membership
            verified by the product; non-member ⇒ ``org_id=None``).
        get_store: zero-arg accessor for the ``EditorialStore`` (request-time, so
            tests/products inject their own).
        get_permission_repo: zero-arg accessor for the permissions organ repo.
        permission_names: consumer's own grant names per workflow ``Grant``
            (default: the ``editorial:*`` names). The STORE always receives the
            workflow's canonical ``Grant`` values — only the lookup is renamed.
    """
    names = {g: (permission_names or {}).get(g, g.value) for g in Grant}
    router = APIRouter(prefix=prefix, tags=tags or ["editorial"])

    def _ctx(auth: Any) -> EditorialContext:
        ctx = resolve_context(auth)
        if ctx.user_id is None:
            raise HTTPException(401, detail={"detail": "Authentication required", "code": "actor_required"})
        if ctx.org_id is None:
            raise HTTPException(
                403, detail={"detail": "Not a member of this organization", "code": "org_membership_required"}
            )
        return ctx

    async def _grants(ctx: EditorialContext) -> list[str]:
        repo = get_permission_repo()
        held: list[str] = []
        for g, name in names.items():
            if await repo.has_permission(user_id=ctx.user_id, permission=name):
                held.append(g.value)
        return held

    def _deny(e: EditorialDenied) -> HTTPException:
        return HTTPException(
            _STATUS_BY_CODE.get(e.code, 409), detail={"detail": e.detail or e.code, "code": e.code}
        )

    def _missing(e: Exception) -> HTTPException:
        return HTTPException(404, detail={"detail": str(e), "code": "not_found"})

    @router.get("")
    async def fila(
        state: str | None = None,
        kind: str | None = None,
        page: int = Query(1, ge=1),
        page_size: int = Query(50, ge=1, le=200),
        auth=Depends(auth_dependency),
    ):
        """The review queue: items by state, newest-updated first, paged."""
        ctx = _ctx(auth)
        items = sorted(
            get_store().list_items(ctx.org_id, state=state, kind=kind),
            key=lambda i: i.updated_at, reverse=True,
        )
        start = (page - 1) * page_size
        return success_response({
            "items": _jsonable(items[start:start + page_size]),
            "total": len(items), "page": page, "page_size": page_size,
        })

    @router.post("", status_code=201)
    async def criar(body: ItemCreate, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        try:
            res = get_store().create_item(
                org_id=ctx.org_id, kind=body.kind, ref=body.ref, content=body.content,
                actor_id=ctx.user_id, grants=await _grants(ctx),
            )
        except EditorialDenied as e:
            raise _deny(e)
        except EditorialConflict as e:
            raise HTTPException(409, detail={"detail": str(e), "code": "already_exists"})
        return success_response(_jsonable(res))

    @router.get("/{item_id}")
    async def detalhe(item_id: UUID, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        store = get_store()
        try:
            return success_response({
                "item": _jsonable(store.get_item(ctx.org_id, item_id)),
                "versions": _jsonable(store.list_versions(ctx.org_id, item_id)),
                "events": _jsonable(store.list_events(ctx.org_id, item_id)),
            })
        except EditorialNotFound as e:
            raise _missing(e)

    @router.post("/{item_id}/versions", status_code=201)
    async def nova_versao(item_id: UUID, body: VersionCreate, auth=Depends(auth_dependency)):
        """New draft version (author = actor). Legal only from rascunho/publicado."""
        ctx = _ctx(auth)
        try:
            res = get_store().apply(
                org_id=ctx.org_id, item_id=item_id, action=Action.EDIT.value,
                actor_id=ctx.user_id, grants=await _grants(ctx), content=body.content,
            )
        except EditorialDenied as e:
            raise _deny(e)
        except EditorialNotFound as e:
            raise _missing(e)
        return success_response(_jsonable(res))

    @router.post("/{item_id}/transitions")
    async def transicionar(item_id: UUID, body: TransitionBody, auth=Depends(auth_dependency)):
        ctx = _ctx(auth)
        if body.action in _VERSION_ACTIONS:
            raise HTTPException(
                422, detail={"detail": "Use the create / versions endpoints for content changes",
                             "code": "use_versions_endpoint"},
            )
        try:
            res = get_store().apply(
                org_id=ctx.org_id, item_id=item_id, action=body.action, actor_id=ctx.user_id,
                grants=await _grants(ctx), motivo=body.motivo,
            )
        except EditorialDenied as e:
            raise _deny(e)
        except EditorialNotFound as e:
            raise _missing(e)
        return success_response(_jsonable(res))

    @router.get("/{item_id}/diff")
    async def diferenca(
        item_id: UUID, from_n: int = Query(..., ge=1), to_n: int = Query(..., ge=1),
        auth=Depends(auth_dependency),
    ):
        ctx = _ctx(auth)
        try:
            versions = {v.n: v for v in get_store().list_versions(ctx.org_id, item_id)}
        except EditorialNotFound as e:
            raise _missing(e)
        for n in (from_n, to_n):
            if n not in versions:
                raise HTTPException(404, detail={"detail": f"version {n} not found", "code": "not_found"})
        return success_response({
            "from_n": from_n, "to_n": to_n,
            "changes": diff_content(versions[from_n].content, versions[to_n].content),
        })

    return router


__all__ = ["EditorialContext", "TransitionBody", "diff_content", "editorial_router"]
