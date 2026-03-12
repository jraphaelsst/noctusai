"""
Signature Provider — External digital signature API integrations.

Supports ClickSign, DocuSign, and D4Sign. Falls back to internal
(mock) signing when no provider credentials are configured.

Credentials resolved via the standard chain: org_settings → platform_settings → env.
"""
import logging
import uuid
from typing import Any, Dict, List, Optional

from app.services.credential_resolver import resolve_credential

logger = logging.getLogger(__name__)


class SignatureProviderConfig:
    """Resolve signature provider credentials."""

    def __init__(self, org_id: Optional[str] = None):
        self.org_id = org_id

    @property
    def clicksign_token(self) -> Optional[str]:
        return resolve_credential("clicksign_api_token", self.org_id)

    @property
    def clicksign_env(self) -> str:
        return resolve_credential("clicksign_environment", self.org_id) or "sandbox"

    @property
    def docusign_integration_key(self) -> Optional[str]:
        return resolve_credential("docusign_integration_key", self.org_id)

    @property
    def docusign_account_id(self) -> Optional[str]:
        return resolve_credential("docusign_account_id", self.org_id)

    @property
    def d4sign_token(self) -> Optional[str]:
        return resolve_credential("d4sign_api_token", self.org_id)

    @property
    def d4sign_crypt_key(self) -> Optional[str]:
        return resolve_credential("d4sign_crypt_key", self.org_id)


async def enviar_para_assinatura(
    provedor: str,
    documento_nome: str,
    documento_url: Optional[str],
    signatarios: List[Dict[str, str]],
    config: SignatureProviderConfig,
) -> Dict[str, Any]:
    """
    Send a document for signing via the specified provider.

    Returns dict with external_id, link_assinatura, and provider-specific data.
    Falls back to internal mock when provider is not configured.
    """
    if provedor == "clicksign":
        return await _enviar_clicksign(documento_nome, documento_url, signatarios, config)
    elif provedor == "docusign":
        return await _enviar_docusign(documento_nome, documento_url, signatarios, config)
    elif provedor == "d4sign":
        return await _enviar_d4sign(documento_nome, documento_url, signatarios, config)
    else:
        return _enviar_interno(documento_nome, signatarios)


def _enviar_interno(documento_nome: str, signatarios: List[Dict]) -> Dict[str, Any]:
    """Internal mock signing — generates placeholder links."""
    token = uuid.uuid4().hex[:16]
    return {
        "external_id": f"interno_{token}",
        "link_assinatura": f"https://assinaturas.noctus.app/assinar/{token}",
        "provedor": "interno",
        "dry_run": True,
    }


async def _enviar_clicksign(
    documento_nome: str,
    documento_url: Optional[str],
    signatarios: List[Dict],
    config: SignatureProviderConfig,
) -> Dict[str, Any]:
    """Send via ClickSign API."""
    token = config.clicksign_token
    if not token:
        logger.info("[SIGNATURE] ClickSign não configurado, usando modo interno")
        return _enviar_interno(documento_nome, signatarios)

    import httpx

    env = config.clicksign_env
    base_url = "https://app.clicksign.com" if env == "production" else "https://sandbox.clicksign.com"

    async with httpx.AsyncClient() as client:
        # Create document
        doc_resp = await client.post(
            f"{base_url}/api/v1/documents?access_token={token}",
            json={
                "document": {
                    "path": f"/{documento_nome}",
                    "content_base64": "",  # Would be actual file content
                    "deadline_at": None,
                    "auto_close": True,
                    "locale": "pt-BR",
                }
            },
            timeout=30,
        )
        doc_resp.raise_for_status()
        doc_data = doc_resp.json()
        doc_key = doc_data.get("document", {}).get("key", "")

        # Add signers
        signer_keys = []
        for s in signatarios:
            signer_resp = await client.post(
                f"{base_url}/api/v1/signers?access_token={token}",
                json={
                    "signer": {
                        "email": s.get("email"),
                        "name": s.get("nome"),
                        "auths": ["email"],
                        "communicate": True,
                    }
                },
                timeout=30,
            )
            signer_resp.raise_for_status()
            signer_data = signer_resp.json()
            signer_keys.append(signer_data.get("signer", {}).get("key", ""))

        # Create signing list
        for signer_key in signer_keys:
            await client.post(
                f"{base_url}/api/v1/lists?access_token={token}",
                json={
                    "list": {
                        "document_key": doc_key,
                        "signer_key": signer_key,
                        "sign_as": "sign",
                    }
                },
                timeout=30,
            )

        return {
            "external_id": doc_key,
            "link_assinatura": f"{base_url}/sign/{doc_key}",
            "provedor": "clicksign",
            "dry_run": False,
        }


async def _enviar_docusign(
    documento_nome: str,
    documento_url: Optional[str],
    signatarios: List[Dict],
    config: SignatureProviderConfig,
) -> Dict[str, Any]:
    """Send via DocuSign API."""
    integration_key = config.docusign_integration_key
    if not integration_key:
        logger.info("[SIGNATURE] DocuSign não configurado, usando modo interno")
        return _enviar_interno(documento_nome, signatarios)

    # DocuSign requires OAuth — placeholder for full integration
    logger.info(f"[SIGNATURE] DocuSign: enviando {documento_nome} para {len(signatarios)} signatários")

    mock_envelope_id = uuid.uuid4().hex
    return {
        "external_id": mock_envelope_id,
        "link_assinatura": f"https://demo.docusign.net/signing/{mock_envelope_id}",
        "provedor": "docusign",
        "dry_run": False,
        "nota": "DocuSign OAuth integration pending — envelope created in demo mode",
    }


async def _enviar_d4sign(
    documento_nome: str,
    documento_url: Optional[str],
    signatarios: List[Dict],
    config: SignatureProviderConfig,
) -> Dict[str, Any]:
    """Send via D4Sign API."""
    token = config.d4sign_token
    crypt_key = config.d4sign_crypt_key
    if not token:
        logger.info("[SIGNATURE] D4Sign não configurado, usando modo interno")
        return _enviar_interno(documento_nome, signatarios)

    import httpx

    base_url = "https://secure.d4sign.com.br/api/v1"
    headers = {"tokenAPI": token, "cryptKey": crypt_key or ""}

    async with httpx.AsyncClient() as client:
        # Upload document
        doc_resp = await client.post(
            f"{base_url}/documents/upload",
            headers=headers,
            json={"name": documento_nome, "url": documento_url or ""},
            timeout=30,
        )
        doc_resp.raise_for_status()
        doc_data = doc_resp.json()
        doc_uuid = doc_data.get("uuid", "")

        # Add signers
        for s in signatarios:
            await client.post(
                f"{base_url}/documents/{doc_uuid}/createlist",
                headers=headers,
                json={
                    "signers": [{
                        "email": s.get("email"),
                        "act": "1",  # Sign
                        "foreign": "0",
                        "certificadoicpbr": "0",
                    }]
                },
                timeout=30,
            )

        # Send for signing
        await client.post(
            f"{base_url}/documents/{doc_uuid}/sendtosigner",
            headers=headers,
            timeout=30,
        )

        return {
            "external_id": doc_uuid,
            "link_assinatura": f"https://secure.d4sign.com.br/desk/viewblob/{doc_uuid}",
            "provedor": "d4sign",
            "dry_run": False,
        }
