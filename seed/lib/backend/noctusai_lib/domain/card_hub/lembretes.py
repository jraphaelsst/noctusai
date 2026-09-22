"""Card reminders — materialised `lembretes` rows, one per scheduled fire.

Lifted from social-wiring's `agendamentos_service._dispara_em` /
`_cancelar_lembretes` / `_sync_lembrete` (migration 056 table, 061 scope
column). The mechanics are generic: "this thing happens at `quando`; remind
`minutos` before; when it moves, cancel the stale reminder and schedule the new
one". What a reminder is ABOUT (an appointment, a delivery date) is the
caller's `scope` — extra columns that both key the cancel and ride on the
insert.

🔴 SCOPE THE CANCEL, NEVER THE CARD. A person-scoped cancel kills every OTHER
pending reminder the card has each time one thing is edited — exactly the
overwrite bug social-wiring migration 061 exists to prevent. Pass the narrowest
`scope` that identifies the reminding thing (`{"agendamento_id": ...}`).

Rows are materialised correctly but not yet DELIVERED — see the remediation
marker below. A card showing "Lembrete 1 hora antes" states what was
SCHEDULED, never that a notification was sent.
"""
# NOC-REMEDIATE[reminder-delivery]: nothing drains the pending-reminder index
# yet (no delivery job); carried forward from social-wiring's
# agendamentos_service, where the gap predates this lift. — 2026-09-22
from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.integrations.persistence.table_reads import table

from .config import CardHubConfig
from .services import now_iso


def dispara_em(quando: Optional[str], minutos: Optional[int]) -> Optional[str]:
    """`quando - minutos`, ISO — or `None` when either is absent (no reminder)."""
    if not quando or minutos is None:
        return None
    dt = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
    return (dt - timedelta(minutes=minutos)).isoformat()


def cancelar_lembretes(cfg: CardHubConfig, db: Any, org_id: UUID, *, scope: dict) -> int:
    """Stamp `cancelado_em` on every PENDING reminder matching `scope`.
    Returns how many were cancelled. `scope` must be non-empty — an unscoped
    cancel would hit the whole org."""
    if not scope:
        raise ValueError("cancelar_lembretes requires a non-empty scope")
    query = table(db, cfg.tables.lembretes).select("id").eq("org_id", str(org_id))
    for key, value in scope.items():
        query = query.eq(key, value)
    pendentes = (query.is_("enviado_em", "null").is_("cancelado_em", "null").execute()).data or []
    for row in pendentes:
        table(db, cfg.tables.lembretes).update({"cancelado_em": now_iso()}).eq("id", row["id"]).execute()
    return len(pendentes)


def sync_lembrete(
    cfg: CardHubConfig,
    db: Any,
    org_id: UUID,
    entity_id: UUID,
    *,
    scope: dict,
    quando: Optional[str],
    minutos: Optional[int],
) -> Optional[str]:
    """Cancel `scope`'s pending reminder, then schedule the new one (if
    `quando`/`minutos` still call for one). Returns the new row's id or
    `None`."""
    cancelar_lembretes(cfg, db, org_id, scope=scope)
    quando_disparo = dispara_em(quando, minutos)
    if not quando_disparo:
        return None
    lembrete_id = str(uuid4())
    table(db, cfg.tables.lembretes).insert(
        {
            "id": lembrete_id,
            "org_id": str(org_id),
            cfg.entity_fk: str(entity_id),
            **{k: v for k, v in scope.items() if k != cfg.entity_fk},
            "dispara_em": quando_disparo,
            "enviado_em": None,
            "cancelado_em": None,
            "destinatarios": [],
            "created_at": now_iso(),
        }
    ).execute()
    return lembrete_id


__all__ = ["cancelar_lembretes", "dispara_em", "sync_lembrete"]
