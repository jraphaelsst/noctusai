"""Commerce HTTP surface -- three mountable router factories.

    commerce_staff_router(...)     license-gated back office   /api/commerce/*
    storefront_router(...)         PUBLIC, org from the Host   /api/storefront/*
    commerce_webhook_router(...)   gateway callbacks           /api/webhooks/payments/{gateway}/{org_id}

Factories (card_hub precedent) because the seed cannot know the product's auth
dependency, its schema-scoped database accessor, its storage, its gateway or its
rate limiter: all arrive as FastAPI DEPENDENCIES / callables, so a product keeps
its own DI seams and its tests keep using `app.dependency_overrides`.

Envelopes (`CONTRACT.md §3`): `success_response` -> `{"data": ...}`; paged lists
`paginated_response` -> `{"data": [...], "pagination": {...}}`; errors go through
the seed's `AppException` handlers -> `{"error": {"code", "message", "details"}}`
(codes `cnpj_invalido`, `versao_conflitante`, `aceite_obrigatorio`, ...).

🔴 NEVER `get_admin_client().schema(...)` in here: `get_db` already returns the
product's schema-scoped client (re-deriving poisons the shared admin client).
"""
from __future__ import annotations

import json
import logging
from typing import Any, Callable, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, File, Form, Query, Request, Response, UploadFile

from noctusai_lib.domain.licensing import LicenseChecker
from noctusai_lib.domain.payments.event_inbox import EventInbox
from noctusai_lib.integrations.cnpj_registry import CnpjRegistryLookup
from noctusai_lib.integrations.email.types import EmailSender
from noctusai_lib.integrations.payments.webhook_events import PaymentWebhookSignatureError, parse_webhook_event
from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.primitives.exceptions import ForbiddenError, NotFoundError
from noctusai_lib.primitives.responses import paginated_response, success_response

from . import catalog as catalog_svc
from . import checkout as checkout_svc
from . import coupons as coupons_svc
from . import customers as customers_svc
from . import hosts as hosts_svc
from . import media as media_svc
from . import orders as orders_svc
from . import profile as profile_svc
from . import storefront as store_svc
from . import webhook as webhook_svc
from .config import CommerceConfig, CommerceContext
from .errors import CommerceError
from .fulfillment import FulfillmentRegistry, make_fulfillment_registry
from .gateway import GATEWAY_NAME, CheckoutGateway
from .schemas import (
    AccessLinkBody,
    CategoryBody,
    CategoryPatch,
    CheckoutBody,
    CnpjLookupBody,
    CouponBody,
    CouponPatch,
    HostBody,
    OfferBody,
    OfferPatch,
    PrivacyRequestBody,
    ProductBody,
    ProductPatch,
    ProfileBody,
    QuoteBody,
    StatusBody,
    TokenBody,
)

logger = logging.getLogger(__name__)

#: `(limit_string) -> decorator` -- e.g. slowapi's `limiter.limit`. Optional: a
#: host without a limiter simply mounts unthrottled routes (tests do).
RateLimit = Callable[[str], Callable[[Callable], Callable]]


def _dump(model: Any, **kw: Any) -> dict:
    return model.model_dump(mode="python", **kw)


def _client_ip(request: Request) -> Optional[str]:
    # Cloudflare overwrites this header on every proxied request (cannot be spoofed from outside).
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    return forwarded or (request.client.host if request.client else None)


def _base_url(request: Request) -> str:
    scheme = request.headers.get("x-forwarded-proto") or request.url.scheme
    return f"{scheme}://{request.headers.get('host', '')}"


# ─── staff ────────────────────────────────────────────────────────────────


