"""Canonical module-group keys and the page vocabulary shared by BE ``ModuleSpec`` and FE ``defineModule``.

``MODULE_GROUP_KEYS`` mirrors ``MODULE_GROUP_ORDER`` in
``seed/lib/frontend/src/design-system/components/nav-groups.ts`` (the sidebar order). A seed test parses that
TypeScript file and fails on divergence, so the two sides cannot drift silently.
"""
from __future__ import annotations

import re

__all__ = [
    "MODULE_GROUP_KEYS",
    "PAGE_STATUSES",
    "PAGE_STATUS_DEFAULT",
    "MODULE_PERMISSION_LEVELS",
    "is_valid_page_key",
    "is_valid_enablement_key",
]

#: Same keys, same order as the FE `MODULE_GROUP_ORDER`.
MODULE_GROUP_KEYS: tuple[str, ...] = (
    "crm",
    "redes-sociais",
    "erp",
    "cms",
    "corestudio",
    "banib",
    "emissoes",
    "integracoes",
    "configuracoes",
)

#: `status_pagina.status` vocabulary (`noctusai_lib.domain.page_status`).
PAGE_STATUSES: tuple[str, ...] = ("producao", "desenvolvimento", "desativado")
PAGE_STATUS_DEFAULT = "producao"

#: A module permission names the lowest org role that may use it: any org `member`, or an org `admin`.
MODULE_PERMISSION_LEVELS: tuple[str, ...] = ("member", "admin")

_PAGE_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_./-]{0,79}$")
_ENABLEMENT_KEY_RE = re.compile(r"^[a-z0-9][a-z0-9_-]{0,59}$")


def is_valid_page_key(value: str) -> bool:
    """A `status_pagina.nome_pagina` shape: lowercase, digits, `_ . / -`, starts alphanumeric."""
    return bool(_PAGE_KEY_RE.match(value or ""))


def is_valid_enablement_key(value: str) -> bool:
    return bool(_ENABLEMENT_KEY_RE.match(value or ""))
