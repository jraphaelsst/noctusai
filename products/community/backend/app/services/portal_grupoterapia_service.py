"""Member-portal grupoterapia service — contract §Grupoterapia, member
side (slice BE-D).

SECURITY (non-negotiable — contract §Grupoterapia + migration 013 §5):
members carry NO RLS read on `community.grupoterapia_sessoes` (the table's
only SELECT policy is `gt_sessoes_equipe`, staff-only). Every read here
therefore:

  1. computes the member's tier level FIRST via
     `acesso_service.nivel_grupoterapia(membro, plano)`, using only data
     the caller is already allowed to read (their own `membros` row, plus
     the `planos_select_ativos_membro` policy migration 013 added
     specifically so a member can see their own active plan's name/price —
     the plan catalog isn't secret, unlike the session table); then
  2. reads sessions/reservations with the SERVICE-ROLE client — never the
     member's own — so `link_sala` is populated only AFTER the tier check
     already ran, never derived from a row the member's own client could
     have read.

Reserving a speaking seat never does check-then-insert in Python: it calls
`community.reservar_vaga_fala(p_sessao, p_membro)` via a service-role RPC.
That function row-locks the session and enforces `vagas_fala` atomically —
the race a Python read-then-write could not close under concurrent
requests for the last seat.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Any
from uuid import UUID

from app.services import acesso_service
from app.services.eventos_service import registrar_evento

_SESSOES_TABLE = "grupoterapia_sessoes"
_RESERVAS_TABLE = "grupoterapia_reservas"
_PLANOS_TABLE = "planos"

_STATUS_AGENDADA = "agendada"
_STATUS_CONFIRMADA = "confirmada"
_STATUS_CANCELADA = "cancelada"
_RESULT_LOTADA = "lotada"
_RESULT_INDISPONIVEL = "indisponivel"

_RPC_RESERVAR_VAGA_FALA = "reservar_vaga_fala"


class PortalGrupoterapiaError(Exception):
    """Domain-level failure surfaced to the router as an HTTP error."""

    def __init__(self, detail: str, *, status_code: int = 502) -> None:
        super().__init__(detail)
        self.detail = detail
        self.status_code = status_code


def _plano_for(user_client: Any, *, org_id: UUID, plano_id: str | None) -> dict | None:
    """The member's plan, read with the member's OWN client.

    `planos_select_ativos_membro` (migration 013 §2) exists for exactly
    this read: any authenticated user may see an ACTIVE plan row in their
    org. A soft-deleted (`ativo=false`) plan therefore reads as `None`
    here — `acesso_service.nivel_grupoterapia` treats a missing plan as
    `"nenhum"`, the least privilege, which is the existing behavior for
    every other consumer of that resolver, not a new rule invented here.
    """
    if not plano_id:
        return None
    result = (
        user_client.table(_PLANOS_TABLE)
        .select("*")
        .eq("org_id", str(org_id))
        .eq("id", str(plano_id))
        .maybe_single()
        .execute()
    )
    return result.data


def _session_still_running(row: dict, *, now: datetime) -> bool:
    """`inicio ≥ now − duracao` (contract §Grupoterapia) — i.e. the session
    hasn't finished yet, whether it's upcoming or already in progress."""
    inicio_raw = row.get("inicio")
    if not inicio_raw:
        return False
    try:
        inicio = datetime.fromisoformat(str(inicio_raw).replace("Z", "+00:00"))
    except ValueError:
        return False
    duracao = row.get("duracao_minutos") or 0
    fim = inicio + timedelta(minutes=duracao)
    return fim >= now


class PortalGrupoterapiaService:
    def __init__(
        self, *, user_client: Any, admin_client: Any, org_id: UUID, membro: dict,
    ) -> None:
        self._user_client = user_client
        self._admin_client = admin_client
        self._org_id = org_id
        self._membro = membro
        self._membro_id = str(membro["id"])

    def _nivel(self) -> str:
        plano = _plano_for(
            self._user_client, org_id=self._org_id, plano_id=self._membro.get("plano_id"),
        )
        return acesso_service.nivel_grupoterapia(self._membro, plano)

    # ── reads ────────────────────────────────────────────────────────

    async def listar(self) -> dict:
        nivel = self._nivel()  # computed FIRST, before any session read.

        rows = (
            self._admin_client.table(_SESSOES_TABLE)
            .select("*")
            .eq("org_id", str(self._org_id))
            .eq("status", _STATUS_AGENDADA)
            .execute()
            .data
            or []
        )
        now = datetime.now(timezone.utc)
        upcoming = [r for r in rows if _session_still_running(r, now=now)]
        upcoming.sort(key=lambda r: r.get("inicio") or "")

        sessao_ids = [str(r["id"]) for r in upcoming]
        confirmadas = self._reservantes_confirmados(sessao_ids)

        acesso = "bloqueado" if nivel == "nenhum" else nivel
        items = []
        for row in upcoming:
            sid = str(row["id"])
            reservantes = confirmadas.get(sid, set())
            vagas_restantes = max(0, (row.get("vagas_fala") or 0) - len(reservantes))
            items.append({
                "id": row["id"],
                "titulo": row.get("titulo"),
                "descricao": row.get("descricao"),
                "inicio": row.get("inicio"),
                "duracao_minutos": row.get("duracao_minutos"),
                "status": row.get("status"),
                "vagas_fala": row.get("vagas_fala"),
                "vagas_restantes": vagas_restantes,
                "minha_reserva": self._membro_id in reservantes,
                "acesso": acesso,
                # Null unless acesso != bloqueado — read with the
                # service-role client, AFTER the tier check above.
                "link_sala": row.get("link_sala") if acesso != "bloqueado" else None,
            })
        return {"nivel": nivel, "items": items}

    def _reservantes_confirmados(self, sessao_ids: list[str]) -> dict[str, set[str]]:
        if not sessao_ids:
            return {}
        rows = (
            self._admin_client.table(_RESERVAS_TABLE)
            .select("sessao_id, membro_id")
            .eq("org_id", str(self._org_id))
            .eq("status", _STATUS_CONFIRMADA)
            .in_("sessao_id", sessao_ids)
            .execute()
            .data
            or []
        )
        out: dict[str, set[str]] = {}
        for row in rows:
            sid = str(row.get("sessao_id"))
            if sid not in sessao_ids:
                continue
            out.setdefault(sid, set()).add(str(row.get("membro_id")))
        return out

    # ── writes ───────────────────────────────────────────────────────

    async def reservar(self, *, sessao_id: str, autor_id: UUID | None) -> str:
        nivel = self._nivel()
        if not acesso_service.pode(nivel, "falar"):
            raise PortalGrupoterapiaError(
                "Seu plano não inclui a vez de fala.", status_code=403,
            )
        result = self._admin_client.rpc(
            _RPC_RESERVAR_VAGA_FALA,
            {"p_sessao": str(sessao_id), "p_membro": self._membro_id},
        ).execute()
        outcome = result.data
        if outcome == _STATUS_CONFIRMADA:
            registrar_evento(
                self._admin_client,
                org_id=self._org_id,
                membro_id=self._membro_id,
                tipo="grupoterapia",
                descricao="Reservou uma vaga de fala em grupoterapia.",
                autor_id=autor_id,
            )
            return _STATUS_CONFIRMADA
        if outcome == _RESULT_LOTADA:
            raise PortalGrupoterapiaError(
                "Não há mais vagas de fala nesta sessão.", status_code=409,
            )
        if outcome == _RESULT_INDISPONIVEL:
            raise PortalGrupoterapiaError(
                "Sessão indisponível para reservas.", status_code=409,
            )
        # No silent fallback: an unrecognized RPC result is a named
        # failure, not a guessed one.
        raise PortalGrupoterapiaError("Falha ao processar a reserva.")

    async def cancelar(self, *, sessao_id: str, autor_id: UUID | None) -> None:
        """Sets the member's own confirmed reservation to `cancelada`.

        Idempotent by construction (`.eq("status", "confirmada")` in the
        filter): calling this twice, or with no reservation ever made,
        both 204 — matching the contract's undocumented-error-case DELETE
        semantics — but the timeline event only fires when a row actually
        transitioned, so a no-op cancel never writes a phantom event.
        Members have no RLS UPDATE policy on `grupoterapia_reservas`
        (`gt_reservas_equipe` is staff-only), so this is the
        service-role client — never the member's own.
        """
        result = (
            self._admin_client.table(_RESERVAS_TABLE)
            .update({"status": _STATUS_CANCELADA})
            .eq("org_id", str(self._org_id))
            .eq("sessao_id", str(sessao_id))
            .eq("membro_id", self._membro_id)
            .eq("status", _STATUS_CONFIRMADA)
            .execute()
        )
        if result.data:
            registrar_evento(
                self._admin_client,
                org_id=self._org_id,
                membro_id=self._membro_id,
                tipo="grupoterapia",
                descricao="Cancelou a reserva de fala em grupoterapia.",
                autor_id=autor_id,
            )
