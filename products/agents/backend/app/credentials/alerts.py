"""Expiry warnings → platform-admin notifications (contract D1 deferral).

The daily job (`app/scheduler.py`) calls :func:`run_credential_maintenance`:
it turns `CredentialService.expiry_alerts()` into rows in core's
`public.notifications` (the table every product's bell reads through the
seed `/api/notificacoes` proxy) for every PLATFORM admin
(`noctus_users.role = 'admin'` — the same actor `require_platform_admin`
gates the Credenciais page on), then drops retired §D ring keys.

Dedup: one notification per (user, credential, expiry date, bucket) —
buckets 30/14/7/3/1/0 days — so a daily run nags at a rising cadence
instead of every day or only once.

Seed IO shape for the sink: ``NotificationSink`` Protocol +
``FakeNotificationSink`` + ``SupabaseNotificationSink`` + factory.
"""
from __future__ import annotations

import logging
from typing import Any, Callable, Protocol

from app.credentials.service import CredentialError, CredentialService, ExpiryAlert

logger = logging.getLogger(__name__)

__all__ = [
    "FakeNotificationSink",
    "NotificationSink",
    "SupabaseNotificationSink",
    "dedup_key",
    "get_notification_sink",
    "notify_expiry_alerts",
    "run_credential_maintenance",
]

_BUCKETS = (0, 1, 3, 7, 14, 30)
_LINK = "/credenciais"


def dedup_key(alert: ExpiryAlert) -> str:
    if alert.reason == "revoked":
        bucket = "revoked"
    elif alert.days_left is None or alert.days_left <= 0:
        bucket = "expired"
    else:
        bucket = str(next((b for b in _BUCKETS if alert.days_left <= b), _BUCKETS[-1]))
    day = alert.expires_at.date().isoformat() if alert.expires_at else "none"
    return f"agents.credential_expiry:{alert.name}:{day}:{bucket}"


def _message(alert: ExpiryAlert) -> tuple[str, str]:
    if alert.reason == "revoked":
        return (f"{alert.label}: token revogado", "Renove em Agentes → Credenciais e integrações.")
    if alert.reason == "expired":
        return (f"{alert.label}: token expirado", "A Julia não consegue usá-lo. Renove em Agentes → Credenciais.")
    return (
        f"{alert.label}: expira em {alert.days_left} dia(s)",
        "Renove em Agentes → Credenciais e integrações antes do vencimento.",
    )


class NotificationSink(Protocol):
    def platform_admin_ids(self) -> list[str]: ...

    def already_sent(self, user_id: str, key: str) -> bool: ...

    def send(self, user_id: str, *, title: str, message: str, metadata: dict[str, Any]) -> None: ...


class FakeNotificationSink:
    def __init__(self, admin_ids: list[str] | None = None) -> None:
        self.admin_ids = list(admin_ids or [])
        self.sent: list[dict[str, Any]] = []

    def platform_admin_ids(self) -> list[str]:
        return list(self.admin_ids)

    def already_sent(self, user_id: str, key: str) -> bool:
        return any(n["user_id"] == user_id and n["metadata"].get("dedup_key") == key for n in self.sent)

    def send(self, user_id: str, *, title: str, message: str, metadata: dict[str, Any]) -> None:
        self.sent.append({"user_id": user_id, "title": title, "message": message, "metadata": metadata})


class SupabaseNotificationSink:
    """Writes to core's ``public.notifications`` with a public-scoped client."""

    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._core = core_client_factory

    def platform_admin_ids(self) -> list[str]:
        resp = self._core().table("noctus_users").select("id").eq("role", "admin").execute()
        return [str(r["id"]) for r in (resp.data or [])]

    def already_sent(self, user_id: str, key: str) -> bool:
        resp = (
            self._core()
            .table("notifications")
            .select("id")
            .eq("user_id", user_id)
            .contains("metadata", {"dedup_key": key})
            .limit(1)
            .execute()
        )
        return bool(resp.data)

    def send(self, user_id: str, *, title: str, message: str, metadata: dict[str, Any]) -> None:
        self._core().table("notifications").insert(
            {"user_id": user_id, "type": "system", "title": title, "message": message, "metadata": metadata}
        ).execute()


def get_notification_sink() -> NotificationSink:
    from app.dependencies import get_core_client

    return SupabaseNotificationSink(get_core_client)


def notify_expiry_alerts(alerts: list[ExpiryAlert], sink: NotificationSink) -> int:
    """Returns how many notifications were created."""
    if not alerts:
        return 0
    admins = sink.platform_admin_ids()
    if not admins:
        logger.error("agents.credential_expiry_alert_undeliverable reason=no_platform_admin alerts=%s", len(alerts))
        return 0
    created = 0
    for alert in alerts:
        key = dedup_key(alert)
        title, message = _message(alert)
        for user_id in admins:
            if sink.already_sent(user_id, key):
                continue
            sink.send(
                user_id,
                title=title,
                message=message,
                metadata={"dedup_key": key, "product": "agents", "link": _LINK, "credential": alert.name},
            )
            created += 1
    return created


def run_credential_maintenance(service: CredentialService, sink: NotificationSink) -> dict[str, Any]:
    """The daily job body. Each leg is isolated and logged; one failing leg
    never hides the other (and nothing is swallowed silently)."""
    result: dict[str, Any] = {"alerts": 0, "notified": 0, "ring": "skipped"}
    try:
        alerts = service.expiry_alerts()
        result["alerts"] = len(alerts)
        result["notified"] = notify_expiry_alerts(alerts, sink)
    except Exception:
        logger.exception("agents.credential_maintenance.alerts_failed")
        result["alerts"] = "error"
    try:
        service.prune_ring()
        result["ring"] = "pruned"
    except CredentialError as exc:
        result["ring"] = exc.code  # e.g. ring_not_in_db — expected before the import
    except Exception:
        logger.exception("agents.credential_maintenance.ring_prune_failed")
        result["ring"] = "error"
    logger.info("agents.credential_maintenance %s", result)
    return result
