"""
Example router — placeholder endpoints for the new product to fill in.

This is the **canonical router skeleton** every scaffolded product
inherits. It demonstrates:

* ``Depends(get_current_user_org)`` → ``(user, token, raw_org_id)`` —
  the factory-bound auth pattern. NEVER use the raw ``Depends(get_org_id)``
  shape; positional args become required query params (the broken pattern
  is what the seed-auth-deps-hardening project formalized 2026-05-06).
* ``coerce_org_uuid(raw_org_id)`` for any DB call needing UUID-typed org.
* User-scoped Supabase client built per-request via ``get_user_client(token)``
  so RLS binds to the JWT.
* Pydantic request + response models from ``app/schemas/example.py``.
* Service-side IO via ``ExampleService`` from ``app/services/``.
* ``status.HTTP_201_CREATED`` on POST, ``200`` (default) on GET — explicit
  ``status_code=`` so the keeper detector ``check_test_status_assertion``
  has something to pin against.

TODO(new-product): rename ``example`` → your domain everywhere, fill in
the service methods, replace placeholder Pydantic fields, and add tests
at ``tests/routers/test_example_router.py`` that pin every response on
``.status_code``.
"""
from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.dependencies import (
    coerce_org_uuid,
    get_current_user_org,
    get_user_client,
)
from app.schemas.example import ExampleCreate, ExampleListResponse, ExampleOut
from app.services.example_service import ExampleService, ExampleServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/example", tags=["example"])


@router.get("", response_model=ExampleListResponse)
async def list_examples(
    limit: int = Query(default=50, ge=1, le=200),
    cursor: str | None = Query(default=None),
    auth: tuple = Depends(get_current_user_org),
) -> ExampleListResponse:
    """List ``example`` rows for the caller's org.

    TODO(new-product): replace with your domain's list endpoint.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = ExampleService(client, org_id=org_id)
    try:
        result = await service.list(limit=limit, cursor=cursor)
    except ExampleServiceError as exc:
        logger.exception("example.list failed for org=%s", org_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ExampleListResponse(**result)


@router.post("", response_model=ExampleOut, status_code=status.HTTP_201_CREATED)
async def create_example(
    payload: ExampleCreate,
    auth: tuple = Depends(get_current_user_org),
) -> ExampleOut:
    """Create an ``example`` row scoped to the caller's org.

    TODO(new-product): replace with your domain's create endpoint.
    """
    _user, token, raw_org = auth
    org_id = coerce_org_uuid(raw_org)
    client = get_user_client(token)
    service = ExampleService(client, org_id=org_id)
    try:
        row = await service.create(payload=payload.model_dump())
    except ExampleServiceError as exc:
        logger.exception("example.create failed for org=%s", org_id)
        raise HTTPException(status_code=502, detail=str(exc)) from exc
    return ExampleOut(**row)