def commerce_staff_router(
    cfg: CommerceConfig,
    *,
    auth_dependency: Callable[..., Any],
    resolve_context: Callable[[Any, Any], CommerceContext],
    get_db: Callable[..., Any],
    get_storage: Callable[..., StorageBackend],
    get_cnpj_lookup: Callable[..., CnpjRegistryLookup],
    is_platform_admin: Callable[[Any], bool],
    prefix: str = "/api/commerce",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """The back-office router.

    Args:
        auth_dependency: the product's license-gated `get_current_user_org` (it is
            where the 401 / 403 come from).
        resolve_context: `(auth_value, db) -> CommerceContext(db, org_id, user_id)`.
        get_db / get_storage / get_cnpj_lookup: FastAPI dependencies.
        is_platform_admin: `(auth_value) -> bool`, decided SERVER-SIDE (the seed's
            `is_platform_staff`); gates `platform_fee_bps` and the `/hosts` routes.
            Never derived from client input.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["commerce"])

    def ctx_dep(auth=Depends(auth_dependency), db=Depends(get_db)) -> CommerceContext:
        return resolve_context(auth, db)

    def platform_admin_dep(auth=Depends(auth_dependency)) -> None:
        if not is_platform_admin(auth):
            raise ForbiddenError("Apenas a administração da plataforma pode fazer isso.")

    # ── profile ──
    @router.get("/profile", name="commerce_get_profile")
    async def get_profile_route(ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(profile_svc.get_profile(ctx.db, ctx.org_id))

    @router.put("/profile", name="commerce_put_profile")
    async def put_profile_route(
        body: ProfileBody, auth=Depends(auth_dependency), ctx: CommerceContext = Depends(ctx_dep)
    ) -> dict:
        data = _dump(body)
        saved = profile_svc.put_profile(
            ctx.db, ctx.org_id, ctx.user_id, data,
            expected_version=body.expected_version, is_platform_admin=is_platform_admin(auth),
        )
        return success_response(saved)

    @router.post("/profile/cnpj-lookup", name="commerce_cnpj_lookup")
    async def cnpj_lookup_route(
        body: CnpjLookupBody, ctx: CommerceContext = Depends(ctx_dep), lookup=Depends(get_cnpj_lookup)
    ) -> dict:
        return success_response(await profile_svc.cnpj_prefill(lookup, body.cnpj))

    # ── categories ──
    @router.get("/categories", name="commerce_list_categories")
    async def list_categories_route(ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(catalog_svc.list_categories(ctx.db, ctx.org_id))

    @router.post("/categories", status_code=201, name="commerce_create_category")
    async def create_category_route(body: CategoryBody, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(catalog_svc.create_category(ctx.db, ctx.org_id, _dump(body)))

    @router.patch("/categories/{category_id}", name="commerce_update_category")
    async def update_category_route(
        category_id: UUID, body: CategoryPatch, ctx: CommerceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(
            catalog_svc.update_category(ctx.db, ctx.org_id, category_id, _dump(body, exclude_unset=True))
        )

    @router.delete("/categories/{category_id}", status_code=204, name="commerce_delete_category")
    async def delete_category_route(category_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> Response:
        catalog_svc.delete_category(ctx.db, ctx.org_id, category_id)
        return Response(status_code=204)

    # ── products ──
    @router.get("/products", name="commerce_list_products")
    async def list_products_route(
        status: Optional[str] = Query(None),
        q: Optional[str] = Query(None, max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: CommerceContext = Depends(ctx_dep),
    ) -> dict:
        try:
            rows, total, page, size = catalog_svc.list_products(
                ctx.db, ctx.org_id, status=status, q=q, page=page, page_size=page_size
            )
        except ValueError as exc:
            raise CommerceError("invalid", "Status de produto inválido.", 422, field="status") from exc
        return paginated_response(rows, total, page, size)

    @router.post("/products", status_code=201, name="commerce_create_product")
    async def create_product_route(body: ProductBody, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(catalog_svc.create_product(ctx.db, ctx.org_id, _dump(body)))

    @router.get("/products/{product_id}", name="commerce_get_product")
    async def get_product_route(
        product_id: UUID, ctx: CommerceContext = Depends(ctx_dep), storage=Depends(get_storage)
    ) -> dict:
        product = catalog_svc.get_product(ctx.db, ctx.org_id, product_id)
        product["offers"] = catalog_svc.list_offers(ctx.db, ctx.org_id, product_id)
        product["media"] = await media_svc.list_media(ctx.db, storage, cfg, ctx.org_id, product_id)
        return success_response(product)

    @router.patch("/products/{product_id}", name="commerce_update_product")
    async def update_product_route(
        product_id: UUID, body: ProductPatch, ctx: CommerceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(
            catalog_svc.update_product(ctx.db, ctx.org_id, product_id, _dump(body, exclude_unset=True))
        )

    @router.delete("/products/{product_id}", status_code=204, name="commerce_delete_product")
    async def delete_product_route(
        product_id: UUID, ctx: CommerceContext = Depends(ctx_dep), storage=Depends(get_storage)
    ) -> Response:
        media_rows = catalog_svc.delete_product_rows(ctx.db, ctx.org_id, product_id)
        await media_svc.delete_objects(storage, cfg, media_rows)
        return Response(status_code=204)

    @router.post("/products/{product_id}/status", name="commerce_set_product_status")
    async def set_status_route(product_id: UUID, body: StatusBody, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(catalog_svc.set_product_status(ctx.db, ctx.org_id, product_id, body.status))

    # ── offers ──
    @router.get("/products/{product_id}/offers", name="commerce_list_offers")
    async def list_offers_route(product_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(catalog_svc.list_offers(ctx.db, ctx.org_id, product_id))

    @router.post("/products/{product_id}/offers", status_code=201, name="commerce_create_offer")
    async def create_offer_route(product_id: UUID, body: OfferBody, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(catalog_svc.create_offer(ctx.db, ctx.org_id, product_id, _dump(body)))

    @router.patch("/products/{product_id}/offers/{offer_id}", name="commerce_update_offer")
    async def update_offer_route(
        product_id: UUID, offer_id: UUID, body: OfferPatch, ctx: CommerceContext = Depends(ctx_dep)
    ) -> dict:
        return success_response(
            catalog_svc.update_offer(ctx.db, ctx.org_id, product_id, offer_id, _dump(body, exclude_unset=True))
        )

    @router.delete("/products/{product_id}/offers/{offer_id}", status_code=204, name="commerce_delete_offer")
    async def delete_offer_route(product_id: UUID, offer_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> Response:
        catalog_svc.delete_offer(ctx.db, ctx.org_id, product_id, offer_id)
        return Response(status_code=204)

    # ── media ──
    @router.post("/products/{product_id}/media", status_code=201, name="commerce_upload_media")
    async def upload_media_route(
        product_id: UUID,
        file: UploadFile = File(...),
        alt: str = Form("", max_length=300),
        ctx: CommerceContext = Depends(ctx_dep),
        storage=Depends(get_storage),
    ) -> dict:
        data = await file.read(media_svc.MAX_VIDEO_BYTES + 1)
        saved = await media_svc.add_media(
            ctx.db, storage, cfg, ctx.org_id, product_id,
            content_type=file.content_type or "", data=data, alt=alt,
        )
        return success_response(saved)

    @router.delete("/products/{product_id}/media/{media_id}", status_code=204, name="commerce_delete_media")
    async def delete_media_route(
        product_id: UUID, media_id: UUID, ctx: CommerceContext = Depends(ctx_dep), storage=Depends(get_storage)
    ) -> Response:
        await media_svc.delete_media(ctx.db, storage, cfg, ctx.org_id, product_id, media_id)
        return Response(status_code=204)

    # ── coupons ──
    @router.get("/coupons", name="commerce_list_coupons")
    async def list_coupons_route(ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(coupons_svc.list_coupons(ctx.db, ctx.org_id))

    @router.post("/coupons", status_code=201, name="commerce_create_coupon")
    async def create_coupon_route(body: CouponBody, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(coupons_svc.create_coupon(ctx.db, ctx.org_id, _dump(body)))

    @router.patch("/coupons/{coupon_id}", name="commerce_update_coupon")
    async def update_coupon_route(coupon_id: UUID, body: CouponPatch, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(
            coupons_svc.update_coupon(ctx.db, ctx.org_id, coupon_id, _dump(body, exclude_unset=True))
        )

    @router.delete("/coupons/{coupon_id}", status_code=204, name="commerce_delete_coupon")
    async def delete_coupon_route(coupon_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> Response:
        coupons_svc.delete_coupon(ctx.db, ctx.org_id, coupon_id)
        return Response(status_code=204)

    # ── customers ──
    @router.get("/customers", name="commerce_list_customers")
    async def list_customers_route(
        q: Optional[str] = Query(None, max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: CommerceContext = Depends(ctx_dep),
    ) -> dict:
        rows, total, page, size = customers_svc.list_customers(ctx.db, ctx.org_id, q=q, page=page, page_size=page_size)
        return paginated_response(rows, total, page, size)

    @router.get("/customers/{customer_id}", name="commerce_get_customer")
    async def get_customer_route(customer_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(customers_svc.customer_detail(ctx.db, ctx.org_id, customer_id))

    @router.get("/customers/{customer_id}/export", name="commerce_export_customer")
    async def export_customer_route(customer_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(customers_svc.export_customer(ctx.db, ctx.org_id, customer_id))

    @router.post("/customers/{customer_id}/anonymize", name="commerce_anonymize_customer")
    async def anonymize_customer_route(customer_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(customers_svc.anonymize_customer(ctx.db, ctx.org_id, customer_id))

    # ── orders ──
    @router.get("/orders", name="commerce_list_orders")
    async def list_orders_route(
        status: Optional[str] = Query(None),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=100),
        ctx: CommerceContext = Depends(ctx_dep),
    ) -> dict:
        try:
            rows, total, page, size = orders_svc.list_orders(ctx.db, ctx.org_id, status=status, page=page, page_size=page_size)
        except ValueError as exc:
            raise CommerceError("invalid", "Status de pedido inválido.", 422, field="status") from exc
        return paginated_response(rows, total, page, size)

    @router.get("/orders/{order_id}", name="commerce_get_order")
    async def get_order_route(order_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(orders_svc.order_detail(ctx.db, ctx.org_id, order_id))

    @router.post("/orders/{order_id}/cancel", name="commerce_cancel_order")
    async def cancel_order_route(order_id: UUID, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        orders_svc.cancel_order(ctx.db, ctx.org_id, order_id)
        return success_response(orders_svc.order_detail(ctx.db, ctx.org_id, order_id))

    # ── hosts (platform admin only) ──
    @router.get("/hosts", name="commerce_list_hosts", dependencies=[Depends(platform_admin_dep)])
    async def list_hosts_route(ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(hosts_svc.list_hosts(ctx.db, ctx.org_id))

    @router.post("/hosts", status_code=201, name="commerce_add_host", dependencies=[Depends(platform_admin_dep)])
    async def add_host_route(body: HostBody, ctx: CommerceContext = Depends(ctx_dep)) -> dict:
        return success_response(hosts_svc.add_host(ctx.db, ctx.org_id, body.hostname, is_primary=body.is_primary))

    @router.delete(
        "/hosts/{hostname}", status_code=204, name="commerce_delete_host", dependencies=[Depends(platform_admin_dep)]
    )
    async def delete_host_route(hostname: str, ctx: CommerceContext = Depends(ctx_dep)) -> Response:
        hosts_svc.delete_host(ctx.db, ctx.org_id, hostname)
        return Response(status_code=204)

    return router


# ─── storefront (public) ──────────────────────────────────────────────────


def storefront_router(
    cfg: CommerceConfig,
    *,
    get_db: Callable[..., Any],
    get_storage: Callable[..., StorageBackend],
    get_gateway: Callable[..., CheckoutGateway],
    get_email: Callable[..., EmailSender],
    get_license_checker: Callable[..., LicenseChecker],
    get_link_secret: Callable[..., str],
    rate_limit: Optional[RateLimit] = None,
    prefix: str = "/api/storefront",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """The PUBLIC storefront router (no login).

    The org is resolved from the `Host` header (`commerce_storefront_hosts`); an
    unknown host or an org without an active license is the SAME 404. Every handler
    takes `request: Request` first so slowapi-style decorators can key on it.
    `rate_limit` (e.g. `limiter.limit`) is applied with `cfg.storefront_rate_limit`
    on reads and `cfg.checkout_rate_limit` on the write routes.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["storefront"])

    def org_dep(request: Request, db=Depends(get_db), checker=Depends(get_license_checker)) -> str:
        return store_svc.resolve_storefront_org(db, request.headers.get("host", ""), checker, cfg)

    def limited(limit: str, fn: Callable) -> Callable:
        return rate_limit(limit)(fn) if rate_limit is not None else fn

    read_limit, write_limit = cfg.storefront_rate_limit, cfg.checkout_rate_limit

    async def info(request: Request, org_id: str = Depends(org_dep), db=Depends(get_db)) -> dict:
        return success_response(store_svc.storefront_info(db, org_id, cfg))

    async def catalog(
        request: Request,
        category: Optional[str] = Query(None, max_length=80),
        q: Optional[str] = Query(None, max_length=100),
        page: int = Query(1, ge=1),
        page_size: int = Query(20, ge=1, le=50),
        org_id: str = Depends(org_dep),
        db=Depends(get_db),
        storage=Depends(get_storage),
    ) -> dict:
        rows, total, page, size = await store_svc.catalog_page(
            db, storage, cfg, org_id, category=category, q=q, page=page, page_size=page_size
        )
        return paginated_response(rows, total, page, size)

    async def product(
        request: Request, slug: str, org_id: str = Depends(org_dep), db=Depends(get_db), storage=Depends(get_storage)
    ) -> dict:
        return success_response(await store_svc.product_view(db, storage, cfg, org_id, slug))

    async def quote(request: Request, body: QuoteBody, org_id: str = Depends(org_dep), db=Depends(get_db)) -> dict:
        built = checkout_svc.build_quote(db, org_id, [_dump(i) for i in body.items], body.coupon)
        return success_response(built.public())

    async def checkout(
        request: Request,
        body: CheckoutBody,
        org_id: str = Depends(org_dep),
        db=Depends(get_db),
        gateway=Depends(get_gateway),
    ) -> dict:
        base = _base_url(request)
        result = checkout_svc.create_checkout(
            db, org_id, cfg, gateway, _dump(body),
            order_url_for=lambda token: base + cfg.order_path_template.format(token=token),
            ip=_client_ip(request), user_agent=request.headers.get("user-agent"),
        )
        return success_response(result)

    async def order_by_token(request: Request, token: str, org_id: str = Depends(org_dep), db=Depends(get_db)) -> dict:
        return success_response(store_svc.order_view_by_token(db, org_id, token))

    async def access_link(
        request: Request,
        body: AccessLinkBody,
        org_id: str = Depends(org_dep),
        db=Depends(get_db),
        sender=Depends(get_email),
        secret: str = Depends(get_link_secret),
    ) -> Response:
        await store_svc.request_access_link(
            db, org_id, cfg, email=body.email, sender=sender, secret=secret, base_url=_base_url(request)
        )
        return _accepted()

    async def my_orders(
        request: Request,
        token: str = Query(..., min_length=10, max_length=2048),
        org_id: str = Depends(org_dep),
        db=Depends(get_db),
        secret: str = Depends(get_link_secret),
    ) -> dict:
        return success_response(store_svc.my_orders_for_token(db, org_id, cfg, token=token, secret=secret))

    async def privacy_request(
        request: Request,
        body: PrivacyRequestBody,
        org_id: str = Depends(org_dep),
        db=Depends(get_db),
        sender=Depends(get_email),
        secret: str = Depends(get_link_secret),
    ) -> Response:
        await store_svc.request_privacy(
            db, org_id, cfg, email=body.email, kind=body.kind, details=body.details,
            sender=sender, secret=secret, base_url=_base_url(request),
        )
        return _accepted()

    async def privacy_verify(
        request: Request,
        body: TokenBody,
        org_id: str = Depends(org_dep),
        db=Depends(get_db),
        secret: str = Depends(get_link_secret),
    ) -> dict:
        return success_response(store_svc.confirm_privacy_request(db, org_id, cfg, token=body.token, secret=secret))

    router.add_api_route("", limited(read_limit, info), methods=["GET"], name="storefront_info")
    router.add_api_route("/catalog", limited(read_limit, catalog), methods=["GET"], name="storefront_catalog")
    router.add_api_route("/products/{slug}", limited(read_limit, product), methods=["GET"], name="storefront_product")
    router.add_api_route("/checkout/quote", limited(read_limit, quote), methods=["POST"], name="storefront_quote")
    router.add_api_route(
        "/checkout", limited(write_limit, checkout), methods=["POST"], status_code=201, name="storefront_checkout"
    )
    router.add_api_route("/orders/access-link", limited(write_limit, access_link), methods=["POST"], status_code=202, name="storefront_access_link")
    router.add_api_route("/orders/{token}", limited(read_limit, order_by_token), methods=["GET"], name="storefront_order")
    router.add_api_route("/my-orders", limited(read_limit, my_orders), methods=["GET"], name="storefront_my_orders")
    router.add_api_route("/privacy-requests", limited(write_limit, privacy_request), methods=["POST"], status_code=202, name="storefront_privacy_request")
    router.add_api_route("/privacy-requests/verify", limited(write_limit, privacy_verify), methods=["POST"], name="storefront_privacy_verify")
    return router


