"""Checkout router — contract §Checkout. PUBLIC, rate-limited, org
resolved via `resolve_public_org_id()` (single-tenant product — see that
function's docstring in `app/dependencies.py`).

Deliberately NO ``from __future__ import annotations`` — same
`@limiter.limit(...)` + Pydantic-body-param interaction documented at
the top of `app/routers/aplicacoes_router.py`; a postponed annotation
here resolves against slowapi's wrapper globals instead of this
module's, and FastAPI silently treats the body model as an unresolved
`Query(...)` param.
"""
import logging

from fastapi import APIRouter, Request, status

from app.config import settings
from app.dependencies import http_error, get_admin_client, resolve_public_org_id
from app.rate_limit import limiter
from app.schemas.checkout import CheckoutCreate, CheckoutOut
from app.services.checkout_service import CheckoutService, CheckoutServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/checkout", tags=["checkout"])


@router.post("", response_model=CheckoutOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.checkout_rate_limit)
async def create_checkout(
    request: Request,
    payload: CheckoutCreate,
) -> CheckoutOut:
    org_id = resolve_public_org_id()
    client = get_admin_client()
    service = CheckoutService(client, org_id=org_id)
    remote_ip = request.client.host if request.client else None
    try:
        result = await service.checkout(payload=payload.model_dump(), remote_ip=remote_ip)
    except CheckoutServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return CheckoutOut(**result)
