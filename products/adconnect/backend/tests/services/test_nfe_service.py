"""Tests for the NF-e Fake provider — verifies the Protocol contract is
honored and Phase 5's Real adapter has a stable testing surface to mirror.

Real provider tests (FocusNFeProvider, etc.) are authored in Phase 5 with
fixture-recorded HTTP cassettes against the provider's sandbox.
"""
from datetime import datetime

import pytest

from app.services.nfe_service import (
    FakeNFeProvider,
    FocusNFeProvider,
    NFeCancelRequest,
    NFeIssueRequest,
    NFeItem,
    make_nfe_provider,
)


@pytest.fixture
def sample_request() -> NFeIssueRequest:
    return NFeIssueRequest(
        fatura_id="fatura-001",
        distributor_cnpj="12.345.678/0001-99",
        distributor_razao_social="Distribuidor Teste LTDA",
        distributor_endereco={
            "logradouro": "Rua Teste",
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


class TestFakeNFeProviderIssue:
    def test_issue_returns_authorized_result(self, sample_request):
        provider = FakeNFeProvider()
        result = provider.issue(sample_request)

        assert result.status == "autorizado"
        assert result.provider == "fake"
        assert len(result.chave) == 44
        assert result.rejection_reason is None
        assert isinstance(result.issued_at, datetime)

    def test_issue_is_idempotent_for_same_fatura_id(self, sample_request):
        provider = FakeNFeProvider()
        first = provider.issue(sample_request)
        second = provider.issue(sample_request)
        assert first.chave == second.chave
        assert first.provider_id == second.provider_id
        assert first.issued_at == second.issued_at

    def test_issue_rejects_when_pattern_matches(self, sample_request):
        provider = FakeNFeProvider(reject_pattern="12.345.678")
        result = provider.issue(sample_request)
        assert result.status == "rejeitado"
        assert result.rejection_reason is not None


class TestFakeNFeProviderCancel:
    def test_cancel_round_trips(self, sample_request):
        provider = FakeNFeProvider()
        issued = provider.issue(sample_request)
        cancel = provider.cancel(NFeCancelRequest(
            chave=issued.chave, justificativa="Teste de cancelamento"
        ))
        assert cancel.chave == issued.chave
        assert provider.status(issued.chave) == "cancelado"

    def test_cancel_unknown_chave_raises(self):
        provider = FakeNFeProvider()
        with pytest.raises(ValueError, match="not found"):
            provider.cancel(NFeCancelRequest(
                chave="X" * 44, justificativa="missing"
            ))


class TestFakeNFeProviderStatus:
    def test_status_returns_pendente_for_unknown(self):
        provider = FakeNFeProvider()
        assert provider.status("Z" * 44) == "pendente"

    def test_status_after_issue_is_autorizado(self, sample_request):
        provider = FakeNFeProvider()
        issued = provider.issue(sample_request)
        assert provider.status(issued.chave) == "autorizado"


class TestFactoryDispatch:
    def test_fake_provider_returns_fake(self):
        provider = make_nfe_provider("fake")
        assert isinstance(provider, FakeNFeProvider)

    def test_focusnfe_returns_real_provider(self):
        # Phase 5: Real adapter shipped; factory now returns a configured
        # FocusNFeProvider (rather than raising NotImplementedError).
        provider = make_nfe_provider(
            "focusnfe", api_key="test-key", ambiente="homologacao"
        )
        assert isinstance(provider, FocusNFeProvider)

    def test_focusnfe_invalid_ambiente_raises(self):
        with pytest.raises(ValueError, match="ambiente"):
            make_nfe_provider("focusnfe", api_key="x", ambiente="bogus")

    def test_unknown_provider_raises(self):
        with pytest.raises(ValueError, match="Unknown NFe provider"):
            make_nfe_provider("nonexistent")
