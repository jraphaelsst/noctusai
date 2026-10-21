"""In-app notification seam of the agents backend (core's ``public.notifications``).

One ``NotificationSink`` Protocol + ``FakeNotificationSink`` + ``SupabaseNotificationSink`` + factory, shared by
every producer: the credential-expiry job (:mod:`app.credentials.alerts`, platform admins) and the lead opt-out
notice (:mod:`app.channels.opt_out`, the admins/owners of the lead's org). The bell every product shows reads
these rows through the seed ``/api/notificacoes`` proxy.

Recipients: :meth:`platform_admin_ids` (``noctus_users.role = 'admin'``, the actor ``require_platform_admin``
gates) and :meth:`org_admin_ids` (owners/admins OF ONE ORG: an active ``org_memberships`` row with
``org_role`` in owner/admin, plus the legacy home-org ``noctus_users`` row -- the same trusted sources the org
role cascade reads, never ``user_metadata``).
"""
from __future__ import annotations

from typing import Any, Callable, Protocol
from uuid import UUID

from noctusai_lib.domain.notifications import write_in_app
from noctusai_lib.integrations.persistence.paging import iter_paged_rows

__all__ = [
    "FakeNotificationSink",
    "NotificationSink",
    "ORG_ADMIN_ROLES",
    "SupabaseNotificationSink",
    "get_notification_sink",
]

#: The org roles that receive an org-level notice (same set as ``app.dependencies.ADMIN_ROLES``).
ORG_ADMIN_ROLES = ("owner", "admin")


class NotificationSink(Protocol):
    def platform_admin_ids(self) -> list[str]: ...

    def org_admin_ids(self, org_id: UUID) -> list[str]: ...

    def user_label(self, user_id: UUID | str) -> str | None:
        """A human label of the user (their e-mail) for a notice's "by whom"; ``None`` = unknown user."""
        ...

    def already_sent(self, user_id: str, key: str) -> bool: ...

    def send(
        self, user_id: str, *, kind: str, title: str, message: str, metadata: dict[str, Any],
        org_id: UUID | None = None,
    ) -> None: ...


class FakeNotificationSink:
    def __init__(
        self, admin_ids: list[str] | None = None, org_admins: dict[UUID, list[str]] | None = None,
    ) -> None:
        self.admin_ids = list(admin_ids or [])
        self.org_admins = {k: list(v) for k, v in (org_admins or {}).items()}
        self.sent: list[dict[str, Any]] = []
        #: Set to an exception to make every ``send`` / ``org_admin_ids`` raise it (the failure path).
        self.fail_with: Exception | None = None
        #: ``user_id -> label`` answered by :meth:`user_label`.
        self.labels: dict[str, str] = {}
        #: Set to an exception to make :meth:`user_label` raise it (the label lookup failing).
        self.label_fail_with: Exception | None = None

    def user_label(self, user_id: UUID | str) -> str | None:
        if self.label_fail_with is not None:
            raise self.label_fail_with
        return self.labels.get(str(user_id))

    def platform_admin_ids(self) -> list[str]:
        return list(self.admin_ids)

    def org_admin_ids(self, org_id: UUID) -> list[str]:
        if self.fail_with is not None:
            raise self.fail_with
        return list(self.org_admins.get(org_id, []))

    def already_sent(self, user_id: str, key: str) -> bool:
        return any(n["user_id"] == user_id and n["metadata"].get("dedup_key") == key for n in self.sent)

    def send(
        self, user_id: str, *, kind: str, title: str, message: str, metadata: dict[str, Any],
        org_id: UUID | None = None,
    ) -> None:
        if self.fail_with is not None:
            raise self.fail_with
        self.sent.append({
            "user_id": user_id, "kind": kind, "title": title, "message": message, "metadata": metadata,
            "org_id": org_id,
        })


class SupabaseNotificationSink:
    """Writes to core's ``public.notifications`` with a public-scoped client."""

    def __init__(self, core_client_factory: Callable[[], Any]) -> None:
        self._core = core_client_factory

    def platform_admin_ids(self) -> list[str]:
        resp = self._core().table("noctus_users").select("id").eq("role", "admin").execute()
        return [str(r["id"]) for r in (resp.data or [])]

    def org_admin_ids(self, org_id: UUID) -> list[str]:
        core = self._core()

        def memberships(start: int, end: int):
            return (
                core.table("org_memberships").select("id, user_id")
                .eq("org_id", str(org_id)).eq("status", "active").in_("org_role", list(ORG_ADMIN_ROLES))
                .order("id").range(start, end).execute().data
            )

        def home(start: int, end: int):
            return (
                core.table("noctus_users").select("id")
                .eq("org_id", str(org_id)).in_("org_role", list(ORG_ADMIN_ROLES))
                .order("id").range(start, end).execute().data
            )

        ids = {str(r["user_id"]) for r in iter_paged_rows(memberships, label="org_memberships") if r.get("user_id")}
        ids |= {str(r["id"]) for r in iter_paged_rows(home, label="noctus_users") if r.get("id")}
        return sorted(ids)

    def user_label(self, user_id: UUID | str) -> str | None:
        rows = self._core().table("noctus_users").select("id, email").eq("id", str(user_id)).limit(1).execute().data or []
        return (rows[0].get("email") or None) if rows else None

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

    def send(
        self, user_id: str, *, kind: str, title: str, message: str, metadata: dict[str, Any],
        org_id: UUID | None = None,
    ) -> None:
        write_in_app(
            self._core(), user_ids=[user_id], kind=kind, title=title, message=message, metadata=metadata,
            org_id=org_id,
        )


def get_notification_sink() -> NotificationSink:
    from app.dependencies import get_core_client

    return SupabaseNotificationSink(get_core_client)
