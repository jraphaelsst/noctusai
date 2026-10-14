"""Contracts vocabulary: status flow, billing models, frequencies, readjustment indexes.

`str` Enums (wire value == the literal the frontend organ mirrors). Renaming a member is a
wire-contract change, never a refactor: `values()` feeds the SQL CHECKs and the parity tests.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class ContractStatus(_StrEnum):
    """draft -> active <-> suspended -> terminated | expired. `terminated` / `expired` are final."""

    DRAFT = "draft"
    ACTIVE = "active"
    SUSPENDED = "suspended"
    TERMINATED = "terminated"
    EXPIRED = "expired"


class BillingModel(_StrEnum):
    """The seam every contract bills through (one value per contract)."""

    ONE_TIME = "one_time"
    INSTALLMENTS = "installments"
    RECURRING = "recurring"
    RETAINER = "retainer"


class BillingFrequency(_StrEnum):
    """Period of a `recurring` contract (a `retainer` is always monthly)."""

    MONTHLY = "monthly"
    QUARTERLY = "quarterly"
    YEARLY = "yearly"


class ReadjustmentIndex(_StrEnum):
    """A STORED choice. v1 never fetches the index value: the operator types the percentage."""

    NONE = "none"
    IPCA = "IPCA"
    IGPM = "IGPM"
    INPC = "INPC"
    FIXED = "fixed"


class VersionKind(_StrEnum):
    INITIAL = "initial"
    AMENDMENT = "amendment"
    READJUSTMENT = "readjustment"
    RENEWAL = "renewal"
    SUSPENSION = "suspension"
    RESUMPTION = "resumption"
    TERMINATION = "termination"


class BillingKind(_StrEnum):
    FIXED = "fixed"
    EXCESS = "excess"
    PENALTY = "penalty"


class AttachmentKind(_StrEnum):
    CONTRACT = "contract"
    SIGNED = "signed"
    OTHER = "other"


class SignatureStatus(_StrEnum):
    NONE = "none"
    PENDING = "pendente"
    PARTIAL = "parcial"
    DONE = "concluido"
    CANCELLED = "cancelado"
    EXPIRED = "expirado"


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    """The wire values of an enum, in declaration order (SQL CHECKs + parity tests)."""
    return tuple(member.value for member in enum_cls)


#: Final statuses -- nothing but reads is allowed on them.
FINAL_STATUSES = (ContractStatus.TERMINATED.value, ContractStatus.EXPIRED.value)

__all__ = [
    "AttachmentKind", "BillingFrequency", "BillingKind", "BillingModel", "ContractStatus", "FINAL_STATUSES",
    "ReadjustmentIndex", "SignatureStatus", "VersionKind", "values",
]
