"""Outbound channel for reminders: Protocol + Fake + Real (WhatsApp via the org's WAHA line) + factory.

`ReminderChannel.send` either returns a `SendReceipt` or raises `ReminderSendError(transient=...)`:
transient (network, 5xx, 429, session not ready) is retried; permanent (4xx, no line, bad number) is not.
Pacing is the WAHA client's own (`rate_limit` bucket "whatsapp") -- this module never sleeps for it.

Line selection (Orbity procedure: a dedicated `billing` line, falling back to `general`): `make_waha_client_resolver`
picks the org's connection whose `purpose` (read by `purpose_of`, default `record.extra["purpose"]`, fed by the
connection store's `record_extension`) matches the first of `purposes` that exists; a connection with no purpose
counts as `general`.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol, Sequence, runtime_checkable

import httpx

from noctusai_lib.integrations.whatsapp.client import WahaNumberNotOnWhatsApp

from .types import CHANNEL_WHATSAPP

logger = logging.getLogger(__name__)

PURPOSE_BILLING = "billing"
PURPOSE_GENERAL = "general"


class ReminderSendError(RuntimeError):
    """A send that did not happen. `transient` => worth retrying; `detail` is generic (never a provider body/secret)."""

    def __init__(self, message: str, *, transient: bool) -> None:
        super().__init__(message)
        self.transient = transient


@dataclass(frozen=True)
class SendReceipt:
    provider_ref: Optional[str] = None


@runtime_checkable
class ReminderChannel(Protocol):
    name: str

    def send(self, *, org_id: str, to: str, text: str) -> SendReceipt: ...


def normalize_br_phone(raw: str) -> str:
    """Digits only, `55` prepended to a 10/11-digit national number. Raises permanent error when unusable."""
    digits = re.sub(r"\D", "", raw or "")
    if len(digits) in (10, 11):
        digits = "55" + digits
    if not 12 <= len(digits) <= 15:
        raise ReminderSendError("telefone inválido", transient=False)
    return digits


@dataclass
class FakeReminderChannel:
    """In-memory channel: records sends; `fail_next` scripts failures (each popped per call)."""

    name: str = CHANNEL_WHATSAPP
    sent: list[dict] = field(default_factory=list)
    fail_next: list[ReminderSendError] = field(default_factory=list)
    calls: int = 0

    def send(self, *, org_id: str, to: str, text: str) -> SendReceipt:
        self.calls += 1
        if self.fail_next:
            raise self.fail_next.pop(0)
        self.sent.append({"org_id": org_id, "to": to, "text": text})
        return SendReceipt(provider_ref=f"fake-{len(self.sent)}")


def _classify_http(exc: BaseException) -> ReminderSendError:
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return ReminderSendError(f"whatsapp http {status}", transient=status == 429 or status >= 500)
    if isinstance(exc, httpx.TransportError):
        return ReminderSendError(f"whatsapp transport {type(exc).__name__}", transient=True)
    return ReminderSendError(f"whatsapp {type(exc).__name__}", transient=False)


class WhatsAppReminderChannel:
    """Real channel: sends through the WAHA client `resolve_client(org_id)` yields for that org.

    `resolve_client` returns an object with `send_text_to_phone_sync(phone, text)` (`WahaClient`) or None when the
    org has no connected line -> a PERMANENT error (a loud `failed` log row, not a silent skip). The send goes
    through the phone path, which resolves the BR 9th-digit variant (check-exists, send-retry fallback) -- never a
    raw `<digits>@c.us` chat id, which silently misses numbers registered without the 9. A number that is on
    neither spelling is a PERMANENT error.
    """

    name = CHANNEL_WHATSAPP

    def __init__(self, resolve_client: Callable[[str], Any]) -> None:
        self._resolve_client = resolve_client

    def send(self, *, org_id: str, to: str, text: str) -> SendReceipt:
        client = self._resolve_client(org_id)
        if client is None:
            raise ReminderSendError("sem linha de WhatsApp conectada", transient=False)
        phone = normalize_br_phone(to)
        try:
            body = client.send_text_to_phone_sync(phone, text)
        except WahaNumberNotOnWhatsApp as exc:
            raise ReminderSendError("número fora do WhatsApp", transient=False) from exc
        except (httpx.HTTPError, RuntimeError) as exc:
            # WahaSessionNotReady is a RuntimeError: the session is recovering -> worth another try.
            if isinstance(exc, httpx.HTTPError):
                raise _classify_http(exc) from exc
            raise ReminderSendError(f"whatsapp {type(exc).__name__}", transient=True) from exc
        ref = None
        if isinstance(body, dict):
            raw = body.get("id")
            ref = raw.get("_serialized") if isinstance(raw, dict) else raw
        return SendReceipt(provider_ref=str(ref) if ref else None)


def make_waha_client_resolver(
    store: Any,
    *,
    purposes: Sequence[str] = (PURPOSE_BILLING, PURPOSE_GENERAL),
    purpose_of: Optional[Callable[[Any], str]] = None,
    client_factory: Optional[Callable[[Any], Any]] = None,
) -> Callable[[str], Any]:
    """`org_id -> WahaClient | None` over a `WhatsAppConnectionStore`: first line matching `purposes` in order."""
    from uuid import UUID

    from noctusai_lib.integrations.whatsapp.client import WahaClient

    read_purpose = purpose_of or (lambda rec: str((rec.extra or {}).get("purpose") or PURPOSE_GENERAL))
    build = client_factory or (lambda rec: WahaClient(rec.base_url, rec.api_key, rec.session_name))

    def resolve(org_id: str) -> Any:
        records = store.list_connections(org_id=UUID(str(org_id)))
        for wanted in purposes:
            for rec in records:
                if read_purpose(rec) == wanted:
                    full = store.get_connection(connection_id=rec.id, org_id=UUID(str(org_id)), decrypt=True)
                    return build(full) if full else None
        return None

    return resolve


def make_reminder_channel(
    kind: str, *, resolve_client: Optional[Callable[[str], Any]] = None
) -> ReminderChannel:
    """`"fake"` | `"whatsapp"` -> a channel. `whatsapp` needs `resolve_client` (see `make_waha_client_resolver`)."""
    if kind == "fake":
        return FakeReminderChannel()
    if kind == CHANNEL_WHATSAPP:
        if resolve_client is None:
            raise ValueError("make_reminder_channel('whatsapp') needs resolve_client=")
        return WhatsAppReminderChannel(resolve_client)
    raise ValueError(f"unknown reminder channel {kind!r}")


__all__ = [
    "FakeReminderChannel",
    "PURPOSE_BILLING",
    "PURPOSE_GENERAL",
    "ReminderChannel",
    "ReminderSendError",
    "SendReceipt",
    "WhatsAppReminderChannel",
    "make_reminder_channel",
    "make_waha_client_resolver",
    "normalize_br_phone",
]
