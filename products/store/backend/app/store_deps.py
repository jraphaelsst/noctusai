"""FastAPI dependency providers for the store's services (the DI seam).

Every external collaborator — the stores (DB), hosted checkout (Asaas), the
event inbox, the email sender, the blob storage — is resolved HERE, per
request, from `settings`. Tests swap any of them with
`app.dependency_overrides[...]` (FastAPI's own seam) for the Fakes; nothing
in the product is monkey-patched.

Fake-or-refuse (`noctusai_lib.integrations.fake_or_refuse`): an unconfigured
Real adapter never silently becomes a Fake — only an explicit
`PAYMENTS_ALLOW_FAKE=true` (test harness / local dev) does.
"""
from __future__ import annotations

import logging
from typing import Any, Callable

from fastapi import Depends

from noctusai_lib.domain.payments import EventInbox, make_event_inbox
from noctusai_lib.integrations.email import EmailNotConfigured, OutgoingEmail, SentEmail, SmtpConfig, make_email_sender
from noctusai_lib.integrations.email.types import EmailSender
from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.integrations.payments.checkout import HostedCheckout, make_hosted_checkout
from noctusai_lib.integrations.storage import make_storage_backend
from noctusai_lib.integrations.storage.fake import FakeStorageBackend
from noctusai_lib.integrations.storage.protocol import StorageBackend

from app.api_keys import key_provider
from app.config import settings
from app.dependencies import get_admin_client
from app.services.assets import AssetService
from app.services.checkout_service import CheckoutError, CheckoutService
from app.services.delivery_service import DeliveryService
from app.services.settings_service import DEFAULT_SETTINGS, SettingsService
from app.services.webhook_service import WebhookService
from app.stores import PedidoStore, SettingsStore, SupabasePedidoStore, SupabaseSettingsStore

logger = logging.getLogger(__name__)

_INBOX_TABLE = "webhook_eventos"
_SCHEMA = "store"

# ── stores ─────────────────────────────────────────────────────────────────


def get_settings_store() -> SettingsStore:
    return SupabaseSettingsStore(get_admin_client)


def get_pedido_store() -> PedidoStore:
    return SupabasePedidoStore(get_admin_client)


# ── storage ────────────────────────────────────────────────────────────────

_storage_cache: dict[int, StorageBackend] = {}


def get_storage() -> StorageBackend:
    admin = get_admin_client()
    cached = _storage_cache.get(id(admin))
    if cached is not None:
        return cached
    if not hasattr(admin, "storage"):  # defensive: a client without Storage
        backend: StorageBackend = FakeStorageBackend()
    else:
        backend = make_storage_backend(kind="supabase", client=admin)
    _storage_cache.clear()
    _storage_cache[id(admin)] = backend
    return backend


def get_assets(storage: StorageBackend = Depends(get_storage)) -> AssetService:
    return AssetService(storage)


# ── hosted checkout (Asaas one-off) ────────────────────────────────────────


def _refuse_checkout() -> HostedCheckout:
    logger.error("checkout: asaas_api_key not configured — charge refused")
    raise CheckoutError(
        "Pagamentos indisponíveis no momento. Tente novamente mais tarde.",
        status_code=503,
        code="payments_unavailable",
    )


def build_hosted_checkout() -> HostedCheckout:
    # DB-stored key (owner directive): local store -> platform chain -> env.
    key = key_provider.resolve("asaas_api_key")
    return resolve_fake_or_refuse(
        configured=bool(key),
        build_real=lambda: make_hosted_checkout(
            provider="asaas", asaas_api_key=key, asaas_base_url=key_provider.asaas_base_url()
        ),
        build_fake=lambda: make_hosted_checkout(use_fake=True),
        allow_fake=settings.payments_allow_fake,
        unconfigured=_refuse_checkout,
    )


def get_checkout_factory() -> Callable[[], HostedCheckout]:
    """The callable the service invokes to obtain the `HostedCheckout`
    (resolved lazily, after the checkout-enabled gate, so a 503 never
    precedes a 409 and never leaves an orphan pedido)."""
    return build_hosted_checkout


