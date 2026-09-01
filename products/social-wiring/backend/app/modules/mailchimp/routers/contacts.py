"""Contacts router — /api/mailchimp/contacts.

Proxies Mailchimp Marketing API member endpoints for the default audience.

  GET    /contacts              → {items: MemberOut[], total}  (?status=&count=&offset=)
  GET    /contacts/{email}      → MemberOut
  PUT    /contacts/{email}      → MemberOut   (upsert)
  DELETE /contacts/{email}      → 204         (archive)
"""
from __future__ import annotations

import logging
from typing import Optional

from fastapi import APIRouter, Depends, Query, Response, status

from app.modules.mailchimp.deps import make_require_mailchimp_client
from app.modules.mailchimp.errors import translate_mailchimp_errors
from app.modules.mailchimp.schemas import (
    ContactListOut,
    ContactPutBody,
    MemberOut,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailchimp/contacts", tags=["Mailchimp"])

_require_client = make_require_mailchimp_client(require_audience=True)



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


@router.get("", response_model=ContactListOut)
async def list_contacts(
    status_filter: Optional[str] = Query(None, alias="status"),
    count: int = Query(25, ge=1, le=100),
    offset: int = Query(0, ge=0),
    client_record=Depends(_require_client),
) -> ContactListOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        page = await client.list_members(
            record.audience_id,
            status=status_filter,
            count=count,
            offset=offset,
        )
    return ContactListOut(
        items=[_member_out(m) for m in page.items],
        total=page.total,
    )


@router.get("/{email}", response_model=MemberOut)
async def get_contact(
    email: str,
    client_record=Depends(_require_client),
) -> MemberOut:
    client, record = client_record
    async with translate_mailchimp_errors():
        member = await client.get_member(record.audience_id, email)
    return _member_out(member)


@router.put("/{email}", response_model=MemberOut)
async def upsert_contact(
    email: str,
    body: ContactPutBody,
    client_record=Depends(_require_client),
) -> MemberOut:
    """Upsert a member. Tags are applied declaratively (diff active/inactive)."""
    client, record = client_record
    async with translate_mailchimp_errors():
        member = await client.upsert_member(
            record.audience_id,
            email,
            status=body.status,
            first_name=body.first_name,
            last_name=body.last_name,
        )
        if body.tags is not None:
            await client.set_member_tags(
                record.audience_id,
                email,
                active_tags=body.tags,
            )
    return _member_out(member)


@router.delete("/{email}", status_code=status.HTTP_204_NO_CONTENT)
async def archive_contact(
    email: str,
    client_record=Depends(_require_client),
) -> Response:
    """Archive (soft-delete) a member from the audience."""
    client, record = client_record
    async with translate_mailchimp_errors():
        await client.archive_member(record.audience_id, email)
    return Response(status_code=status.HTTP_204_NO_CONTENT)
