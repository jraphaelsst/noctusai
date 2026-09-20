"""
Tests for Assinaturas (digital signatures) router — /api/assinaturas

Provider-level and side-effect isolation goes through the router's own
FastAPI dependency seams (`get_assinatura_service` /
`get_assinatura_service_webhook` / `get_signature_adapter_factory`,
`app.dependency_overrides[...]`) — never by patching `AssinaturaService`
methods or the seed's `make_signature_adapter` (`KB § PATTERNS/backend/
di-test-seam.md`; patching our own class would stop exercising it).
"""
import hashlib
import json

import pytest

from noctusai_lib.integrations.signature import (
    EnvelopeRecusado,
    EventoAssinatura,
    FakeSignatureAdapter,
    ProvedorIndisponivel,
    ProvedorNaoConfigurado,
)


class _FakeAssinaturaService:
    """A tiny test double satisfying the shape `AssinaturaService` exposes
    to the router — only the methods a given test needs are meaningful."""

    def __init__(
        self,
        *,
        preparar_envio_result=None,
        preparar_envio_error: Exception | None = None,
        cancelar_result=None,
        processar_webhook_result=None,
    ):
        self._preparar_envio_result = preparar_envio_result
        self._preparar_envio_error = preparar_envio_error
        self._cancelar_result = cancelar_result
        self._processar_webhook_result = processar_webhook_result

    async def preparar_envio(self, **kwargs):
        if self._preparar_envio_error is not None:
            raise self._preparar_envio_error
        return self._preparar_envio_result

    async def cancelar(self, assinatura_id):
        return self._cancelar_result

    async def processar_webhook(self, evento: EventoAssinatura):
        return self._processar_webhook_result


@pytest.fixture
def override_assinatura_service(client):
    """Override `get_assinatura_service` / `get_assinatura_service_webhook`
    for the duration of one test, restoring whatever was there before."""
    from app.main import app
    from app.routers.assinaturas import (
        get_assinatura_service,
        get_assinatura_service_webhook,
    )

    applied = []

    def _apply(service, *, webhook: bool = False):
        dep = get_assinatura_service_webhook if webhook else get_assinatura_service
        app.dependency_overrides[dep] = lambda: service
        applied.append(dep)

    yield _apply

    for dep in applied:
        app.dependency_overrides.pop(dep, None)


@pytest.fixture
def override_signature_adapter_factory(client):
    """Override `get_signature_adapter_factory` (the webhook route's D4Sign
    seam) for the duration of one test — same shape as social-wiring's
    `card_hub` `fake_signature_adapter` fixture."""
    from app.main import app
    from app.routers.assinaturas import get_signature_adapter_factory

    prev = app.dependency_overrides.get(get_signature_adapter_factory)

    def _apply(adapter):
        app.dependency_overrides[get_signature_adapter_factory] = lambda: (
            lambda org_id: adapter
        )

    yield _apply

    if prev is not None:
        app.dependency_overrides[get_signature_adapter_factory] = prev
    else:
        app.dependency_overrides.pop(get_signature_adapter_factory, None)


@pytest.fixture
def fake_signature_adapter(override_signature_adapter_factory):
    """A real `FakeSignatureAdapter` wired as the webhook route's D4Sign
    adapter — exercises the REAL `validar_webhook` HMAC-check + parsing
    path (never mocked out), only the underlying secret/provider is a
    test double."""
    adapter = FakeSignatureAdapter()
    override_signature_adapter_factory(adapter)
    return adapter


def _signed_webhook_body(payload: dict) -> tuple[bytes, dict]:
    """A `FakeSignatureAdapter.validar_webhook`-shaped signed body: JSON
    `{external_id, status}` + `x-fake-signature` = sha256 hex of the body
    (mirrors `card_hub`'s `test_contratos_assinatura.py::_fake_webhook_headers`)."""
    body = json.dumps(payload).encode("utf-8")
    return body, {"x-fake-signature": hashlib.sha256(body).hexdigest()}


class TestListarAssinaturas:
    def test_list_all(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "documento_nome": "Contrato de Venda", "status": "enviado"},
            {"id": "a2", "documento_nome": "Procuração", "status": "assinado"},
        ])
        resp = client.get("/api/assinaturas")
        assert resp.status_code == 200

    def test_filter_by_status(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "documento_nome": "Contrato", "status": "pendente"},
        ])
        resp = client.get("/api/assinaturas?status=pendente")
        assert resp.status_code == 200

    def test_filter_by_contrato_id(self, client):
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "documento_nome": "Contrato", "contrato_id": "ct1"},
        ])
        resp = client.get("/api/assinaturas?contrato_id=ct1")
        assert resp.status_code == 200


