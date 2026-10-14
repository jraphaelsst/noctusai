"""Shared plumbing for the items services: the org `Scope` (see `_organ_common`) and row helpers.

Every query is filtered by `org_id`, so an id from another org is indistinguishable from a missing one
(404). RLS is the floor, never the only check.
"""
from __future__ import annotations

from dataclasses import dataclass

from noctusai_lib.domain._organ_common import OrganScope, first, like_term_wildcard as like_term, new_id, now_iso

from .config import ItemsConfig
from .errors import invalid


@dataclass(frozen=True)
class Scope(OrganScope):
    """`(db, cfg, org_id)` -- the unit every service function operates on."""

    cfg: ItemsConfig

    def _invalid(self, field: str, message: str, code: str) -> Exception:
        return invalid(field, message, code=code)


__all__ = ["Scope", "first", "like_term", "new_id", "now_iso"]
