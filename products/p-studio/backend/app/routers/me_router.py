"""Perfil do usuário logado. O frontend chama isto no boot para saber quem é
e para provar que o backend está de pé antes de renderizar o app."""
from fastapi import APIRouter, Depends

from app.dependencies import CurrentUser, get_current_user

router = APIRouter(prefix="/api", tags=["me"])


@router.get("/me")
def me(user: CurrentUser = Depends(get_current_user)):
    return {
        "id": user.id,
        "email": user.email,
        "nome": user.nome,
        "org_id": user.org_id,
    }
