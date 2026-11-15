"""Approvals errors. `ApprovalError` is an `AppException` (pt-BR, stable `code`); the ledger exceptions are what the atomic write raises."""
from __future__ import annotations

from noctusai_lib.domain._organ_common import OrganError, error_factories

MOTIVO_OBRIGATORIO = "motivo_obrigatorio"
VERSAO_OBSOLETA = "versao_obsoleta"
SEM_SUBMISSAO = "sem_submissao"
JA_DECIDIDO = "ja_decidido"


class ApprovalError(OrganError):
    """An approvals refusal carrying its stable machine `code`."""


invalid, conflict = error_factories(ApprovalError)


class StaleVersion(Exception):
    """The versao is not the subject's current one (it was edited and resubmitted, or a newer one already exists)."""


class NotSubmitted(Exception):
    """Nothing was ever submitted for this subject: there is nothing to decide."""


class AlreadyDecided(Exception):
    """This versao already has its (single) decision."""


__all__ = [
    "AlreadyDecided", "ApprovalError", "JA_DECIDIDO", "MOTIVO_OBRIGATORIO", "NotSubmitted", "SEM_SUBMISSAO", "StaleVersion",
    "VERSAO_OBSOLETA", "conflict", "invalid",
]
