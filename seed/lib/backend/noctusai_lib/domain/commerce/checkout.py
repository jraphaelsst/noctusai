"""Quote + checkout -- the public purchase path.

PRICE IS ALWAYS RECOMPUTED SERVER-SIDE: the request carries `{offer_id, qty}` and a
coupon code, never an amount. `build_quote` reads the live offers (active, product
published, same org), applies the coupon in integer cents and reports whether the
cart needs the CDC art. 49 immediate-delivery waiver. `create_checkout` re-runs the
quote, enforces consents, validates the buyer, reserves the coupon use, writes
customer + order + items + consents + the `created` event, then creates the
hosted charge (Asaas, one-off) and moves the order to `pending_payment` -- or to
`failed` with a 502 when the gateway refuses (the row stays: a failed attempt is
still an order-shaped fact).

Platform fee (D27): when the org's `platform_fee_bps > 0` AND the platform wallet
is configured the charge carries a split `{walletId, percentualValue: bps/100}` and
`platform_fee_cents` records the EXPECTED fee; with no wallet there is no split and
the fact is logged ONCE per org (not an error).

PII: buyer name/e-mail/doc are never logged.
"""
from __future__ import annotations

import logging
import math
from dataclasses import dataclass, field
from datetime import timedelta
from typing import Any, Callable, Mapping, Optional

from noctusai_lib.integrations.payments.checkout import CheckoutRequest, PixQr
from noctusai_lib.integrations.payments.errors import PaymentGatewayError
from noctusai_lib.integrations.payments.types import Money
from noctusai_lib.integrations.persistence.table_reads import in_batched_rows
from noctusai_lib.primitives.identificador import cnpj_dv_valido, cpf_dv_valido

from . import coupons as coupons_svc
from ._common import digits, first, new_id, now, tbl, valid_email
from .config import CommerceConfig
from .customers import record_consents, upsert_buyer
from .errors import ACEITE_OBRIGATORIO, CommerceError, GatewayNotConfigured, invalid
from .gateway import GATEWAY_NAME, CheckoutGateway
from .order_state import OrderEvent
from .orders import append_event, apply_transition, new_token
from .profile import get_profile
from .types import ConsentKind, OrderEventSource, OrderStatus, PaymentMethod, is_digital_line

logger = logging.getLogger(__name__)

_OFFERS = "commerce_offers"
_PRODUCTS = "commerce_products"
_ORDERS = "commerce_orders"
_ITEMS = "commerce_order_items"

MAX_SUBTOTAL_CENTS = 2_000_000_000  # keeps every sum inside Postgres INTEGER

#: PaymentMethod -> the seed `BillingMethod` literal.
_BILLING_METHOD = {
    PaymentMethod.PIX.value: "pix",
    PaymentMethod.BOLETO.value: "boleto",
    PaymentMethod.CREDIT_CARD.value: "card",
}

_NO_WALLET_LOGGED: set[str] = set()


@dataclass
class Quote:
    lines: list[dict]
    subtotal_cents: int
    discount_cents: int
    total_cents: int
    currency: str
    coupon: Optional[dict] = None
    coupon_error: Optional[str] = None
    requires_immediate_delivery_waiver: bool = False
    #: full offer/product rows behind each line (order-item snapshot source); not public.
    sources: list[dict] = field(default_factory=list, repr=False)

    def public(self) -> dict:
        out: dict[str, Any] = {
            "lines": self.lines,
            "subtotal_cents": self.subtotal_cents,
            "discount_cents": self.discount_cents,
            "total_cents": self.total_cents,
            "currency": self.currency,
            "requires_immediate_delivery_waiver": self.requires_immediate_delivery_waiver,
        }
        if self.coupon_error:
            out["coupon_error"] = self.coupon_error
        return out


def _unavailable(offer_id: str) -> CommerceError:
    return CommerceError(
        "oferta_indisponivel", "Um item do carrinho não está mais disponível.", 422, details={"offer_id": offer_id}
    )


