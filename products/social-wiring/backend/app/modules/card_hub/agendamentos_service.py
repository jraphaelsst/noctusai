"""Agendamentos — many appointments per atendimento, each with its own reminder.

WHY THIS MODULE EXISTS
----------------------
The card used to hold exactly ONE appointment, because "the appointment" was
three columns on `clientes`. Booking a second one overwrote the first, which the
user named exactly: *"it doesnt add multiple schedules, it replaces the last one
with the nem set one. That works fine but it's not functional to the use i
imagine to it."* Migration `061` gives appointments their own table; this module
is the service over it.

WHOSE APPOINTMENT IS IT — the ATENDIMENTO's
-------------------------------------------
The user's ruling. Not the person's. D17 says a person accumulates negotiations
over time and closed ones stay as history, so a visit booked for a deal closed
in 2024 and one booked for a live negotiation are different things that must not
share a list. The card IS the person, so it reads across that person's
atendimentos — but each row knows which deal it belongs to.

Today every cliente has exactly ONE open atendimento (measured: 1 015 of 1 015,
max 1), so `create` can resolve the target itself. It REFUSES rather than
guessing when that stops being true — see `resolve_atendimento_id`.

REMINDERS
---------
One appointment ↔ at most one PENDING `cliente_lembretes` row, linked by the
`agendamento_id` column `061` adds. Before that column the "cancel the stale
reminder" query could only match *by person*, so booking a second appointment
would have cancelled the first one's notification — the overwrite bug one layer
down.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any, Optional
from uuid import UUID, uuid4

from noctusai_lib.primitives.exceptions import NotFoundError

from app.modules.card_hub.services import (
    # Re-exported below: the resolver moved to `services` when compradores
    # became its second caller, and this module's importers keep working.
    AmbiguousAtendimento,
    _atendimentos_do_cliente,
    _batched,
    _now,
    _paged_rows,
    _t,
    ensure_cliente,
    resolve_atendimento_id,
)

TABLE = "atendimento_agendamentos"

#: The four the user asked for. A `tipo` outside this set is a 422 from the
#: schema, and the DB CHECK in `061` is the backstop — both, because the schema
#: protects the API and the CHECK protects every other writer.
TIPOS = ("visita", "ligacao", "reuniao", "outro")

_FIELDS = (
    "id", "atendimento_id", "quando", "tipo", "nota",
    "lembrete_minutos_antes", "created_at",
)


def _out(row: dict) -> dict:
    return {k: row.get(k) for k in _FIELDS}


def listar(client: Any, org_id: UUID, cliente_id: UUID) -> dict:
    """Every live appointment across this person's atendimentos, soonest first."""
    ensure_cliente(client, org_id, cliente_id)
    atendimento_ids = [str(r["id"]) for r in _atendimentos_do_cliente(client, org_id, cliente_id)]
    if not atendimento_ids:
        return {"items": []}

    rows: list[dict] = []
    for chunk in _batched(atendimento_ids):
        rows += _paged_rows(
            client,
            TABLE,
            org_id,
            order_col="quando",
            refine=lambda q, c=chunk: q.in_("atendimento_id", c).is_("deleted_at", "null"),
        )
    rows.sort(key=lambda r: r.get("quando") or "")
    return {"items": [_out(r) for r in rows]}


def criar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    *,
    quando: str,
    tipo: str,
    nota: Optional[str] = None,
    lembrete_minutos_antes: Optional[int] = None,
    atendimento_id: Optional[UUID] = None,
) -> dict:
    ensure_cliente(client, org_id, cliente_id)
    alvo = resolve_atendimento_id(client, org_id, cliente_id, atendimento_id)

    row = {
        "id": str(uuid4()),
        "org_id": str(org_id),
        "atendimento_id": alvo,
        "quando": quando,
        "tipo": tipo,
        "nota": nota,
        "lembrete_minutos_antes": lembrete_minutos_antes,
        "created_at": _now(),
    }
    _t(client, TABLE).insert(row).execute()
    _sync_lembrete(client, org_id, cliente_id, row["id"], quando, lembrete_minutos_antes)
    _sync_mirror(client, org_id, cliente_id)
    return _out(row)


def atualizar(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    agendamento_id: UUID,
    *,
    quando: Optional[str] = ...,
    tipo: Optional[str] = ...,
    nota: Optional[str] = ...,
    lembrete_minutos_antes: Optional[int] = ...,
) -> dict:
    """`...` sentinels an unset field — only what the PATCH carried is written."""
    atual = _obter(client, org_id, cliente_id, agendamento_id)

    updates: dict = {}
    if quando is not ...:
        updates["quando"] = quando
    if tipo is not ...:
        updates["tipo"] = tipo
    if nota is not ...:
        updates["nota"] = nota
    if lembrete_minutos_antes is not ...:
        updates["lembrete_minutos_antes"] = lembrete_minutos_antes

    if updates:
        _t(client, TABLE).update(updates).eq("id", str(agendamento_id)).execute()

    merged = {**atual, **updates}
    # Re-materialise ONLY when an input the reminder depends on moved. A note
    # edit must not silently reschedule a notification.
    if "quando" in updates or "lembrete_minutos_antes" in updates:
        _sync_lembrete(
            client, org_id, cliente_id, str(agendamento_id),
            merged.get("quando"), merged.get("lembrete_minutos_antes"),
        )
    _sync_mirror(client, org_id, cliente_id)
    return _out(merged)


