"""Segments router — /api/mailchimp/segments.

Static segments ("Listas") inside the org's default audience.

  GET    /segments                           → {items, total}
  POST   /segments                           → SegmentOut (201)
  PATCH  /segments/{segment_id}              → SegmentOut
  DELETE /segments/{segment_id}              → 204
  GET    /segments/{segment_id}/members      → {items, total}
  POST   /segments/{segment_id}/members      → MemberOut (201)
  DELETE /segments/{segment_id}/members/{email} → 204
"""
from __future__ import annotations

import hashlib
import logging

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.mailchimp.deps import make_require_mailchimp_client
from app.modules.mailchimp.errors import translate_mailchimp_errors
from app.modules.mailchimp.schemas import (
    MemberOut,
    SegmentCreateBody,
    SegmentListOut,
    SegmentMemberAddBody,
    SegmentMemberListOut,
    SegmentOut,
    SegmentPatchBody,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailchimp/segments", tags=["Mailchimp"])

_require_client = make_require_mailchimp_client(require_audience=True)


def _subscriber_hash(email: str) -> str:
    return hashlib.md5(email.strip().lower().encode("utf-8"), usedforsecurity=False).hexdigest()  # noqa: S324


def _segment_out(s) -> SegmentOut:
    return SegmentOut(
        id=s.id,
        name=s.name,
        member_count=s.member_count,
        created_at=s.created_at,
        updated_at=s.updated_at,
    )


def _member_out(m) -> MemberOut:
    return MemberOut(
        email=m.email,
        status=m.status,
        first_name=m.first_name,
        last_name=m.last_name,
        tags=m.tags or [],
        vip=m.vip or False,
        last_changed=m.last_changed,
    )


@router.get("", response_model=SegmentListOut)
async def list_segments(
    count: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    client_record=Depends(_require_client),
) -> SegmentListOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        page = await client.list_segments(record.audience_id, count=count, offset=offset)
    return SegmentListOut(
        items=[_segment_out(s) for s in page.items],
        total=page.total,
    )


@router.post("", response_model=SegmentOut, status_code=status.HTTP_201_CREATED)
async def create_segment(
    body: SegmentCreateBody,
    client_record=Depends(_require_client),
) -> SegmentOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        seg = await client.create_static_segment(record.audience_id, name=body.name)
    return _segment_out(seg)


@router.patch("/{segment_id}", response_model=SegmentOut)
async def update_segment(
    segment_id: int,
    body: SegmentPatchBody,
    client_record=Depends(_require_client),
) -> SegmentOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        seg = await client.update_segment(record.audience_id, segment_id, name=body.name)
    return _segment_out(seg)


@router.delete("/{segment_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_segment(
    segment_id: int,
    client_record=Depends(_require_client),
) -> Response:
    client, record = client_record
    async with translate_mailchimp_errors():
        await client.delete_segment(record.audience_id, segment_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/{segment_id}/members", response_model=SegmentMemberListOut)
async def list_segment_members(
    segment_id: int,
    count: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    client_record=Depends(_require_client),
) -> SegmentMemberListOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        page = await client.list_segment_members(
            record.audience_id, segment_id, count=count, offset=offset
        )
    return SegmentMemberListOut(
        items=[_member_out(m) for m in page.items],
        total=page.total,
    )


@router.post(
    "/{segment_id}/members",
    response_model=MemberOut,
    status_code=status.HTTP_201_CREATED,
)
async def add_segment_member(
    segment_id: int,
    body: SegmentMemberAddBody,
    client_record=Depends(_require_client),
) -> MemberOut:
    """Add a member to a segment. 400 if the email is not in the audience."""
    client, record = client_record
    async with translate_mailchimp_errors():
        member = await client.add_segment_member(
            record.audience_id, segment_id, email=body.email
        )
    return _member_out(member)


@router.delete(
    "/{segment_id}/members/{email}",
    status_code=status.HTTP_204_NO_CONTENT,
)
async def remove_segment_member(
    segment_id: int,
    email: str,
    client_record=Depends(_require_client),
) -> Response:
    client, record = client_record
    async with translate_mailchimp_errors():
        await client.remove_segment_member(
            record.audience_id, segment_id, _subscriber_hash(email)
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)
