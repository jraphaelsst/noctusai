"""Shared router plumbing — contract §A.11/§B.0.

`error_response` is the ONE place a `KnowledgeStore` error becomes an
HTTP response, per contract §B.0's status taxonomy:

    NotFound  -> 404
    Conflict  -> 409 `conflict`
    Invalid   -> 422
    AssertionUsed -> 409 `assertion_used`

`RevisionRefOut` / `RevisionOut` are the shared response shapes (§B.1's
`RevisionRef` / `Revision`) every entity-with-history route composes.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any
from uuid import UUID

from fastapi import HTTPException
from pydantic import BaseModel

from app.knowledge import AssertionUsed, Conflict, Invalid, KnowledgeStore, NotFound

_NOT_FOUND_DETAIL = {"detail": "Não encontrado.", "code": "not_found"}


def error_response(exc: Exception) -> HTTPException:
    """Map a `KnowledgeStore` error to the contract §B.0 HTTP response.

    Usage::

        try:
            row = await store.get_kb(org_id, slug)
        except NotFound as exc:
            raise error_response(exc) from exc
    """
    if isinstance(exc, AssertionUsed):
        return HTTPException(
            status_code=409,
            detail={"detail": "Esta aprovação já foi usada.", "code": "assertion_used"},
        )
    if isinstance(exc, NotFound):
        return HTTPException(status_code=404, detail=_NOT_FOUND_DETAIL)
    if isinstance(exc, Conflict):
        return HTTPException(
            status_code=409,
            detail={"detail": str(exc) or "Conflito.", "code": "conflict"},
        )
    if isinstance(exc, Invalid):
        return HTTPException(
            status_code=422,
            detail={"detail": str(exc) or "Dado inválido.", "code": "invalid"},
        )
    raise exc


class RevisionRefOut(BaseModel):
    rev_no: int
    author_kind: str
    created_at: datetime


class RevisionOut(BaseModel):
    rev_no: int
    op: str
    author_kind: str
    user_id: UUID | None = None
    agent_id: UUID | None = None
    approval_id: UUID | None = None
    channel: str | None = None
    conversation_id: UUID | None = None
    motivo: str | None = None
    git_sha: str | None = None
    git_committed_at: datetime | None = None
    created_at: datetime
    snapshot: dict[str, Any]


def revision_ref_out(revisions: list[dict]) -> RevisionRefOut | None:
    """The newest revision (index 0 — `list_revisions` returns newest
    first) projected to a `RevisionRefOut`, or `None` for an entity with
    no revisions yet (should not happen post-write; defensive only)."""
    if not revisions:
        return None
    latest = revisions[0]
    return RevisionRefOut(
        rev_no=latest["rev_no"],
        author_kind=latest["author_kind"],
        created_at=latest["created_at"],
    )


async def latest_revision_ref(
    store: KnowledgeStore, org_id, entity_type: str, entity_id
) -> RevisionRefOut | None:
    revisions = await store.list_revisions(org_id, entity_type, entity_id)
    return revision_ref_out(revisions)


__all__ = [
    "RevisionOut",
    "RevisionRefOut",
    "error_response",
    "latest_revision_ref",
    "revision_ref_out",
]
