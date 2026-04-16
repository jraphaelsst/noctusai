"""
Shared page status utilities for dev-gated page visibility.

Each product schema has a ``status_pagina`` table. This module provides
helpers for querying visible pages based on user role.

Status values:
- ``producao``        — visible to all users
- ``desenvolvimento`` — visible ONLY to dev + owner roles
- ``desativado``      — hidden from everyone
"""
from __future__ import annotations

from noctusai_shared.roles import DEV_ROLES


def get_visible_pages(db, user_org_role: str | None = None) -> list[str]:
    """Return list of visible page route names for the given user role.

    If the user is dev/owner, all non-desativado pages are visible.
    Otherwise only producao pages are visible.
    """
    if user_org_role in DEV_ROLES:
        result = db.table("status_pagina").select("nome_pagina").neq(
            "status", "desativado"
        ).execute()
    else:
        result = db.table("status_pagina").select("nome_pagina").eq(
            "status", "producao"
        ).execute()

    return [row["nome_pagina"] for row in (result.data or [])]
