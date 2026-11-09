"""Who may do what on a roteiro — the caller as the roteiro services see it (CONTRACT roteiro-ciclo §1/§2).

`pode_supervisionar_roteiros(user, org) = org role in {owner, admin} OR papel 'supervisor'`.

SEED-FIRST CHECK (2026-11-09): the seed knows one `org_role` per user per org (`noctusai_lib.primitives.roles`,
`noctus_users` / `org_memberships`) and no additive per-product role, so the `supervisor` lives in this product's own
`usuario_papeis` (migration 338). The org role is read from the TRUSTED `noctus_users` row via the seed's
`resolve_org_role_for` — never `user_metadata`, which the user can rewrite.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional
from uuid import UUID

from noctusai_lib.api.auth.session import ADMIN_ORG_ROLES, resolve_org_role_for

from app.services import table_reads

PAPEIS_TABLE = "usuario_papeis"
PAPEL_SUPERVISOR = "supervisor"


@dataclass(frozen=True)
class Ator:
    """The caller, reduced to what the roteiro rules need. `None` everywhere = no identity, no privilege."""

    usuario_id: Optional[str] = None
    pode_supervisionar: bool = False
    #: `public` client, only to join user NAMES onto a roteiro (`gerado_por_nome`); never part of identity.
    core_client: Any = field(default=None, compare=False, repr=False)


SEM_ATOR = Ator()


def tem_papel_supervisor(client: Any, org_id: UUID, usuario_id: Any) -> bool:
    """Is there a `supervisor` row for (org, user)? Service client only — the table has no browser grant."""
    if not usuario_id:
        return False
    rows = (
        table_reads.table(client, PAPEIS_TABLE)
        .select("user_id")
        .eq("org_id", str(org_id))
        .eq("user_id", str(usuario_id))
        .eq("papel", PAPEL_SUPERVISOR)
        .limit(1)
        .execute()
    ).data or []
    return bool(rows)


def pode_supervisionar_roteiros(
    client: Any, core_client: Any, auth: Any, org_id: UUID, request: Any = None
) -> bool:
    """owner/admin of the SELECTED org (trusted row, B3) or a `supervisor` of it."""
    user = auth[0]
    usuario_id = getattr(user, "id", None)
    if not usuario_id:
        return False
    if resolve_org_role_for(core_client, auth, request) in ADMIN_ORG_ROLES:
        return True
    return tem_papel_supervisor(client, org_id, usuario_id)


def ator_da_requisicao(
    client: Any, core_client: Any, auth: Any, org_id: UUID, request: Any = None
) -> Ator:
    user = auth[0]
    usuario_id = getattr(user, "id", None)
    return Ator(
        usuario_id=str(usuario_id) if usuario_id else None,
        pode_supervisionar=pode_supervisionar_roteiros(client, core_client, auth, org_id, request),
        core_client=core_client,
    )
