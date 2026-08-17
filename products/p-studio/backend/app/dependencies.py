"""Auth guard — resolve o usuário logado e o client RLS-scoped da requisição.

Todo membro da organização é equipe do estúdio: um fotógrafo precisa poder
editar a captação agendada por outro. Por isso não há papel por linha — a
fronteira é a organização, e ela é imposta pela RLS, não por este guard.

O `org_id` que o guard devolve vem de `settings.org_id` (deploy single-tenant).
Ele é usado para CARIMBAR inserts; quem AUTORIZA é a policy do Postgres, que
confere contra public.current_org_id(). Se os dois divergirem o banco recusa.
"""
from dataclasses import dataclass
from typing import Optional

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from supabase import Client

from app.config import settings
from app.database import get_anon_client, get_user_client

security = HTTPBearer(auto_error=False)


@dataclass
class CurrentUser:
    id: str
    email: str
    nome: str
    org_id: str
    token: str
    db: Client  # client RLS-scoped no schema p_studio


def get_current_user(
    credentials: Optional[HTTPAuthorizationCredentials] = Depends(security),
) -> CurrentUser:
    if credentials is None:
        raise HTTPException(status_code=401, detail="Não autenticado")
    token = credentials.credentials

    try:
        user = get_anon_client().auth.get_user(token).user
    except Exception:
        user = None
    if user is None:
        raise HTTPException(status_code=401, detail="Sessão inválida ou expirada")

    # `settings.org_id` tem default "" para que IMPORTAR `app.config` não
    # exija a env var (ver o comentário longo em config.py). Este é o único
    # ponto onde o valor entra num request, então é aqui que ele precisa ser
    # real. Recusa ALTO em vez de deixar "" escopar queries: um org_id vazio
    # carimbaria INSERTs e filtraria leituras contra nada — erro silencioso.
    # 500, não 401: o token do usuário está bom; quem está mal configurado é
    # o deploy, e confundir os dois manda o operador depurar o login errado.
    if not settings.org_id:
        raise HTTPException(
            status_code=500,
            detail=(
                "P_STUDIO_ORG_ID não configurado neste deploy — o backend não "
                "sabe a qual organização carimbar as escritas."
            ),
        )

    metadata = user.user_metadata or {}
    return CurrentUser(
        id=user.id,
        email=user.email or "",
        nome=metadata.get("nome") or (user.email or "").split("@")[0],
        org_id=settings.org_id,
        token=token,
        db=get_user_client(token),
    )


def get_provedor_cobranca():
    """O provedor de cobrança configurado.

    Dependência separada do `get_current_user` de propósito: as rotas que
    apenas leem lançamentos não devem exigir integração configurada. Quem pede
    esta dependência é só quem vai falar com o banco.

    Nos testes, uma linha substitui tudo:

        app.dependency_overrides[get_provedor_cobranca] = lambda: ProvedorFake()
    """
    from app.providers import provedor_padrao

    return provedor_padrao()
