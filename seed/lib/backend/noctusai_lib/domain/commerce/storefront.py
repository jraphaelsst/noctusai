"""Public storefront services -- org from the Host header, no internal ids out.

Resolution order (CONTRACT §4): `Host` -> `commerce_storefront_hosts` -> org ->
active `commerce` license. An unknown host AND an unlicensed org are the SAME 404 --
the response never says which, so hostnames cannot be probed for licence state.
Every response below is built from an explicit allow-list of fields: ids of
orgs/customers/products/gateway charges and costs (`platform_fee_cents`) never appear.
`offer_id` is public by necessity (the quote/checkout accept it).
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from noctusai_lib.domain.licensing import LicenseChecker, LicenseCheckUnavailable
from noctusai_lib.integrations.email.types import EmailSender
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows, paged_rows
from noctusai_lib.integrations.storage.protocol import StorageBackend
from noctusai_lib.primitives.exceptions import NotFoundError

from ._common import get_row, like_term, page_rows, tbl
from . import access_links as links
from .catalog import active_offers
from .config import CommerceConfig
from .customers import (
    create_privacy_request,
    find_by_email,
    get_customer,
    verify_privacy_request,
)
from .errors import CommerceError, not_found
from .hosts import resolve_host
from .media import with_url
from .order_charges import current_attempt, list_charges
from .orders import get_order_by_token, list_items
from .profile import get_profile
from .types import PrivacyRequestKind, ProductStatus

logger = logging.getLogger(__name__)

_PRODUCTS = "commerce_products"
_OFFERS = "commerce_offers"
_MEDIA = "commerce_media"
_CATEGORIES = "commerce_categories"
_ORDERS = "commerce_orders"


def resolve_storefront_org(db: Any, host_header: str, checker: LicenseChecker, cfg: CommerceConfig) -> str:
    """The org this `Host` serves, or the uniform 404."""
    host = resolve_host(db, host_header)
    if host is None:
        raise NotFoundError("Loja")
    org_id = str(host["org_id"])
    try:
        licensed = checker.has_license(org_id, cfg.license_product_slug)
    except LicenseCheckUnavailable as exc:
        logger.error("commerce storefront: license lookup unavailable (org=%s): %s", org_id, exc)
        raise CommerceError("licenca_indisponivel", "Loja temporariamente indisponível.", 503) from exc
    if not licensed:
        raise NotFoundError("Loja")
    return org_id


def storefront_info(db: Any, org_id: Any, cfg: CommerceConfig) -> dict:
    """The Decreto 7.962 art. 2 disclosures + brand tokens. 404 `loja_nao_configurada`
    when the org has not saved a store profile yet."""
    profile = get_profile(db, org_id)
    if profile is None:
        raise CommerceError("loja_nao_configurada", "Esta loja ainda não foi configurada.", 404)
    return {
        "trade_name": profile["trade_name"],
        "legal_name": profile["legal_name"],
        "cnpj": profile["cnpj"],
        "address": profile.get("address") or {},
        "contact": {"email": profile.get("contact_email"), "phone": profile.get("contact_phone")},
        "brand_tokens": profile.get("brand_tokens") or {},
        "locale": profile.get("locale", "pt-BR"),
        "currency": profile.get("currency", "BRL"),
        "legal": {
            "terms_version": cfg.terms_version,
            "privacy_version": cfg.privacy_version,
            "withdrawal_text": cfg.withdrawal_text,
        },
    }


def _public_offer(offer: dict) -> dict:
    return {
        "id": str(offer["id"]),
        "name": offer["name"],
        "price_cents": int(offer["price_cents"]),
        "currency": offer["currency"],
    }


async def _media_for(db: Any, storage: StorageBackend, cfg: CommerceConfig, org_id: Any, product_ids: list[str]) -> dict[str, list[dict]]:
    rows = in_batched_rows(db, _MEDIA, org_id, "product_id", product_ids)
    rows.sort(key=lambda r: (r.get("position", 0), str(r["id"])))
    by_product: dict[str, list[dict]] = {}
    for row in rows:
        signed = await with_url(storage, cfg, row)
        by_product.setdefault(str(row["product_id"]), []).append(
            {
                "id": str(row["id"]),
                "kind": signed["kind"],
                "alt": signed.get("alt", ""),
                "position": row.get("position", 0),
                "url": signed["url"],
            }
        )
    return by_product


async def catalog_page(
    db: Any,
    storage: StorageBackend,
    cfg: CommerceConfig,
    org_id: Any,
    *,
    category: Optional[str] = None,
    q: Optional[str] = None,
    page: int = 1,
    page_size: int = 20,
) -> tuple[list[dict], int, int, int]:
    """Published products that still have >= 1 active offer, each with its offers and
    first media. (A product whose last offer was deactivated after publishing is
    skipped from the page, so a page can hold fewer than `page_size` rows.)"""
    filters: dict[str, Any] = {"status": ProductStatus.PUBLISHED.value}
    if category:
        cat = tbl(db, _CATEGORIES).select("id").eq("org_id", str(org_id)).eq("slug", category).limit(1).execute().data or []
        if not cat:
            return [], 0, max(1, page), max(1, page_size)
        filters["category_id"] = str(cat[0]["id"])

    def refine(query):
        return query.ilike("title", like_term(q)) if q and q.strip() else query

    rows, total, page, size = page_rows(db, _PRODUCTS, org_id, page=page, page_size=page_size, refine=refine, eq_filters=filters)
    ids = [str(r["id"]) for r in rows]
    offers = in_batched_rows(db, _OFFERS, org_id, "product_id", ids)
    media = await _media_for(db, storage, cfg, org_id, ids)
    out: list[dict] = []
    for row in rows:
        pid = str(row["id"])
        live = sorted((o for o in offers if str(o["product_id"]) == pid and o.get("active")), key=lambda o: (o.get("position", 0), str(o["id"])))
        if not live:
            continue
        out.append(
            {
                "id": pid,
                "slug": row["slug"],
                "title": row["title"],
                "description": row.get("description", ""),
                "product_type": row["product_type"],
                "fulfillment_type": row["fulfillment_type"],
                "category_id": str(row["category_id"]) if row.get("category_id") else None,
                "offers": [_public_offer(o) for o in live],
                "media_url": (media.get(pid) or [{}])[0].get("url"),
            }
        )
    return out, total, page, size


async def product_view(db: Any, storage: StorageBackend, cfg: CommerceConfig, org_id: Any, slug: str) -> dict:
    rows = (
        tbl(db, _PRODUCTS)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("slug", slug)
        .eq("status", ProductStatus.PUBLISHED.value)
        .limit(1)
        .execute()
        .data
        or []
    )
    if not rows:
        raise not_found("Produto")
    product = dict(rows[0])
    pid = str(product["id"])
    live = active_offers(db, org_id, pid)
    if not live:
        raise not_found("Produto")
    category = None
    if product.get("category_id"):
        cat = tbl(db, _CATEGORIES).select("slug,name").eq("org_id", str(org_id)).eq("id", str(product["category_id"])).limit(1).execute().data or []
        category = {"slug": cat[0]["slug"], "name": cat[0]["name"]} if cat else None
    media = await _media_for(db, storage, cfg, org_id, [pid])
    return {
        "id": pid,
        "slug": product["slug"],
        "title": product["title"],
        "description": product.get("description", ""),
        "product_type": product["product_type"],
        "fulfillment_type": product["fulfillment_type"],
        "category_id": str(product["category_id"]) if product.get("category_id") else None,
        "attributes": product.get("attributes") or {},
        "category": category,
        "offers": [_public_offer(o) for o in live],
        "media": media.get(pid, []),
    }


# ─── orders ──────────────────────────────────────────────────────────────


def public_order_view(db: Any, org_id: Any, order: dict) -> dict:
    """Allow-listed order view: status, items, totals, payment affordances -- no ids."""
    pending = order["status"] in ("pending_payment", "created")
    return {
        "token": order["token"],
        "status": order["status"],
        "items": [
            {
                "title": i["title_snapshot"],
                "product_type": i["product_type"],
                "qty": i["qty"],
                "unit_price_cents": i["unit_price_cents"],
                "total_cents": i["total_cents"],
            }
            for i in list_items(db, org_id, order["id"])
        ],
        "subtotal_cents": order["subtotal_cents"],
        "discount_cents": order["discount_cents"],
        "total_cents": order["total_cents"],
        "currency": order["currency"],
        "payment_method": order["payment_method"],
        "checkout_url": order.get("checkout_url") if pending else None,
        "pix_qr": order.get("pix_qr") if pending else None,
        "expires_at": order.get("expires_at"),
        "paid_at": order.get("paid_at"),
        "created_at": order.get("created_at"),
    }


def resolve_order_token(db: Any, org_id: Any, token: str, secret: Optional[str]) -> str:
    """The order's own (bare) token for whatever the buyer's link carries.

    The payment-recovery e-mails link a SIGNED, expiring, order-scoped token (`access_links.PURPOSE_ORDER`); it is
    exchanged here for the order's bare token, so it opens that one order (its page + regenerate) and nothing else.
    A bare token (`secrets.token_urlsafe`, never contains a dot) passes through unchanged. A signed token with no
    configured secret is a 503, never a silent pass."""
    if "." not in token:
        return token
    if not secret:
        raise CommerceError("link_indisponivel", "Links por e-mail não estão configurados.", 503)
    claim = links.verify_token(secret, token, purpose=links.PURPOSE_ORDER, org_id=org_id)
    order = get_row(db, _ORDERS, org_id, claim["s"])
    if order is None:
        raise not_found("Pedido")
    return order["token"]


def order_view_by_token(db: Any, org_id: Any, token: str) -> dict:
    order = get_order_by_token(db, org_id, token)
    if order is None:
        raise not_found("Pedido")
    view = public_order_view(db, org_id, order)
    # What the buyer actually pays (interest included) and in how many parcelas -- from the CURRENT attempt.
    current = current_attempt(list_charges(db, org_id, order["id"]), order)
    view["installment_count"] = int(current["installment_count"]) if current else 1
    view["charged_cents"] = int(current["amount_cents"]) if current else int(order["total_cents"])
    return view


def my_orders_view(db: Any, org_id: Any, customer_id: Any) -> list[dict]:
    customer = get_customer(db, org_id, customer_id)  # 404 if gone
    orders = paged_rows(db, _ORDERS, org_id, eq_filters={"customer_id": str(customer["id"])})
    orders.sort(key=lambda r: str(r.get("created_at", "")), reverse=True)
    return [public_order_view(db, org_id, o) for o in orders[:50]]


# ─── e-mailed links (no enumeration: callers always answer 202) ──────────


async def request_access_link(
    db: Any, org_id: Any, cfg: CommerceConfig, *, email: str, sender: EmailSender, secret: str, base_url: str
) -> None:
    customer = find_by_email(db, org_id, email)
    if customer is None or customer.get("anonymized_at"):
        return
    profile = get_profile(db, org_id) or {}
    token = links.sign_token(
        secret, purpose=links.PURPOSE_MY_ORDERS, org_id=org_id, subject=customer["id"], ttl_minutes=cfg.link_ttl_minutes
    )
    url = base_url.rstrip("/") + cfg.my_orders_path_template.format(token=token)
    await _send_safely(
        sender, to=customer["email"], store_name=profile.get("trade_name", "Loja"),
        subject="Seus pedidos", intro="Use o link abaixo para ver seus pedidos.", url=url, ttl=cfg.link_ttl_minutes,
    )


async def request_privacy(
    db: Any,
    org_id: Any,
    cfg: CommerceConfig,
    *,
    email: str,
    kind: PrivacyRequestKind,
    details: Optional[str],
    sender: EmailSender,
    secret: str,
    base_url: str,
) -> None:
    customer = find_by_email(db, org_id, email)
    if customer is None or customer.get("anonymized_at"):
        return
    request = create_privacy_request(db, org_id, customer["id"], kind, details)
    profile = get_profile(db, org_id) or {}
    token = links.sign_token(
        secret, purpose=links.PURPOSE_PRIVACY_VERIFY, org_id=org_id, subject=request["id"], ttl_minutes=cfg.link_ttl_minutes
    )
    url = base_url.rstrip("/") + cfg.privacy_verify_path_template.format(token=token)
    await _send_safely(
        sender, to=customer["email"], store_name=profile.get("trade_name", "Loja"),
        subject="Confirme sua solicitação de privacidade",
        intro="Recebemos uma solicitação sobre seus dados pessoais. Confirme que foi você pelo link abaixo.",
        url=url, ttl=cfg.link_ttl_minutes,
    )


async def _send_safely(sender: EmailSender, *, to: str, store_name: str, subject: str, intro: str, url: str, ttl: int) -> None:
    """Send; a mailer failure is logged LOUDLY but never changes the HTTP answer
    (a 5xx here would let a caller distinguish an existing mailbox from a missing one)."""
    try:
        await links.send_link_email(sender, to=to, store_name=store_name, subject=subject, intro=intro, url=url, ttl_minutes=ttl)
    except Exception:  # noqa: BLE001 - see docstring
        logger.error("commerce: could not send the %r e-mail", subject, exc_info=True)


def confirm_privacy_request(db: Any, org_id: Any, cfg: CommerceConfig, *, token: str, secret: str) -> dict:
    claim = links.verify_token(secret, token, purpose=links.PURPOSE_PRIVACY_VERIFY, org_id=org_id)
    request = verify_privacy_request(db, org_id, claim["s"])
    return {"status": request["status"], "kind": request["kind"]}


def my_orders_for_token(db: Any, org_id: Any, cfg: CommerceConfig, *, token: str, secret: str) -> list[dict]:
    claim = links.verify_token(secret, token, purpose=links.PURPOSE_MY_ORDERS, org_id=org_id)
    return my_orders_view(db, org_id, claim["s"])


__all__ = [
    "catalog_page",
    "confirm_privacy_request",
    "my_orders_for_token",
    "my_orders_view",
    "order_view_by_token",
    "product_view",
    "resolve_order_token",
    "public_order_view",
    "request_access_link",
    "request_privacy",
    "resolve_storefront_org",
    "storefront_info",
]
