"""`D4SignAdapter` — the real D4Sign wire calls. Contract §1.4.

Pinned wire shapes only; **no live D4Sign account was available while
building this** (contract §0/F2 — zero signing credentials exist on the
platform at authoring time), so every request/response shape below is
unit-tested against the wire shapes §1.4 documents, not verified against
a live response. Two shapes fall outside what §1.4 pins explicitly and
are called out at their call site instead of asserted as fact:

- `link_assinatura` on `criar_envelope`'s return value — the upload step's
  documented response is `{"uuid": ...}` only, with no signing-portal URL.
  A `https://secure.d4sign.com.br/documents/{uuid}` link is synthesized
  from the well-known D4Sign document-viewer path; TODO verify against a
  live account once credentials land (`NOC-REMEDIATE[d4sign-portal-link]`).
- `SignatarioRemoto.external_id` per signer — the `createlist` response
  shape is not part of the pinned contract (§1.4 only pins its request
  body), so each signer's id is synthesized as `f"{external_id}:{email}"`
  rather than trusting an unverified vendor field.

🔴 There is no silent fallback anywhere in this file. A transport failure,
timeout or 5xx raises `ProvedorIndisponivel`; a 4xx raises `EnvelopeRecusado`
with the provider's own message attached. Nothing here ever returns a mock
envelope — `make_signature_adapter` is the only place a credential-less org
is refused, and it raises `ProvedorNaoConfigurado` before this class is even
constructed.
"""
from __future__ import annotations

import base64
from datetime import datetime, timezone
from typing import Any, Mapping, cast
from urllib.parse import parse_qs

import httpx

from noctusai_lib.integrations import rate_limit
from noctusai_lib.integrations.signature.exceptions import (
    DocumentoAssinadoIndisponivel,
    EnvelopeRecusado,
    ProvedorIndisponivel,
    WebhookInvalido,
)
from noctusai_lib.integrations.signature.types import (
    DocumentoParaAssinar,
    EnvelopeCriado,
    EventoAssinatura,
    Signatario,
    SignatarioRemoto,
    StatusAssinatura,
)
from noctusai_lib.security.webhook_signatures import verify_hmac_sha256_hex

DEFAULT_BASE_URL = "https://secure.d4sign.com.br/api/v1"
DEFAULT_TIMEOUT_SECONDS = 30.0

#: Shared token-bucket name — see `noctusai_lib.integrations.rate_limit`.
#: One bucket for every org's D4Sign traffic; a slow org can't starve a
#: fast one because pacing is per-provider, not per-org, but this keeps
#: the whole platform under D4Sign's ceiling regardless of which org's
#: request triggered it.
RATE_LIMIT_BUCKET = "d4sign"

#: §1.4's statusId → StatusAssinatura mapping. Reused by both `consultar`
#: (the documented field) and `validar_webhook` (D4Sign's `type_post` is
#: NOT pinned by the contract as a separate vocabulary, and reusing the
#: statusId table is the only defensible reading absent a live account to
#: confirm the webhook's own code list against —
#: `NOC-REMEDIATE[d4sign-webhook-type-post]`).
_STATUS_POR_ID: dict[str, StatusAssinatura] = {
    "1": "pendente",
    "2": "pendente",
    "3": "parcial",
    "4": "concluido",
    "5": "cancelado",
    "6": "cancelado",
    "7": "expirado",
}

#: `sendtosigner`'s "message" field has no source in the Protocol —
#: `criar_envelope(documento, signatarios)` carries no message parameter
#: (contract §1.1). Using a fixed default here is a known gap; surface to
#: the tech-lead if a product needs this to be operator-editable copy.
_MENSAGEM_ENVIO_PADRAO = "Você recebeu um documento para assinatura eletrônica."


def _mapear_status_id(bruto: Any) -> StatusAssinatura:
    chave = str(bruto)
    try:
        return _STATUS_POR_ID[chave]
    except KeyError:
        raise ProvedorIndisponivel(
            f"D4Sign returned an unrecognised statusId/type_post: {bruto!r}"
        ) from None


