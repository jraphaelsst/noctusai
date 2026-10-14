"""FastAPI dependency providers for the commerce organ (the DI seam).

Every collaborator -- DB, storage, gateway, e-mail, licence checker, event inbox,
CNPJ lookup, link secret -- is resolved HERE, per request, from `settings`. Tests
swap any of them with `app.dependency_overrides[...]`; nothing is monkey-patched.

Fake-or-refuse (`noctusai_lib.integrations.fake_or_refuse`): an unconfigured Real
adapter never silently becomes a Fake -- only an explicit `PAYMENTS_ALLOW_FAKE=true`
(test harness / local dev) does. The Asaas gateway already refuses without a key
(`GatewayNotConfigured`); this module applies the same rule to e-mail and the link secret.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from fastapi import Depends, HTTPException, Request
from noctusai_lib.api.auth.effective_org import acting_header_of, is_platform_staff
from noctusai_lib.api.auth.session.scopes import require_org_admin_role
from noctusai_lib.domain.commerce import (
    CommerceContext,
    FulfillmentType,
    MoneyDeps,
    make_checkout_gateway,
    make_fulfillment_registry,
)
from noctusai_lib.domain.commerce.quote_handlers import CommerceQuoteAcceptHandler
from noctusai_lib.domain.commerce.stock_fulfillment import StockFulfillment
from noctusai_lib.domain.contracts.quote_handler import ContractQuoteAcceptHandler
from noctusai_lib.domain.inventory import make_stock_port
from noctusai_lib.domain.inventory.port import StockPort
from noctusai_lib.domain.quotes import QuoteAcceptHandler, RoutingQuoteAcceptHandler
from noctusai_lib.domain.commerce import invoices as invoices_svc
from noctusai_lib.domain.commerce.errors import GatewayNotConfigured
from noctusai_lib.domain.commerce.fulfillment import FulfillmentRegistry
from noctusai_lib.domain.commerce.gateway import CheckoutGateway
from noctusai_lib.domain.commerce.profile import get_profile
from noctusai_lib.domain.finance import FinanceContext
from noctusai_lib.domain.finance.booking import FinanceBooking, make_finance_booking
from noctusai_lib.domain.jobs import JobRepository, make_job_repository
from noctusai_lib.integrations.invoices import InvoiceProvider, make_invoice_provider
from noctusai_lib.integrations.invoices.credentials import CompanyTokenStore
from noctusai_lib.integrations.invoices.factory import resolve_invoice_environment
from noctusai_lib.integrations.payments.charges import ChargeOperations
from noctusai_lib.primitives.exceptions import ForbiddenError
from noctusai_lib.domain.licensing import LicenseChecker, make_license_checker
from noctusai_lib.domain.payments import EventInbox, make_event_inbox
from noctusai_lib.integrations.cnpj_registry import make_cnpj_registry_lookup
from noctusai_lib.integrations.cnpj_registry.types import CnpjRegistryLookup
from noctusai_lib.integrations.email import EmailNotConfigured, OutgoingEmail, SentEmail, SmtpConfig, make_email_sender
from noctusai_lib.integrations.email.types import EmailSender
from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.integrations.storage import make_storage_backend
from noctusai_lib.integrations.storage.fake import FakeStorageBackend
from noctusai_lib.integrations.storage.protocol import StorageBackend

from app.api_keys import build_store
from app.commerce import CFG, CONTRACTS_CFG, FINANCE_CFG, INVENTORY_CFG, SCHEMA
from app.config import settings
from app.database import _db
from app.dependencies import get_admin_client, get_current_user_org

logger = logging.getLogger(__name__)

_INBOX_TABLE = "payment_gateway_events"


def platform_resolve(name: str, org_id: Any) -> Any:
    from noctusai_lib.config.credentials import resolve_credential

    return resolve_credential(name, org_id)


# ── DB / storage ───────────────────────────────────────────────────────────


def get_db() -> Any:
    """The schema-pinned admin client. The organ filters `org_id` on every query
    explicitly; the caller's org comes from the trusted `get_current_user_org`."""
    return get_admin_client()


