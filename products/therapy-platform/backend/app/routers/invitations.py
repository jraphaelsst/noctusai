"""
Invitations Router — Multi-type invitation system for the Therapy Platform.

Supports 6 invite types with role-based permission checks:
- platform_to_clinic: platform_admin invites a new clinic (creates clinic + clinic_admin)
- platform_to_therapist: platform_admin invites independent therapist
- clinic_to_therapist: clinic_admin invites therapist to their clinic
- clinic_to_patient: clinic_admin invites patient to their clinic
- therapist_to_patient: therapist invites patient (bound_to = therapist)
- therapist_to_therapist: therapist invites another therapist (no binding)

Permissions:
- platform_admin: all types
- clinic_admin: clinic_to_therapist, clinic_to_patient (own clinic only)
- therapist: therapist_to_patient, therapist_to_therapist
- patient: cannot invite
"""
import logging
from typing import Literal, Optional

from fastapi import APIRouter, Header, HTTPException, Query
from pydantic import BaseModel, EmailStr, Field

from app.dependencies import (
    get_admin_client,
    get_clinic_id_for_user,
    get_current_user,
    get_user_role,
    log_action,
)
from app.responses import ok_response, paginated_response, success_response
from noctusai_lib.invitations import (
    accept_invitation,
    generate_invite_token,
    validate_invitation,
)
from noctusai_lib.email_templates import send_product_invitation_email

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/invitations", tags=["Invitations"])

TABLE = "invitations"

INVITE_TYPES = (
    "platform_to_clinic",
    "platform_to_therapist",
    "clinic_to_therapist",
    "clinic_to_patient",
    "therapist_to_patient",
    "therapist_to_therapist",
)

# Which invite types each role can use
ROLE_ALLOWED_TYPES: dict[str, tuple[str, ...]] = {
    "platform_admin": INVITE_TYPES,
    "clinic_admin": ("clinic_to_therapist", "clinic_to_patient"),
    "therapist": ("therapist_to_patient", "therapist_to_therapist"),
    "patient": (),
}

# Target role assigned to the invitee when they accept
INVITE_TYPE_TARGET_ROLE: dict[str, str] = {
    "platform_to_clinic": "clinic_admin",
    "platform_to_therapist": "therapist",
    "clinic_to_therapist": "therapist",
    "clinic_to_patient": "patient",
    "therapist_to_patient": "patient",
    "therapist_to_therapist": "therapist",
}

ROLE_LABELS: dict[str, str] = {
    "clinic_admin": "Administrador de Clínica",
    "therapist": "Terapeuta",
    "patient": "Paciente",
}

FRONTEND_BASE_URL = "http://localhost:8095"


# ---------------------------------------------------------------------------
# Schemas
# ---------------------------------------------------------------------------

class CreateInvitationBody(BaseModel):
    email: EmailStr
    invite_type: Literal[
        "platform_to_clinic",
        "platform_to_therapist",
        "clinic_to_therapist",
        "clinic_to_patient",
        "therapist_to_patient",
        "therapist_to_therapist",
    ]
    clinic_id: Optional[str] = None
    bound_to: Optional[str] = None


class AcceptInvitationBody(BaseModel):
    token: str
    nome: str = Field(..., min_length=2, max_length=200)
    password: str = Field(..., min_length=6, max_length=128)
    extra_fields: Optional[dict] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _resolve_clinic_id(
    invite_type: str,
    user_clinic_id: Optional[str],
    body_clinic_id: Optional[str],
    role: str,
) -> Optional[str]:
    """Determine the clinic_id to attach to the invitation.

    - platform_admin can specify any clinic_id in the body.
    - clinic_admin uses their own clinic_id (body ignored).
    - therapist invites are not clinic-scoped (returns user's clinic or None).
    - platform_to_clinic creates a new clinic on accept, so no clinic_id needed.
    """
    if invite_type == "platform_to_clinic":
        return None

    if invite_type in ("clinic_to_therapist", "clinic_to_patient"):
        if role == "platform_admin":
            if not body_clinic_id:
                raise HTTPException(
                    status_code=422,
                    detail="clinic_id e obrigatorio para convites de clinica",
                )
            return body_clinic_id
        # clinic_admin — always uses own clinic
        if not user_clinic_id:
            raise HTTPException(
                status_code=422,
                detail="Voce nao esta vinculado a nenhuma clinica",
            )
        return user_clinic_id

    if invite_type in ("platform_to_therapist", "therapist_to_patient", "therapist_to_therapist"):
        return body_clinic_id or user_clinic_id

    return None


