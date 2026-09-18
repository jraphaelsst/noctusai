"""`D4SignSandbox` — drives the real `D4SignAdapter` against the local stub
with zero network (`httpx.ASGITransport`). Proves the sandbox speaks the
SAME wire protocol `test_real.py` pins its `httpx.MockTransport` fixtures
against, end to end: upload -> signers -> send -> advance -> webhook ->
download -> cancel.
"""
from __future__ import annotations

import asyncio

import httpx
import pytest

from noctusai_lib.integrations.signature import (
    D4SignAdapter,
    DocumentoAssinadoIndisponivel,
    DocumentoParaAssinar,
    Signatario,
)
from noctusai_lib.testing.d4sign_sandbox import (
    D4SignSandbox,
    UnknownDocumentError,
)

CRYPT_KEY = "sandbox-crypt-key"
SAFE_UUID = "sandbox-safe-uuid"


def _sandbox() -> D4SignSandbox:
    return D4SignSandbox(crypt_key=CRYPT_KEY, safe_uuid=SAFE_UUID)


def _adapter(sandbox: D4SignSandbox, **kwargs) -> D4SignAdapter:
    return D4SignAdapter(
        api_token="tok",
        crypt_key=CRYPT_KEY,
        safe_uuid=SAFE_UUID,
        transport=httpx.ASGITransport(app=sandbox.app()),
        **kwargs,
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
        )
    ]


def test_criar_envelope_round_trips_through_the_sandbox() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    assert envelope.external_id.startswith("sbx-")
    assert envelope.provedor == "d4sign"
    assert envelope.link_assinatura == f"https://secure.d4sign.com.br/documents/{envelope.external_id}"
    assert [s.email for s in envelope.signatarios] == ["ana@example.com"]


def test_consultar_starts_pendente() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    evento = asyncio.run(adapter.consultar(envelope.external_id))
    assert evento.status == "pendente"
    assert evento.documento_assinado_disponivel is False


def test_advance_partial_then_completed_flips_status() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    signatarios = _signatarios() + [
        Signatario(
            nome="Beto Vendedor",
            email="beto@example.com",
            cpf="123.456.789-09",
            papel="vendedor",
        )
    ]
    envelope = asyncio.run(adapter.criar_envelope(_documento(), signatarios))

    asyncio.run(sandbox.advance(envelope.external_id, signer_email="ana@example.com"))
    parcial = asyncio.run(adapter.consultar(envelope.external_id))
    assert parcial.status == "parcial"

    asyncio.run(sandbox.advance(envelope.external_id, signer_email="beto@example.com"))
    concluido = asyncio.run(adapter.consultar(envelope.external_id))
    assert concluido.status == "concluido"
    assert concluido.documento_assinado_disponivel is True


def test_advance_force_completed_skips_partial() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    asyncio.run(sandbox.advance(envelope.external_id, force_completed=True))
    evento = asyncio.run(adapter.consultar(envelope.external_id))
    assert evento.status == "concluido"


def test_advance_unknown_document_raises() -> None:
    sandbox = _sandbox()
    with pytest.raises(UnknownDocumentError):
        asyncio.run(sandbox.advance("does-not-exist"))


def test_baixar_assinado_downloads_original_bytes_once_concluido() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    with pytest.raises(DocumentoAssinadoIndisponivel):
        asyncio.run(adapter.baixar_assinado(envelope.external_id))

    asyncio.run(sandbox.advance(envelope.external_id, force_completed=True))
    conteudo = asyncio.run(adapter.baixar_assinado(envelope.external_id))
    assert conteudo == b"%PDF-1.4 ..."


def test_cancelar_marks_cancelado() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    evento = asyncio.run(adapter.cancelar(envelope.external_id, "cliente desistiu"))
    assert evento.status == "cancelado"

    consulta = asyncio.run(adapter.consultar(envelope.external_id))
    assert consulta.status == "cancelado"


def test_emitted_webhook_carries_a_real_verifiable_hmac() -> None:
    """The core promise of the sandbox: what it emits is byte-for-byte what
    `D4SignAdapter.validar_webhook` (the REAL, unmodified verification
    code) accepts — computed with `compute_hmac_sha256_hex`, verified with
    `verify_hmac_sha256_hex`, no test-only shortcut on either side."""
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    evento_emitido = asyncio.run(
        sandbox.advance(envelope.external_id, force_completed=True)
    )
    assert "Content-HMAC" in evento_emitido.headers

    evento = adapter.validar_webhook(*evento_emitido.as_wire())
    assert evento.external_id == envelope.external_id
    assert evento.status == "concluido"
    assert evento.documento_assinado_disponivel is True


def test_emitted_webhook_rejected_by_a_different_crypt_key() -> None:
    """Proves the sandbox's HMAC is a REAL secret-bound signature, not a
    fixed/ignorable stamp — an adapter configured with the wrong crypt_key
    must reject it exactly as it would reject a tampered live webhook."""
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))
    evento_emitido = asyncio.run(
        sandbox.advance(envelope.external_id, force_completed=True)
    )

    wrong_key_adapter = D4SignAdapter(
        api_token="tok", crypt_key="not-the-real-key", safe_uuid=SAFE_UUID
    )
    from noctusai_lib.integrations.signature import WebhookInvalido

    with pytest.raises(WebhookInvalido):
        wrong_key_adapter.validar_webhook(*evento_emitido.as_wire())


def test_control_webhooks_lists_every_emitted_event() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))

    asyncio.run(sandbox.advance(envelope.external_id, force_completed=True))
    asyncio.run(adapter.cancelar(envelope.external_id, "motivo"))

    assert len(sandbox.emitted_webhooks) == 1  # cancelar doesn't emit a webhook


def test_uploadbinary_to_the_wrong_safe_uuid_is_rejected() -> None:
    """Coherence with §1.4: the safe_uuid in the path IS the cofre — a
    request for a different one must not silently succeed."""
    sandbox = _sandbox()
    adapter = D4SignAdapter(
        api_token="tok",
        crypt_key=CRYPT_KEY,
        safe_uuid="wrong-safe-uuid",
        transport=httpx.ASGITransport(app=sandbox.app()),
    )
    from noctusai_lib.integrations.signature import EnvelopeRecusado

    with pytest.raises(EnvelopeRecusado):
        asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))


def test_consultar_unknown_document_is_a_404() -> None:
    sandbox = _sandbox()
    adapter = _adapter(sandbox)
    from noctusai_lib.integrations.signature import EnvelopeRecusado

    with pytest.raises(EnvelopeRecusado):
        asyncio.run(adapter.consultar("never-created"))


def test_response_hook_observes_every_step_without_changing_behaviour() -> None:
    sandbox = _sandbox()
    observed: list[tuple[str, dict]] = []
    adapter = _adapter(sandbox, response_hook=lambda step, body: observed.append((step, body)))

    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))
    asyncio.run(adapter.consultar(envelope.external_id))

    steps = [step for step, _ in observed]
    assert steps == ["uploadbinary", "createlist", "sendtosigner", "status"]
    assert observed[0][1] == {"uuid": envelope.external_id}


def test_response_hook_failure_never_breaks_a_real_call() -> None:
    sandbox = _sandbox()

    def boom(step: str, body: dict) -> None:
        raise RuntimeError("instrumentation bug, must never surface")

    adapter = _adapter(sandbox, response_hook=boom)
    envelope = asyncio.run(adapter.criar_envelope(_documento(), _signatarios()))
    assert envelope.external_id.startswith("sbx-")
