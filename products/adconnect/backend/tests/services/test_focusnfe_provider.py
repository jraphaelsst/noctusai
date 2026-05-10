"""
Tests for FocusNFeProvider — the Real adapter for Focus NFe REST API.

External-SDK / external-HTTP integration: per CLAUDE.md no-monkey-patching
rule, patching httpx.Client at the test boundary is allowed (httpx is
external; the rule covers OUR code, not external integrations).

Strategy: stub `httpx.Client` to a context-manager returning a fake
response. We assert:
  • Configuration errors raise FocusNFeMisconfiguredError when API key absent.
  • Issue maps the JSON body to the canonical NFeIssueResult shape.
  • Issue maps 422 / 400 to status='rejeitado' with a reason.
  • Cancel returns NFeCancelResult on 200/202/204.
  • Status maps Focus NFe vocabulary to ours.
  • ambiente toggle selects the right base URL.
"""
from __future__ import annotations

import os
from contextlib import contextmanager
from datetime import datetime
from typing import Any

import pytest

from app.services.nfe_service import (
    FocusNFeMisconfiguredError,
    FocusNFeProvider,
    NFeCancelRequest,
    NFeIssueRequest,
    NFeItem,
)


# ---------------------------------------------------------------------------
# httpx stub helpers
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status_code: int, body: Any = None, text: str = ""):
        self.status_code = status_code
        self._body = body
        self.text = text

    def json(self) -> Any:
        if self._body is None:
            raise ValueError("No JSON body")
        return self._body


class _FakeClient:
    """Mimics httpx.Client as a context manager that records calls."""

    def __init__(self, response: _FakeResponse):
        self._response = response
        self.calls: list[dict[str, Any]] = []

    def __enter__(self) -> "_FakeClient":
        return self

    def __exit__(self, *args, **kwargs) -> None:
        return None

    def post(self, url: str, json: Any = None, **kw) -> _FakeResponse:
        self.calls.append({"method": "POST", "url": url, "json": json})
        return self._response

    def get(self, url: str, **kw) -> _FakeResponse:
        self.calls.append({"method": "GET", "url": url})
        return self._response

    def delete(self, url: str, params: Any = None, **kw) -> _FakeResponse:
        self.calls.append({"method": "DELETE", "url": url, "params": params})
        return self._response


def _patch_httpx(monkeypatch, response: _FakeResponse) -> _FakeClient:
    """Patch httpx.Client to return a recording fake client."""
    fake = _FakeClient(response)

    class _ModuleStub:
        @staticmethod
        def Client(**kw) -> _FakeClient:  # noqa: N802 — match httpx API
            return fake

    import sys
    monkeypatch.setitem(sys.modules, "httpx", _ModuleStub())
    return fake


@pytest.fixture
def sample_request() -> NFeIssueRequest:
    return NFeIssueRequest(
        fatura_id="fatura-001",
        distributor_cnpj="12.345.678/0001-99",
        distributor_razao_social="Distribuidor Teste LTDA",
        distributor_endereco={
            "logradouro": "Rua X",
            "numero": "100",
            "bairro": "Centro",
            "cidade": "São Paulo",
            "uf": "SP",
            "cep": "01000-000",
        },
        items=[
            NFeItem(
                sku="SKU-001",
                descricao="Item de teste",
                quantidade=2,
                valor_unitario=50.0,
                cfop="5102",
            ),
        ],
        valor_total=100.0,
    )


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------


class TestConfiguration:
    def test_no_api_key_raises_on_issue(self, sample_request, monkeypatch):
        monkeypatch.delenv("FOCUSNFE_API_KEY", raising=False)
        provider = FocusNFeProvider(api_key=None)
        with pytest.raises(FocusNFeMisconfiguredError, match="FOCUSNFE_API_KEY"):
            provider.issue(sample_request)

    def test_api_key_via_env(self, monkeypatch):
        monkeypatch.setenv("FOCUSNFE_API_KEY", "env-key-123")
        provider = FocusNFeProvider()
        # _ensure_configured returns the key without raising.
        assert provider._ensure_configured() == "env-key-123"

    def test_invalid_ambiente_raises(self):
        with pytest.raises(ValueError, match="ambiente"):
            FocusNFeProvider(api_key="x", ambiente="invalid")

    def test_homologacao_uses_sandbox_url(self):
        provider = FocusNFeProvider(api_key="x", ambiente="homologacao")
        assert "homologacao" in provider.base_url

    def test_producao_uses_prod_url(self):
        provider = FocusNFeProvider(api_key="x", ambiente="producao")
        assert provider.base_url == "https://api.focusnfe.com.br"


