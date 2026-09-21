"""Interessados routes -- public "receber futuras comunicacoes" signup.

Contract: `products/academia-de-reciclagem/projects/interessados-CONTRACT.md`.

`POST /api/public/interessados` has NO auth dependency at all -- the seed's
`create_product_app` wires no global auth middleware (auth is per-route
`Depends(...)`, see `noctusai_lib.api.app_factory.configure_app`), so a
route that simply never declares an auth dep is reachable unauthenticated
by construction. This is the only unauthenticated WRITE route in the
fleet (contract "Why").

`GET`/`DELETE /api/interessados` reuse the SAME `require_scopes(...,
user_roles=ADMIN)` shape `app.dependencies.require_import_admin` already
established for this product's other admin-only route (`POST
/api/import`) -- `require_interessados_admin`, defined alongside it in
`app.dependencies`.

Deliberately NO ``from __future__ import annotations`` here: combined
with ``@limiter.limit(...)`` (slowapi), a postponed annotation on a
Pydantic body param resolves against the WRAPPER's ``__globals__``
(``slowapi.extension``, where the model name doesn't exist) rather than
this module's -- FastAPI silently falls back to treating the body model
as an unresolved ``Query(...)`` param instead of the request body. Same
footgun `products/community/backend/app/routers/aplicacoes_router.py`
documents; that product's public+rate-limited routers already avoid
this import for the same reason.
"""
import logging
from uuid import UUID

from email_validator import EmailNotValidError, validate_email
from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session.types import AuthContext
from noctusai_lib.api.rate_limit import client_ip_key
from noctusai_lib.primitives.phone import normalize_phone

from app.dependencies import get_interessados_store, require_interessados_admin
from app.interessados import InteressadosStore
from app.rate_limit import limiter

logger = logging.getLogger(__name__)

router = APIRouter(tags=["interessados"])

# contract: "identifies the consent wording shown" -- bump this string
# (never overwrite its meaning) the day the popup's copy changes.
CONSENTIMENTO_VERSAO = "v1-2026-09"

_ORIGEM_MAX_LEN = 80


# --------------------------------------------------------------------------
# Schemas
# --------------------------------------------------------------------------


class InteressadoIn(StrictHttpModel):
    """Every field is loosely typed on purpose (plain `str`/`bool`, no
    `EmailStr`/`Field(min_length=...)`): the contract demands a specific
    422 body shape (`{"detail","code":"invalid","field"}` in pt-BR) for
    each business rule, which only the handler's own checks below can
    produce -- a pydantic-level type/constraint failure would instead
    surface FastAPI's own default `RequestValidationError` shape.
    `extra="forbid"` (via `StrictHttpModel`) still runs at the pydantic
    layer for an unknown field -- the contract does not prescribe a
    custom body for THAT case, only that it 422s."""

    nome: str
    whatsapp: str
    email: str
    consentimento: bool
    origem: str | None = Field(default=None, max_length=_ORIGEM_MAX_LEN)


class InteressadoOut(StrictHttpModel):
    id: str
    nome: str
    whatsapp: str
    email: str
    origem: str | None
    consentimento_versao: str
    consentimento_em: str
    criado_em: str


class InteressadosListOut(StrictHttpModel):
    items: list[InteressadoOut]
    total: int


def _invalid(field: str, message: str) -> HTTPException:
    return HTTPException(
        status_code=422,
        detail={"detail": message, "code": "invalid", "field": field},
    )


def _row_out(row: dict) -> InteressadoOut:
    return InteressadoOut(
        id=str(row["id"]),
        nome=row["nome"],
        whatsapp=row["whatsapp"],
        email=row["email"],
        origem=row.get("origem"),
        consentimento_versao=row["consentimento_versao"],
        consentimento_em=str(row["consentimento_em"]),
        criado_em=str(row["criado_em"]),
    )


# --------------------------------------------------------------------------
# Public route -- no auth dependency
# --------------------------------------------------------------------------


@router.post(
    "/api/public/interessados",
    status_code=status.HTTP_201_CREATED,
    response_model=None,
)
@limiter.limit("5/minute;30/hour", key_func=client_ip_key)
async def create_interessado(
    request: Request,  # required positionally by @limiter.limit (slowapi)
    payload: InteressadoIn,
    store: InteressadosStore = Depends(get_interessados_store),
) -> dict:
    nome = payload.nome.strip()
    if not (2 <= len(nome) <= 120):
        raise _invalid("nome", "Informe um nome com 2 a 120 caracteres.")

    normalized_phone = normalize_phone(payload.whatsapp)
    if normalized_phone is None:
        raise _invalid("whatsapp", "Informe um número de WhatsApp válido.")

    try:
        email_info = validate_email(payload.email, check_deliverability=False)
    except EmailNotValidError:
        raise _invalid("email", "Informe um e-mail válido.")
    email = email_info.normalized.lower()

    if payload.consentimento is not True:
        raise _invalid(
            "consentimento", "É necessário aceitar o consentimento para continuar."
        )

    # Never log nome/whatsapp/email in plain text (LGPD -- contract "LGPD").
    logger.info(
        "interessado_upsert origem=%r consentimento_versao=%s",
        payload.origem,
        CONSENTIMENTO_VERSAO,
    )
    await store.upsert(
        nome=nome,
        whatsapp=normalized_phone,
        email=email,
        origem=payload.origem,
        consentimento_versao=CONSENTIMENTO_VERSAO,
    )
    # Identical response for a new address and an already-registered one --
    # the route never reveals whether an email is registered (contract).
    return {"ok": True}


# --------------------------------------------------------------------------
# Admin routes
# --------------------------------------------------------------------------


@router.get("/api/interessados", response_model=InteressadosListOut)
async def list_interessados(
    limit: int = Query(default=50, ge=1, le=200),
    offset: int = Query(default=0, ge=0),
    ctx: AuthContext = Depends(require_interessados_admin),
    store: InteressadosStore = Depends(get_interessados_store),
) -> InteressadosListOut:
    rows, total = await store.list(limit=limit, offset=offset)
    return InteressadosListOut(items=[_row_out(r) for r in rows], total=total)


@router.delete("/api/interessados/{interessado_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_interessado(
    interessado_id: str,
    ctx: AuthContext = Depends(require_interessados_admin),
    store: InteressadosStore = Depends(get_interessados_store),
) -> None:
    try:
        parsed_id = UUID(interessado_id)
    except ValueError:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Não encontrado.", "code": "not_found"},
        )
    deleted = await store.delete(parsed_id)
    if not deleted:
        raise HTTPException(
            status_code=404,
            detail={"detail": "Não encontrado.", "code": "not_found"},
        )


__all__ = ["router"]
