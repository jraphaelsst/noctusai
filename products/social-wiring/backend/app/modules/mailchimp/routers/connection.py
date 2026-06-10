"""Connection router — /api/mailchimp/connection.

Manages the per-org Mailchimp API key + audience configuration.

  GET    /connection       → ConnectionOut  (always 200; FE probe)
  PUT    /connection       → ConnectionOut  (validate key → live ping → encrypt+upsert)
  PATCH  /connection       → ConnectionOut  (update audience_id only)
  DELETE /connection       → 204
  GET    /audiences        → AudienceListOut (audience picker)
"""
from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Response, status
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.modules.mailchimp.deps import (
    get_mailchimp_client_factory,
    get_mailchimp_store,
    make_require_mailchimp_client,
)
from app.modules.mailchimp.errors import (
    MailchimpAuthError,
    MailchimpUnreachableError,
    translate_mailchimp_errors,
)
from app.modules.mailchimp.schemas import (
    AudienceListOut,
    AudienceOut,
    ConnectionOut,
    ConnectionPatchBody,
    ConnectionPutBody,
    parse_server_prefix,
)
from app.modules.mailchimp.store import MailchimpConnectionStore
from app.services.credential_vault import CredentialStoreError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/mailchimp", tags=["Mailchimp"])


def _record_to_out(record, audience_name: str | None = None) -> ConnectionOut:
    return ConnectionOut(
        connected=True,
        server_prefix=record.server_prefix,
        audience_id=record.audience_id,
        audience_name=audience_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


@router.get("/connection", response_model=ConnectionOut)
async def get_connection(
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
) -> ConnectionOut:
    """Always 200 — returns nulls when not connected (FE probe endpoint)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    record = store.get_connection(org_id)
    if record is None:
        return ConnectionOut(connected=False)
    return _record_to_out(record)


@router.put("/connection", response_model=ConnectionOut)
async def put_connection(
    body: ConnectionPutBody,
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
    factory: Any = Depends(get_mailchimp_client_factory),
) -> ConnectionOut:
    """Validate API key via live ping, then encrypt+upsert.

    1. Parse server_prefix from the key suffix (ValueError → 400).
    2. Build a client and call ping() to verify the key is valid.
    3. Encrypt+upsert the connection row.
    4. Return the GET shape (api_key never returned).
    """
    api_key = body.api_key.strip()

    # 1. Parse server_prefix (ValueError → 400)
    try:
        server_prefix = parse_server_prefix(api_key)
    except ValueError as exc:
        raise AppException(
            code="mailchimp_rejected",
            message=str(exc),
            status_code=400,
        ) from exc

    # 2. Live ping to validate the key
    client = factory(api_key=api_key, server_prefix=server_prefix)
    async with translate_mailchimp_errors():
        await client.ping()

    # 3. Encrypt+upsert
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    try:
        record = store.upsert_connection(
            org_id=org_id,
            api_key=api_key,
            server_prefix=server_prefix,
            audience_id=body.audience_id,
        )
    except CredentialStoreError as exc:
        raise AppException(
            code="mailchimp_not_configured",
            message=str(exc),
            status_code=503,
        ) from exc

    return _record_to_out(record)


@router.patch("/connection", response_model=ConnectionOut)
async def patch_connection(
    body: ConnectionPatchBody,
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
) -> ConnectionOut:
    """Update the default audience_id."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    record = store.set_audience(org_id, body.audience_id)
    if record is None:
        raise AppException(
            code="mailchimp_not_configured",
            message="No connection found.",
            status_code=503,
        )
    return _record_to_out(record)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
) -> Response:
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = store.delete_connection(org_id)
    if not deleted:
        raise AppException(
            code="not_found",
            message="No connection found.",
            status_code=404,
        )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.get("/audiences", response_model=AudienceListOut)
async def list_audiences(
    client_record=Depends(make_require_mailchimp_client(require_audience=False)),
) -> AudienceListOut:
    """List all audiences for the configured account (audience picker)."""
    client, _record = client_record
    async with translate_mailchimp_errors():
        page = await client.list_audiences()
    items = [
        AudienceOut(id=a.id, name=a.name, member_count=a.member_count)
        for a in page.items
    ]
    return AudienceListOut(items=items, total=page.total)
