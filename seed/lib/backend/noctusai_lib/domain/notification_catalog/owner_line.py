"""Owner line — NoctusAI's OWN WhatsApp number sends every owner notification, for every product.

Owner decision (2026-11-10): "warn me" is a WhatsApp scripted message (see `catalog.py`); it leaves from the seed
owner line (the platform's own number), never from a client's line. Contract: `projects/noc-whatsapp-lines/owner-line-CONTRACT.md`.

Flow of ``notify_owner``: ``gate.allowed(kind)`` → ``recipients.active()`` → ``transport.send_text`` per recipient →
``gate.record(...)``. It never raises (except an undeclared kind — a programming error) and EVERY outcome is recorded.

Lives outside `integrations/whatsapp/` on purpose: the transport takes an injected ``client_factory`` returning an
object with the seed WAHA client's ``send_text_sync(chat_id, text)``, so this module constructs nothing there.
Fake + Real + factory per `KB § PATTERNS/backend/seed-fake-real-adapter.md`.
"""
from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from noctusai_lib.primitives.phone import phone_digits

from .catalog import (
    NotificationGate,
    get_notification_gate,
    require_declared,
    status_for,
)

logger = logging.getLogger(__name__)

RECIPIENTS_TABLE = "notification_owner_recipients"
RECIPIENTS_TTL_SECONDS = 60.0
REASON_NO_RECIPIENT = "nenhum destinatário do dono configurado"
REASON_NO_TRANSPORT = "linha_noc_nao_configurada"


@dataclass(frozen=True)
class OwnerRecipient:
    numero: str  # E.164, e.g. "+5511999999999"
    nome: Optional[str] = None


class OwnerRecipientSource(Protocol):
    def active(self) -> list[OwnerRecipient]: ...


class OwnerLineTransport(Protocol):
    def send_text(self, numero_e164: str, texto: str) -> None: ...


@dataclass(frozen=True)
class OwnerDispatch:
    status: str
    recipients: int
    delivered: int
    reason: Optional[str]


# ── Fakes ────────────────────────────────────────────────────────────────────────────────────────────────────────
class FakeOwnerRecipientSource:
    def __init__(self, recipients: Optional[list[OwnerRecipient]] = None) -> None:
        self.recipients = list(recipients or [])

    def active(self) -> list[OwnerRecipient]:
        return list(self.recipients)


@dataclass
class FakeOwnerLineTransport:
    """Records sends; numbers in ``fail_numbers`` raise."""

    fail_numbers: set[str] = field(default_factory=set)
    sent: list[tuple[str, str]] = field(default_factory=list)

    def send_text(self, numero_e164: str, texto: str) -> None:
        if numero_e164 in self.fail_numbers:
            raise RuntimeError("fake owner line: send failed")
        self.sent.append((numero_e164, texto))


