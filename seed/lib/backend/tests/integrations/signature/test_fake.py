"""`FakeSignatureAdapter` — full lifecycle, no network."""
from __future__ import annotations

import asyncio
import hashlib
import json

import pytest

from noctusai_lib.integrations.signature import (
    DocumentoAssinadoIndisponivel,
    DocumentoParaAssinar,
    FakeSignatureAdapter,
    Signatario,
    SignatureAdapter,
    WebhookInvalido,
)


def _documento() -> DocumentoParaAssinar:
    return DocumentoParaAssinar(nome="Promessa - v3.pdf", conteudo=b"%PDF-1.4 ...")


def _signatarios() -> list[Signatario]:
    return [
        Signatario(
            nome="Ana Compradora",
            email="ana@example.com",
            cpf="412.954.238-98",
            papel="comprador",
        ),
        Signatario(
            nome="Beto Vendedor",
            email="beto@example.com",
            cpf="123.456.789-09",
            papel="vendedor",
        ),
    ]


def test_satisfies_the_protocol() -> None:
    assert isinstance(FakeSignatureAdapter(), SignatureAdapter)


def test_criar_envelope_is_deterministic() -> None:
    adapter = FakeSignatureAdapter()
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    assert envelope.provedor == "d4sign"
    assert envelope.external_id.startswith("fake-")
    assert envelope.link_assinatura == f"https://fake.assinatura.local/{envelope.external_id}"
    assert [s.email for s in envelope.signatarios] == ["ana@example.com", "beto@example.com"]
    assert all(s.assinado_em is None for s in envelope.signatarios)

    # Same document name + same signer e-mails => same external_id.
    outro = FakeSignatureAdapter()
    de_novo = asyncio.run(outro.criar_envelope(_documento(), _signatarios()))
    assert de_novo.external_id == envelope.external_id


def test_full_lifecycle_create_sign_download() -> None:
    adapter = FakeSignatureAdapter()
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))
    external_id = envelope.external_id

    evento = asyncio.run(adapter.consultar(external_id))
    assert evento.status == "pendente"
    assert evento.documento_assinado_disponivel is False

    with pytest.raises(DocumentoAssinadoIndisponivel):
        asyncio.run(adapter.baixar_assinado(external_id))

    adapter.marcar_assinado(external_id, "ana@example.com")
    evento_parcial = asyncio.run(adapter.consultar(external_id))
    assert evento_parcial.status == "parcial"
    assinantes = {s.email: s.assinado_em for s in evento_parcial.signatarios}
    assert assinantes["ana@example.com"] is not None
    assert assinantes["beto@example.com"] is None

    adapter.marcar_assinado(external_id, "beto@example.com")
    evento_final = asyncio.run(adapter.consultar(external_id))
    assert evento_final.status == "concluido"
    assert evento_final.documento_assinado_disponivel is True

    pdf = asyncio.run(adapter.baixar_assinado(external_id))
    assert pdf.startswith(b"%PDF-1.4")


def test_cancelar_sets_status_and_returns_evento() -> None:
    adapter = FakeSignatureAdapter()
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    evento = asyncio.run(adapter.cancelar(envelope.external_id, "cliente desistiu"))
    assert evento.status == "cancelado"

    consultado = asyncio.run(adapter.consultar(envelope.external_id))
    assert consultado.status == "cancelado"


def test_unknown_external_id_raises_key_error() -> None:
    adapter = FakeSignatureAdapter()
    with pytest.raises(KeyError):
        asyncio.run(adapter.consultar("nope"))


# ---------------------------------------------------------------------------
# validar_webhook
# ---------------------------------------------------------------------------


def _webhook_corpo(external_id: str, status: str) -> bytes:
    return json.dumps({"external_id": external_id, "status": status}).encode("utf-8")


def _fake_signature_header(corpo: bytes) -> dict[str, str]:
    return {"x-fake-signature": hashlib.sha256(corpo).hexdigest()}


def test_validar_webhook_valid_signature_returns_evento() -> None:
    adapter = FakeSignatureAdapter()
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))
    corpo = _webhook_corpo(envelope.external_id, "concluido")

    evento = adapter.validar_webhook(corpo, _fake_signature_header(corpo))

    assert evento.external_id == envelope.external_id
    assert evento.status == "concluido"
    assert evento.documento_assinado_disponivel is True


def test_validar_webhook_tampered_body_raises() -> None:
    adapter = FakeSignatureAdapter()
    corpo = _webhook_corpo("fake-abc", "concluido")
    cabecalhos = _fake_signature_header(corpo)
    corpo_adulterado = _webhook_corpo("fake-abc", "cancelado")

    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(corpo_adulterado, cabecalhos)


def test_validar_webhook_absent_signature_raises() -> None:
    adapter = FakeSignatureAdapter()
    corpo = _webhook_corpo("fake-abc", "concluido")

    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(corpo, {})


def test_validar_webhook_never_returns_none_on_bad_json() -> None:
    adapter = FakeSignatureAdapter()
    corpo = b"not json"
    cabecalhos = _fake_signature_header(corpo)

    with pytest.raises(WebhookInvalido):
        adapter.validar_webhook(corpo, cabecalhos)


def test_validar_webhook_header_lookup_is_case_insensitive() -> None:
    adapter = FakeSignatureAdapter()
    corpo = _webhook_corpo("fake-abc", "pendente")
    cabecalhos = {"X-Fake-Signature": hashlib.sha256(corpo).hexdigest()}

    evento = adapter.validar_webhook(corpo, cabecalhos)
    assert evento.status == "pendente"
