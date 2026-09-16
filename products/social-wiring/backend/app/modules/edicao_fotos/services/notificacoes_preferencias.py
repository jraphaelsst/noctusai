"""Per-user opt-in for the "batch ready" notification (migration 131).

Plan §1: "Creator always; agency admins opt in per user; platform admin
can switch the whole notification off/on." The platform + org switches
already exist (`fotos_platform_settings.notificacoes_globais_ativas`,
`fotos_org_settings.notificacoes_ativas`) — this module is the third
layer: which agency admin (`AGENCY_ADMIN_ROLES`) individually opted in,
plus the WhatsApp number that channel sends to (`noctus_users` carries no
phone column).

Two collaborators:
    NotificationPreference          -- one user's own opt-in row.
    AdminNotificationTarget         -- a resolved fan-out recipient
                                        (nome/email from `noctus_users`,
                                        opt-in + whatsapp from this
                                        module's own table).

`NotificationPreferencesRepository` is the DI seam (`KB § PATTERNS/
backend/di-test-seam.md`) — `SupabaseNotificationPreferencesRepository`
for the real product, `InMemoryNotificationPreferencesRepository` for
tests. Neither talks to the seed engine: this is product-local storage,
consistent with the module docstring ("this module owns ... notification
fan-out")."""
from __future__ import annotations

import asyncio
import re
from dataclasses import dataclass, field
from typing import Any, Callable, Optional, Protocol

from noctusai_lib.domain.photo_editing.types import AGENCY_ADMIN_ROLES

TABLE = "fotos_notificacoes_preferencias"
SCHEMA = "social_wiring"
CORE_TABLE = "noctus_users"

#: E.164: `+` then 8-15 digits (ITU-T E.164 max length). Loose on purpose —
#: this module does not attempt BR-specific formatting; that lives in
#: `noctusai_lib.integrations.whatsapp` (`chat_id_for_phone`/`normalize_phone`),
#: which this repository's callers apply before dialing out.
_E164_RE = re.compile(r"^\+[1-9]\d{7,14}$")


class InvalidWhatsappNumberError(ValueError):
    """Raised by `save()` when `whatsapp_number` is set but not E.164."""


def validate_whatsapp_number(value: Optional[str]) -> Optional[str]:
    """Normalize + validate an opt-in WhatsApp number. `None`/blank passes
    through as `None` (channel skipped for this user); anything else must
    be E.164 (`+<country><number>`, 8-15 digits) — the shape
    `chat_id_for_phone` expects before it strips the `+`."""
    if value is None:
        return None
    trimmed = value.strip()
    if not trimmed:
        return None
    if not _E164_RE.match(trimmed):
        raise InvalidWhatsappNumberError(
            f"whatsapp_number {trimmed!r} não está em E.164 (ex.: +5511999998888)."
        )
    return trimmed


@dataclass(frozen=True)
class NotificationPreference:
    org_id: str
    user_id: str
    ativo: bool = False
    whatsapp_number: Optional[str] = None


@dataclass(frozen=True)
class AdminNotificationTarget:
    """One resolved fan-out recipient — an opted-in agency admin."""

    user_id: str
    nome: Optional[str]
    email: Optional[str]
    whatsapp_number: Optional[str]


class NotificationPreferencesRepository(Protocol):
    async def get(self, *, org_id: str, user_id: str) -> NotificationPreference: ...

    async def save(
        self, *, org_id: str, user_id: str, ativo: bool, whatsapp_number: Optional[str]
    ) -> NotificationPreference: ...

    async def list_opted_in_admins(
        self, *, org_id: str, exclude_user_id: Optional[str] = None
    ) -> list[AdminNotificationTarget]:
        """Agency admins (`AGENCY_ADMIN_ROLES`) with `ativo=true`, minus
        `exclude_user_id` (typically the batch's creator — already
        notified through the always-on creator path, never twice)."""
        ...


