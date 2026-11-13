"""`ApprovalService` -- submit a versao of a subject, approve or reject it, ask where it stands.

Any org member may decide (the host decides who may CALL these); approval is always required: a subject nobody submitted, or
whose current versao nobody approved, is NOT approved. Only the CURRENT versao can be decided; submitting a newer one makes
the previous decision history. Every change is an immutable event (`submitted` / `approved` / `rejected`).
"""
from __future__ import annotations

import re
import uuid
from dataclasses import dataclass
from typing import Any, Optional

from .config import ApprovalsConfig
from .errors import (
    JA_DECIDIDO, MOTIVO_OBRIGATORIO, SEM_SUBMISSAO, VERSAO_OBSOLETA, AlreadyDecided, ApprovalError, NotSubmitted, StaleVersion,
    conflict, invalid,
)
from .store import T_EVENTS, ApprovalStore
from .types import (
    DECISION_EVENTS, EVENT_APPROVED, EVENT_REJECTED, EVENT_SUBMITTED, STATUS_APPROVED, STATUS_NONE, STATUS_PENDING, STATUS_REJECTED,
)

_KIND = re.compile(r"^[a-z][a-z0-9_]{0,39}$")
_STATUS_OF = {EVENT_APPROVED: STATUS_APPROVED, EVENT_REJECTED: STATUS_REJECTED}


@dataclass(frozen=True)
class ApprovalState:
    """Where the CURRENT versao of a subject stands (`status` none = nothing submitted)."""

    subject_kind: str
    subject_id: str
    versao: Optional[int]
    status: str
    decided_by: Optional[str] = None
    decided_at: Optional[str] = None
    motivo: Optional[str] = None


class ApprovalService:
    def __init__(self, store: ApprovalStore, cfg: ApprovalsConfig) -> None:
        self._s, self._cfg = store, cfg

    # -- writes ------------------------------------------------------------------------------------------------
    def submit(self, org_id: str, subject_kind: str, subject_id: str, versao: int, *, actor_id: Optional[str] = None,
               note: Optional[str] = None) -> ApprovalState:
        """Put `versao` up for approval. The same versao again is a no-op; a lower one is refused."""
        return self._record(org_id, subject_kind, subject_id, versao, EVENT_SUBMITTED, actor_id, None, note)

    def approve(self, org_id: str, subject_kind: str, subject_id: str, versao: int, *, actor_id: Optional[str] = None,
                note: Optional[str] = None) -> ApprovalState:
        return self._record(org_id, subject_kind, subject_id, versao, EVENT_APPROVED, actor_id, None, note)

    def reject(self, org_id: str, subject_kind: str, subject_id: str, versao: int, *, actor_id: Optional[str] = None,
               motivo: Optional[str] = None, note: Optional[str] = None) -> ApprovalState:
        motivo = (motivo or "").strip()
        if not motivo:
            raise ApprovalError(MOTIVO_OBRIGATORIO, "Informe o motivo da rejeição.", 422, field="motivo")
        return self._record(org_id, subject_kind, subject_id, versao, EVENT_REJECTED, actor_id, motivo, note)

    def _record(self, org_id: str, kind: str, subject_id: str, versao: Any, event: str, actor_id: Optional[str],
                motivo: Optional[str], note: Optional[str]) -> ApprovalState:
        self._check(kind, subject_id, versao)
        row = {"subject_kind": kind, "subject_id": str(subject_id), "versao": int(versao), "event": event,
               "actor_id": actor_id, "motivo": motivo, "note": note}
        try:
            self._s.ledger.record(org_id, row)
        except StaleVersion as exc:
            raise conflict(VERSAO_OBSOLETA, "Esta versão não é mais a atual: recarregue e decida sobre a versão vigente.",
                           versao=int(versao)) from exc
        except NotSubmitted as exc:
            raise ApprovalError(SEM_SUBMISSAO, "Nada foi enviado para aprovação.", 409) from exc
        except AlreadyDecided as exc:
            raise conflict(JA_DECIDIDO, "Esta versão já foi decidida.", versao=int(versao)) from exc
        return self.state(org_id, kind, subject_id)

    @staticmethod
    def _check(kind: str, subject_id: str, versao: Any) -> None:
        if not isinstance(kind, str) or not _KIND.match(kind):
            raise invalid("subject_kind", "Tipo de item inválido.")
        try:
            uuid.UUID(str(subject_id))
        except ValueError:
            raise invalid("subject_id", "Identificador do item inválido.") from None
        if isinstance(versao, bool) or not isinstance(versao, int) or versao < 1:
            raise invalid("versao", "A versão deve ser um inteiro positivo.")

    # -- reads -------------------------------------------------------------------------------------------------
    def history(self, org_id: str, subject_kind: str, subject_id: str) -> list[dict]:
        """Every event of the subject, oldest first (the audit trail)."""
        return self._s.tables.select(T_EVENTS, org_id, eq={"subject_kind": subject_kind, "subject_id": str(subject_id)},
                                     order=[("created_at", False), ("versao", False)])

    def state(self, org_id: str, subject_kind: str, subject_id: str) -> ApprovalState:
        events = self.history(org_id, subject_kind, subject_id)
        submitted = [e["versao"] for e in events if e["event"] == EVENT_SUBMITTED]
        if not submitted:
            return ApprovalState(subject_kind, str(subject_id), None, STATUS_NONE)
        current = max(submitted)
        decision = next((e for e in events if e["versao"] == current and e["event"] in DECISION_EVENTS), None)
        if decision is None:
            return ApprovalState(subject_kind, str(subject_id), current, STATUS_PENDING)
        return ApprovalState(subject_kind, str(subject_id), current, _STATUS_OF[decision["event"]], decision.get("actor_id"),
                             decision.get("created_at"), decision.get("motivo"))

    def is_approved(self, org_id: str, subject_kind: str, subject_id: str, versao: Optional[int] = None) -> bool:
        """True only when the CURRENT versao is approved (and equals `versao` when given). Absence is never a pass."""
        state = self.state(org_id, subject_kind, subject_id)
        return state.status == STATUS_APPROVED and (versao is None or versao == state.versao)


__all__ = ["ApprovalService", "ApprovalState"]
