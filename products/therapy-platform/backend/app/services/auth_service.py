"""
Auth Service — Registration, login, password recovery.

Users authenticate directly with Supabase Auth (not NoctusAI SSO).
Each registration flow creates:
  1. Supabase auth user (via admin client)
  2. Role-specific profile row(s)
  3. Wallet row for financial operations
"""
from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from fastapi import HTTPException
from gotrue.errors import AuthApiError

logger = logging.getLogger(__name__)


async def register_patient(
    nome: str,
    email: str,
    password: str,
    phone: Optional[str],
    admin_db: Any,
) -> Dict:
    """Register a new patient.

    Creates auth user, patient_profiles row, and wallet.
    """
    try:
        user_resp = admin_db.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "role": "patient",
                "nome": nome,
            },
        })
    except AuthApiError as e:
        if "already" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email já cadastrado")
        raise HTTPException(status_code=400, detail=f"Erro ao criar usuário: {e}")

    user = user_resp.user
    user_id = user.id

    # Create patient profile
    profile_data: Dict[str, Any] = {
        "user_id": user_id,
        "phone": phone,
        "origin": "self_registration",
        "is_active": True,
    }
    admin_db.table("patient_profiles").insert(profile_data).execute()

    # Create wallet
    admin_db.table("wallets").insert({
        "owner_type": "patient",
        "owner_id": user_id,
        "balance": 0,
    }).execute()

    logger.info("Patient registered: user_id=%s email=%s", user_id, email)
    return {
        "user_id": user_id,
        "email": email,
        "nome": nome,
        "role": "patient",
    }


async def register_therapist(
    nome: str,
    email: str,
    password: str,
    crp: str,
    bio: Optional[str],
    specialties: list[str],
    approaches: list[str],
    photo_url: Optional[str],
    default_session_price: float,
    admin_db: Any,
) -> Dict:
    """Register a new therapist.

    Creates auth user, therapist_profiles row, therapist_settings row, and wallet.
    Therapist starts as is_approved=False — requires admin approval.
    """
    try:
        user_resp = admin_db.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "role": "therapist",
                "nome": nome,
            },
        })
    except AuthApiError as e:
        if "already" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email já cadastrado")
        raise HTTPException(status_code=400, detail=f"Erro ao criar usuário: {e}")

    user = user_resp.user
    user_id = user.id

    # Create therapist profile
    profile_data: Dict[str, Any] = {
        "user_id": user_id,
        "crp": crp,
        "bio": bio,
        "specialties": specialties,
        "approaches": approaches,
        "photo_url": photo_url,
        "default_session_price": default_session_price,
        "is_approved": False,
        "is_active": True,
    }
    admin_db.table("therapist_profiles").insert(profile_data).execute()

    # Create therapist settings
    admin_db.table("therapist_settings").insert({
        "therapist_id": user_id,
        "session_duration_minutes": 50,
    }).execute()

    # Create wallet
    admin_db.table("wallets").insert({
        "owner_type": "therapist",
        "owner_id": user_id,
        "balance": 0,
    }).execute()

    logger.info("Therapist registered: user_id=%s email=%s crp=%s", user_id, email, crp)
    return {
        "user_id": user_id,
        "email": email,
        "nome": nome,
        "role": "therapist",
        "is_approved": False,
    }