def _resolve_bound_to(
    invite_type: str,
    user_id: str,
    body_bound_to: Optional[str],
    role: str,
) -> Optional[str]:
    """Determine the bound_to field (therapist binding for patient invites).

    - therapist_to_patient: automatically bound to the inviting therapist.
    - platform_admin / clinic_admin: can specify bound_to in body.
    - Other types: no binding.
    """
    if invite_type == "therapist_to_patient":
        return user_id

    if invite_type in ("clinic_to_patient", "platform_to_therapist"):
        return body_bound_to

    return None


# ---------------------------------------------------------------------------
# POST /api/invitations — Create invitation
# ---------------------------------------------------------------------------

@router.post("")
async def create_invitation(
    body: CreateInvitationBody,
    authorization: Optional[str] = Header(None),
):
    """Create a new invitation.

    Permission checks enforce role-based access to invite types.
    Clinic-scoped invites validate clinic ownership for clinic_admin users.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    user_id = str(user.id)

    # Permission: role must be allowed to use this invite type
    allowed = ROLE_ALLOWED_TYPES.get(role, ())
    if body.invite_type not in allowed:
        raise HTTPException(
            status_code=403,
            detail=f"Seu perfil ({role}) nao pode enviar convites do tipo {body.invite_type}",
        )

    db = get_admin_client()

    # Resolve clinic_id and bound_to
    user_clinic_id = get_clinic_id_for_user(user)
    clinic_id = _resolve_clinic_id(body.invite_type, user_clinic_id, body.clinic_id, role)
    bound_to = _resolve_bound_to(body.invite_type, user_id, body.bound_to, role)
    target_role = INVITE_TYPE_TARGET_ROLE[body.invite_type]

    # Check for existing pending invitation for same email + clinic
    pending_filter = db.table(TABLE).select("id").eq("email", body.email).eq("status", "pending")
    if clinic_id:
        pending_filter = pending_filter.eq("clinic_id", clinic_id)
    pending = pending_filter.execute()
    if pending.data:
        raise HTTPException(
            status_code=409,
            detail="Ja existe um convite pendente para este email",
        )

    # Build invitation record
    invite_token = generate_invite_token()
    invite_data = {
        "email": body.email,
        "role": target_role,
        "invite_type": body.invite_type,
        "invited_by": user_id,
        "token": invite_token,
        "status": "pending",
    }
    if clinic_id:
        invite_data["clinic_id"] = clinic_id
    if bound_to:
        invite_data["bound_to"] = bound_to

    result = db.table(TABLE).insert(invite_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar convite")

    invitation = result.data[0] if isinstance(result.data, list) else result.data

    # Send email (best-effort — does not block on failure)
    try:
        org_name = "Plataforma Therapy"
        if clinic_id:
            clinic = db.table("clinics").select("nome").eq("id", clinic_id).single().execute()
            if clinic.data:
                org_name = clinic.data.get("nome", org_name)

        send_product_invitation_email(
            to=body.email,
            product_name="Therapy Platform",
            org_name=org_name,
            role_label=ROLE_LABELS.get(target_role, target_role),
            invite_token=invite_token,
            invited_by=user_id,
            base_url=FRONTEND_BASE_URL,
        )
    except Exception as exc:
        logger.warning("Falha ao enviar email de convite: %s", exc)

    log_action(
        user_id=user_id,
        tipo_acao="criar",
        tipo_entidade="invitation",
        entidade_id=invitation.get("id"),
        descricao=f"Convite {body.invite_type} enviado para {body.email}",
    )

    logger.info(
        "Invitation created: type=%s email=%s clinic=%s by=%s",
        body.invite_type, body.email, clinic_id, user_id,
    )
    return success_response(invitation)


# ---------------------------------------------------------------------------
# GET /api/invitations/accept/validate — Validate invitation token (public)
# ---------------------------------------------------------------------------

@router.get("/accept/validate")
async def validate_invitation_endpoint(token: str):
    """Validate an invitation token — public endpoint (no auth required).

    Returns the invitation email and role so the frontend can pre-fill the form.
    """
    db = get_admin_client()
    invitation = validate_invitation(db, TABLE, token)

    return success_response({
        "email": invitation["email"],
        "role": ROLE_LABELS.get(invitation["role"], invitation["role"]),
    })


# ---------------------------------------------------------------------------
# POST /api/invitations/accept — Accept invitation (public, no auth)
# ---------------------------------------------------------------------------

@router.post("/accept")
async def accept_invitation_endpoint(body: AcceptInvitationBody):
    """Accept an invitation by token. Creates auth user + profile.

    This endpoint is public (no auth required) because the invitee
    does not yet have an account.
    """
    db = get_admin_client()

    # Validate token
    invitation = validate_invitation(db, TABLE, body.token)
    invite_type = invitation["invite_type"]
    target_role = invitation["role"]
    clinic_id = invitation.get("clinic_id")
    bound_to = invitation.get("bound_to")
    email = invitation["email"]

    # Build user metadata
    user_metadata: dict = {
        "role": target_role,
        "nome": body.nome,
    }
    if clinic_id:
        user_metadata["clinic_id"] = clinic_id

    # Create Supabase auth user
    try:
        auth_response = db.auth.admin.create_user({
            "email": email,
            "password": body.password,
            "email_confirm": True,
            "user_metadata": user_metadata,
        })
        new_user = auth_response.user
        if not new_user:
            raise HTTPException(status_code=500, detail="Erro ao criar usuario")
        new_user_id = str(new_user.id)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Falha ao criar usuario para convite %s: %s", invitation["id"], exc)
        raise HTTPException(
            status_code=500,
            detail="Erro ao criar usuario. Email ja cadastrado?",
        )

    # Create profile based on invite type
    try:
        if invite_type == "platform_to_clinic":
            _create_clinic_and_admin(db, new_user_id, body.nome, email, body.extra_fields)
        elif target_role == "therapist":
            _create_therapist_profile(db, new_user_id, body.nome, email, clinic_id, body.extra_fields)
        elif target_role == "patient":
            _create_patient_profile(db, new_user_id, body.nome, email, clinic_id, bound_to, body.extra_fields)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("Falha ao criar perfil para usuario %s: %s", new_user_id, exc)
        raise HTTPException(status_code=500, detail="Usuario criado mas houve erro ao criar perfil")

    # Mark invitation as accepted
    accept_invitation(db, TABLE, invitation["id"])

    logger.info(
        "Invitation accepted: id=%s type=%s email=%s new_user=%s",
        invitation["id"], invite_type, email, new_user_id,
    )
    return success_response({
        "message": "Convite aceito com sucesso",
        "user_id": new_user_id,
        "role": target_role,
    })


def _create_clinic_and_admin(
    db, user_id: str, nome: str, email: str, extra_fields: Optional[dict]
):
    """Create a new clinic and set the user as its admin."""
    clinic_data = {
        "nome": extra_fields.get("clinic_nome", f"Clinica de {nome}") if extra_fields else f"Clinica de {nome}",
    }
    if extra_fields:
        for field in ("telefone", "endereco", "descricao", "logo_url"):
            if field in extra_fields:
                clinic_data[field] = extra_fields[field]

    clinic_result = db.table("clinics").insert(clinic_data).execute()
    if not clinic_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar clinica")

    clinic = clinic_result.data[0] if isinstance(clinic_result.data, list) else clinic_result.data
    clinic_id = clinic["id"]

    # Update user metadata with the new clinic_id
    db.auth.admin.update_user_by_id(user_id, {"user_metadata": {
        "role": "clinic_admin",
        "nome": nome,
        "clinic_id": clinic_id,
    }})

    logger.info("Clinic created: id=%s admin=%s", clinic_id, user_id)


def _create_therapist_profile(
    db, user_id: str, nome: str, email: str, clinic_id: Optional[str], extra_fields: Optional[dict]
):
    """Create a therapist_profiles record."""
    profile_data = {
        "user_id": user_id,
        "nome": nome,
        "email": email,
    }
    if clinic_id:
        profile_data["clinic_id"] = clinic_id
    if extra_fields:
        for field in ("crp", "especialidade", "abordagem", "telefone", "bio"):
            if field in extra_fields:
                profile_data[field] = extra_fields[field]

    result = db.table("therapist_profiles").insert(profile_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar perfil de terapeuta")

    logger.info("Therapist profile created: user_id=%s clinic=%s", user_id, clinic_id)


def _create_patient_profile(
    db,
    user_id: str,
    nome: str,
    email: str,
    clinic_id: Optional[str],
    bound_to: Optional[str],
    extra_fields: Optional[dict],
):
    """Create a patient_profiles record with optional therapist binding."""
    profile_data = {
        "user_id": user_id,
        "nome": nome,
        "email": email,
    }
    if clinic_id:
        profile_data["clinic_id"] = clinic_id
    if bound_to:
        profile_data["therapist_id"] = bound_to
    if extra_fields:
        for field in ("telefone", "data_nascimento", "cpf"):
            if field in extra_fields:
                profile_data[field] = extra_fields[field]

    result = db.table("patient_profiles").insert(profile_data).execute()
    if not result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar perfil de paciente")

    logger.info("Patient profile created: user_id=%s clinic=%s bound_to=%s", user_id, clinic_id, bound_to)


# ---------------------------------------------------------------------------
# GET /api/invitations — List invitations
# ---------------------------------------------------------------------------

@router.get("")
async def list_invitations(
    authorization: Optional[str] = Header(None),
    page: int = Query(1, ge=1),
    page_size: int = Query(20, ge=1, le=100),
    status: Optional[str] = Query(None),
):
    """List invitations filtered by the caller's role.

    - platform_admin: sees all invitations.
    - clinic_admin: sees invitations for their clinic.
    - therapist: sees invitations they sent.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    user_id = str(user.id)

    if role == "patient":
        raise HTTPException(status_code=403, detail="Acesso negado")

    db = get_admin_client()

    query = db.table(TABLE).select(
        "id, email, role, invite_type, clinic_id, bound_to, "
        "invited_by, status, expires_at, created_at",
        count="exact",
    )

    # Role-based filtering
    if role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if not clinic_id:
            raise HTTPException(status_code=422, detail="Voce nao esta vinculado a nenhuma clinica")
        query = query.eq("clinic_id", clinic_id)
    elif role == "therapist":
        query = query.eq("invited_by", user_id)
    # platform_admin: no filter — sees all

    if status:
        query = query.eq("status", status)

    query = query.order("created_at", desc=True)

    # Pagination
    start = (page - 1) * page_size
    end = start + page_size - 1
    result = query.range(start, end).execute()

    total = result.count if result.count is not None else len(result.data or [])
    return paginated_response(result.data or [], total, page, page_size)


