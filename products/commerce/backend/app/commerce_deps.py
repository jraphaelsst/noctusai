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
from typing import Any

from fastapi import HTTPException
from noctusai_lib.api.auth.effective_org import is_platform_staff
from noctusai_lib.domain.commerce import CommerceContext, make_checkout_gateway
from noctusai_lib.domain.commerce.gateway import CheckoutGateway
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
from app.commerce import CFG, SCHEMA
from app.config import settings
from app.database import _db
from app.dependencies import get_admin_client

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