def build_quote(
    db: Any, org_id: Any, items: list[Mapping[str, Any]], coupon_code: Optional[str] = None
) -> Quote:
    """Price a cart server-side. Raises `oferta_indisponivel` (422) for an unknown /
    inactive offer or an unpublished product -- never prices something unsellable."""
    qty_by_offer: dict[str, int] = {}
    for item in items:
        oid = str(item["offer_id"])
        qty_by_offer[oid] = min(99, qty_by_offer.get(oid, 0) + int(item["qty"]))
    if not qty_by_offer:
        raise invalid("items", "O carrinho está vazio.")

    offers = {str(o["id"]): o for o in in_batched_rows(db, _OFFERS, org_id, "id", list(qty_by_offer))}
    products = {
        str(p["id"]): p
        for p in in_batched_rows(db, _PRODUCTS, org_id, "id", sorted({str(o["product_id"]) for o in offers.values()}))
    }
    lines: list[dict] = []
    sources: list[dict] = []
    currencies: set[str] = set()
    subtotal = 0
    for oid, qty in qty_by_offer.items():
        offer = offers.get(oid)
        product = products.get(str(offer["product_id"])) if offer else None
        if offer is None or not offer.get("active") or product is None or product.get("status") != "published":
            raise _unavailable(oid)
        unit = int(offer["price_cents"])
        total = unit * qty
        subtotal += total
        currencies.add(offer["currency"])
        lines.append(
            {
                "offer_id": oid,
                "product_id": str(product["id"]),
                "title": product["title"],
                "product_type": product["product_type"],
                "fulfillment_type": product["fulfillment_type"],
                "unit_price_cents": unit,
                "qty": qty,
                "total_cents": total,
            }
        )
        sources.append({"offer": offer, "product": product})
    if len(currencies) != 1:
        raise CommerceError("moeda_mista", "O carrinho mistura moedas diferentes.", 422)
    if subtotal > MAX_SUBTOTAL_CENTS:
        raise CommerceError("carrinho_grande", "O valor do carrinho excede o limite.", 422)

    discount, coupon, coupon_error = 0, None, None
    if coupon_code and coupon_code.strip():
        coupon, discount, coupon_error = coupons_svc.check_coupon(db, org_id, coupon_code, subtotal)
    return Quote(
        lines=lines,
        subtotal_cents=subtotal,
        discount_cents=discount,
        total_cents=subtotal - discount,
        currency=currencies.pop(),
        coupon=coupon,
        coupon_error=coupon_error,
        requires_immediate_delivery_waiver=any(
            is_digital_line(s["product"]["product_type"], s["product"]["fulfillment_type"]) for s in sources
        ),
        sources=sources,
    )


# ─── validation ──────────────────────────────────────────────────────────


def validate_consents(cfg: CommerceConfig, consents: Optional[Mapping[str, Any]], needs_waiver: bool) -> None:
    """422 `aceite_obrigatorio` unless terms + privacy (CURRENT versions) are accepted
    and, for any digital line, the immediate-delivery waiver is given."""
    c = consents or {}
    missing: list[str] = []
    if not c.get("terms_version") or c.get("terms_version") != cfg.terms_version:
        missing.append(ConsentKind.TERMS.value)
    if not c.get("privacy_version") or c.get("privacy_version") != cfg.privacy_version:
        missing.append(ConsentKind.PRIVACY.value)
    if needs_waiver and not c.get("immediate_delivery_waiver"):
        missing.append(ConsentKind.IMMEDIATE_DELIVERY_WAIVER.value)
    if missing:
        raise CommerceError(
            ACEITE_OBRIGATORIO,
            "É necessário aceitar os termos e a política de privacidade"
            + (" e a renúncia ao arrependimento para produtos digitais" if "immediate_delivery_waiver" in missing else "")
            + ".",
            422,
            details={"missing": missing, "terms_version": cfg.terms_version, "privacy_version": cfg.privacy_version},
        )


def validate_buyer(buyer: Mapping[str, Any]) -> dict:
    name = (buyer.get("name") or "").strip()
    if not 2 <= len(name) <= 120:
        raise invalid("buyer.name", "Informe seu nome completo.")
    email = (buyer.get("email") or "").strip().lower()
    if not valid_email(email):
        raise invalid("buyer.email", "Informe um e-mail válido.")
    doc = digits(buyer.get("doc"))
    if not ((len(doc) == 11 and cpf_dv_valido(doc)) or (len(doc) == 14 and cnpj_dv_valido(doc))):
        raise invalid("buyer.doc", "Informe um CPF ou CNPJ válido.", code="documento_invalido")
    phone = digits(buyer.get("phone"))
    if phone and not 10 <= len(phone) <= 13:
        raise invalid("buyer.phone", "Informe um telefone válido com DDD.")
    return {"name": name, "email": email, "doc": doc, "phone": phone or None}


