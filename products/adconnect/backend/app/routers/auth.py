"""
AdConnect auth router — Phase 1 (Option A: distributor-as-noc-user).

Replaces the previous custom-JWT scaffold. SSO comes from the seed's
standard surface (Supabase auth — no `/api/auth/login` here, no password
hashing, no `_seed_users()` bootstrap). The only AdConnect-specific
endpoint is the distributor-invitation acceptance flow:

    POST /api/auth/accept-distributor-invite
        Validates an invitation token (seed-managed, written to
        `adconnect.invitations` by the seed's team router); creates a
        matching `adconnect.distributor_memberships` row tying the
        currently-authenticated user to the named distributor.

The legacy `GET /api/auth/me` is kept as a thin wrapper around the seed's
get_current_user so the frontend's session-bootstrap call path doesn't
break during the swap. Authoritative user / org info comes from the
seed's standard surface; this is just the dict-shaped projection legacy
callers expect.
"""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status

from ..auth_deps import get_current_user
from .. import database as _database
from ..schemas.identity import AcceptDistributorInviteIn, MembershipOut


def _get_admin_client():
    """Lazy admin-client lookup — resolves through the class MRO at call
    time so `tests/conftest.py`'s patch on
    `noctusai_seed.database.DatabaseModule.get_admin_client` takes
    effect (the bound method captured at `database.py` import is
    pre-patch and would defeat the fixture).
    """
    return _database._db.get_admin_client()

# Constructor-time prefix — assigning `router.prefix = "/auth"` after the
# `@router.<verb>(...)` decorators are evaluated is a no-op for already-
# registered routes (FastAPI captures the prefix at route-registration time,
# not at include_router time). The MVP project's main.py loop assigned
# `/auth` post-construction and the routes silently mounted at `/me` /
# `/accept-distributor-invite` (bare). Match the seed convention with the
# `/api/...` prefix the test suite already targets. (Per Phase 3 of the
# closed MVP: cart/orders/distributors moved to constructor-time prefixes
# for the same structural reason.)
#
# Picked up by `adconnect-test-conftest-distributor-binding` Phase 1 as a
# drive-by structural fix that closes 9 of the 19 baseline failures.
router = APIRouter(prefix="/api/auth", tags=["auth"])


@router.get("/me")
def me(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    """Return the current user as the dict-shape legacy callers expect.

    The seed framework owns the canonical session payload at
    `/api/auth/session` (mounted by core); this endpoint exists only to
    preserve the AdConnect-specific projection (`{ id, email, role,
    distributorId }`) historic frontend code reads.
    """
    return {
        "id": current.get("sub"),
        "email": current.get("email"),
        "role": current.get("role"),
        "distributorId": current.get("distributorId"),
    }


@router.post(
    "/accept-distributor-invite",
    status_code=status.HTTP_201_CREATED,
    response_model=MembershipOut,
)
def accept_distributor_invite(
    body: AcceptDistributorInviteIn,
    current: dict[str, Any] = Depends(get_current_user),
) -> dict[str, Any]:
    """Convert a brand-issued invitation into a distributor membership.

    Flow:
      1. Brand admin invites the user via the seed's team router
         (`POST /api/team/invite` → row in `adconnect.invitations`).
      2. User clicks the link, signs in via SSO, lands here.
      3. We validate the token exists in `adconnect.invitations` with
         `status='pending'` and is not expired, mark it `accepted`, and
         insert a `distributor_memberships` row.
      4. Returns the new membership row.

    Failure modes:
      - 404 if the token is not found.
      - 410 if the token is expired or already accepted/canceled.
      - 403 if the invitation's org doesn't own the named distributor.
    """
    if not current.get("sub"):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Sessao invalida")

    admin = _get_admin_client()

    # 1. Look up the invitation
    inv_resp = (
        admin.table("invitations")
        .select("*")
        .eq("token", body.token)
        .limit(1)
        .execute()
    )
    inv_rows = inv_resp.data or []
    if not inv_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Convite nao encontrado")
    invitation = inv_rows[0]

    if invitation.get("status") != "pending":
        raise HTTPException(status.HTTP_410_GONE, "Convite ja consumido ou cancelado")
    expires_at = invitation.get("expires_at")
    if expires_at:
        try:
            exp = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
            if exp < datetime.now(timezone.utc):
                raise HTTPException(status.HTTP_410_GONE, "Convite expirado")
        except (TypeError, ValueError):
            # Malformed expires_at on the row — surface as gone rather
            # than silently accepting; better-explicit than implicit.
            raise HTTPException(status.HTTP_410_GONE, "Convite com data invalida")

    # 2. Validate the named distributor belongs to the invitation's org
    dist_resp = (
        admin.table("distributors")
        .select("id, org_id")
        .eq("id", body.distributor_id)
        .limit(1)
        .execute()
    )
    dist_rows = dist_resp.data or []
    if not dist_rows:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "Distribuidor nao encontrado")
    if dist_rows[0].get("org_id") != invitation.get("org_id"):
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Convite nao corresponde ao distribuidor")

    # 3. Insert membership row (UNIQUE constraint protects against double-claim)
    membership_resp = (
        admin.table("distributor_memberships")
        .insert({
            "user_id": current["sub"],
            "distributor_id": body.distributor_id,
            "role": body.role,
        })
        .execute()
    )
    rows = membership_resp.data or []
    if not rows:
        raise HTTPException(
            status.HTTP_500_INTERNAL_SERVER_ERROR,
            "Falha ao criar associacao com distribuidor",
        )

    # 4. Mark invitation accepted
    admin.table("invitations").update(
        {"status": "accepted"}
    ).eq("id", invitation["id"]).execute()

    return rows[0]