# ── Real ─────────────────────────────────────────────────────────────────────────────────────────────────────────
class SupabaseOwnerRecipientSource:
    """Enabled rows of core ``public.notification_owner_recipients`` (ordered), cached 60 s."""

    def __init__(
        self,
        core_client_factory: Callable[[], Any],
        *,
        ttl_seconds: float = RECIPIENTS_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self._core = core_client_factory
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: Optional[tuple[float, list[OwnerRecipient]]] = None
        self._lock = threading.Lock()

    def active(self) -> list[OwnerRecipient]:
        now = self._clock()
        with self._lock:
            if self._cache is not None and now - self._cache[0] < self._ttl:
                return list(self._cache[1])
        rows = (
            self._core().table(RECIPIENTS_TABLE).select("numero, nome").eq("ativo", True)
            .order("created_at").execute().data or []
        )
        found = [OwnerRecipient(numero=str(r["numero"]), nome=r.get("nome")) for r in rows]
        with self._lock:
            self._cache = (now, found)
        return list(found)


class WahaOwnerLineTransport:
    """Sends through an injected WAHA client (``client_factory()`` → object with ``send_text_sync(chat_id, text)``)."""

    def __init__(self, client_factory: Callable[[], Any]) -> None:
        self._factory = client_factory

    def send_text(self, numero_e164: str, texto: str) -> None:
        digits = phone_digits(numero_e164)
        if not digits:
            raise ValueError("owner line: recipient number is not a valid phone")
        self._factory().send_text_sync(f"{digits}@c.us", texto)


@dataclass
class OwnerLine:
    recipients: OwnerRecipientSource
    transport: Optional[OwnerLineTransport]


def make_owner_line(
    core_client_factory: Optional[Callable[[], Any]],
    waha_factory: Optional[Callable[[], Any]],
) -> OwnerLine:
    """Real recipients+transport when configured; otherwise the missing piece is absent (transport-less ⇒ the
    send records ``failed`` loudly, never a silent Fake)."""
    if core_client_factory is None:
        logger.warning("owner line: no core client — recipients kept in memory only (empty)")
        recipients: OwnerRecipientSource = FakeOwnerRecipientSource()
    else:
        recipients = SupabaseOwnerRecipientSource(core_client_factory)
    transport = WahaOwnerLineTransport(waha_factory) if waha_factory is not None else None
    return OwnerLine(recipients=recipients, transport=transport)


# ── process-wide line (installed by the seed framework, like the gate) ───────────────────────────────────────────
_line: Optional[OwnerLine] = None


def configure_owner_line(
    *, recipients: Optional[OwnerRecipientSource] = None, transport: Optional[OwnerLineTransport] = None,
) -> None:
    """Install the process-wide owner line. Both ``None`` clears it."""
    global _line
    _line = None if recipients is None and transport is None else OwnerLine(
        recipients=recipients if recipients is not None else FakeOwnerRecipientSource(), transport=transport,
    )


def get_owner_line() -> OwnerLine:
    """The installed line, or an empty one (no recipients, no transport) when none was installed."""
    return _line if _line is not None else OwnerLine(recipients=FakeOwnerRecipientSource(), transport=None)


# ── the send ─────────────────────────────────────────────────────────────────────────────────────────────────────
def notify_owner(
    product: str,
    kind: str,
    texto: str,
    *,
    org_id: Any = None,
    gate: Optional[NotificationGate] = None,
    recipients: Optional[OwnerRecipientSource] = None,
    transport: Optional[OwnerLineTransport] = None,
) -> OwnerDispatch:
    """Send ``texto`` to every active owner recipient from the owner line. Never raises (bar an undeclared kind)."""
    require_declared(product, kind)  # programming error, raised on purpose
    gate = gate or get_notification_gate(product)
    line = get_owner_line()
    recipients = recipients if recipients is not None else line.recipients
    transport = transport if transport is not None else line.transport

    def _done(status: str, n: int, ok: int, reason: Optional[str]) -> OwnerDispatch:
        try:
            gate.record(kind, org_id=org_id, status=status, recipients=n, delivered=ok, reason=reason)
        except Exception:  # noqa: BLE001 — the ledger never breaks the caller
            logger.error("owner line: ledger record failed product=%s kind=%s", product, kind, exc_info=True)
        return OwnerDispatch(status=status, recipients=n, delivered=ok, reason=(reason[:300] if reason else None))

    try:
        if not gate.allowed(kind):
            return _done("suppressed", 0, 0, "desligado pelo dono")
        active = recipients.active()
    except Exception as exc:  # noqa: BLE001 — recorded as failed, never raised
        logger.error("owner line: could not read switch/recipients product=%s kind=%s", product, kind,
                     exc_info=True)
        return _done("failed", 0, 0, f"leitura falhou: {type(exc).__name__}")
    if not active:
        return _done("no_recipient", 0, 0, REASON_NO_RECIPIENT)
    if transport is None:
        logger.error("seed.owner_line.nao_configurada product=%s kind=%s", product, kind)
        return _done("failed", len(active), 0, REASON_NO_TRANSPORT)

    delivered, errors = 0, []
    for r in active:
        try:
            transport.send_text(r.numero, texto)
            delivered += 1
        except Exception as exc:  # noqa: BLE001 — counted; the reason names the class, never text/numbers
            errors.append(type(exc).__name__)
            logger.error("owner line: send failed product=%s kind=%s err=%s", product, kind, type(exc).__name__,
                         exc_info=True)
    n = len(active)
    status = status_for(recipients=n, delivered=delivered, failed=n - delivered)
    reason = None if status == "sent" else f"{n - delivered} de {n} falharam: {', '.join(sorted(set(errors)))}"
    return _done(status, n, delivered, reason)


__all__ = [
    "FakeOwnerLineTransport",
    "FakeOwnerRecipientSource",
    "OwnerDispatch",
    "OwnerLine",
    "OwnerLineTransport",
    "OwnerRecipient",
    "OwnerRecipientSource",
    "SupabaseOwnerRecipientSource",
    "WahaOwnerLineTransport",
    "configure_owner_line",
    "get_owner_line",
    "make_owner_line",
    "notify_owner",
]