def _cabecalho(cabecalhos: Mapping[str, str], nome: str) -> str | None:
    alvo = nome.lower()
    for chave, valor in cabecalhos.items():
        if chave.lower() == alvo:
            return valor
    return None


def _mensagem_provedor(response: httpx.Response) -> str | None:
    """Best-effort provider error text — D4Sign's error body shape isn't
    pinned by the contract, so this degrades to raw text rather than
    assuming a JSON field name that might not exist."""
    try:
        body = response.json()
    except ValueError:
        texto = response.text
        return texto or None
    if isinstance(body, dict):
        for chave in ("message", "error", "erro"):
            valor = body.get(chave)
            if valor:
                return str(valor)
    return str(body)


class D4SignAdapter:
    """Real D4Sign adapter. Auth by query string
    (`?tokenAPI=<t>&cryptKey=<c>` — D4Sign does not accept these as
    headers). One `httpx.AsyncClient` held for the adapter's lifetime;
    inject `transport=` (an `httpx.MockTransport`) to test the exact
    request/response path with no network, mirroring
    `noctusai_lib.integrations.mailchimp.client.HttpxMailchimpClient`'s
    seam.
    """

    def __init__(
        self,
        *,
        api_token: str,
        crypt_key: str,
        safe_uuid: str,
        base_url: str = DEFAULT_BASE_URL,
        timeout: float = DEFAULT_TIMEOUT_SECONDS,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._crypt_key = crypt_key
        self._safe_uuid = safe_uuid
        self._base_url = base_url.rstrip("/")
        self._params = {"tokenAPI": api_token, "cryptKey": crypt_key}
        self._client = httpx.AsyncClient(timeout=timeout, transport=transport)

    async def aclose(self) -> None:
        """Release the held `AsyncClient`. Optional — call at shutdown for
        a long-lived process; a short-lived job handler may skip it."""
        await self._client.aclose()

    async def _request(
        self, method: str, path: str, *, json_body: dict | None = None
    ) -> dict:
        url = f"{self._base_url}{path}"
        await rate_limit.acquire_async(RATE_LIMIT_BUCKET)
        try:
            response = await self._client.request(
                method, url, params=self._params, json=json_body
            )
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProvedorIndisponivel(f"D4Sign unreachable: {exc}") from exc

        if response.status_code >= 500:
            raise ProvedorIndisponivel(
                f"D4Sign {response.status_code}: {_mensagem_provedor(response)}"
            )
        if response.status_code >= 400:
            raise EnvelopeRecusado(
                f"D4Sign rejected the request ({response.status_code})",
                provedor_mensagem=_mensagem_provedor(response),
            )
        if not response.content:
            return {}
        try:
            body = response.json()
        except ValueError:
            return {}
        return body if isinstance(body, dict) else {}

    async def criar_envelope(
        self, documento: DocumentoParaAssinar, signatarios: list[Signatario]
    ) -> EnvelopeCriado:
        # Step 1 — upload. The document BYTES go up here (F1's fix; erp's
        # scaffold posted a URL instead).
        b64 = base64.b64encode(documento.conteudo).decode("ascii")
        upload = await self._request(
            "POST",
            f"/documents/{self._safe_uuid}/uploadbinary",
            json_body={
                "base64_binary_file": b64,
                "mime_type": documento.mime_type,
                "name": documento.nome,
            },
        )
        external_id = upload.get("uuid")
        if not external_id:
            raise ProvedorIndisponivel(
                "D4Sign uploadbinary response carried no 'uuid'"
            )

        # Step 2 — signers, one call for all of them.
        await self._request(
            "POST",
            f"/documents/{external_id}/createlist",
            json_body={
                "signers": [
                    {
                        "email": s.email,
                        "act": "1",
                        "foreign": "0",
                        "certificadoicpbr": "0",
                        "assinatura_presencial": "0",
                    }
                    for s in signatarios
                ]
            },
        )

        # Step 3 — send to signers.
        await self._request(
            "POST",
            f"/documents/{external_id}/sendtosigner",
            json_body={
                "message": _MENSAGEM_ENVIO_PADRAO,
                "skip_email": "0",
                "workflow": "0",
            },
        )

        # createlist's response shape isn't pinned (see module docstring) —
        # synthesize a stable per-signer id from what IS known.
        remotos = tuple(
            SignatarioRemoto(email=s.email, external_id=f"{external_id}:{s.email}")
            for s in signatarios
        )
        return EnvelopeCriado(
            external_id=external_id,
            link_assinatura=f"https://secure.d4sign.com.br/documents/{external_id}",
            provedor="d4sign",
            signatarios=remotos,
            criado_em=datetime.now(timezone.utc),
        )

    async def consultar(self, external_id: str) -> EventoAssinatura:
        body = await self._request("GET", f"/documents/{external_id}")
        status = _mapear_status_id(body.get("statusId"))
        return EventoAssinatura(
            external_id=external_id,
            status=status,
            provedor="d4sign",
            ocorrido_em=datetime.now(timezone.utc),
            # D4Sign's per-signer detail in this response isn't pinned by
            # the contract (§1.4 documents `statusId` only) — left empty
            # rather than trusting an unverified field shape.
            signatarios=(),
            documento_assinado_disponivel=status == "concluido",
        )

    async def baixar_assinado(self, external_id: str) -> bytes:
        evento = await self.consultar(external_id)
        if evento.status != "concluido":
            raise DocumentoAssinadoIndisponivel(
                f"external_id={external_id} status={evento.status!r} != 'concluido'"
            )

        body = await self._request("GET", f"/documents/{external_id}/download")
        url = body.get("url")
        if not url:
            raise ProvedorIndisponivel(
                "D4Sign download step returned no 'url'"
            )

        await rate_limit.acquire_async(RATE_LIMIT_BUCKET)
        try:
            response = await self._client.get(url)
        except (httpx.TimeoutException, httpx.TransportError) as exc:
            raise ProvedorIndisponivel(
                f"D4Sign unreachable fetching signed document: {exc}"
            ) from exc
        if response.status_code >= 500:
            raise ProvedorIndisponivel(
                f"D4Sign signed-document fetch failed ({response.status_code})"
            )
        if response.status_code >= 400:
            raise EnvelopeRecusado(
                f"D4Sign rejected the signed-document fetch ({response.status_code})",
                provedor_mensagem=_mensagem_provedor(response),
            )
        return response.content

    def validar_webhook(
        self, corpo: bytes, cabecalhos: Mapping[str, str]
    ) -> EventoAssinatura:
        assinatura = _cabecalho(cabecalhos, "Content-HMAC")
        if not assinatura:
            raise WebhookInvalido("missing Content-HMAC header")
        if not verify_hmac_sha256_hex(corpo, assinatura, self._crypt_key):
            raise WebhookInvalido("Content-HMAC did not verify")

        try:
            texto = corpo.decode("utf-8")
        except UnicodeDecodeError as exc:
            raise WebhookInvalido(f"malformed webhook body: {exc}") from exc
        campos = parse_qs(texto)

        uuid_doc = (campos.get("uuid") or [None])[0]
        type_post = (campos.get("type_post") or [None])[0]
        if not uuid_doc or type_post is None:
            raise WebhookInvalido(
                f"webhook body missing 'uuid'/'type_post': {texto!r}"
            )

        try:
            status = _mapear_status_id(type_post)
        except ProvedorIndisponivel as exc:
            raise WebhookInvalido(str(exc)) from exc

        return EventoAssinatura(
            external_id=cast(str, uuid_doc),
            status=status,
            provedor="d4sign",
            ocorrido_em=datetime.now(timezone.utc),
            signatarios=(),
            documento_assinado_disponivel=status == "concluido",
        )

    async def cancelar(self, external_id: str, motivo: str) -> EventoAssinatura:
        await self._request(
            "POST", f"/documents/{external_id}/cancel", json_body={"comment": motivo}
        )
        return EventoAssinatura(
            external_id=external_id,
            status="cancelado",
            provedor="d4sign",
            ocorrido_em=datetime.now(timezone.utc),
            signatarios=(),
        )


__all__ = ["D4SignAdapter"]
