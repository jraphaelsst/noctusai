"""Shared plumbing for the contracts services: the org `Scope`.

Every service function takes a `Scope(db, cfg, org_id)`; EVERY query it issues is filtered by that
org, so an id from another org is indistinguishable from a missing one (404). RLS is the floor.

Scope + row helpers are the shared `_organ_common`; the date arithmetic (`add_months` anchors, `to_date`) is finance's, imported not copied.
"""
from __future__ import annotations

from dataclasses import dataclass

from noctusai_lib.domain._organ_common import OrganScope, first, like_term, new_id, now_iso
from noctusai_lib.domain.finance._common import add_months, iso, month_start, to_date, today

from .config import ContractsConfig
from .errors import invalid


@dataclass(frozen=True)
class Scope(OrganScope):
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    cfg: ContractsConfig

    def _invalid(self, field: str, message: str, code: str) -> Exception:
        return invalid(field, message, code=code)


__all__ = ["Scope", "add_months", "first", "iso", "like_term", "month_start", "new_id", "now_iso", "to_date", "today"]