class SupabaseNotificationPreferencesRepository:
    """Real adapter. `core_client` reads `public.noctus_users` (roles +
    contact directory, Core's schema); `admin_client` reads/writes this
    module's own `social_wiring.fotos_notificacoes_preferencias` table —
    same two-client split `services/ports.py` already draws for the
    engine (`repo` on `core`, everything social_wiring-scoped on
    `admin`)."""

    def __init__(self, *, admin_client: Callable[[], Any], core_client: Callable[[], Any]) -> None:
        self._admin_client = admin_client
        self._core_client = core_client

    async def get(self, *, org_id: str, user_id: str) -> NotificationPreference:
        def _query() -> list[dict]:
            return (
                self._admin_client()
                .schema(SCHEMA)
                .table(TABLE)
                .select("org_id, user_id, ativo, whatsapp_number")
                .eq("org_id", org_id)
                .eq("user_id", user_id)
                .limit(1)
                .execute()
                .data
                or []
            )

        rows = await asyncio.to_thread(_query)
        if not rows:
            return NotificationPreference(org_id=org_id, user_id=user_id)
        row = rows[0]
        return NotificationPreference(
            org_id=str(row["org_id"]),
            user_id=str(row["user_id"]),
            ativo=bool(row["ativo"]),
            whatsapp_number=row.get("whatsapp_number"),
        )

    async def save(
        self, *, org_id: str, user_id: str, ativo: bool, whatsapp_number: Optional[str]
    ) -> NotificationPreference:
        normalized = validate_whatsapp_number(whatsapp_number)

        def _upsert() -> None:
            (
                self._admin_client()
                .schema(SCHEMA)
                .table(TABLE)
                .upsert(
                    {
                        "org_id": org_id,
                        "user_id": user_id,
                        "ativo": ativo,
                        "whatsapp_number": normalized,
                    },
                    on_conflict="org_id,user_id",
                )
                .execute()
            )

        await asyncio.to_thread(_upsert)
        return NotificationPreference(
            org_id=org_id, user_id=user_id, ativo=ativo, whatsapp_number=normalized
        )

    async def list_opted_in_admins(
        self, *, org_id: str, exclude_user_id: Optional[str] = None
    ) -> list[AdminNotificationTarget]:
        def _admins() -> list[dict]:
            return (
                self._core_client()
                .table(CORE_TABLE)
                .select("id, nome, email, org_role")
                .eq("org_id", org_id)
                .in_("org_role", sorted(AGENCY_ADMIN_ROLES))
                .execute()
                .data
                or []
            )

        def _preferences() -> list[dict]:
            return (
                self._admin_client()
                .schema(SCHEMA)
                .table(TABLE)
                .select("user_id, ativo, whatsapp_number")
                .eq("org_id", org_id)
                .eq("ativo", True)
                .execute()
                .data
                or []
            )

        admins, prefs = await asyncio.gather(
            asyncio.to_thread(_admins), asyncio.to_thread(_preferences)
        )
        opted_in = {str(p["user_id"]): p.get("whatsapp_number") for p in prefs}
        targets: list[AdminNotificationTarget] = []
        for admin in admins:
            user_id = str(admin["id"])
            if user_id not in opted_in or user_id == exclude_user_id:
                continue
            targets.append(
                AdminNotificationTarget(
                    user_id=user_id,
                    nome=admin.get("nome"),
                    email=admin.get("email"),
                    whatsapp_number=opted_in[user_id],
                )
            )
        return targets


@dataclass
class InMemoryNotificationPreferencesRepository:
    """Fake for tests. `admins` seeds the org roster this repository
    pretends `noctus_users` would return — `{user_id: {"nome", "email",
    "org_role", "org_id"}}` — since this fake has no Core table to read."""

    admins: dict[str, dict[str, Any]] = field(default_factory=dict)
    _prefs: dict[tuple[str, str], NotificationPreference] = field(default_factory=dict)

    def seed_admin(
        self, user_id: str, *, org_id: str, nome: str, email: str, org_role: str = "owner"
    ) -> None:
        self.admins[user_id] = {"org_id": org_id, "nome": nome, "email": email, "org_role": org_role}

    async def get(self, *, org_id: str, user_id: str) -> NotificationPreference:
        return self._prefs.get(
            (org_id, user_id), NotificationPreference(org_id=org_id, user_id=user_id)
        )

    async def save(
        self, *, org_id: str, user_id: str, ativo: bool, whatsapp_number: Optional[str]
    ) -> NotificationPreference:
        normalized = validate_whatsapp_number(whatsapp_number)
        pref = NotificationPreference(
            org_id=org_id, user_id=user_id, ativo=ativo, whatsapp_number=normalized
        )
        self._prefs[(org_id, user_id)] = pref
        return pref

    async def list_opted_in_admins(
        self, *, org_id: str, exclude_user_id: Optional[str] = None
    ) -> list[AdminNotificationTarget]:
        targets: list[AdminNotificationTarget] = []
        for user_id, info in self.admins.items():
            if info["org_id"] != org_id or info["org_role"] not in AGENCY_ADMIN_ROLES:
                continue
            if user_id == exclude_user_id:
                continue
            pref = self._prefs.get((org_id, user_id))
            if pref is None or not pref.ativo:
                continue
            targets.append(
                AdminNotificationTarget(
                    user_id=user_id,
                    nome=info.get("nome"),
                    email=info.get("email"),
                    whatsapp_number=pref.whatsapp_number,
                )
            )
        return targets


__all__ = [
    "AdminNotificationTarget",
    "InMemoryNotificationPreferencesRepository",
    "InvalidWhatsappNumberError",
    "NotificationPreference",
    "NotificationPreferencesRepository",
    "SupabaseNotificationPreferencesRepository",
    "validate_whatsapp_number",
]
