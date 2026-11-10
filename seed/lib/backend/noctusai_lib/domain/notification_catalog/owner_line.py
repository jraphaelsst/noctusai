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

from noctusai_lib.primitives.phone import br_mobile_variants, is_valid_phone

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
REASON_NOT_INSTALLED = "linha_noc_nao_instalada"
REASON_NUMBER_MISMATCH = "linha_noc_numero_divergente"
REASON_NUMBER_UNDECLARED = "linha_noc_numero_nao_declarado"
REASON_NUMBER_UNKNOWN = "linha_noc_numero_desconhecido"
VERIFY_TTL_SECONDS = 900.0


class OwnerLineNumberMismatch(RuntimeError):
    """The WAHA session's paired number is not NoctusAI's declared owner-line number (or is unknown)."""

    reason_code = REASON_NUMBER_MISMATCH


class OwnerLineNumberUnknown(RuntimeError):
    """The paired account id carries no phone digits (e.g. an ``@lid`` form) — fails closed."""

    reason_code = REASON_NUMBER_UNKNOWN


def _paired_digits(me: Optional[str]) -> Optional[str]:
    """Phone digits of a WAHA ``me.id``: ``<digits>@c.us`` | ``<digits>:<device>@c.us`` | ``<id>@lid`` (None)."""
    if not me:
        return None
    user, _, domain = me.partition("@")
    if domain.startswith("lid"):
        return None
    return user.split(":", 1)[0].lstrip("+") or None


def _mask(numero: str) -> str:
    return "…" + "".join(c for c in numero if c.isdigit())[-4:]


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
    """Sends through an injected WAHA client (``client_factory()`` → object with ``send_text_to_phone_sync(phone,
    text)``, which resolves BR 9th-digit variants via check-exists with a send-retry fallback).

    Only NoctusAI's own number may send: on first use ``me_fetch()`` (the session's paired account id/number) is
    compared with ``expected_numero``; a mismatch or unknown account raises ``OwnerLineNumberMismatch``. A match
    is cached for 15 minutes and dropped after any send failure."""

    def __init__(self, client_factory: Callable[[], Any], *, expected_numero: str,
                 me_fetch: Callable[[], Optional[str]], ttl_seconds: float = VERIFY_TTL_SECONDS,
                 clock: Callable[[], float] = time.monotonic) -> None:
        expected = set(br_mobile_variants(expected_numero))
        if not expected:
            raise ValueError("owner line: expected_numero is not a valid phone")
        self._factory = client_factory
        self._expected = expected
        self._me_fetch = me_fetch
        self._ttl = ttl_seconds
        self._clock = clock
        self._verified_at: Optional[float] = None

    def _verify(self) -> None:
        if self._verified_at is not None and self._clock() - self._verified_at < self._ttl:
            return
        self._verified_at = None
        me = self._me_fetch()
        digits = _paired_digits(me)
        if me and digits is None:
            logger.error("seed.owner_line.numero_desconhecido: the session's paired id has no phone digits")
            raise OwnerLineNumberUnknown(REASON_NUMBER_UNKNOWN)
        # WhatsApp may pair a BR mobile without the 9th digit: match by the seed's variant set.
        paired = set(br_mobile_variants("+" + digits)) if digits else set()
        if not paired & self._expected:
            raise OwnerLineNumberMismatch(REASON_NUMBER_MISMATCH)
        self._verified_at = self._clock()

    def send_text(self, numero_e164: str, texto: str) -> None:
        if not is_valid_phone(numero_e164):
            raise ValueError("owner line: recipient number is not a valid phone")
        self._verify()
        try:
            self._factory().send_text_to_phone_sync(numero_e164, texto)
        except Exception:
            self._verified_at = None  # a failure may mean a re-pair: re-verify on the next send
            raise


@dataclass
class OwnerLine:
    recipients: OwnerRecipientSource
    transport: Optional[OwnerLineTransport]
    installed: bool = True
    transport_reason: Optional[str] = None  # why ``transport`` is None (default: not configured)


class _UnreadableRecipientSource:
    """Production stand-in when the recipients cannot be read: ``active()`` raises, so ``notify_owner`` records
    ``failed`` loudly instead of a misleading ``no_recipient``."""

    def __init__(self, why: str) -> None:
        self._why = why

    def active(self) -> list[OwnerRecipient]:
        raise RuntimeError(self._why)


