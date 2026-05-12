"""
Auth Router — Registration (patient, therapist, clinic), login, Google OAuth, password recovery.
"""
import logging
from typing import Optional

from fastapi import APIRouter, Header, Request

from app.dependencies import get_current_user, get_admin_client
from app.rate_limit import limiter
from app.responses import success_response
from noctusai_lib.api.rate_limit_policies import DEFAULT_AUTH_RL
from app.schemas.auth import (
    PatientRegister,
    TherapistRegister,
    ClinicRegister,
    LoginRequest,
    GoogleAuthRequest,
    ForgotPasswordRequest,
)
from app.services import auth_service

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/auth", tags=["Auth"])


@router.post("/register/patient")
@limiter.limit("10/minute")
async def register_patient(request: Request, body: PatientRegister):
    """Register a new patient account."""
    admin_db = get_admin_client()
    result = await auth_service.register_patient(
        nome=body.nome,
        email=body.email,
        password=body.password,
        phone=body.phone,
        admin_db=admin_db,
    )
    return success_response(result)


@router.post("/register/therapist")
@limiter.limit("10/minute")
async def register_therapist(request: Request, body: TherapistRegister):
    """Register a new therapist account (requires admin approval)."""
    admin_db = get_admin_client()
    result = await auth_service.register_therapist(
        nome=body.nome,
        email=body.email,
        password=body.password,
        crp=body.crp,
        bio=body.bio,
        specialties=body.specialties,
        approaches=body.approaches,
        photo_url=body.photo_url,
        default_session_price=body.default_session_price,
        admin_db=admin_db,
    )
    return success_response(result)


@router.post("/register/clinic")
@limiter.limit("10/minute")
async def register_clinic(request: Request, body: ClinicRegister):
    """Register a new clinic account (requires admin approval)."""
    admin_db = get_admin_client()
    result = await auth_service.register_clinic(
        nome=body.nome,
        email=body.email,
        password=body.password,
        clinic_name=body.clinic_name,
        cnpj=body.cnpj,
        responsible_person=body.responsible_person,
        contact_email=body.contact_email,
        phone=body.phone,
        admin_db=admin_db,
    )
    return success_response(result)


@router.post("/login")
@limiter.limit(DEFAULT_AUTH_RL)
async def login(request: Request, body: LoginRequest):
    """Authenticate with email and password."""
    admin_db = get_admin_client()
    result = await auth_service.login(
        email=body.email,
        password=body.password,
        admin_db=admin_db,
    )
    return success_response(result)


@router.post("/google")
@limiter.limit(DEFAULT_AUTH_RL)
async def google_auth(request: Request, body: GoogleAuthRequest):
    """Authenticate with Google OAuth ID token."""
    admin_db = get_admin_client()
    result = await auth_service.google_auth(
        token=body.token,
        admin_db=admin_db,
    )
    return success_response(result)


@router.post("/forgot-password")
@limiter.limit("5/minute")
async def forgot_password(request: Request, body: ForgotPasswordRequest):
    """Trigger password reset email."""
    admin_db = get_admin_client()
    await auth_service.forgot_password(
        email=body.email,
        admin_db=admin_db,
    )
    return success_response({"message": "Se o email existir, um link de redefinição foi enviado"})


@router.get("/me")
@limiter.limit(DEFAULT_AUTH_RL)
async def get_me(request: Request, authorization: Optional[str] = Header(None)):
    """Get current user info and role-specific profile."""
    user, _ = await get_current_user(authorization)
    admin_db = get_admin_client()
    result = await auth_service.get_user_profile(user=user, admin_db=admin_db)
    return success_response(result)
