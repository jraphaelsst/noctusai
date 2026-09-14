"""The card_hub routers' shared auth unpacking.

`get_current_user_org` yields `(user, token, raw_org)`; every card_hub route
needs `(user, org_uuid)`. This two-liner was copied into `router.py` and
`negociacao_estruturada_router.py`, and the contract generator's router would
have been the third copy (the N=3 recurrence rule) — so it lives here, in a
module neither router imports the other through, which is what forced the
copy in the first place (a circular import).
"""
from __future__ import annotations

from typing import Any
from uuid import UUID

from app.dependencies import coerce_org_uuid


def auth_parts(auth: tuple) -> tuple[Any, UUID]:
    user, _token, raw_org = auth
    return user, coerce_org_uuid(raw_org)


__all__ = ["auth_parts"]