def make_owner_line(
    core_client_factory: Optional[Callable[[], Any]],
    waha_factory: Optional[Callable[[], Any]],
    *,
    expected_numero: Optional[str] = None,
    me_fetch: Optional[Callable[[], Optional[str]]] = None,
) -> OwnerLine:
    """Real recipients+transport when configured; otherwise the missing piece is absent (transport-less ⇒ the
    send records ``failed`` loudly, never a silent Fake)."""
    if core_client_factory is None:
        logger.error("owner line: no core client — recipients unreadable, sends will record failed")
        recipients: OwnerRecipientSource = _UnreadableRecipientSource("sem cliente core")
    else:
        recipients = SupabaseOwnerRecipientSource(core_client_factory)
    transport: Optional[OwnerLineTransport] = None
    reason: Optional[str] = None
    if waha_factory is not None:
        if not expected_numero or me_fetch is None or not br_mobile_variants(expected_numero):
            logger.error("owner line: WAHA is set but the line's number is not declared (NOC_OWNER_LINE_EXPECTED_NUMBER)"
                         " — no transport, sends will record failed")
            reason = REASON_NUMBER_UNDECLARED
        else:
            transport = WahaOwnerLineTransport(waha_factory, expected_numero=expected_numero, me_fetch=me_fetch)
    return OwnerLine(recipients=recipients, transport=transport, transport_reason=reason)


# ── process-wide line (installed by the seed framework, like the gate) ───────────────────────────────────────────
_line: Optional[OwnerLine] = None


def configure_owner_line(
    *, recipients: Optional[OwnerRecipientSource] = None, transport: Optional[OwnerLineTransport] = None,
    transport_reason: Optional[str] = None,
) -> None:
    """Install the process-wide owner line. Both ``None`` clears it."""
    global _line
    _line = None if recipients is None and transport is None else OwnerLine(
        recipients=recipients if recipients is not None else FakeOwnerRecipientSource(), transport=transport,
        transport_reason=transport_reason,
    )


def get_owner_line() -> OwnerLine:
    """The installed line, or an empty one (no recipients, no transport) when none was installed."""
    return _line if _line is not None else OwnerLine(
        recipients=FakeOwnerRecipientSource(), transport=None, installed=False,
    )


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
    not_installed = not line.installed and recipients is None and transport is None
    recipients = recipients if recipients is not None else line.recipients
    transport_reason = line.transport_reason if transport is None else None
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
        if not_installed:
            logger.error("seed.owner_line.nao_instalada product=%s kind=%s", product, kind)
            return _done("failed", 0, 0, REASON_NOT_INSTALLED)
        active = recipients.active()
    except Exception as exc:  # noqa: BLE001 — recorded as failed, never raised
        logger.error("owner line: could not read switch/recipients product=%s kind=%s", product, kind,
                     exc_info=True)
        return _done("failed", 0, 0, f"leitura falhou: {type(exc).__name__}")
    if not active:
        return _done("no_recipient", 0, 0, REASON_NO_RECIPIENT)
    if transport is None:
        logger.error("seed.owner_line.nao_configurada product=%s kind=%s", product, kind)
        return _done("failed", len(active), 0, transport_reason or REASON_NO_TRANSPORT)

    delivered, errors = 0, []
    for r in active:
        try:
            transport.send_text(r.numero, texto)
            delivered += 1
        except Exception as exc:  # noqa: BLE001 — counted; the reason names the class, never text/numbers
            code = getattr(exc, "reason_code", None) or type(exc).__name__
            errors.append(code)
            # class name + masked recipient only: vendor exceptions carry the full number in their message
            logger.error("owner line: send failed product=%s kind=%s err=%s to=%s", product, kind, code,
                         _mask(r.numero))
    n = len(active)
    status = status_for(recipients=n, delivered=delivered, failed=n - delivered)
    reason = None if status == "sent" else f"{n - delivered} de {n} falharam: {', '.join(sorted(set(errors)))}"
    return _done(status, n, delivered, reason)


__all__ = [
    "FakeOwnerLineTransport",
    "FakeOwnerRecipientSource",
    "OwnerDispatch",
    "OwnerLine",
    "OwnerLineNumberMismatch",
    "OwnerLineNumberUnknown",
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