def _accepted() -> Response:
    """A uniform 202 with a fixed body: the answer never varies with whether the mailbox exists."""
    return Response(content=json.dumps({"data": {"accepted": True}}), status_code=202, media_type="application/json")


# ─── webhook ──────────────────────────────────────────────────────────────


def commerce_webhook_router(
    cfg: CommerceConfig,
    *,
    get_db: Callable[..., Any],
    get_gateway: Callable[..., CheckoutGateway],
    get_event_inbox: Callable[..., EventInbox],
    get_fulfillment: Optional[Callable[..., FulfillmentRegistry]] = None,
    rate_limit: Optional[RateLimit] = None,
    prefix: str = "/api/webhooks/payments",
    tags: Optional[list[str]] = None,
) -> APIRouter:
    """`POST {prefix}/{gateway}/{org_id}` -- the payment-gateway callback.

    The webhook 5-pin contract (`KB § PATTERNS/security/webhook-signatures.md`):
    (1) verify via the seed (`parse_webhook_event`, constant-time) BEFORE any DB work;
    (2) the per-org secret is resolved PER REQUEST (`gateway.webhook_token(org_id)`);
    (3) fail-closed -- an unset token is a 401, never an open door;
    (4) `rate_limit(cfg.webhook_rate_limit)` -- the only throttle on this unauthenticated surface;
    (5) status-code-pinned tests. Always 200 for a verified event we do not act on.
    """
    router = APIRouter(prefix=prefix, tags=tags or ["commerce-webhooks"])
    registry_dep = get_fulfillment or (lambda: _DEFAULT_REGISTRY)

    async def receive(
        request: Request,
        gateway_name: str,
        org_id: UUID,
        db=Depends(get_db),
        gateway=Depends(get_gateway),
        inbox=Depends(get_event_inbox),
        fulfillment=Depends(registry_dep),
    ) -> dict:
        if gateway_name != GATEWAY_NAME:
            raise NotFoundError("Gateway")
        body = await request.body()
        token = gateway.webhook_token(org_id)
        try:
            event = parse_webhook_event(body, request.headers, gateway=GATEWAY_NAME, asaas_webhook_token=token or None)
        except PaymentWebhookSignatureError as exc:
            logger.warning("commerce webhook: verification failed (org=%s): %s", org_id, getattr(exc, "detail", exc))
            raise CommerceError("assinatura_invalida", "Assinatura do webhook inválida.", 401) from exc
        outcome = webhook_svc.handle_event(db, str(org_id), event, inbox=inbox, gateway=gateway, fulfillment=fulfillment)
        return {"received": True, "outcome": outcome}

    handler = rate_limit(cfg.webhook_rate_limit)(receive) if rate_limit is not None else receive
    router.add_api_route("/{gateway_name}/{org_id}", handler, methods=["POST"], name="commerce_payment_webhook")
    return router


_DEFAULT_REGISTRY = make_fulfillment_registry()


__all__ = ["RateLimit", "commerce_staff_router", "commerce_webhook_router", "storefront_router"]
