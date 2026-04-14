"""
{{PRODUCT_NAME}} — Team management router (invitation-based).

Uses shared invitation helpers from noctusai_shared.invitations.
Customize roles and accept logic for your product.

POST   /api/team/invite              — Invite member (admin only)
POST   /api/team/accept              — Accept invitation (public)
GET    /api/team/accept/validate     — Validate invitation token (public)
GET    /api/team                     — List team members
GET    /api/team/invitations         — List pending invitations
DELETE /api/team/invitations/{id}    — Cancel invitation
DELETE /api/team/{user_id}           — Remove member
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, Field

from app.database import get_admin_client
from app.dependencies import get_current_user, get_user_role
from noctusai_shared.invitations import (
    create_invitation,
    validate_invitation,
    accept_invitation as mark_accepted,
    cancel_invitation,
    list_pending_invitations,
)
from noctusai_shared.email_templates import send_product_invitation_email
from noctusai_shared.roles import ORG_ROLE_LABELS

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/team", tags=["Team"])

# TODO: Replace with your product's valid roles
VALID_ROLES = ("admin", "member")
INVITATIONS_TABLE = "invitations"
PRODUCT_NAME = "{{PRODUCT_NAME}}"


# ── Schemas ──────────────────────────────────────────────────

class InviteBody(BaseModel):
    email: str = Field(..., max_length=255)
    role: str = Field(default="member", max_length=50)


class AcceptBody(BaseModel):
    token: str = Field(..., max_length=128)
    nome: str = Field(..., min_length=2, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)


# ── Helpers ──────────────────────────────────────────────────

def _require_admin(user):
    """Raise 403 if user is not an admin."""
    role = get_user_role(user)
    if role != "platform_admin":
        raise HTTPException(status_code=403, detail="Acesso restrito a administradores")


# ── Endpoints ────────────────────────────────────────────────

# TODO: Implement endpoints following the ERP team.py pattern.
# See products/erp-imobiliario/backend/app/routers/team.py for reference.
# Key endpoints: invite, accept, validate, list, cancel, remove.
