"""
AdConnect Distributors Router — Supabase-backed.

Replaces the mock-JSON-backed shape (was `from ..data.store import store`).
The route shape is preserved verbatim where reasonable; CNPJ sub-resource
endpoints from the mock are deferred until Engineer A's Phase 1 finalizes
the distributor-CRUD service.

Endpoints (Phase 2 surface — read-side):
  • GET /distributors        — brand admin lists all in their org;
                               distributor user gets only their own.
  • GET /distributors/me     — current user's distributor.
  • GET /distributors/{id}   — fetch a distributor (admin: any in org;
                               distributor user: only their own).
"""
from __future__ import annotations

from typing import Any, Optional

from fastapi import APIRouter, Depends, HTTPException

from ..dependencies import get_current_user_org, require_role, resolve_role
from ..database import get_admin_client
from ..services import distributors_service

# Prefix is set here (rather than via main.py's router.prefix-after-construction
# loop, which is a no-op for routes already added — see findings.md).
router = APIRouter(prefix="/distributors", tags=["distributors"])


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _resolve_org_id(user: Any, org_id: Optional[str] = None) -> str:
    """Read brand ``org_id`` from the auth-resolved triple's ``org_id``
    (canonical), falling back to ``user.user_metadata.org_id``, then the
    single-instance default."""
    if org_id:
        return str(org_id)
    metadata = getattr(user, "user_metadata", None) or {}
    return str(metadata.get("org_id") or "00000000-0000-0000-0000-000000000001")


def _check_visibility(user: Any, distributor: dict[str, Any], auth_org_id: Optional[str] = None) -> None:
    """Enforce: brand admin in same org OR distributor user with matching id."""
    role = resolve_role(user).lower()
    org_id = _resolve_org_id(user, auth_org_id)
    if role == "admin" and str(distributor.get("org_id")) == org_id:
        return
    metadata = getattr(user, "user_metadata", None) or {}
    user_did = metadata.get("distributor_id") or metadata.get("distributorId")
    if user_did and str(user_did) == str(distributor.get("id")):
        return
    raise HTTPException(403)


# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------


@router.get("")
def list_all(
    auth: tuple = Depends(require_role("admin")),
) -> dict[str, Any]:
    """List every distributor in the brand's org. Admin only."""
    user, _token, _role = auth
    db = get_admin_client()
    org_id = _resolve_org_id(user)
    rows = distributors_service.list_distributors_for_brand(db, org_id=org_id)
    return {"data": rows}


@router.get("/me")
def me(auth: tuple = Depends(get_current_user_org)) -> dict[str, Any]:
    """Return the current user's distributor.

    Distributor users have a `distributor_id` in `user_metadata` (synced from
    `distributor_memberships`). Brand admins do not have a single distributor
    → 401 (the brand admin uses GET / instead).
    """
    user, _token, _org_id = auth
    metadata = getattr(user, "user_metadata", None) or {}
    did = metadata.get("distributor_id") or metadata.get("distributorId")
    if not did:
        # Multi-distributor / lookup path: query memberships from the user_id.
        user_id = getattr(user, "id", None)
        if user_id:
            db = get_admin_client()
            rows = distributors_service.list_distributors_for_user(
                db, user_id=str(user_id)
            )
            if rows:
                return rows[0]
        raise HTTPException(401)
    db = get_admin_client()
    distributor = distributors_service.get_distributor(db, distributor_id=str(did))
    if not distributor:
        raise HTTPException(404, "Distribuidor não encontrado")
    return distributor


@router.get("/{id}")
def get_one(
    id: str,
    auth: tuple = Depends(get_current_user_org),
) -> dict[str, Any]:
    """Fetch a distributor by id (admin: any in org; user: only own)."""
    user, _token, auth_org_id = auth
    db = get_admin_client()
    distributor = distributors_service.get_distributor(db, distributor_id=id)
    if not distributor:
        raise HTTPException(404, "Distribuidor não encontrado")
    _check_visibility(user, distributor, auth_org_id)
    return distributor
