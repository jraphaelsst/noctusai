"""
Real WhatsApp send for the Orbity automation engine.

Resolution -- the org's OWN line or nothing:
  1. the org's NEWEST saved connection in `orbity.whatsapp_connections`
     (base_url + decrypted api_key + session_name — saved via
     `Configurações → Conexões WhatsApp`);
  2. else REFUSE — `WhatsAppNotConnected`. There is NO fallback to the static
     fleet `WAHA_*` line (a host shared across tenants: a message must leave
     from the number the org itself connected). The seed `FakeWahaClient` is
     used ONLY under `settings.whatsapp_allow_fake` (test harness / local
     dev): a Fake in a real deploy reports "sent" with nothing sent.
  In prod WhatsApp is also OFF at the seed's line policy (no declared policy
  => every write refused; NOC-REMEDIATE[orbity-waha-own-instance]).

`send` is SYNC (`WahaClient.send_text_to_phone_sync`): the engine drain is sync code
that the scheduler runs via `anyio.to_thread.run_sync` (igig pattern), so it
never blocks the event loop and needs no loop of its own.

Messages go out whole (one bubble). Multi-bubble splitting is deliberately
not applied: `send_reply_parts_sync(text, send_one, *, split, delay_seconds)`
is a chatbot-conversation affordance; an authored automation template is one
message by design.
"""
from __future__ import annotations

import logging
from typing import Any

from noctusai_lib.integrations.fake_or_refuse import resolve_fake_or_refuse
from noctusai_lib.integrations.whatsapp import (
    build_whatsapp_connection_store,
    WahaNumberNotOnWhatsApp,
    get_whatsapp_client,
)
from noctusai_lib.primitives.phone import phone_digits
from noctusai_lib.security.api_keys import EncryptionNotConfigured

from app.services.automation_errors import AutomationUserError

logger = logging.getLogger(__name__)

NAO_CONECTADO_DETAIL = (
    "WhatsApp não conectado. Conecte um número em Configurações → Conexões WhatsApp."
)


class WhatsAppNotConnected(AutomationUserError):
    """No WAHA connection resolves for the org (pt-BR message, shown to the user)."""

    def __init__(self, detail: str = NAO_CONECTADO_DETAIL) -> None:
        super().__init__(detail)


class WhatsAppSendError(AutomationUserError):
    """The send was attempted and failed (pt-BR message, shown to the user)."""


def chat_id_for(phone: str | None) -> str | None:
    """`<digits>@c.us`, or None when `phone` is not a real number."""
    digits = phone_digits(phone)
    return f"{digits}@c.us" if digits else None


def resolve_org_waha_client(
    *,
    org_id: Any,
    admin_client: Any,
    settings: Any,
    allow_fake: bool | None = None,
):
    """The org's OWN WAHA client. No saved connection => :class:`WhatsAppNotConnected` (loud, pt-BR), never a fallback.

    Deliberately there is NO static fleet ``WAHA_*`` line: that host is shared across tenants, so a message must go out
    through the number the org itself connected (security review F1, 2026-11-10). The only other source is the fake,
    and only under an explicit ``whatsapp_allow_fake`` (tests / local dev).
    """
    fake_ok = settings.whatsapp_allow_fake if allow_fake is None else allow_fake

    record = None
    try:
        store = build_whatsapp_connection_store(
            admin_client, encryption_key=settings.encryption_key, schema="orbity",
        )
        connections = store.list_connections(org_id=org_id)
        if connections:
            record = store.get_connection(
                connection_id=connections[0].id, org_id=org_id, decrypt=True
            )
    except EncryptionNotConfigured:
        logger.warning(
            "orbity whatsapp: ENCRYPTION_KEY ausente — conexões salvas ignoradas (org=%s)",
            org_id,
        )

    base_url = api_key = session = None
    if record is not None:
        base_url, api_key, session = record.base_url, record.api_key, record.session_name

    def _client(url: str | None):
        return get_whatsapp_client(
            base_url=url,
            api_key=api_key,
            session=session,
            external_base_url=settings.waha_external_base_url or None,
        )

    return resolve_fake_or_refuse(
        configured=bool(base_url),
        build_real=lambda: _client(base_url),
        build_fake=lambda: _client(None),
        allow_fake=bool(fake_ok),
        unconfigured=_not_connected,
    )


def _not_connected():
    raise WhatsAppNotConnected()


class RealWhatsAppSender:
    """`WhatsAppSender` over the org's real WAHA line. Stateless per call.

    Args:
        get_admin_client: zero-arg callable returning the service-role client
            (late-bound so tests/DI hand in a mock — no module singleton).
        settings: the product settings (encryption key; the optional fake-allow
            switch). The static fleet ``WAHA_*`` line is never used.
        resolve_client: DI seam for the org -> WAHA client resolution (tests
            inject a `FakeWahaClient` to assert `sent_messages`).
    """

    def __init__(
        self,
        get_admin_client: Any,
        settings: Any,
        *,
        resolve_client: Any = None,
    ) -> None:
        self._get_admin_client = get_admin_client  # org-scope-ok: WhatsApp connection store (not a tenant table)
        self._settings = settings
        self._resolve_client = resolve_client or resolve_org_waha_client

    def send(self, phone: str, message: str, org_id: str) -> None:
        chat_id = chat_id_for(phone)
        if chat_id is None:
            raise WhatsAppSendError("Telefone do contato inválido para WhatsApp.")
        client = self._resolve_client(
            org_id=org_id, admin_client=self._get_admin_client(), settings=self._settings,
        )
        if client is None:
            raise WhatsAppNotConnected()
        try:
            # Resolves the BR 9th-digit variant before sending. The resolved
            # number is deliberately NOT persisted over the contact's phone.
            client.send_text_to_phone_sync(phone, message)
        except WahaNumberNotOnWhatsApp as exc:
            logger.warning("orbity whatsapp: número fora do WhatsApp org=%s tried=%s", org_id, exc.tried)
            raise WhatsAppSendError(
                "Este número não está no WhatsApp (tentamos com e sem o 9º dígito)."
            ) from exc
        except Exception as exc:  # noqa: BLE001 — mapped to a user-facing pt-BR failure
            logger.exception("orbity whatsapp: envio falhou org=%s chat=%s", org_id, chat_id)
            raise WhatsAppSendError(f"Falha ao enviar pelo WhatsApp: {_reason(exc)}") from exc


def _reason(exc: Exception) -> str:
    """Short, secret-free reason: HTTP status when there is one, else the type."""
    response = getattr(exc, "response", None)
    status = getattr(response, "status_code", None)
    if status:
        return f"o servidor WhatsApp respondeu HTTP {status}"
    return type(exc).__name__


def make_default_sender() -> RealWhatsAppSender:
    """The app-default sender (REAL). Fake only via explicit injection in tests."""
    from app.config import settings
    from app.dependencies import get_admin_client

    return RealWhatsAppSender(get_admin_client, settings)  # org-scope-ok: WhatsApp connection store (not a tenant table)
