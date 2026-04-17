from __future__ import annotations

import secrets
from datetime import datetime, timezone
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr

from ..data.store import store
from ..auth_deps import get_current_user
from ..security import create_token, hash_password, verify_password

router = APIRouter()


class LoginInput(BaseModel):
    email: EmailStr
    password: str


class RegisterInput(BaseModel):
    email: EmailStr
    password: str
    name: str
    role: str | None = None
    distributorId: str | None = None


def _to_public(u: dict[str, Any]) -> dict[str, Any]:
    return {k: v for k, v in u.items() if k != "passwordHash"}


def _seed_users() -> None:
    if store.users:
        return
    now = datetime.now(timezone.utc).isoformat()
    store.users.extend(
        [
            {
                "id": "user-admin-1",
                "email": "admin@adconnect.com",
                "name": "Admin AdConnect",
                "role": "admin",
                "distributorId": None,
                "passwordHash": hash_password("admin123"),
                "createdAt": now,
            },
            {
                "id": "user-cust-1",
                "email": "joao@exemplo.com.br",
                "name": "João Silva",
                "role": "customer",
                "distributorId": "dist-001",
                "passwordHash": hash_password("customer123"),
                "createdAt": now,
            },
        ]
    )


_seed_users()


@router.post("/login")
def login(body: LoginInput) -> dict[str, Any]:
    user = next(
        (u for u in store.users if u["email"].lower() == body.email.lower()), None
    )
    if not user or not verify_password(body.password, user["passwordHash"]):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Credenciais inválidas")
    token = create_token(
        {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "distributorId": user.get("distributorId"),
        }
    )
    return {"token": token, "user": _to_public(user)}


@router.post("/register", status_code=status.HTTP_201_CREATED)
def register(body: RegisterInput) -> dict[str, Any]:
    if any(u["email"].lower() == body.email.lower() for u in store.users):
        raise HTTPException(status.HTTP_409_CONFLICT, "E-mail já cadastrado")
    user = {
        "id": f"user-{secrets.token_hex(4)}",
        "email": body.email,
        "name": body.name,
        "role": body.role or "customer",
        "distributorId": body.distributorId,
        "passwordHash": hash_password(body.password),
        "createdAt": datetime.now(timezone.utc).isoformat(),
    }
    store.users.append(user)
    token = create_token(
        {
            "sub": user["id"],
            "email": user["email"],
            "role": user["role"],
            "distributorId": user.get("distributorId"),
        }
    )
    return {"token": token, "user": _to_public(user)}


@router.get("/me")
def me(current: dict[str, Any] = Depends(get_current_user)) -> dict[str, Any]:
    user = next((u for u in store.users if u["id"] == current["sub"]), None)
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED)
    return _to_public(user)
