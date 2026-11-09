"""Owner-notification catalog — every WhatsApp "warn me" message, listed and switchable.

THE RULE (owner, 2026-11-09): when the owner says "warn me" / "notify me" about a process, he means a WhatsApp
scripted message reaching his phone — never a DB row nobody reads. Every such message is a declared KIND here, so
core's admin page "Notificações" lists all of them and the owner can switch each one off per product to validate
how they behave day to day.

Shape (same as the scheduler run ledger, `domain/scheduler_runs`):

* A product DECLARES its kinds in code — ``declare_kinds("social-wiring", [NotificationKind(...), ...])`` at import
  time of the module that sends them. Declaring is how a kind exists; sending an undeclared kind raises
  ``UndeclaredNotificationKind`` (a programming error, caught by tests, never a silent send).
* At startup the seed framework installs a gate per product (``make_notification_gate``) and the gate upserts the
  declared kinds into core's ``public.notification_kinds`` (migration core 117). The upsert never writes
  ``enabled``, so a redeploy never re-enables a kind the owner switched off.
* Before a send, the product asks ``gate.allowed(kind)``; after it, ``gate.record(...)`` writes one row to
  ``public.notification_sends`` (status + counts + short reason, never message text or phone numbers).

Failure posture — fail toward WARNING the owner: when the switch cannot be read (core down, table missing) the gate
logs an ERROR and answers ``True``. A notification the owner did not want is a nuisance; a warning that silently
never arrived is the bug this module exists to end.

Shipped Fake + Real + factory (`KB § PATTERNS/backend/seed-fake-real-adapter.md`).
"""
from __future__ import annotations

import logging
import re
import threading
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Callable, Iterable, Optional, Protocol, Sequence

logger = logging.getLogger(__name__)

KINDS_TABLE = "notification_kinds"
SENDS_TABLE = "notification_sends"
SEND_STATUSES = ("sent", "partial", "failed", "suppressed", "no_recipient")
CHANNELS = ("whatsapp", "email", "in_app")
SWITCH_TTL_SECONDS = 60.0
REASON_MAX_CHARS = 300
_KIND_RE = re.compile(r"^[a-z0-9_]{1,80}$")


class UndeclaredNotificationKind(LookupError):
    """A product tried to send a notification kind it never declared."""


@dataclass(frozen=True)
class NotificationKind:
    """One owner-facing notification a product can send.

    ``titulo`` / ``descricao`` / ``gatilho`` are pt-BR and shown verbatim on the admin page: say what the owner
    receives and exactly what triggers it, so he can judge whether it behaves as intended.
    """

    kind: str
    titulo: str
    descricao: str
    gatilho: str
    canais: tuple[str, ...] = ("whatsapp",)

    def __post_init__(self) -> None:
        if not _KIND_RE.match(self.kind):
            raise ValueError(f"notification kind {self.kind!r} must match {_KIND_RE.pattern}")
        for name in ("titulo", "descricao", "gatilho"):
            if not getattr(self, name).strip():
                raise ValueError(f"notification kind {self.kind!r}: {name} is empty")
        unknown = set(self.canais) - set(CHANNELS)
        if not self.canais or unknown:
            raise ValueError(f"notification kind {self.kind!r}: canais must be a non-empty subset of {CHANNELS}")


# ── declarations (process-wide; one product per process in prod, several in tests) ─────────────────────────────
_declared: dict[str, dict[str, NotificationKind]] = {}
_declared_lock = threading.Lock()


def declare_kinds(product: str, kinds: Iterable[NotificationKind]) -> None:
    """Declare a product's notification kinds. Re-declaring the same kind with the same content is a no-op;
    with different content it raises (two modules disagreeing about one kind is a bug)."""
    if not product:
        raise ValueError("declare_kinds needs the product slug")
    with _declared_lock:
        bucket = _declared.setdefault(product, {})
        for k in kinds:
            existing = bucket.get(k.kind)
            if existing is not None and existing != k:
                raise ValueError(f"notification kind {product}/{k.kind} declared twice with different content")
            bucket[k.kind] = k


