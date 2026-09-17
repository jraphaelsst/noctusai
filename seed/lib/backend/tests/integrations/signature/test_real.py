"""`D4SignAdapter` — pinned wire shapes, contract §1.4. No network:
`httpx.MockTransport` is the DI seam (mirrors
`noctusai_lib.integrations.mailchimp.client.HttpxMailchimpClient`'s tests).

Every one of the 6 documented D4Sign calls (upload, createlist,
sendtosigner, status, download, cancel) gets its own pinned-response test,
plus the HMAC webhook validation (valid / tampered / absent) and the
error-taxonomy mapping (4xx -> EnvelopeRecusado, 5xx/timeout ->
ProvedorIndisponivel).
"""
from __future__ import annotations

import asyncio
import base64
import json
from urllib.parse import parse_qs, urlparse

import httpx
import pytest

from noctusai_lib.integrations.signature import (
    D4SignAdapter,
    DocumentoAssinadoIndisponivel,
    DocumentoParaAssinar,
    EnvelopeRecusado,
    ProvedorIndisponivel,
    Signatario,
    SignatureAdapter,
    WebhookInvalido,
)
from noctusai_lib.security.webhook_signatures import compute_hmac_sha256_hex

API_TOKEN = "tok-123"
CRYPT_KEY = "crypt-456"
SAFE_UUID = "safe-uuid-789"


def _documento() -> DocumentoParaAssinar:
    return DocumentoParaAssinar(nome="Promessa - v3.pdf", conteudo=b"%PDF-1.4 ...")


def _signatarios() -> list[Signatario]:
    return [
        Signatario(
            nome="Ana Compradora",
            email="ana@example.com",
            cpf="412.954.238-98",
            papel="comprador",
        )
    ]


def _adapter(handler, **kwargs) -> D4SignAdapter:
    return D4SignAdapter(
        api_token=API_TOKEN,
        crypt_key=CRYPT_KEY,
        safe_uuid=SAFE_UUID,
        transport=httpx.MockTransport(handler),
        **kwargs,
    )


def _json_response(status: int, body: dict) -> httpx.Response:
    return httpx.Response(status, content=json.dumps(body).encode())


def test_satisfies_the_protocol() -> None:
    adapter = D4SignAdapter(api_token="t", crypt_key="c", safe_uuid="s")
    assert isinstance(adapter, SignatureAdapter)


# ---------------------------------------------------------------------------
# Step 1 — upload
# ---------------------------------------------------------------------------


def test_criar_envelope_uploads_the_document_bytes() -> None:
    """F1's fix: the ACTUAL bytes go up, never a URL."""
    captured: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        captured.append(request)
        if request.url.path.endswith("/uploadbinary"):
            return _json_response(200, {"uuid": "doc-uuid-1"})
        if request.url.path.endswith("/createlist"):
            return _json_response(200, {})
        if request.url.path.endswith("/sendtosigner"):
            return _json_response(200, {})
        raise AssertionError(f"unexpected path: {request.url.path}")

    adapter = _adapter(handler)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    assert envelope.external_id == "doc-uuid-1"
    assert envelope.provedor == "d4sign"
    assert envelope.link_assinatura == "https://secure.d4sign.com.br/documents/doc-uuid-1"

    upload_req = captured[0]
    assert upload_req.url.path == f"/api/v1/documents/{SAFE_UUID}/uploadbinary"
    params = parse_qs(upload_req.url.query.decode())
    assert params["tokenAPI"] == [API_TOKEN]
    assert params["cryptKey"] == [CRYPT_KEY]

    upload_body = json.loads(upload_req.content)
    assert upload_body["mime_type"] == "application/pdf"
    assert upload_body["name"] == "Promessa - v3.pdf"
    assert base64.b64decode(upload_body["base64_binary_file"]) == b"%PDF-1.4 ..."


# ---------------------------------------------------------------------------
# Step 2 — signers
# ---------------------------------------------------------------------------