async def register_clinic(
    nome: str,
    email: str,
    password: str,
    clinic_name: str,
    cnpj: str,
    responsible_person: str,
    contact_email: str,
    phone: str,
    admin_db: Any,
) -> Dict:
    """Register a new clinic.

    Creates auth user (clinic_admin role), clinics row, clinic_settings,
    clinic_branding, and wallet. Clinic starts as is_approved=False.
    """
    # Create clinic row first to get clinic_id
    clinic_result = admin_db.table("clinics").insert({
        "name": clinic_name,
        "cnpj": cnpj,
        "responsible_person": responsible_person,
        "contact_email": contact_email,
        "phone": phone,
        "is_approved": False,
        "is_active": True,
    }).execute()

    if not clinic_result.data:
        raise HTTPException(status_code=500, detail="Erro ao criar clínica")

    clinic_id = clinic_result.data[0]["id"]

    try:
        user_resp = admin_db.auth.admin.create_user({
            "email": email,
            "password": password,
            "email_confirm": True,
            "user_metadata": {
                "role": "clinic_admin",
                "nome": nome,
                "clinic_id": clinic_id,
            },
        })
    except AuthApiError as e:
        # Rollback clinic creation on auth failure
        admin_db.table("clinics").delete().eq("id", clinic_id).execute()
        if "already" in str(e).lower():
            raise HTTPException(status_code=409, detail="Email já cadastrado")
        raise HTTPException(status_code=400, detail=f"Erro ao criar usuário: {e}")

    user = user_resp.user
    user_id = user.id

    # Create clinic settings
    admin_db.table("clinic_settings").insert({
        "clinic_id": clinic_id,
        "default_commission_pct_clinic_sourced": 30,
        "default_commission_pct_therapist_sourced": 15,
    }).execute()

    # Create clinic branding
    admin_db.table("clinic_branding").insert({
        "clinic_id": clinic_id,
    }).execute()

    # Create wallet
    admin_db.table("wallets").insert({
        "owner_type": "clinic",
        "owner_id": clinic_id,
        "balance": 0,
    }).execute()

    logger.info(
        "Clinic registered: user_id=%s clinic_id=%s name=%s",
        user_id, clinic_id, clinic_name,
    )
    return {
        "user_id": user_id,
        "clinic_id": clinic_id,
        "email": email,
        "nome": nome,
        "clinic_name": clinic_name,
        "role": "clinic_admin",
        "is_approved": False,
    }


async def login(email: str, password: str, admin_db: Any) -> Dict:
    """Authenticate with email + password via Supabase Auth."""
    try:
        result = admin_db.auth.sign_in_with_password({
            "email": email,
            "password": password,
        })
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")

    session = result.session
    user = result.user
    if not session or not user:
        raise HTTPException(status_code=401, detail="Email ou senha inválidos")

    metadata = user.user_metadata or {}
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": user.id,
        "email": user.email,
        "role": metadata.get("role", "patient"),
        "nome": metadata.get("nome", ""),
    }


async def google_auth(token: str, admin_db: Any) -> Dict:
    """Exchange Google OAuth ID token for a Supabase session.

    Note: The actual Google token verification and user creation is handled
    by Supabase's built-in Google provider. This endpoint is for the frontend
    to exchange the Google token via Supabase's sign-in-with-id-token flow.
    """
    try:
        result = admin_db.auth.sign_in_with_id_token({
            "provider": "google",
            "token": token,
        })
    except AuthApiError as e:
        raise HTTPException(status_code=401, detail=f"Falha na autenticação Google: {e}")

    session = result.session
    user = result.user
    if not session or not user:
        raise HTTPException(status_code=401, detail="Falha na autenticação Google")

    metadata = user.user_metadata or {}
    return {
        "access_token": session.access_token,
        "refresh_token": session.refresh_token,
        "user_id": user.id,
        "email": user.email,
        "role": metadata.get("role", "patient"),
        "nome": metadata.get("nome", metadata.get("full_name", "")),
    }


async def forgot_password(email: str, admin_db: Any) -> None:
    """Trigger Supabase password reset email."""
    try:
        admin_db.auth.reset_password_email(email)
    except AuthApiError:
        # Don't reveal whether email exists
        pass
    logger.info("Password reset requested for email=%s", email)


async def get_user_profile(user: Any, admin_db: Any) -> Dict:
    """Get current user info + role-specific profile.

    Fetches the appropriate profile table based on role.
    """
    metadata = user.user_metadata or {}
    role = metadata.get("role", "patient")
    user_id = user.id

    base = {
        "user_id": user_id,
        "email": user.email,
        "role": role,
        "nome": metadata.get("nome", ""),
    }

    if role == "patient":
        result = admin_db.table("patient_profiles").select("*").eq("user_id", user_id).execute()
        if result.data:
            base["profile"] = result.data[0]

    elif role == "therapist":
        result = admin_db.table("therapist_profiles").select("*").eq("user_id", user_id).execute()
        if result.data:
            base["profile"] = result.data[0]

    elif role == "clinic_admin":
        clinic_id = metadata.get("clinic_id")
        if clinic_id:
            result = admin_db.table("clinics").select("*").eq("id", clinic_id).execute()
            if result.data:
                base["clinic"] = result.data[0]
        base["clinic_id"] = clinic_id

    elif role == "platform_admin":
        base["is_admin"] = True

    return base