def remover(client: Any, org_id: UUID, cliente_id: UUID, agendamento_id: UUID) -> None:
    """Soft delete + cancel its pending reminder.

    Cancelling matters as much as the delete: a notification for an appointment
    that no longer exists is worse than no notification, because the person it
    reaches has no way to find out why.
    """
    _obter(client, org_id, cliente_id, agendamento_id)
    _t(client, TABLE).update({"deleted_at": _now()}).eq("id", str(agendamento_id)).execute()
    _cancelar_lembretes(client, org_id, str(agendamento_id))
    _sync_mirror(client, org_id, cliente_id)


def _obter(client: Any, org_id: UUID, cliente_id: UUID, agendamento_id: UUID) -> dict:
    """The row, proven to belong to THIS cliente. The ownership check is the
    authorisation — an id alone must never be enough to edit someone else's."""
    ensure_cliente(client, org_id, cliente_id)
    permitidos = {str(r["id"]) for r in _atendimentos_do_cliente(client, org_id, cliente_id)}
    rows = (
        _t(client, TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(agendamento_id))
        .execute()
    ).data or []
    row = rows[0] if rows else None
    if row is None or row.get("deleted_at") or str(row.get("atendimento_id")) not in permitidos:
        raise NotFoundError(TABLE, str(agendamento_id))
    return row


# ── the board-pill mirror ──────────────────────────────────────────────────

def _sync_mirror(client: Any, org_id: UUID, cliente_id: UUID) -> None:
    """Mirror the SOONEST upcoming appointment onto `clientes.data_entrega`.

    The Clientes board draws its due pill from `clientes.data_entrega`, read by
    the LIST endpoint — not by the card resumo. Repointing that query at this
    table means joining atendimentos → agendamentos for every row on a
    thousand-row board, which is its own slice with its own paging questions.

    Until then this keeps the board honest. Note what it is and is not:

    * It is DERIVED. `atendimento_agendamentos` is the source of truth; this
      column is a cache of one value computed from it. There is still exactly
      one writer.
    * It is NOT a second input. Nothing reads `clientes.data_entrega` to decide
      anything any more — the card reads the table. If this mirror were dropped
      tomorrow, no behaviour would change except a stale pill on the board.

    Written after every create/update/delete so the pill cannot drift. A pill
    showing an appointment that was moved or cancelled is worse than no pill.
    """
    agendamentos = listar(client, org_id, cliente_id)["items"]
    agora = datetime.now(timezone.utc)

    def _futuro(row: dict) -> bool:
        quando = row.get("quando")
        if not quando:
            return False
        try:
            return datetime.fromisoformat(str(quando).replace("Z", "+00:00")) >= agora
        except ValueError:
            return False

    proximos = [r for r in agendamentos if _futuro(r)]
    proximo = proximos[0] if proximos else None

    _t(client, "clientes").update(
        {
            "data_entrega": proximo["quando"] if proximo else None,
            "lembrete_minutos_antes": proximo.get("lembrete_minutos_antes") if proximo else None,
        }
    ).eq("id", str(cliente_id)).execute()


# ── reminders ──────────────────────────────────────────────────────────────

def _dispara_em(quando: Optional[str], minutos: Optional[int]) -> Optional[str]:
    if not quando or minutos is None:
        return None
    dt = datetime.fromisoformat(str(quando).replace("Z", "+00:00"))
    return (dt - timedelta(minutes=minutos)).isoformat()


def _cancelar_lembretes(client: Any, org_id: UUID, agendamento_id: str) -> None:
    pendentes = (
        _t(client, "cliente_lembretes")
        .select("id")
        .eq("org_id", str(org_id))
        .eq("agendamento_id", agendamento_id)
        .is_("enviado_em", "null")
        .is_("cancelado_em", "null")
        .execute()
    ).data or []
    for row in pendentes:
        _t(client, "cliente_lembretes").update({"cancelado_em": _now()}).eq("id", row["id"]).execute()


def _sync_lembrete(
    client: Any,
    org_id: UUID,
    cliente_id: UUID,
    agendamento_id: str,
    quando: Optional[str],
    minutos: Optional[int],
) -> Optional[str]:
    """Cancel this appointment's pending reminder, then schedule the new one.

    🔴 NOC-REMEDIATE[reminder-delivery]: `cliente_lembretes` rows are
    materialised correctly here — the right `dispara_em`, cancelled and
    rescheduled on every relevant edit — but NOTHING DELIVERS THEM. No job
    drains the pending index. Carried forward verbatim from `patch_datas`,
    which this replaces: the gap is older than agendamentos and outlives them,
    so retiring that function must not retire its marker.

    The card is honest about this by construction — it shows "Lembrete 1 hora
    antes", which is a true statement about what was SCHEDULED, and never
    claims a notification was sent. The delivery leg is a named follow-up, not
    a silently accepted gap. 2026-08-18, re-anchored 2026-08-19.

    Scoped to `agendamento_id`, never to the person — that is the whole reason
    `061` adds the column. A person-scoped cancel would kill the reminders of
    every OTHER appointment they have every time one was edited.
    """
    _cancelar_lembretes(client, org_id, agendamento_id)
    dispara = _dispara_em(quando, minutos)
    if not dispara:
        return None
    lembrete_id = str(uuid4())
    _t(client, "cliente_lembretes").insert(
        {
            "id": lembrete_id,
            "org_id": str(org_id),
            "cliente_id": str(cliente_id),
            "agendamento_id": agendamento_id,
            "dispara_em": dispara,
            "enviado_em": None,
            "cancelado_em": None,
            "destinatarios": [],
            "created_at": _now(),
        }
    ).execute()
    return lembrete_id


__all__ = [
    "AmbiguousAtendimento",
    "TIPOS",
    "atualizar",
    "criar",
    "listar",
    "remover",
    "resolve_atendimento_id",
]
