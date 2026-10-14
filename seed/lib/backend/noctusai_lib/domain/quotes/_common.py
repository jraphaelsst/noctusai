"""Shared plumbing for the quote services: the org `Scope` (see `_organ_common`) and the org's civil day.

Every service function takes a `Scope(db, cfg, org_id)`; EVERY query it issues is filtered by that org, so an id
from another org is indistinguishable from a missing one (404). RLS is the floor, never the only check.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Optional

from noctusai_lib.domain._organ_common import OrganScope, first, like_term, new_id, now_iso

from .config import QuotesConfig
from .errors import invalid


def dec(value: Any) -> Decimal:
    """A PostgREST numeric (float / str / int / None) -> exact `Decimal` (via `str`, never the float repr)."""
    if value is None or value == "":
        return Decimal(0)
    return value if isinstance(value, Decimal) else Decimal(str(value))


def to_date(value: Any) -> Optional[date]:
    """`date` | ISO string (date or datetime) | None -> `date` | None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def local_today(cfg: QuotesConfig, at: Optional[datetime] = None) -> date:
    """The org's civil day (a container's UTC `date.today()` disagrees with Brazil for hours every evening)."""
    return (at or datetime.now(timezone.utc)).astimezone(cfg.tz).date()


@dataclass(frozen=True)
class Scope(OrganScope):
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    cfg: QuotesConfig

    def _invalid(self, field: str, message: str, code: str) -> Exception:
        return invalid(field, message, code=code)


__all__ = ["Scope", "dec", "first", "like_term", "local_today", "new_id", "now_iso", "to_date"]
