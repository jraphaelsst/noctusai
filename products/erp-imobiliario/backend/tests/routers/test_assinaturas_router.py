"""
Tests for Assinaturas (digital signatures) router — /api/assinaturas

Provider-level and side-effect isolation goes through the router's own
FastAPI dependency seams (`get_assinatura_service` /
`get_assinatura_service_webhook`, `app.dependency_overrides[...]`) —
never by patching `AssinaturaService` methods (`KB § PATTERNS/backend/
di-test-seam.md`; patching our own class would stop exercising it).
"""
import pytest

from noctusai_lib.integrations.signature import (
    EnvelopeRecusado,
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

    async def processar_webhook(self, **kwargs):
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
    def test_webhook_success(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(processar_webhook_result={"id": "a1", "status": "assinado"}),
            webhook=True,
        )
        resp = client._tc.post("/api/assinaturas/webhook", json={
            "assinatura_id": "a1",
            "evento": "assinado",
        })
        assert resp.status_code == 200

    def test_webhook_missing_fields(self, client):
        resp = client._tc.post("/api/assinaturas/webhook", json={})
        assert resp.status_code == 422

    def test_webhook_unknown_assinatura_returns_404(self, client, override_assinatura_service):
        override_assinatura_service(
            _FakeAssinaturaService(processar_webhook_result=None),
            webhook=True,
        )
        resp = client._tc.post("/api/assinaturas/webhook", json={
            "assinatura_id": "does-not-exist",
            "evento": "assinado",
        })
        assert resp.status_code == 404


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