def test_criar_envelope_sends_one_createlist_call_with_all_signers() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/uploadbinary"):
            return _json_response(200, {"uuid": "doc-uuid-2"})
        if request.url.path.endswith("/createlist"):
            captured["createlist"] = request
            return _json_response(200, {})
        if request.url.path.endswith("/sendtosigner"):
            return _json_response(200, {})
        raise AssertionError(f"unexpected path: {request.url.path}")

    adapter = _adapter(handler)
    signatarios = _signatarios() + [
        Signatario(
            nome="Beto Vendedor",
            email="beto@example.com",
            cpf="123.456.789-09",
            papel="vendedor",
        )
    ]
    envelope = asyncio.run(adapter.criar_envelope(_documento(), signatarios))

    assert [s.email for s in envelope.signatarios] == ["ana@example.com", "beto@example.com"]

    createlist_req = captured["createlist"]
    assert createlist_req.url.path == "/api/v1/documents/doc-uuid-2/createlist"
    body = json.loads(createlist_req.content)
    assert body == {
        "signers": [
            {
                "email": "ana@example.com",
                "act": "1",
                "foreign": "0",
                "certificadoicpbr": "0",
                "assinatura_presencial": "0",
            },
            {
                "email": "beto@example.com",
                "act": "1",
                "foreign": "0",
                "certificadoicpbr": "0",
                "assinatura_presencial": "0",
            },
        ]
    }


# ---------------------------------------------------------------------------
# Step 3 — send
# ---------------------------------------------------------------------------


def test_criar_envelope_calls_sendtosigner() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/uploadbinary"):
            return _json_response(200, {"uuid": "doc-uuid-3"})
        if request.url.path.endswith("/createlist"):
            return _json_response(200, {})
        if request.url.path.endswith("/sendtosigner"):
            captured["sendtosigner"] = request
            return _json_response(200, {})
        raise AssertionError(f"unexpected path: {request.url.path}")

    adapter = _adapter(handler)
    asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    req = captured["sendtosigner"]
    assert req.url.path == "/api/v1/documents/doc-uuid-3/sendtosigner"
    body = json.loads(req.content)
    assert body["skip_email"] == "0"
    assert body["workflow"] == "0"
    assert isinstance(body["message"], str) and body["message"]


def test_upload_with_no_uuid_raises_provedor_indisponivel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {})

    adapter = _adapter(handler)
    with pytest.raises(ProvedorIndisponivel):
        asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))


# ---------------------------------------------------------------------------
# Step 4 — status
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "status_id, esperado",
    [
        (1, "pendente"),
        (2, "pendente"),
        (3, "parcial"),
        (4, "concluido"),
        (5, "cancelado"),
        (6, "cancelado"),
        (7, "expirado"),
    ],
)
def test_consultar_maps_status_id(status_id: int, esperado: str) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/api/v1/documents/doc-uuid-4"
        return _json_response(200, {"statusId": status_id})

    adapter = _adapter(handler)
    evento = asyncio.run(adapter.consultar("doc-uuid-4"))

    assert evento.status == esperado
    assert evento.provedor == "d4sign"
    assert evento.documento_assinado_disponivel == (esperado == "concluido")


def test_consultar_unrecognised_status_id_raises_provedor_indisponivel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"statusId": 99})

    adapter = _adapter(handler)
    with pytest.raises(ProvedorIndisponivel):
        asyncio.run(adapter.consultar("doc-uuid-4"))


# ---------------------------------------------------------------------------
# Step 5 — download
# ---------------------------------------------------------------------------


def test_baixar_assinado_downloads_after_status_check() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/api/v1/documents/doc-uuid-5":
            return _json_response(200, {"statusId": 4})
        if request.url.path == "/api/v1/documents/doc-uuid-5/download":
            return _json_response(200, {"url": "https://files.d4sign.com.br/signed.pdf"})
        if request.url.path == "/signed.pdf":
            return httpx.Response(200, content=b"%PDF-1.4 signed bytes")
        raise AssertionError(f"unexpected path: {request.url.path}")

    adapter = _adapter(handler)
    conteudo = asyncio.run(adapter.baixar_assinado("doc-uuid-5"))
    assert conteudo == b"%PDF-1.4 signed bytes"


def test_baixar_assinado_before_concluido_raises_documento_indisponivel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(200, {"statusId": 1})

    adapter = _adapter(handler)
    with pytest.raises(DocumentoAssinadoIndisponivel):
        asyncio.run(adapter.baixar_assinado("doc-uuid-5"))