def declared_kinds(product: str) -> list[NotificationKind]:
    with _declared_lock:
        return sorted(_declared.get(product, {}).values(), key=lambda k: k.kind)


def require_declared(product: str, kind: str) -> NotificationKind:
    with _declared_lock:
        found = _declared.get(product, {}).get(kind)
    if found is None:
        raise UndeclaredNotificationKind(
            f"notification kind {product}/{kind} was never declared — add it to the product's declare_kinds(...) "
            "so it shows on core's Notificações page (KB § PATTERNS/backend/owner-notification-catalog.md)"
        )
    return found


def kind_row(product: str, k: NotificationKind, *, seen_at: datetime) -> dict:
    """The ``public.notification_kinds`` upsert row — deliberately WITHOUT ``enabled`` (the owner's switch)."""
    return {
        "product": product,
        "kind": k.kind,
        "titulo": k.titulo,
        "descricao": k.descricao,
        "gatilho": k.gatilho,
        "canais": list(k.canais),
        "last_seen_at": seen_at.isoformat(),
    }


def send_row(
    product: str, kind: str, *, org_id: Any, status: str, recipients: int, delivered: int, reason: Optional[str],
) -> dict:
    if status not in SEND_STATUSES:
        raise ValueError(f"notification send status {status!r} not in {SEND_STATUSES}")
    return {
        "product": product,
        "kind": kind,
        "org_id": str(org_id) if org_id else None,
        "status": status,
        "recipients": max(0, int(recipients)),
        "delivered": max(0, int(delivered)),
        "reason": (reason or None) and str(reason)[:REASON_MAX_CHARS],
    }


def status_for(*, recipients: int, delivered: int, failed: int) -> str:
    """The send status from a dispatch outcome's counts."""
    if recipients <= 0:
        return "no_recipient"
    if failed <= 0 and delivered > 0:
        return "sent"
    if delivered > 0:
        return "partial"
    return "failed"


# ── the gate ─────────────────────────────────────────────────────────────────────────────────────────────────────
class NotificationGate(Protocol):
    product: str

    def register(self) -> None: ...

    def allowed(self, kind: str) -> bool: ...

    def record(
        self, kind: str, *, org_id: Any = None, status: str, recipients: int = 0, delivered: int = 0,
        reason: Optional[str] = None,
    ) -> None: ...


@dataclass
class FakeNotificationGate:
    """In-memory gate for tests: switches in ``disabled``, sends in ``sends``."""

    product: str = "test-product"
    disabled: set[str] = field(default_factory=set)
    sends: list[dict] = field(default_factory=list)
    registered: list[dict] = field(default_factory=list)

    def register(self) -> None:
        now = datetime.now(timezone.utc)
        self.registered = [kind_row(self.product, k, seen_at=now) for k in declared_kinds(self.product)]

    def allowed(self, kind: str) -> bool:
        require_declared(self.product, kind)
        return kind not in self.disabled

    def record(self, kind, *, org_id=None, status, recipients=0, delivered=0, reason=None) -> None:
        require_declared(self.product, kind)
        self.sends.append(send_row(self.product, kind, org_id=org_id, status=status, recipients=recipients,
                                   delivered=delivered, reason=reason))