class TestEnviarAssinatura:
    def test_enviar_success(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(
                preparar_envio_result={
                    "id": "new-a",
                    "documento_nome": "Contrato de Locação",
                    "status": "enviado",
                }
            )
        )
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato de Locação",
            "documento_url": "https://storage.example.com/contrato.pdf",
            "signatarios": [
                {"nome": "João", "email": "joao@test.com", "papel": "locatario"},
            ],
        })
        assert resp.status_code == 200

    def test_enviar_missing_fields(self, client):
        resp = client.post("/api/assinaturas/enviar", json={})
        assert resp.status_code == 422

    def test_enviar_missing_signatarios(self, client):
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato de Venda",
        })
        assert resp.status_code == 422

    def test_enviar_empty_signatarios(self, client):
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato de Venda",
            "signatarios": [],
        })
        assert resp.status_code == 422

    def test_enviar_defaults_to_d4sign(self, client, override_assinatura_service):
        """2026-09-20 wiring audit, task 2: the untouched form must send
        via `d4sign` (the only seed-supported provider), never `interno`."""
        captured = {}

        class _Capturing(_FakeAssinaturaService):
            async def preparar_envio(self, **kwargs):
                captured.update(kwargs)
                return {"id": "a1", "status": "enviado"}

        override_assinatura_service(_Capturing())
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato.pdf",
            "documento_url": "https://storage.example.com/contrato.pdf",
            "signatarios": [{"nome": "X", "email": "x@x.com", "papel": "comprador"}],
        })
        assert resp.status_code == 200
        assert captured["provedor"] == "d4sign"

    def test_enviar_unconfigured_provider_returns_503(self, client, override_assinatura_service):
        """No silent fallback: a missing-credential refusal surfaces as a
        typed 503, never a 200 with a mocked envelope (contract F1/§0)."""
        override_assinatura_service(
            _FakeAssinaturaService(
                preparar_envio_error=ProvedorNaoConfigurado(
                    ["d4sign_api_token", "d4sign_crypt_key", "d4sign_safe_uuid"],
                    provedor="d4sign",
                )
            )
        )
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato.pdf",
            "documento_url": "https://storage.example.com/contrato.pdf",
            "signatarios": [{"nome": "X", "email": "x@x.com", "papel": "comprador"}],
        })
        assert resp.status_code == 503
        assert "d4sign_api_token" in resp.json()["error"]["message"]

    def test_enviar_unsupported_provider_returns_503(self, client, override_assinatura_service):
        """ClickSign/DocuSign aren't implemented in this pass — a request
        naming either is refused, not silently downgraded (contract §5)."""
        override_assinatura_service(
            _FakeAssinaturaService(
                preparar_envio_error=ProvedorNaoConfigurado(
                    ["provedor 'clicksign' não é suportado nesta versão (suportado: d4sign)"],
                    provedor="clicksign",
                )
            )
        )
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato.pdf",
            "documento_url": "https://storage.example.com/contrato.pdf",
            "signatarios": [{"nome": "X", "email": "x@x.com", "papel": "comprador"}],
            "provedor": "clicksign",
        })
        assert resp.status_code == 503
        assert "clicksign" in resp.json()["error"]["message"]

    def test_enviar_provider_rejected_returns_502(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(
                preparar_envio_error=EnvelopeRecusado("rejected", provedor_mensagem="bad request")
            )
        )
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato.pdf",
            "documento_url": "https://storage.example.com/contrato.pdf",
            "signatarios": [{"nome": "X", "email": "x@x.com", "papel": "comprador"}],
        })
        assert resp.status_code == 502

    def test_enviar_provider_unavailable_returns_502(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(preparar_envio_error=ProvedorIndisponivel("timeout"))
        )
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato.pdf",
            "documento_url": "https://storage.example.com/contrato.pdf",
            "signatarios": [{"nome": "X", "email": "x@x.com", "papel": "comprador"}],
        })
        assert resp.status_code == 502

    def test_enviar_missing_documento_url_returns_400(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(
                preparar_envio_error=ValueError(
                    "documento_url é obrigatório para enviar um documento para assinatura"
                )
            )
        )
        resp = client.post("/api/assinaturas/enviar", json={
            "documento_nome": "Contrato.pdf",
            "signatarios": [{"nome": "X", "email": "x@x.com", "papel": "comprador"}],
        })
        assert resp.status_code == 400


class TestListarProvedores:
    def test_returns_only_seed_supported_providers(self, client):
        """2026-09-20 wiring audit, task 2: the list is derived from the
        seed's `PROVEDORES_SUPORTADOS`, not a second hand-kept copy."""
        resp = client.get("/api/assinaturas/provedores")
        assert resp.status_code == 200
        assert resp.json()["data"] == {"suportados": ["d4sign"]}


class TestObterAssinatura:
    def test_get_by_id(self, client):
        client._mock_supabase.set_table_data("assinaturas", {
            "id": "a1",
            "documento_nome": "Contrato",
            "status": "enviado",
            "signatarios": [],
            "historico": [],
        })
        resp = client.get("/api/assinaturas/a1")
        assert resp.status_code == 200

    def test_not_found(self, client):
        client._mock_supabase.set_table_data("assinaturas", None)
        resp = client.get("/api/assinaturas/nonexistent")
        assert resp.status_code == 404