_storage_cache: dict[int, StorageBackend] = {}


def get_storage() -> StorageBackend:
    admin = get_admin_client()
    cached = _storage_cache.get(id(admin))
    if cached is not None:
        return cached
    backend: StorageBackend = (
        make_storage_backend(kind="supabase", client=admin) if hasattr(admin, "storage") else FakeStorageBackend()
    )
    _storage_cache.clear()
    _storage_cache[id(admin)] = backend
    return backend


# ── staff context ──────────────────────────────────────────────────────────


def resolve_context(auth: Any, db: Any) -> CommerceContext:
    """`get_current_user_org` yields `(user, token, org_id)`."""
    user, _token, org_id = auth
    return CommerceContext(db=db, org_id=str(org_id), user_id=str(getattr(user, "id", "") or ""))


def is_platform_admin(auth: Any) -> bool:
    """Decided SERVER-SIDE from the trusted `noctus_users` row; fails CLOSED."""
    user = auth[0]
    try:
        return bool(is_platform_staff(_db.get_core_client(), getattr(user, "id", None)))
    except Exception:  # noqa: BLE001 -- fail closed on any lookup failure, logged
        logger.warning("commerce: platform-staff lookup failed -- treating as non-admin", exc_info=True)
        return False


# ── cnpj / licence ─────────────────────────────────────────────────────────


def get_cnpj_lookup() -> CnpjRegistryLookup:
    # Public keyless registries (BrasilAPI / ReceitaWS): Real unless the harness opted into fakes.
    return make_cnpj_registry_lookup(real=not settings.payments_allow_fake)


def get_license_checker() -> LicenseChecker:
    return make_license_checker(lambda: _db.get_core_client())


# ── gateway / inbox ────────────────────────────────────────────────────────


def get_gateway() -> CheckoutGateway:
    return make_checkout_gateway(
        CFG,
        use_fake=settings.payments_allow_fake,
        store_factory=build_store,
        resolver=platform_resolve,
    )


def get_event_inbox() -> EventInbox:
    return make_event_inbox(supabase_client=get_admin_client(), schema_name=SCHEMA, table_name=_INBOX_TABLE)


# ── link secret ────────────────────────────────────────────────────────────


def get_link_secret() -> str:
    secret = settings.commerce_link_secret
    if not secret:
        logger.error("commerce: COMMERCE_LINK_SECRET not configured -- access links refused")
        raise HTTPException(status_code=503, detail="Links de acesso indisponíveis no momento.")
    return secret


# ── email ──────────────────────────────────────────────────────────────────


class UnconfiguredEmailSender:
    """The DECLARED not-configured state: `send` raises, so the failure is surfaced
    instead of a Fake pretending the mail left."""

    async def send(self, email: OutgoingEmail) -> SentEmail:
        raise EmailNotConfigured("SMTP não configurado (SMTP_HOST/PORT/USERNAME/PASSWORD).")


_SMTP_KEYS = ("smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_security", "email_from", "email_from_name")


def get_email_sender() -> EmailSender:
    """SMTP is PLATFORM config (org_settings -> platform_settings -> env), not a store key."""
    creds = {name: platform_resolve(name, None) or "" for name in _SMTP_KEYS}
    configured = bool(creds["smtp_host"] and creds["smtp_username"] and creds["smtp_password"])
    return resolve_fake_or_refuse(
        configured=configured,
        build_real=lambda: make_email_sender(SmtpConfig.from_credentials(creds)),
        build_fake=lambda: make_email_sender(None),
        allow_fake=settings.payments_allow_fake,
        unconfigured=UnconfiguredEmailSender,
    )


# ── org-admin gate / platform-admin gate ───────────────────────────────────