def test_baixar_assinado_missing_url_raises_provedor_indisponivel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/download"):
            return _json_response(200, {})
        return _json_response(200, {"statusId": 4})

    adapter = _adapter(handler)
    with pytest.raises(ProvedorIndisponivel):
        asyncio.run(adapter.baixar_assinado("doc-uuid-5"))


# ---------------------------------------------------------------------------
# Step 6 — cancel
# ---------------------------------------------------------------------------


def test_cancelar_posts_comment_and_returns_cancelado() -> None:
    captured: dict[str, httpx.Request] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["req"] = request
        return _json_response(200, {})

    adapter = _adapter(handler)
    evento = asyncio.run(adapter.cancelar("doc-uuid-6", "cliente desistiu"))

    assert evento.status == "cancelado"
    req = captured["req"]
    assert req.url.path == "/api/v1/documents/doc-uuid-6/cancel"
    assert json.loads(req.content) == {"comment": "cliente desistiu"}


# ---------------------------------------------------------------------------
# Error taxonomy
# ---------------------------------------------------------------------------


def test_4xx_raises_envelope_recusado_with_provider_message() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return _json_response(400, {"message": "documento inválido"})

    adapter = _adapter(handler)
    with pytest.raises(EnvelopeRecusado) as excinfo:
        asyncio.run(adapter.consultar("doc-uuid-7"))
    assert excinfo.value.details["provedor_mensagem"] == "documento inválido"


def test_5xx_raises_provedor_indisponivel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, content=b"internal error")

    adapter = _adapter(handler)
    with pytest.raises(ProvedorIndisponivel):
        asyncio.run(adapter.consultar("doc-uuid-7"))


def test_timeout_raises_provedor_indisponivel() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("boom", request=request)

    adapter = _adapter(handler)
    with pytest.raises(ProvedorIndisponivel):
        asyncio.run(adapter.consultar("doc-uuid-7"))


# ---------------------------------------------------------------------------
# Webhook HMAC validation
# ---------------------------------------------------------------------------


def _webhook_corpo(uuid: str, type_post: str) -> bytes:
    return f"uuid={uuid}&type_post={type_post}&message=ok".encode()


def test_validar_webhook_valid_signature() -> None:
    adapter = D4SignAdapter(api_token="t", crypt_key=CRYPT_KEY, safe_uuid="s")
    corpo = _webhook_corpo("doc-uuid-8", "4")
    assinatura = compute_hmac_sha256_hex(corpo, CRYPT_KEY)

    evento = adapter.validar_webhook(corpo, {"Content-HMAC": assinatura})

    assert evento.external_id == "doc-uuid-8"
    assert evento.status == "concluido"
    assert evento.documento_assinado_disponivel is True


def test_validar_webhook_tampered_body_raises() -> None:
    adapter = D4SignAdapter(api_token="t", crypt_key=CRYPT_KEY, safe_uuid="s")
    corpo = _webhook_corpo("doc-uuid-8", "4")
    assinatura = compute_hmac_sha256_hex(corpo, CRYPT_KEY)
    corpo_adulterado = _webhook_corpo("doc-uuid-8", "5")

    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(corpo_adulterado, {"Content-HMAC": assinatura})


def test_validar_webhook_absent_signature_raises() -> None:
    adapter = D4SignAdapter(api_token="t", crypt_key=CRYPT_KEY, safe_uuid="s")
    corpo = _webhook_corpo("doc-uuid-8", "4")

    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(corpo, {})


def test_validar_webhook_wrong_secret_raises() -> None:
    adapter = D4SignAdapter(api_token="t", crypt_key=CRYPT_KEY, safe_uuid="s")
    corpo = _webhook_corpo("doc-uuid-8", "4")
    assinatura_errada = compute_hmac_sha256_hex(corpo, "not-the-secret")

    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(corpo, {"Content-HMAC": assinatura_errada})


def test_validar_webhook_never_returns_none() -> None:
    adapter = D4SignAdapter(api_token="t", crypt_key=CRYPT_KEY, safe_uuid="s")
    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(b"", {})