def _split_for(db: Any, org_id: Any, gateway: CheckoutGateway, total_cents: int) -> tuple[Optional[str], Optional[float], int]:
    """`(wallet_id, percent, expected_fee_cents)`; `(None, None, 0)` when no split applies."""
    profile = get_profile(db, org_id) or {}
    bps = int(profile.get("platform_fee_bps") or 0)
    if bps <= 0:
        return None, None, 0
    wallet = gateway.platform_wallet_id()
    if not wallet:
        key = str(org_id)
        if key not in _NO_WALLET_LOGGED:
            _NO_WALLET_LOGGED.add(key)
            logger.info("commerce: platform_fee_bps=%s but no platform wallet configured; charging WITHOUT split (org=%s)", bps, org_id)
        return None, None, 0
    return wallet, bps / 100, (total_cents * bps) // 10000


def _public_pix(pix: Optional[PixQr]) -> Optional[dict]:
    if pix is None:
        return None
    return {"payload": pix.payload, "encoded_image": pix.encoded_image, "expires_at": pix.expiration_date}


def create_checkout(
    db: Any,
    org_id: Any,
    cfg: CommerceConfig,
    gateway: CheckoutGateway,
    body: Mapping[str, Any],
    *,
    order_url_for: Callable[[str], str],
    ip: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> dict:
    """Run a checkout; returns `{order_token, status, checkout_url, pix_qr, expires_at}`.

    `order_url_for(token)` returns the absolute storefront URL of the public order
    page (the gateway's success/cancel redirect); the token only exists once the
    order does, hence a function and not a string.
    """
    if get_profile(db, org_id) is None:
        raise CommerceError("loja_nao_configurada", "A loja ainda não está configurada.", 409)

    quote = build_quote(db, org_id, list(body["items"]), body.get("coupon"))
    validate_consents(cfg, body.get("consents"), quote.requires_immediate_delivery_waiver)
    buyer = validate_buyer(body["buyer"])
    if quote.coupon_error:
        raise CommerceError(
            "cupom_invalido", "O cupom informado não pode ser aplicado.", 422, details={"reason": quote.coupon_error}
        )
    if quote.total_cents <= 0:
        raise CommerceError("total_zero", "O total do pedido deve ser maior que zero.", 422)

    method = PaymentMethod(body["payment_method"]).value
    # Resolved BEFORE any write: an unconfigured gateway must not leave an orphan order.
    try:
        hosted = gateway.hosted_checkout(org_id)
    except GatewayNotConfigured as exc:
        logger.error("commerce checkout: gateway not configured (org=%s): %s", org_id, exc)
        raise CommerceError("pagamento_indisponivel", "O pagamento não está disponível nesta loja agora.", 503) from exc

    coupon = quote.coupon
    if coupon is not None and not coupons_svc.reserve_use(db, org_id, coupon):
        raise CommerceError("cupom_invalido", "O cupom informado não pode ser aplicado.", 422, details={"reason": coupons_svc.ESGOTADO})

    try:
        wallet, percent, fee_cents = _split_for(db, org_id, gateway, quote.total_cents)
        at = now()
        order_id, token = new_id(), new_token()
        customer = upsert_buyer(db, org_id, {**buyer, "address": body.get("address") or {}})
        order_row = {
            "id": order_id,
            "org_id": str(org_id),
            "token": token,
            "customer_id": str(customer["id"]),
            "status": OrderStatus.CREATED.value,
            "subtotal_cents": quote.subtotal_cents,
            "discount_cents": quote.discount_cents,
            "total_cents": quote.total_cents,
            "currency": quote.currency,
            "coupon_id": str(coupon["id"]) if coupon else None,
            "payment_method": method,
            "gateway": GATEWAY_NAME,
            "gateway_charge_id": None,
            "checkout_url": None,
            "pix_qr": None,
            "expires_at": (at + timedelta(hours=cfg.order_expiry_hours)).isoformat(),
            "paid_at": None,
            "platform_fee_cents": fee_cents,
            "created_at": at.isoformat(),
            "updated_at": at.isoformat(),
        }
        order = first(tbl(db, _ORDERS).insert(order_row).execute()) or order_row
        tbl(db, _ITEMS).insert(
            [
                {
                    "id": new_id(),
                    "org_id": str(org_id),
                    "order_id": order_id,
                    "product_id": str(src["product"]["id"]),
                    "offer_id": str(src["offer"]["id"]),
                    "title_snapshot": f"{line['title']} — {src['offer']['name']}"[:300],
                    "product_type": src["product"]["product_type"],
                    "fulfillment_type": src["product"]["fulfillment_type"],
                    "unit_price_cents": line["unit_price_cents"],
                    "qty": line["qty"],
                    "total_cents": line["total_cents"],
                }
                for line, src in zip(quote.lines, quote.sources)
            ]
        ).execute()
        append_event(
            db, org_id, order_id, from_status=None, to_status=OrderStatus.CREATED.value,
            source=OrderEventSource.CHECKOUT, reason="pedido criado",
        )
        c = body["consents"]
        entries = [
            (ConsentKind.TERMS, c["terms_version"], True),
            (ConsentKind.PRIVACY, c["privacy_version"], True),
            (ConsentKind.MARKETING, c["privacy_version"], bool(c.get("marketing"))),
        ]
        if quote.requires_immediate_delivery_waiver:
            entries.append((ConsentKind.IMMEDIATE_DELIVERY_WAIVER, c["terms_version"], True))
        record_consents(db, org_id, customer["id"], order_id=order_id, entries=entries, ip=ip, user_agent=user_agent)

        try:
            session = hosted.create_checkout(
                CheckoutRequest(
                    external_reference=order_id,
                    email=buyer["email"],
                    name=buyer["name"],
                    price=Money(quote.total_cents, quote.currency),
                    billing_cycle=None,
                    billing_method=_BILLING_METHOD[method],
                    tax_id=buyer["doc"],
                    description=f"Pedido {order_id[:8]}",
                    success_url=order_url_for(token),
                    cancel_url=order_url_for(token),
                    metadata={"order_id": order_id},
                    due_days=max(1, math.ceil(cfg.order_expiry_hours / 24)),
                    split_wallet_id=wallet,
                    split_percent=percent,
                )
            )
        except PaymentGatewayError as exc:
            logger.error(
                "commerce checkout: gateway refused order=%s status=%s code=%s retryable=%s message=%s",
                order_id, exc.status, exc.code, exc.retryable, exc.message,
            )
            apply_transition(
                db, org_id, order, OrderEvent.CHARGE_FAILED, source=OrderEventSource.CHECKOUT,
                reason=f"gateway: {exc.code or exc.status}",
            )
            if coupon is not None:
                coupons_svc.release_use(db, org_id, coupon)
            raise CommerceError(
                "pagamento_falhou", "Não foi possível iniciar o pagamento agora. Tente novamente em instantes.", 502
            ) from exc

        pix = _public_pix(session.pix_qr)
        order = apply_transition(
            db, org_id, order, OrderEvent.CHARGE_CREATED, source=OrderEventSource.CHECKOUT,
            reason="cobrança criada",
            extra={"gateway_charge_id": session.id_at_gateway, "checkout_url": session.checkout_url, "pix_qr": pix},
        )
    except CommerceError:
        raise
    except Exception:
        # Anything unexpected before the charge exists: give the coupon back, surface loudly.
        if coupon is not None:
            coupons_svc.release_use(db, org_id, coupon)
        raise
    return {
        "order_token": token,
        "status": order["status"],
        "checkout_url": session.checkout_url,
        "pix_qr": pix,
        "expires_at": order_row["expires_at"],
    }


__all__ = [
    "MAX_SUBTOTAL_CENTS",
    "Quote",
    "build_quote",
    "create_checkout",
    "validate_buyer",
    "validate_consents",
]
