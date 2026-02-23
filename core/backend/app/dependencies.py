"""
NoctusAI Core — Auth dependencies and JWT helpers.
"""
import jwt
import datetime
from typing import Optional, Tuple
from fastapi import Header, HTTPException
from app.config import settings
from app.database import get_supabase_client


async def get_current_user(authorization: Optional[str] = Header(None)) -> Tuple:
    """Extract and validate user from Supabase auth token."""
    if not authorization or not authorization.startswith("Bearer "):
        raise HTTPException(status_code=401, detail="Token ausente")

    token = authorization.replace("Bearer ", "")
    client = get_supabase_client()

    try:
        user_response = client.auth.get_user(token)
        if not user_response or not user_response.user:
            raise HTTPException(status_code=401, detail="Token inválido")
        return user_response.user, token
    except Exception:
        raise HTTPException(status_code=401, detail="Não autenticado")


def create_sso_token(user_id: str, org_id: str, product_slug: str,
                     email: str, role: str = "user") -> str:
    """Create a short-lived SSO token for product access."""
    payload = {
        "sub": user_id,
        "org_id": org_id,
        "product": product_slug,
        "email": email,
        "role": role,
        "type": "sso",
        "exp": datetime.datetime.utcnow() + datetime.timedelta(
            minutes=settings.sso_token_expiration_minutes
        ),
        "iat": datetime.datetime.utcnow(),
    }
    return jwt.encode(payload, settings.jwt_secret, algorithm=settings.jwt_algorithm)


def verify_sso_token(token: str) -> dict:
    """Verify and decode an SSO token. Used by products to validate access."""
    try:
        payload = jwt.decode(token, settings.jwt_secret, algorithms=[settings.jwt_algorithm])
        if payload.get("type") != "sso":
            raise HTTPException(status_code=401, detail="Token não é SSO")
        return payload
    except jwt.ExpiredSignatureError:
        raise HTTPException(status_code=401, detail="Token SSO expirado")
    except jwt.InvalidTokenError:
        raise HTTPException(status_code=401, detail="Token SSO inválido")
