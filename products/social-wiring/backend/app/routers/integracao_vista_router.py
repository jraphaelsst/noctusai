"""Integrações > Vista CRM -- the org's own Vista credential (julia-v3; owner 2026-11-03: keys live in the DB, not .env).

  GET    /api/integracoes/vista          org admin  {data: {configurado, base_url, chave_final, verificado_em}}
  PUT    /api/integracoes/vista          org admin  {base_url, api_key} -> validated, live-checked, THEN stored
  POST   /api/integracoes/vista/testar   org admin  {data: {ok, mensagem}}  (re-checks the STORED credential)
  DELETE /api/integracoes/vista          org admin  removes the record (idempotent)

The key is write-only: no response, log line or error ever carries it (only `chave_final`, the last 4). The base URL
must be `https://<tenant>.vistahost.com.br` (SSRF guard: the server calls it with the key attached). A key is stored only
after a live read-only call (`/corretores/listar`, one row) succeeds. The platform AuditMiddleware records every write
with the acting admin; `_auditar` adds the structured line (actor, org, action, chave_final).

Errors: 401 no session, 403 non-admin, 422 `invalid_field` / `vista_url_invalida` / `vista_chave_recusada`,
503 `vista_indisponivel` (the platform masks 502 to 503 on the wire) / `credencial_indisponivel` (ENCRYPTION_KEY missing).
"""
# No `from __future__ import annotations`: FastAPI body models are resolved from the signature.
import logging
from typing import Any, Awaitable, Callable, Optional

import anyio

from fastapi import APIRouter, Depends, Request
from pydantic import Field

from noctusai_lib.api import StrictHttpModel
from noctusai_lib.api.auth.session import require_org_admin_for
from noctusai_lib.integrations.vista import VistaConfigError, VistaError, VistaPermissionDenied
from noctusai_lib.integrations.vista.client import redact_api_key
from noctusai_lib.integrations.vista.credentials import VistaBaseUrlInvalida, chave_final, validar_base_url, verificar_conexao
from noctusai_lib.primitives.exceptions import AppException

from app.dependencies import coerce_org_uuid, get_core_client, get_current_user_org
from app.services import vista_credenciais
from app.services.credential_vault import EncryptionNotConfigured

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/integracoes/vista", tags=["integracoes-vista"])

Verificador = Callable[[str, str], Awaitable[None]]


def get_vista_verificador() -> Verificador:
    """DI seam: the live read-only check (tests inject a Fake that never touches the network)."""
    return verificar_conexao


def get_vista_store() -> Any:
    """DI seam: the credential store (tests override with a `FakeCredentialStore`)."""
    try:
        return vista_credenciais.build_store()
    except EncryptionNotConfigured as exc:
        raise AppException("credencial_indisponivel", str(exc), status_code=503) from exc


def get_vista_core() -> Any:
    """DI seam: the core client (admin check)."""
    return get_core_client()


class VistaIn(StrictHttpModel):
    base_url: str = Field(min_length=1, max_length=200)
    api_key: str = Field(min_length=8, max_length=200)


def _estado(registro: Optional[dict[str, Any]]) -> dict[str, Any]:
    if registro is None:
        return {"configurado": False, "base_url": None, "chave_final": None, "verificado_em": None}
    return {"configurado": True, **{k: registro.get(k) for k in ("base_url", "chave_final", "verificado_em")}}


def _admin(auth: tuple, request: Optional[Request], core: Any) -> tuple[Any, str]:
    require_org_admin_for(core, auth, request, "A integração com o Vista")
    user = auth[0]
    ator = getattr(user, "id", None) or (user.get("id") if isinstance(user, dict) else None)
    return coerce_org_uuid(auth[2]), str(ator or "desconhecido")


def _auditar(acao: str, org_id: Any, ator: str, final: Optional[str]) -> None:
    logger.info("audit: vista_credencial %s org=%s ator=%s chave_final=%s", acao, org_id, ator, final or "-")


def _erro_vista(exc: Exception, api_key: str) -> AppException:
    limpa = redact_api_key(str(exc), api_key)[:200]
    if isinstance(exc, VistaPermissionDenied):
        return AppException("vista_chave_recusada", "O Vista recusou esta chave (ou ela não tem permissão de leitura).", status_code=422)
    logger.warning("vista: live check failed (%s): %s", type(exc).__name__, limpa)
    return AppException("vista_indisponivel", "Não foi possível falar com o Vista agora. Tente de novo em instantes.", status_code=503)


@router.get("")
def ler(request: Request = None, auth: tuple = Depends(get_current_user_org), core: Any = Depends(get_vista_core),
        store: Any = Depends(get_vista_store)) -> dict[str, Any]:
    org_id, _ = _admin(auth, request, core)
    return {"data": _estado(vista_credenciais.ler(org_id, store))}


@router.put("")
async def salvar(corpo: VistaIn, request: Request = None, auth: tuple = Depends(get_current_user_org),
                 core: Any = Depends(get_vista_core), store: Any = Depends(get_vista_store),
                 verificar: Verificador = Depends(get_vista_verificador)) -> dict[str, Any]:
    org_id, ator = await anyio.to_thread.run_sync(lambda: _admin(auth, request, core))
    try:
        base_url = validar_base_url(corpo.base_url)
    except VistaBaseUrlInvalida as exc:
        raise AppException("vista_url_invalida", str(exc), status_code=422) from exc
    api_key = corpo.api_key.strip()
    try:
        await verificar(base_url, api_key)
    except VistaError as exc:
        raise _erro_vista(exc, api_key) from None
    registro = await anyio.to_thread.run_sync(lambda: vista_credenciais.salvar(org_id, base_url, api_key, ator, store))
    _auditar("salvar", org_id, ator, registro["chave_final"])
    return {"data": _estado(registro)}


@router.post("/testar")
async def testar(request: Request = None, auth: tuple = Depends(get_current_user_org), core: Any = Depends(get_vista_core),
                 store: Any = Depends(get_vista_store),
                 verificar: Verificador = Depends(get_vista_verificador)) -> dict[str, Any]:
    org_id, _ = await anyio.to_thread.run_sync(lambda: _admin(auth, request, core))
    try:
        base_url, api_key = await anyio.to_thread.run_sync(lambda: vista_credenciais.VistaCredentialResolver(store).get(str(org_id)))
    except VistaConfigError as exc:
        return {"data": {"ok": False, "mensagem": str(exc)}}
    try:
        await verificar(base_url, api_key)
    except VistaError as exc:
        return {"data": {"ok": False, "mensagem": _erro_vista(exc, api_key).message}}
    return {"data": {"ok": True, "mensagem": "Conexão com o Vista funcionando."}}


@router.delete("")
def remover(request: Request = None, auth: tuple = Depends(get_current_user_org), core: Any = Depends(get_vista_core),
            store: Any = Depends(get_vista_store)) -> dict[str, Any]:
    org_id, ator = _admin(auth, request, core)
    atual = vista_credenciais.ler(org_id, store)
    vista_credenciais.remover(org_id, store)
    _auditar("remover", org_id, ator, (atual or {}).get("chave_final"))
    return {"data": _estado(None)}


__all__ = ["router"]
