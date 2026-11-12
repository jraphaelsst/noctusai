"""Page keys of the assignment organ: what a CRM module declares so `GET /api/modules` / `status_pagina` know the two pages.

    from noctusai_seed.modules import ModuleSpec
    from noctusai_seed.modules.assignment import assignment_pages
    crm = ModuleSpec(key="crm", organs=[mount_assignment(...)], pages=(*lead_pages, *assignment_pages()))

The keys + default paths are the FE `ASSIGNMENT_PAGE_KEYS` / `ASSIGNMENT_DEFAULT_PATHS` of `@noctusai/lib` `assignment/pages.tsx`;
`tests/test_assignment_pages.py` parses that file and fails on divergence. A market may move a page (`paths=`) or relabel it
(`labels=`) exactly as `assignmentModuleItems` does on the FE side.
"""
from __future__ import annotations

from typing import Mapping, Optional

from noctusai_seed.modules.spec import PageSpec

ASSIGNMENT_PAGE_KEYS: Mapping[str, str] = {"rules": "crm_distribuicao", "teams": "crm_equipes"}
ASSIGNMENT_DEFAULT_PATHS: Mapping[str, str] = {"rules": "/crm/distribuicao", "teams": "/crm/equipes"}
ASSIGNMENT_DEFAULT_LABELS: Mapping[str, str] = {"rules": "Distribuição", "teams": "Equipes"}

__all__ = ["ASSIGNMENT_DEFAULT_LABELS", "ASSIGNMENT_DEFAULT_PATHS", "ASSIGNMENT_PAGE_KEYS", "assignment_pages"]


def assignment_pages(
    *,
    paths: Optional[Mapping[str, str]] = None,
    labels: Optional[Mapping[str, str]] = None,
    status: Optional[str] = None,
) -> tuple[PageSpec, ...]:
    """The two `PageSpec`s (rules page, teams page). Unknown override keys are an error, not silently ignored."""
    for name, given in (("paths", paths), ("labels", labels)):
        unknown = set(given or {}) - set(ASSIGNMENT_PAGE_KEYS)
        if unknown:
            raise ValueError(f"assignment_pages({name}=...) names unknown pages {sorted(unknown)}; known: {sorted(ASSIGNMENT_PAGE_KEYS)}")
    extra = {"status": status} if status else {}
    return tuple(
        PageSpec(
            key=ASSIGNMENT_PAGE_KEYS[k],
            path=(paths or {}).get(k, ASSIGNMENT_DEFAULT_PATHS[k]),
            label=(labels or {}).get(k, ASSIGNMENT_DEFAULT_LABELS[k]),
            **extra,
        )
        for k in ("rules", "teams")
    )