class TestWebhook:
    """2026-09-20 wiring audit, tasks 3+4: D4Sign posts form-urlencoded
    `uuid`/`type_post` + `Content-HMAC` — this endpoint delegates BOTH
    parsing and HMAC verification to the seed adapter's `validar_webhook`,
    never re-implementing D4Sign's wire shape locally. These tests drive
    the REAL `FakeSignatureAdapter.validar_webhook` (JSON `{external_id,
    status}` + `x-fake-signature`) rather than mocking that method out —
    the seed's Fake stands in for the vendor, `AssinaturaService` is the
    only thing double'd."""

    def test_invalid_signature_is_strict_401(
        self, client, override_assinatura_service, fake_signature_adapter
    ):
        override_assinatura_service(_FakeAssinaturaService(), webhook=True)
        body, _headers = _signed_webhook_body({"external_id": "a1", "status": "concluido"})
        resp = client._tc.post(
            "/api/assinaturas/webhook",
            content=body,
            headers={"x-fake-signature": "0" * 64},
        )
        assert resp.status_code == 401

    def test_absent_signature_is_strict_401(
        self, client, override_assinatura_service, fake_signature_adapter
    ):
        override_assinatura_service(_FakeAssinaturaService(), webhook=True)
        body, _headers = _signed_webhook_body({"external_id": "a1", "status": "concluido"})
        resp = client._tc.post("/api/assinaturas/webhook", content=body)
        assert resp.status_code == 401

    def test_provedor_nao_configurado_is_strict_401(
        self, client, override_assinatura_service, override_signature_adapter_factory
    ):
        """No unset-credential bypass (task 4) — a missing platform-tier
        D4Sign credential refuses, it never lets the (unverifiable) body
        through."""
        from app.main import app
        from app.routers.assinaturas import get_signature_adapter_factory

        def _raising(org_id):
            raise ProvedorNaoConfigurado(
                ["d4sign_api_token", "d4sign_crypt_key", "d4sign_safe_uuid"],
                provedor="d4sign",
            )

        app.dependency_overrides[get_signature_adapter_factory] = lambda: _raising
        override_assinatura_service(_FakeAssinaturaService(), webhook=True)

        body, headers = _signed_webhook_body({"external_id": "a1", "status": "concluido"})
        resp = client._tc.post("/api/assinaturas/webhook", content=body, headers=headers)
        assert resp.status_code == 401

    def test_webhook_success(
        self, client, override_assinatura_service, fake_signature_adapter
    ):
        override_assinatura_service(
            _FakeAssinaturaService(processar_webhook_result={"id": "a1", "status": "assinado"}),
            webhook=True,
        )
        body, headers = _signed_webhook_body({"external_id": "ext-1", "status": "concluido"})
        resp = client._tc.post("/api/assinaturas/webhook", content=body, headers=headers)
        assert resp.status_code == 200

    def test_webhook_unknown_assinatura_returns_404(
        self, client, override_assinatura_service, fake_signature_adapter
    ):
        override_assinatura_service(
            _FakeAssinaturaService(processar_webhook_result=None),
            webhook=True,
        )
        body, headers = _signed_webhook_body({"external_id": "does-not-exist", "status": "concluido"})
        resp = client._tc.post("/api/assinaturas/webhook", content=body, headers=headers)
        assert resp.status_code == 404

    def test_webhook_passes_the_verified_event_to_the_service(
        self, client, override_assinatura_service, fake_signature_adapter
    ):
        """The router must hand the SERVICE the parsed `EventoAssinatura`
        from `validar_webhook` — not re-derive it from the raw body."""
        captured = {}

        class _Capturing(_FakeAssinaturaService):
            async def processar_webhook(self, evento: EventoAssinatura):
                captured["evento"] = evento
                return {"id": "a1", "status": "assinado"}

        override_assinatura_service(_Capturing(), webhook=True)
        body, headers = _signed_webhook_body({"external_id": "ext-42", "status": "concluido"})
        resp = client._tc.post("/api/assinaturas/webhook", content=body, headers=headers)
        assert resp.status_code == 200
        assert captured["evento"].external_id == "ext-42"
        assert captured["evento"].status == "concluido"


class TestCancelarAssinatura:
    def test_cancel_success(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(cancelar_result={"id": "a1", "status": "cancelado"})
        )
        resp = client.delete("/api/assinaturas/a1")
        assert resp.status_code == 200

    def test_cancel_not_found(self, client, override_assinatura_service):
        override_assinatura_service(_FakeAssinaturaService(cancelar_result=None))
        resp = client.delete("/api/assinaturas/nonexistent")
        assert resp.status_code == 404


class TestResumoAssinaturas:
    def test_resumo(self, client):
        """`get_resumo` is a pure function of the fetched rows — exercise
        the REAL implementation end to end rather than mocking it."""
        client._mock_supabase.set_table_data("assinaturas", [
            {"id": "a1", "status": "enviado"},
            {"id": "a2", "status": "assinado"},
            {"id": "a3", "status": "pendente"},
        ])
        resp = client.get("/api/assinaturas/resumo")
        assert resp.status_code == 200
        resumo = resp.json()["data"]
        assert resumo == {
            "pendentes": 1,
            "enviadas": 1,
            "assinadas": 1,
            "recusadas": 0,
            "expiradas": 0,
            "canceladas": 0,
            "total": 3,
        }
