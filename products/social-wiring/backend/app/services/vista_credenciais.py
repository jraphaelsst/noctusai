"""Vista credentials are PER ORG and live in the encrypted `CredentialStore` -- never in the process environment.

Owner, 2026-11-03: "Our keys are to be stored in the db, not .env". The record is `social_wiring.credentials`
`(org_id, provider='vista')` (the seed `VISTA_PROVIDER`), a Fernet-encrypted bundle
`{"base_url", "api_key", "chave_final", "verificado_em", "verificado_por"}`. The non-secret extras ride INSIDE the
encrypted bundle because this table has no free-form metadata column (`credential_vault`: `metadata_column=None`);
`chave_final` is the last 4 characters of the key, the only fragment that is ever shown.

EVERY Vista adapter in this product is built here, by `adapter_da_org(org_id)`, through the seed
`VistaCredentialResolver` + `get_vista_adapter_for_org`. There is NO fallback to `VISTA_API_KEY` / `crm_api_key`: an org
with no record is refused with `Vista não configurada para esta empresa` (503 on a request, a logged skip in a job).

NOC-REMEDIATE[vista-env-keys-removed]: `crm_base_url` / `crm_api_key` / `vista_base_url` / `vista_api_key` are gone from
this product's settings; `mcp/vista` (the dev MCP server) keeps its own env-based key by design -- it is not a product
runtime path -- 2026-11-03
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any, Callable, Optional

from fastapi import HTTPException, status
from noctusai_lib.integrations.credential_resolvers import VISTA_PROVIDER, VistaCredentialResolver
from noctusai_lib.integrations.vista import VistaConfigError, VistaRESTAdapter, get_vista_adapter_for_org
from noctusai_lib.integrations.vista.credentials import chave_final as _chave_final

from app.services.credential_vault import CredentialStore, EncryptionNotConfigured, build_credential_store

logger = logging.getLogger(__name__)

MENSAGEM_NAO_CONFIGURADA = VistaCredentialResolver.MENSAGEM

#: DI slot: a zero-arg factory returning the `CredentialStore` (tests install a `FakeCredentialStore`; None = the real
#: encrypted store over the admin client).
_store_factory: Optional[Callable[[], CredentialStore]] = None


def configure_store(factory: Optional[Callable[[], CredentialStore]]) -> None:
    global _store_factory
    _store_factory = factory


def build_store() -> CredentialStore:
    """The credential store (raises `EncryptionNotConfigured` when ENCRYPTION_KEY is missing -- never plaintext)."""
    if _store_factory is not None:
        return _store_factory()
    from app.dependencies import get_admin_client

    return build_credential_store(get_admin_client())


def adapter_da_org(org_id: Any, store: Optional[CredentialStore] = None) -> VistaRESTAdapter:
    """The Real Vista adapter for this org. Raises `VistaConfigError` when the org has no usable record."""
    try:
        return get_vista_adapter_for_org(VistaCredentialResolver(store or build_store()), str(org_id))  # type: ignore[return-value]
    except EncryptionNotConfigured as exc:
        raise VistaConfigError(str(exc)) from exc


def adapter_ou_503(org_id: Any) -> VistaRESTAdapter:
    """Request path: the adapter or a 503 (`Vista não configurada para esta empresa`)."""
    try:
        return adapter_da_org(org_id)
    except VistaConfigError as exc:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)) from exc


def adapter_ou_none(org_id: Any) -> Optional[VistaRESTAdapter]:
    """Optional-Vista paths (a WhatsApp upload degrades to a manual title): the adapter or None, logged."""
    try:
        return adapter_da_org(org_id)
    except VistaConfigError as exc:
        logger.info("Vista not configured for org %s (%s)", org_id, exc)
        return None


def ler(org_id: Any, store: Optional[CredentialStore] = None) -> Optional[dict[str, Any]]:
    """The org's record as the settings screen may see it -- NEVER the key: `{base_url, chave_final, verificado_em}`."""
    stored = (store or build_store()).get(str(org_id), VISTA_PROVIDER)
    tokens = (stored.tokens if stored is not None else None) or {}
    if not tokens.get("api_key"):
        return None
    return {"base_url": tokens.get("base_url"), "chave_final": tokens.get("chave_final") or _chave_final(tokens["api_key"]),
            "verificado_em": tokens.get("verificado_em")}


def salvar(org_id: Any, base_url: str, api_key: str, verificado_por: Optional[str], store: Optional[CredentialStore] = None) -> dict[str, Any]:
    agora = datetime.now(timezone.utc).isoformat()
    (store or build_store()).put(str(org_id), VISTA_PROVIDER, {
        "base_url": base_url, "api_key": api_key, "chave_final": _chave_final(api_key),
        "verificado_em": agora, "verificado_por": verificado_por,
    })
    return {"base_url": base_url, "chave_final": _chave_final(api_key), "verificado_em": agora}


def remover(org_id: Any, store: Optional[CredentialStore] = None) -> bool:
    return (store or build_store()).delete(str(org_id), VISTA_PROVIDER)
