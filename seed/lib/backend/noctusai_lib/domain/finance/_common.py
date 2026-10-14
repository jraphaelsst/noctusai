"""Shared plumbing for the finance services: the org `Scope`, row helpers, dates.

Every service function takes a `Scope(db, cfg, org_id)`; EVERY query it issues is
filtered by that org, so an id from another org is indistinguishable from a
missing one (404). RLS is the floor, never the only check (contract §0).
"""
from __future__ import annotations

import calendar
from dataclasses import dataclass
from datetime import date, datetime
from typing import Any, Optional

from noctusai_lib.domain._organ_common import OrganScope, digits, first, like_term, new_id, now, now_iso

from .config import FinanceConfig
from .errors import invalid


def today() -> date:
    return now().date()


def to_date(value: Any) -> Optional[date]:
    """`date` | ISO string (date or datetime) | None -> `date` | None."""
    if value is None or value == "":
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    return date.fromisoformat(str(value)[:10])


def iso(value: Any) -> Optional[str]:
    d = to_date(value)
    return d.isoformat() if d else None


def month_start(value: Any) -> date:
    d = to_date(value)
    assert d is not None
    return d.replace(day=1)


def add_months(d: date, months: int, anchor_day: Optional[int] = None) -> date:
    """`d` + `months`, keeping `anchor_day` (default `d.day`) clamped to the month's last day.

    Anchoring matters: Jan 31 -> Feb 28 -> Mar 28 would drift; with the anchor
    kept at 31 it goes Feb 28 -> Mar 31.
    """
    total = d.year * 12 + (d.month - 1) + months
    year, month = divmod(total, 12)
    month += 1
    day = min(anchor_day or d.day, calendar.monthrange(year, month)[1])
    return date(year, month, day)


@dataclass(frozen=True)
class Scope(OrganScope):
    """`(db, cfg, org_id)` -- the unit every service function operates on (see `_organ_common.OrganScope`)."""

    cfg: FinanceConfig

    def _invalid(self, field: str, message: str, code: str) -> Exception:
        return invalid(field, message, code=code)


__all__ = [
    "Scope",
    "add_months",
    "digits",
    "first",
    "iso",
    "like_term",
    "month_start",
    "new_id",
    "now",
    "now_iso",
    "to_date",
    "today",
]
