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
from typing import Any, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_current_user_org
from app.routers.clients_router import get_client_service
from app.services.clients_service import ClientService
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
        client_id=record.client_id,
        server_prefix=record.server_prefix,
        audience_id=record.audience_id,
        audience_name=audience_name,
        created_at=record.created_at,
        updated_at=record.updated_at,
    )


def _validate_client_ownership(
    client_svc: ClientService,
    client_id: Optional[UUID],
    org_id: UUID,
) -> None:
    """Reject a client_id that does not belong to the calling org (404).

    Mirrors the OAuth-start ownership check in integration_accounts_router
    (migration 017). No-op when ``client_id`` is None (org-level scope)."""
    if client_id is None:
        return
    if client_svc.get_client(client_id, org_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="client_id not found or does not belong to this org.",
        )


@router.get("/connection", response_model=ConnectionOut)
async def get_connection(
    client_id: Optional[UUID] = Query(
        default=None,
        description="Scope to a cliente's connection; omit for the org default.",
    ),
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
) -> ConnectionOut:
    """Always 200 — returns nulls when not connected (FE probe endpoint).

    ``client_id`` omitted → the org-level default (client_id NULL); a UUID →
    that cliente's connection (migration 019)."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    record = store.get_connection(org_id, client_id=client_id)
    if record is None:
        # Echo the probed scope so the FE knows which cliente it queried.
        return ConnectionOut(connected=False, client_id=client_id)
    return _record_to_out(record)


@router.put("/connection", response_model=ConnectionOut)
async def put_connection(
    body: ConnectionPutBody,
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
    factory: Any = Depends(get_mailchimp_client_factory),
    client_svc: ClientService = Depends(get_client_service),
) -> ConnectionOut:
    """Validate API key via live ping, then encrypt+upsert.

    1. Validate ``client_id`` belongs to the org (404 when not — migration 019).
    2. Parse server_prefix from the key suffix (ValueError → 400).
    3. Build a client and call ping() to verify the key is valid.
    4. Encrypt+upsert the connection row for (org, client_id) scope.
    5. Return the GET shape (api_key never returned).
    """
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)

    # 1. Validate client scope belongs to the org (no-op when client_id None).
    _validate_client_ownership(client_svc, body.client_id, org_id)

    api_key = body.api_key.strip()

    # 2. Parse server_prefix (ValueError → 400)
    try:
        server_prefix = parse_server_prefix(api_key)
    except ValueError as exc:
        raise AppException(
            code="mailchimp_rejected",
            message=str(exc),
            status_code=400,
        ) from exc

    # 3. Live ping to validate the key
    client = factory(api_key=api_key, server_prefix=server_prefix)
    async with translate_mailchimp_errors():
        await client.ping()

    # 4. Encrypt+upsert
    try:
        record = store.upsert_connection(
            org_id=org_id,
            api_key=api_key,
            server_prefix=server_prefix,
            audience_id=body.audience_id,
            client_id=body.client_id,
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
    client_id: Optional[UUID] = Query(
        default=None,
        description="Scope to a cliente's connection; omit for the org default.",
    ),
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
) -> ConnectionOut:
    """Update the audience_id on the scoped connection (org default when
    ``client_id`` is omitted). The row is already org-scoped, so a foreign
    client_id resolves to no row → 503."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    record = store.set_audience(org_id, body.audience_id, client_id=client_id)
    if record is None:
        raise AppException(
            code="mailchimp_not_configured",
            message="No connection found.",
            status_code=503,
        )
    return _record_to_out(record)


@router.delete("/connection", status_code=status.HTTP_204_NO_CONTENT)
async def delete_connection(
    client_id: Optional[UUID] = Query(
        default=None,
        description="Scope to a cliente's connection; omit for the org default.",
    ),
    auth: tuple = Depends(get_current_user_org),
    store: MailchimpConnectionStore = Depends(get_mailchimp_store),
) -> Response:
    """Delete the scoped connection (org default when ``client_id`` is
    omitted). The row is already org-scoped, so a foreign client_id resolves
    to no row → 404."""
    _user, _token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    deleted = store.delete_connection(org_id, client_id=client_id)
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