async def require_org_admin(request: Request, auth: Any = Depends(get_current_user_org)) -> Any:
    """ORG-admin gate for money-moving / fiscal writes (CONTRACT §0). The role is read from the
    TRUSTED `noctus_users` row (core client) IN the request's SELECTED org (B3), never `user_metadata`
    nor the home-org role; plain staff get 403."""
    require_org_admin_role(
        _db.get_core_client(), getattr(auth[0], "id", None), "Comércio",
        org_id=auth[2], token=auth[1], acting_header=acting_header_of(request),
    )
    return auth


def require_platform_admin(auth: Any = Depends(get_current_user_org)) -> None:
    """Widens WHO may write fiscal settings to platform staff acting on another org (server-side check)."""
    if not is_platform_admin(auth):
        raise ForbiddenError("Apenas a administração da plataforma pode fazer isso.")


# ── fulfillment / finance ──────────────────────────────────────────────────

def get_stock_port() -> StockPort:
    """The inventory organ's `StockPort` over the admin client (row-locked RPCs, scoped per call to the order's org)."""
    return make_stock_port("supabase", db=get_admin_client(), cfg=INVENTORY_CFG)


# Physical orders hold, ship and give back STOCK (roadmap E6): created -> reserve, paid -> commit, expired/cancelled/
# revoked -> release. Only lines whose product carries an `item_id` take part; digital fulfillment stays a Noop.
_stock_fulfillment = StockFulfillment(get_stock=get_stock_port, get_db=get_admin_client)
_fulfillment = make_fulfillment_registry(
    {
        FulfillmentType.SHIPPING: _stock_fulfillment,
        FulfillmentType.PICKUP: _stock_fulfillment,
        FulfillmentType.LOCAL_DELIVERY: _stock_fulfillment,
    }
)


def get_fulfillment() -> FulfillmentRegistry:
    return _fulfillment


# ── quotes: accept handler, issuer, public link ────────────────────────────


def get_quote_accept_handler() -> QuoteAcceptHandler:
    """Convert-on-accept: goods -> a commerce order (manual channel, stock held), services -> a draft contract.
    Both are idempotent on the quote id; the deps are resolved per conversion, never captured."""
    return RoutingQuoteAcceptHandler(
        {
            "order": CommerceQuoteAcceptHandler(get_db=get_admin_client, get_fulfillment=get_fulfillment),
            "contract": ContractQuoteAcceptHandler(get_db=get_admin_client, cfg=CONTRACTS_CFG),
        }
    )


def quote_accept_url(token: str) -> str:
    """The public accept page the e-mailed link points at (a `publicRoutes` entry of the SPA, outside the authed shell)."""
    return f"{settings.commerce_public_url.rstrip('/')}/orcamento/{token}"


def quote_issuer(org_id: str) -> dict:
    """The seller identity printed on quote PDFs / e-mails: the store profile's trade name."""
    profile = get_profile(get_admin_client(), org_id) or {}
    return {"name": profile.get("trade_name") or profile.get("legal_name") or "Loja"}


def quote_client_ip(request: Request) -> Optional[str]:
    """The address recorded on a customer's decision. Cloudflare overwrites this header on every proxied request."""
    forwarded = request.headers.get("cf-connecting-ip", "").strip()
    return forwarded or (request.client.host if request.client else None)


def quote_org_is_active(db: Any, org_id: str) -> bool:
    """A lapsed licence refuses the quote link with the same 404 as a bad token; a failed lookup fails CLOSED."""
    try:
        return bool(get_license_checker().has_license(org_id, CFG.license_product_slug))
    except Exception:  # noqa: BLE001 -- fail closed, logged
        logger.warning("commerce: licence lookup failed for a quote link -- refusing", exc_info=True)
        return False


def get_finance() -> FinanceBooking:
    """Books receivables / settlements / fees into the finance organ (same schema, `fin_*`)."""
    return make_finance_booking("supabase", db=get_admin_client(), cfg=FINANCE_CFG)


def get_charge_operations(auth: Any = Depends(get_current_user_org)) -> ChargeOperations:
    """The CALLER'S org's gateway `ChargeOperations` (finance statement sync). An org with no usable
    gateway credentials answers 503 -- the declared not-configured state, reads still work."""
    try:
        return get_gateway().charge_operations(auth[2])
    except GatewayNotConfigured:
        raise HTTPException(status_code=503, detail="Gateway de cobrança não configurado.") from None


