"""
AdConnect domain authentication dependencies.

AdConnect uses its own JWT-based auth (not Supabase). These dependencies are
used by the domain routers (products, cart, orders, rewards, sellout, financial,
distributors, admin). The framework's standard routers (health, team, notificacoes)
use Supabase auth via dependencies.py — they coexist without conflict.
"""
from __future__ import annotations

from typing import Any, Callable

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from .security import decode_token

_bearer = HTTPBearer(auto_error=False)


def get_current_user(
    creds: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict[str, Any]:
    if creds is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Missing bearer token")
    try:
        return decode_token(creds.credentials)
    except jwt.PyJWTError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid or expired token")


def require_role(*roles: str) -> Callable[..., dict[str, Any]]:
    def checker(user: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
        if user.get("role") not in roles:
            raise HTTPException(status.HTTP_403_FORBIDDEN, "Role not allowed")
        return user

    return checker
