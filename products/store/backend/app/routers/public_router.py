"""Public storefront API — NO auth dependency, rate-limited per visitor IP.

Contract §3 "Public". The seed wires no global auth middleware (auth is
per-route `Depends(...)`), so a route that never declares an auth dep is
reachable unauthenticated by construction. Every route here carries
`@limiter.limit(..., key_func=client_ip_key)` — behind the Cloudflare tunnel
the socket peer is one shared address; `client_ip_key` reads the real visitor.

Deliberately NO ``from __future__ import annotations`` here: combined with
``@limiter.limit(...)`` (slowapi), a postponed annotation on a Pydantic body
param resolves against the WRAPPER's ``__globals__`` (``slowapi.extension``)
instead of this module's, and FastAPI silently treats the body model as a
``Query(...)`` param. Same footgun academia's ``interessados_router`` documents.
"""
import logging

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse

from noctusai_lib.api.rate_limit import client_ip_key

from app.config import settings
from app.rate_limit import limiter
from app.schemas.store import CheckoutIn, CheckoutOut, PedidoPublicOut
from app.services.assets import AssetService
from app.services.checkout_service import CheckoutError, CheckoutService
from app.services.delivery_service import DeliveryService, DownloadRefused
from app.services.settings_service import SettingsService
from app.store_deps import (
    get_assets,
    get_checkout_service,
    get_delivery_service,
    get_pedido_store,
    get_settings_service,
)
from app.stores import PedidoStore

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/public", tags=["store-public"])

_TOKEN_MAX_LEN = 128


def _not_found(detail: str = "Não encontrado.") -> HTTPException:
    return HTTPException(status_code=404, detail={"detail": detail, "code": "not_found"})


def _pedido_or_404(pedidos: PedidoStore, token: str) -> dict:
    if not token or len(token) > _TOKEN_MAX_LEN:
        raise _not_found("Pedido não encontrado.")
    pedido = pedidos.get_by_token(token)
    if pedido is None:
        raise _not_found("Pedido não encontrado.")
    return pedido


@router.get("/settings")
@limiter.limit(settings.public_read_rate_limit, key_func=client_ip_key)
async def public_settings(
    request: Request,  # required positionally by @limiter.limit (slowapi)
    service: SettingsService = Depends(get_settings_service),
) -> dict:
    return await service.public_view()


@router.get("/autor/foto")
@limiter.limit(settings.public_read_rate_limit, key_func=client_ip_key)
async def author_photo(
    request: Request,
    assets: AssetService = Depends(get_assets),
) -> RedirectResponse:
    url = await assets.photo_signed_url(expires_in_seconds=300)
    if url is None:
        raise _not_found("Foto não encontrada.")
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


@router.post("/checkout", status_code=status.HTTP_201_CREATED, response_model=CheckoutOut)
@limiter.limit(settings.checkout_rate_limit, key_func=client_ip_key)
async def create_checkout(
    request: Request,
    payload: CheckoutIn,
    service: CheckoutService = Depends(get_checkout_service),
) -> dict:
    try:
        return service.create(nome=payload.nome, email=payload.email, cpf=payload.cpf)
    except CheckoutError as exc:
        body: dict = {"detail": exc.detail, "code": exc.code}
        if exc.field:
            body["field"] = exc.field
        raise HTTPException(status_code=exc.status_code, detail=body) from exc


@router.get("/pedidos/{token}", response_model=PedidoPublicOut)
@limiter.limit(settings.public_read_rate_limit, key_func=client_ip_key)
async def pedido_status(
    request: Request,
    token: str,
    pedidos: PedidoStore = Depends(get_pedido_store),
    delivery: DeliveryService = Depends(get_delivery_service),
) -> dict:
    return delivery.status_view(_pedido_or_404(pedidos, token))


@router.get("/download/{token}")
@limiter.limit(settings.download_rate_limit, key_func=client_ip_key)
async def download(
    request: Request,
    token: str,
    pedidos: PedidoStore = Depends(get_pedido_store),
    delivery: DeliveryService = Depends(get_delivery_service),
) -> RedirectResponse:
    pedido = _pedido_or_404(pedidos, token)
    try:
        url = await delivery.take_download(pedido)
    except DownloadRefused as exc:
        raise HTTPException(
            status_code=exc.status_code, detail={"detail": exc.detail, "code": "download_unavailable"}
        ) from exc
    return RedirectResponse(url, status_code=302, headers={"Cache-Control": "no-store"})


__all__ = ["router"]