def charge_operations_for(org_id: str, gateway: str) -> Optional[ChargeOperations]:
    """Scheduler-side lookup for `finance_gateway_sync`: `None` skips an org without credentials."""
    try:
        return get_gateway().charge_operations(org_id)
    except GatewayNotConfigured:
        logger.info("finance gateway sync: org %s has no usable gateway credentials; skipped", org_id)
        return None


_TAX_REGIME_TO_FINANCE = {"mei": "mei", "simples": "simples", "lucro_presumido": "presumido"}


def default_tax_regime(ctx: FinanceContext) -> Optional[str]:
    """Finance DRE prefill (CONTRACT §10.5.1): the commerce store profile's tax regime, mapped to the
    finance enum. `lucro_real` / `outro` / no profile => `None` (the DRE then reports `regime_nao_informado`)."""
    profile = get_profile(ctx.db, ctx.org_id)
    return _TAX_REGIME_TO_FINANCE.get(str((profile or {}).get("tax_regime") or ""))


# ── invoices (fiscal) ──────────────────────────────────────────────────────


def get_jobs() -> JobRepository:
    return make_job_repository(supabase_client=get_admin_client(), schema_name=SCHEMA)


def make_provider(org_id: str) -> InvoiceProvider:
    """ONE provider per org/call (the per-company token sink is org-bound). Fake-or-refuse: a missing
    `focusnfe_token` REFUSES unless `INVOICES_ALLOW_FAKE`. Company tokens live Fernet-encrypted in
    `commerce.credentials`; the store is built lazily so the Fake path needs no `ENCRYPTION_KEY`."""
    tokens: dict[str, CompanyTokenStore] = {}

    def store() -> CompanyTokenStore:
        if "s" not in tokens:
            tokens["s"] = CompanyTokenStore(build_store(), environment=resolve_invoice_environment())
        return tokens["s"]

    return make_invoice_provider(
        "focusnfe",
        allow_fake=settings.invoices_allow_fake,
        company_tokens=lambda ref: store().resolver_for(org_id)(ref),
        token_sink=lambda ref, cnpj, token: store().sink_for(org_id)(ref, cnpj, token),
    )


def get_webhook_token(org_id: str) -> Optional[str]:
    """Per-org invoice-webhook secret, resolved per request (org -> platform -> env); fail-closed when unset."""
    return platform_resolve("invoice_webhook_token", org_id) or None


_REVOKE_TEXT = {
    "refunded": "Pedido {id} reembolsado integralmente",
    "chargeback": "Pedido {id} com contestação de pagamento perdida (chargeback)",
}


async def invoices_on_paid(db: Any, order: Any) -> None:
    """`MoneyDeps.on_paid_hooks`: enqueue the invoices when the store opted into `auto_issue_invoices`."""
    await invoices_svc.on_order_paid(db, order, jobs=get_jobs())


async def invoices_on_revoked(db: Any, order: Any, reason: Optional[str] = None) -> None:
    """`MoneyDeps.on_revoked_hooks`: full refund / lost chargeback => cancel every authorized invoice."""
    text = _REVOKE_TEXT.get(str(reason), "Pedido {id} estornado integralmente").format(id=order["id"])
    await invoices_svc.on_order_revoked(db, order, jobs=get_jobs(), reason=text)


ON_PAID_HOOKS = (invoices_on_paid,)
ON_REVOKED_HOOKS = (invoices_on_revoked,)


def get_money_deps() -> MoneyDeps:
    """The same collaborator set the routers build, for the scheduler (per tick; never captured)."""
    return MoneyDeps(
        cfg=CFG, gateway=get_gateway(), fulfillment=get_fulfillment(), finance=get_finance(),
        email=get_email_sender(), on_paid_hooks=ON_PAID_HOOKS, on_revoked_hooks=ON_REVOKED_HOOKS,
    )
