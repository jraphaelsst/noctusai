"""Cadastro router — contract §Identity, slice BE-A. PUBLIC,
rate-limited, org resolved via `resolve_public_org_id()` (single-tenant
product — see that function's docstring in `app/dependencies.py`).

Deliberately NO ``from __future__ import annotations`` — same
`@limiter.limit(...)` + Pydantic-body-param interaction documented at
the top of `app/routers/checkout_router.py` / `app/routers/
aplicacoes_router.py`; a postponed annotation here resolves against
slowapi's wrapper globals instead of this module's, and FastAPI
silently treats the body model as an unresolved `Query(...)` param.
"""
import logging

from fastapi import APIRouter, Request, status

from app.config import settings
from app.dependencies import get_admin_client, get_core_client, http_error, resolve_public_org_id
from app.rate_limit import limiter
from app.schemas.cadastro import CadastroCreate, CadastroOut
from app.services.cadastro_service import CadastroService, CadastroServiceError

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cadastro", tags=["cadastro"])


@router.post("", response_model=CadastroOut, status_code=status.HTTP_201_CREATED)
@limiter.limit(settings.cadastro_rate_limit)
async def create_cadastro(
    request: Request,
    payload: CadastroCreate,
) -> CadastroOut:
    org_id = resolve_public_org_id()
    admin_client = get_admin_client()
    core_client = get_core_client()
    service = CadastroService(admin_client, core_client, org_id=org_id)
    remote_ip = request.client.host if request.client else None
    try:
        result = await service.cadastrar(payload=payload.model_dump(), remote_ip=remote_ip)
    except CadastroServiceError as exc:
        raise http_error(exc.status_code, exc.detail) from exc
    return CadastroOut(**result)
