"""Integrações de canal — the setup surface for Módulo 5's credentials.

  GET    /api/integracoes            connection status per channel
  POST   /api/integracoes/{canal}    connect (store an encrypted token)
  DELETE /api/integracoes/{canal}    disconnect

**Nothing here ever returns a token.** `IntegracaoStatus` has no token field,
mirroring social-wiring's `KeyStatusEntry` convention ("never echoes the actual
values back"). The UI shows connected / not connected / needs reconnect, and
that is all it needs to render a setup screen.

Per-ORG credentials rather than one global token per channel: an agency
publishes to many different clients' accounts, so a single platform-wide token
is the wrong model. `settings.igig_*_token` remains as an env-level fallback
for a single-tenant deployment.
"""
# NOTE: no `from __future__ import annotations` — consistent with the other
# IgIg routers; see esteira_router.py.
import logging

from fastapi import APIRouter, Depends, HTTPException, status
from noctusai_lib.integrations.persistence import RecordNotFound

from app.config import settings
from app.dependencies import coerce_org_uuid, get_current_user_org
from app.repositories import Repositorios
from app.schemas.integracoes import ConectarCanal, IntegracaoStatus
from app.services.publicacao_publisher import CANAIS
from app.store import get_repositorios

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integracoes", tags=["integracoes"])


def _org(auth: tuple) -> str:
    _user, _token, raw_org = auth
    return str(coerce_org_uuid(raw_org))


def _chave() -> bytes:
    """The Fernet key, or a loud 409 — same contract as the Cofre."""
    if not settings.igig_cofre_key:
        raise HTTPException(
            status_code=409,
            detail=(
                "Criptografia não configurada: defina IGIG_COFRE_KEY. "
                "Nenhum token é gravado em texto puro."
            ),
        )
    return settings.igig_cofre_key.encode("utf-8")


def _fallback_env(canal: str) -> bool:
    """Whether an env-level token exists for this channel."""
    if canal in ("instagram", "facebook"):
        return bool(settings.igig_meta_token)
    if canal == "tiktok":
        return bool(settings.igig_tiktok_token)
    return bool(settings.igig_linkedin_token)


@router.get("", response_model=list[IntegracaoStatus])
async def listar_integracoes(
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> list[IntegracaoStatus]:
    """Status for EVERY channel, including the ones never connected.

    Returning the full set — rather than only stored rows — means the setup
    screen renders the same shape whether or not anything is configured, and
    an operator can see what is still missing.
    """
    org_id = _org(auth)
    saida: list[IntegracaoStatus] = []
    for canal in CANAIS:
        registro = repos.integracao.por_canal(org_id, canal)
        if registro is None:
            saida.append(IntegracaoStatus(
                canal=canal,
                conectado=_fallback_env(canal),
                origem="env" if _fallback_env(canal) else "nenhuma",
            ))
            continue
        saida.append(IntegracaoStatus(
            canal=canal,
            conectado=bool(registro.get("token_cifrado")) and bool(registro.get("ativo")),
            origem="org",
            conta_externa=registro.get("conta_externa"),
            conectado_em=registro.get("conectado_em"),
            ultimo_erro=registro.get("ultimo_erro"),
        ))
    return saida


@router.post("/{canal}", response_model=IntegracaoStatus, status_code=status.HTTP_201_CREATED)
async def conectar_canal(
    canal: str,
    payload: ConectarCanal,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> IntegracaoStatus:
    """Store a channel token, encrypted. Re-connecting replaces it."""
    if canal not in CANAIS:
        raise HTTPException(status_code=422, detail=f"Canal inválido: {canal}")
    org_id = _org(auth)
    registro = repos.integracao.conectar(
        org_id, canal,
        token=payload.token, chave=_chave(), conta_externa=payload.conta_externa,
    )
    logger.info("canal conectado org=%s canal=%s", org_id, canal)
    return IntegracaoStatus(
        canal=canal,
        conectado=True,
        origem="org",
        conta_externa=registro.get("conta_externa"),
        conectado_em=registro.get("conectado_em"),
    )


@router.delete("/{canal}", status_code=status.HTTP_200_OK)
async def desconectar_canal(
    canal: str,
    auth: tuple = Depends(get_current_user_org),
    repos: Repositorios = Depends(get_repositorios),
) -> dict:
    if canal not in CANAIS:
        raise HTTPException(status_code=422, detail=f"Canal inválido: {canal}")
    if not repos.integracao.desconectar(_org(auth), canal):
        raise HTTPException(status_code=404, detail="Canal não conectado")
    return {"ok": True}