class SupabaseNotificationGate:
    """Real gate: core's tables through a ``public``-schema service-role client (resolved per call)."""

    def __init__(
        self,
        product: str,
        core_client_factory: Callable[[], Any],
        *,
        ttl_seconds: float = SWITCH_TTL_SECONDS,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        if not product:
            raise ValueError("a notification gate needs the product slug")
        self.product = product
        self._core = core_client_factory
        self._ttl = ttl_seconds
        self._clock = clock
        self._cache: Optional[tuple[float, dict[str, bool]]] = None
        self._lock = threading.Lock()
        self._registered = False

    def register(self) -> None:
        rows = [kind_row(self.product, k, seen_at=datetime.now(timezone.utc)) for k in declared_kinds(self.product)]
        if not rows:
            self._registered = True
            return
        try:
            self._core().table(KINDS_TABLE).upsert(rows, on_conflict="product,kind").execute()
            self._registered = True
        except Exception:  # noqa: BLE001 — loud; sends still work (fail toward warning)
            logger.error("notification catalog: registering %d kind(s) for %s FAILED — they will not show on "
                         "core's Notificações page until the next start", len(rows), self.product, exc_info=True)

    def _switches(self) -> dict[str, bool]:
        now = self._clock()
        with self._lock:
            if self._cache is not None and now - self._cache[0] < self._ttl:
                return self._cache[1]
        rows = (
            self._core().table(KINDS_TABLE).select("kind, enabled").eq("product", self.product).execute().data or []
        )
        switches = {str(r["kind"]): bool(r.get("enabled", True)) for r in rows}
        with self._lock:
            self._cache = (now, switches)
        return switches

    def allowed(self, kind: str) -> bool:
        require_declared(self.product, kind)
        if not self._registered:
            self.register()
        try:
            return self._switches().get(kind, True)
        except Exception:  # noqa: BLE001 — fail toward warning the owner, loudly
            logger.error("notification switch for %s/%s unreadable — sending anyway", self.product, kind,
                         exc_info=True)
            return True

    def record(self, kind, *, org_id=None, status, recipients=0, delivered=0, reason=None) -> None:
        require_declared(self.product, kind)
        row = send_row(self.product, kind, org_id=org_id, status=status, recipients=recipients,
                       delivered=delivered, reason=reason)
        try:
            self._core().table(SENDS_TABLE).insert(row).execute()
        except Exception:  # noqa: BLE001 — the send already happened; the ledger row is diagnostics
            logger.error("notification send ledger write FAILED for %s/%s (status=%s)", self.product, kind, status,
                         exc_info=True)


def make_notification_gate(product: str, core_client_factory: Optional[Callable[[], Any]]) -> NotificationGate:
    """Real when a core client factory is supplied, else the Fake (logged)."""
    if core_client_factory is None:
        logger.warning("notification gate for %s: no core client — switches/ledger kept in memory only", product)
        return FakeNotificationGate(product)
    return SupabaseNotificationGate(product, core_client_factory)


# ── process-wide gate (installed by the seed framework, like the run ledger / span sink) ─────────────────────────
_gate: Optional[NotificationGate] = None


def configure_notification_gate(gate: Optional[NotificationGate]) -> None:
    global _gate
    _gate = gate


def get_notification_gate(product: str) -> NotificationGate:
    """The installed gate, or a Fake for ``product`` when none was installed (scripts, tests)."""
    if _gate is not None and _gate.product == product:
        return _gate
    if _gate is not None:
        logger.warning("notification gate installed for %s, asked for %s — using an in-memory gate",
                       _gate.product, product)
    return FakeNotificationGate(product)


def reset_declarations_for_tests(product: Optional[str] = None) -> None:
    with _declared_lock:
        if product is None:
            _declared.clear()
        else:
            _declared.pop(product, None)


__all__: Sequence[str] = (
    "CHANNELS",
    "KINDS_TABLE",
    "SENDS_TABLE",
    "SEND_STATUSES",
    "FakeNotificationGate",
    "NotificationGate",
    "NotificationKind",
    "SupabaseNotificationGate",
    "UndeclaredNotificationKind",
    "configure_notification_gate",
    "declare_kinds",
    "declared_kinds",
    "get_notification_gate",
    "kind_row",
    "make_notification_gate",
    "require_declared",
    "reset_declarations_for_tests",
    "send_row",
    "status_for",
)
