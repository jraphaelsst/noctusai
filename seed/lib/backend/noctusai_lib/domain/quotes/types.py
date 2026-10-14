"""Quote vocabulary. `str` Enums: a value serialises as its bare string and feeds the SQL CHECKs.

Renaming a member is a wire-contract change, never a refactor.
"""
from __future__ import annotations

from enum import Enum


class _StrEnum(str, Enum):
    def __str__(self) -> str:  # pragma: no cover - cosmetic
        return self.value


class QuoteStatus(_StrEnum):
    DRAFT = "draft"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"


class LineKind(_StrEnum):
    """What a line sells -- drives the convert-on-accept target (goods -> order, services -> contract)."""

    GOODS = "goods"
    SERVICE = "service"


class ConvertTo(_StrEnum):
    ORDER = "order"
    CONTRACT = "contract"
    NONE = "none"


class ConversionStatus(_StrEnum):
    NONE = "none"          # nothing to convert yet (not accepted / convert_to = none)
    PENDING = "pending"    # accepted; the handler has not run (or is running)
    DONE = "done"
    FAILED = "failed"      # the handler raised: retry with POST /{id}/convert
    SKIPPED = "skipped"    # the host wired no handler (no-op default): retry once one is wired


class Decision(_StrEnum):
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class Channel(_StrEnum):
    PUBLIC_LINK = "public_link"
    STAFF = "staff"


class EventKind(_StrEnum):
    CREATED = "created"
    UPDATED = "updated"
    DELETED = "deleted"
    SENT = "sent"
    VIEWED = "viewed"
    ACCEPTED = "accepted"
    REJECTED = "rejected"
    EXPIRED = "expired"
    SUPERSEDED = "superseded"
    VERSIONED = "versioned"
    CONVERTED = "converted"
    CONVERSION_FAILED = "conversion_failed"
    SIGNATURE_REQUESTED = "signature_requested"
    SIGNATURE_UPDATED = "signature_updated"


#: Statuses a customer / staff can still decide on.
OPEN_STATUSES = (QuoteStatus.SENT.value, QuoteStatus.VIEWED.value)
#: Statuses a revision may start from (accepted is final; a draft is edited in place).
REVISABLE_STATUSES = (
    QuoteStatus.SENT.value,
    QuoteStatus.VIEWED.value,
    QuoteStatus.REJECTED.value,
    QuoteStatus.EXPIRED.value,
)


def values(enum_cls: type[Enum]) -> tuple[str, ...]:
    return tuple(member.value for member in enum_cls)


__all__ = [
    "Channel",
    "ConversionStatus",
    "ConvertTo",
    "Decision",
    "EventKind",
    "LineKind",
    "OPEN_STATUSES",
    "QuoteStatus",
    "REVISABLE_STATUSES",
    "values",
]