# ---------------------------------------------------------------------------
# DELETE /api/invitations/{id} — Cancel invitation
# ---------------------------------------------------------------------------

@router.delete("/{invitation_id}")
async def cancel_invitation_endpoint(
    invitation_id: str,
    authorization: Optional[str] = Header(None),
):
    """Cancel a pending invitation.

    - platform_admin: can cancel any invitation.
    - clinic_admin: can cancel invitations for their clinic.
    - therapist: can cancel invitations they sent.
    """
    user, token = await get_current_user(authorization)
    role = get_user_role(user)
    user_id = str(user.id)

    db = get_admin_client()

    # Fetch the invitation first (DELETE pre-check)
    invite_result = db.table(TABLE).select("id, status, clinic_id, invited_by").eq("id", invitation_id).execute()
    if not invite_result.data:
        raise HTTPException(status_code=404, detail="Convite nao encontrado")

    invitation = invite_result.data[0]

    if invitation["status"] != "pending":
        raise HTTPException(status_code=400, detail="Apenas convites pendentes podem ser cancelados")

    # Permission check
    if role == "clinic_admin":
        clinic_id = get_clinic_id_for_user(user)
        if invitation.get("clinic_id") != clinic_id:
            raise HTTPException(status_code=403, detail="Voce so pode cancelar convites da sua clinica")
    elif role == "therapist":
        if invitation["invited_by"] != user_id:
            raise HTTPException(status_code=403, detail="Voce so pode cancelar convites que voce enviou")
    elif role == "patient":
        raise HTTPException(status_code=403, detail="Acesso negado")
    # platform_admin: can cancel any

    db.table(TABLE).update({"status": "canceled"}).eq("id", invitation_id).execute()

    log_action(
        user_id=user_id,
        tipo_acao="cancelar",
        tipo_entidade="invitation",
        entidade_id=invitation_id,
        descricao=f"Convite cancelado",
    )

    logger.info("Invitation canceled: id=%s by=%s", invitation_id, user_id)
    return ok_response("Convite cancelado com sucesso")
