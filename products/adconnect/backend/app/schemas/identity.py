"""
Pydantic schemas for AdConnect identity foundation (Phase 1).

Mirrors `adconnect.distributors` + `adconnect.distributor_memberships`. See
`migrations/002_adconnect_identity.sql` for the canonical column shape.
"""
from __future__ import annotations

from typing import Literal, Optional

from pydantic import EmailStr, Field
from noctusai_lib.api import StrictHttpModel

DistributorStatus = Literal["ativo", "pendente", "suspenso", "inativo"]
DistributorTier = Literal["STARTER", "INSIDER", "MASTER", "SMARTER"]
MembershipRole = Literal[
    "distributor_owner",
    "distributor_member",
    "distributor_viewer",
]


class DistributorIn(StrictHttpModel):
    """Brand-admin payload to register a new distributor."""

    cnpj: str = Field(..., min_length=14, max_length=18)
    nome: str = Field(..., min_length=1, max_length=200)
    endereco_logradouro: Optional[str] = None
    endereco_numero: Optional[str] = None
    endereco_complemento: Optional[str] = None
    endereco_bairro: Optional[str] = None
    endereco_cidade: Optional[str] = None
    endereco_uf: Optional[str] = Field(default=None, max_length=2)
    endereco_cep: Optional[str] = None
    contato_nome: Optional[str] = None
    contato_email: Optional[EmailStr] = None
    contato_telefone: Optional[str] = None
    status: DistributorStatus = "ativo"
    tier: DistributorTier = "STARTER"


class DistributorOut(DistributorIn):
    id: str
    org_id: str
    created_at: Optional[str] = None
    updated_at: Optional[str] = None


class MembershipIn(StrictHttpModel):
    """Brand-admin payload to grant a user membership to a distributor."""

    user_id: str
    distributor_id: str
    role: MembershipRole = "distributor_member"


class MembershipOut(MembershipIn):
    id: str
    created_at: Optional[str] = None


class AcceptDistributorInviteIn(StrictHttpModel):
    """Payload for `/api/auth/accept-distributor-invite` (Phase 1).

    The brand admin invites a user via the seed's `team` standard router
    (which writes to `adconnect.invitations`). The user clicks the link,
    authenticates via SSO, and POSTs this payload to claim the membership.
    """

    token: str
    distributor_id: str
    role: MembershipRole = "distributor_member"
