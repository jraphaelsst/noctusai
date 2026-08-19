"""Clients Supabase — padrão NoctusAI.

- get_user_client(token): client com o JWT do usuário → RESPEITA RLS.
  Toda query de domínio passa por aqui.
- get_admin_client(): service-role → ignora RLS. Reservado para operações
  administrativas (criar login de membro da equipe). Nunca em rota de leitura.
"""
from fastapi import HTTPException
from postgrest.exceptions import APIError
from supabase import Client, create_client
from supabase.lib.client_options import ClientOptions

from app.config import settings

SCHEMA = "p_studio"


def get_anon_client(schema: str = SCHEMA) -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(schema=schema),
    )


def get_user_client(token: str, schema: str = SCHEMA) -> Client:
    return create_client(
        settings.supabase_url,
        settings.supabase_anon_key,
        options=ClientOptions(
            schema=schema, headers={"Authorization": f"Bearer {token}"}
        ),
    )


def get_admin_client(schema: str = SCHEMA) -> Client:
    if not settings.supabase_service_role_key:
        # 503, NOT 400. A missing server-side key is OUR misconfiguration, and
        # 4xx tells the caller their request was wrong. That distinction is not
        # cosmetic here: this factory sits behind the PUBLIC Asaas webhook, and
        # the provider reads status codes to decide whether to keep delivering.
        # A 400 says "malformed, do not retry" about a request that was
        # perfectly well-formed — so a key we forgot to set would look like the
        # provider's fault and silently poison the delivery queue.
        #
        # Same class as the seed's auth path reporting an unreachable Supabase
        # as 401 (fixed 2026-08-18): an infrastructure failure must never be
        # dressed up as a client error.
        raise HTTPException(
            status_code=503,
            detail="SUPABASE_SERVICE_ROLE_KEY não configurada no backend/.env — "
            "necessária para operações administrativas.",
        )
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=ClientOptions(schema=schema),
    )


# Códigos PostgREST/Postgres que têm tradução HTTP específica. O resto vira
# 400 com a mensagem do banco — melhor que um 500 opaco.
_PG_ERRORS: dict[str, tuple[int, str]] = {
    "23505": (409, "Já existe um registro com esses dados."),
    "23503": (409, "Registro referenciado por outro cadastro — remova o vínculo antes."),
    "42501": (403, "Sem permissão para esta operação."),
}


def execute(query):
    """Executa uma query PostgREST convertendo APIError em erro HTTP.

    Concentrar a tradução aqui mantém os routers livres de try/except e
    garante que toda falha de banco vira a mesma forma de resposta.
    """
    try:
        return query.execute()
    except APIError as e:
        status, message = _PG_ERRORS.get(e.code or "", (400, e.message or "Erro no banco de dados"))
        raise HTTPException(status_code=status, detail=message)