# ── event inbox (webhook idempotency) ──────────────────────────────────────


def get_event_inbox() -> EventInbox:
    return make_event_inbox(supabase_client=get_admin_client(), schema_name=_SCHEMA, table_name=_INBOX_TABLE)


# ── email ──────────────────────────────────────────────────────────────────


class UnconfiguredEmailSender:
    """The DECLARED not-configured state: `send` raises, so the failure is
    recorded on the pedido instead of a Fake pretending the mail left."""

    async def send(self, email: OutgoingEmail) -> SentEmail:
        raise EmailNotConfigured("SMTP não configurado (SMTP_HOST/PORT/USERNAME/PASSWORD).")


_SMTP_KEYS = (
    "smtp_host", "smtp_port", "smtp_username", "smtp_password", "smtp_security", "email_from", "email_from_name",
)


def _smtp_credentials() -> dict[str, str]:
    """SMTP is PLATFORM config, not a store key: the seed email sender's own
    names (`digest._resolve_smtp_config`) resolve through the platform chain
    (org_settings -> platform_settings -> env), scoped to the owner org."""
    org = key_provider.org_id()
    return {name: key_provider.platform_resolve(name, org) or "" for name in _SMTP_KEYS}


def _sender_name(settings_store: SettingsStore) -> str:
    """The buyer sees the PRODUCT as the sender ("Contrato Blindado de Compra
    e Venda <noreply@…>"), not the platform's default name: the transport and
    address stay platform config, the display name is the store's own setting
    (the same `product_name` the landing page shows). Empty when the ledger
    has no product name, so the platform default applies."""
    row = settings_store.current()
    data = row["data"] if row else DEFAULT_SETTINGS
    return str(data.get("product_name") or "").strip()


def get_email_sender(settings_store: SettingsStore = Depends(get_settings_store)) -> EmailSender:
    creds = _smtp_credentials()
    creds["email_from_name"] = _sender_name(settings_store) or creds["email_from_name"]
    configured = bool(creds["smtp_host"] and creds["smtp_username"] and creds["smtp_password"])
    return resolve_fake_or_refuse(
        configured=configured,
        build_real=lambda: make_email_sender(SmtpConfig.from_credentials(creds)),
        build_fake=lambda: make_email_sender(None),
        allow_fake=settings.payments_allow_fake,
        unconfigured=UnconfiguredEmailSender,
    )


# ── services ───────────────────────────────────────────────────────────────


def get_settings_service(
    store: SettingsStore = Depends(get_settings_store),
    assets: AssetService = Depends(get_assets),
) -> SettingsService:
    return SettingsService(store, assets)


def get_checkout_service(
    settings_service: SettingsService = Depends(get_settings_service),
    pedidos: PedidoStore = Depends(get_pedido_store),
    factory: Callable[[], HostedCheckout] = Depends(get_checkout_factory),
) -> CheckoutService:
    return CheckoutService(
        settings_service=settings_service,
        pedidos=pedidos,
        checkout_factory=factory,
        public_url=settings.store_public_url,
    )


def get_delivery_service(
    pedidos: PedidoStore = Depends(get_pedido_store),
    sender: EmailSender = Depends(get_email_sender),
    assets: AssetService = Depends(get_assets),
) -> DeliveryService:
    return DeliveryService(
        pedidos=pedidos, email_sender=sender, assets=assets, public_url=settings.store_public_url
    )


def get_webhook_service(
    pedidos: PedidoStore = Depends(get_pedido_store),
    inbox: EventInbox = Depends(get_event_inbox),
    delivery: DeliveryService = Depends(get_delivery_service),
) -> WebhookService:
    return WebhookService(pedidos=pedidos, inbox=inbox, delivery=delivery)


def get_asaas_webhook_token() -> str:
    """Per-request secret resolver (webhook pin 2): DB-stored token, read at request time."""
    return key_provider.resolve("asaas_webhook_token") or ""