# ---------------------------------------------------------------------------
# Issue
# ---------------------------------------------------------------------------


class TestIssue:
    def test_happy_path_authorized(self, monkeypatch, sample_request):
        response = _FakeResponse(
            status_code=201,
            body={
                "status": "autorizado",
                "chave_nfe": "1" * 44,
                "caminho_xml_nota_fiscal": "https://focusnfe/xml/abc",
            },
        )
        fake = _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key", ambiente="homologacao")
        result = provider.issue(sample_request)

        assert result.status == "autorizado"
        assert result.provider == "focusnfe"
        assert result.chave == "1" * 44
        assert result.xml_url == "https://focusnfe/xml/abc"
        assert isinstance(result.issued_at, datetime)
        # Verify the request was made.
        assert len(fake.calls) == 1
        assert fake.calls[0]["method"] == "POST"
        assert "fatura-001" in fake.calls[0]["url"]

    def test_processando_maps_to_pendente(self, monkeypatch, sample_request):
        response = _FakeResponse(
            status_code=202,
            body={"status": "processando_autorizacao", "chave_nfe": "2" * 44},
        )
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        result = provider.issue(sample_request)
        assert result.status == "pendente"

    def test_422_returns_rejeitado(self, monkeypatch, sample_request):
        response = _FakeResponse(
            status_code=422,
            body={"mensagem": "CNPJ inválido", "erros": []},
        )
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        result = provider.issue(sample_request)
        assert result.status == "rejeitado"
        assert "CNPJ inválido" in (result.rejection_reason or "")

    def test_500_raises_runtime_error(self, monkeypatch, sample_request):
        response = _FakeResponse(status_code=500, body={"err": "boom"})
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        with pytest.raises(RuntimeError, match="HTTP 500"):
            provider.issue(sample_request)

    def test_payload_includes_emitter_cnpj(self, monkeypatch, sample_request):
        response = _FakeResponse(
            status_code=201, body={"status": "autorizado", "chave_nfe": "X" * 44}
        )
        fake = _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(
            api_key="test-key",
            emitter_cnpj="98.765.432/0001-00",
        )
        provider.issue(sample_request)
        payload = fake.calls[0]["json"]
        assert payload["cnpj_emitente"] == "98.765.432/0001-00"
        assert payload["cnpj_destinatario"] == "12.345.678/0001-99"
        assert len(payload["items"]) == 1
        assert payload["items"][0]["codigo_produto"] == "SKU-001"


# ---------------------------------------------------------------------------
# Cancel
# ---------------------------------------------------------------------------


class TestCancel:
    def test_200_returns_cancel_result(self, monkeypatch):
        response = _FakeResponse(status_code=200, body={"status": "cancelado"})
        fake = _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        result = provider.cancel(NFeCancelRequest(
            chave="A" * 44, justificativa="Erro de digitação na nota fiscal emitida"
        ))
        assert result.chave == "A" * 44
        assert isinstance(result.canceled_at, datetime)
        assert fake.calls[0]["method"] == "DELETE"
        assert fake.calls[0]["params"]["justificativa"].startswith("Erro")

    def test_404_raises_runtime_error(self, monkeypatch):
        response = _FakeResponse(status_code=404, body={"err": "not found"})
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        with pytest.raises(RuntimeError, match="HTTP 404"):
            provider.cancel(NFeCancelRequest(
                chave="X" * 44,
                justificativa="Cancelamento por solicitação do cliente final",
            ))


# ---------------------------------------------------------------------------
# Status
# ---------------------------------------------------------------------------


class TestStatus:
    def test_autorizado_maps(self, monkeypatch):
        response = _FakeResponse(status_code=200, body={"status": "autorizado"})
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        assert provider.status("Z" * 44) == "autorizado"

    def test_404_returns_pendente(self, monkeypatch):
        response = _FakeResponse(status_code=404, body=None, text="not found")
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        assert provider.status("Z" * 44) == "pendente"

    def test_unknown_status_falls_back_to_pendente(self, monkeypatch):
        response = _FakeResponse(status_code=200, body={"status": "unknown_state"})
        _patch_httpx(monkeypatch, response)
        provider = FocusNFeProvider(api_key="test-key")
        assert provider.status("Z" * 44) == "pendente"
