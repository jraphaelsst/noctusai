"""
Unit tests for signature_provider — credential resolution via resolve_credential,
dry-run mode, internal/mock signing, provider fallbacks.
"""
import pytest
from unittest.mock import patch


# ---------------------------------------------------------------------------
# SignatureProviderConfig
# ---------------------------------------------------------------------------

class TestSignatureProviderConfig:

    def test_clicksign_token_from_resolver(self):
        from app.services.signature_provider import SignatureProviderConfig

        config = SignatureProviderConfig(org_id="org-1")
        with patch("app.services.signature_provider.resolve_credential", return_value="cs-token"):
            assert config.clicksign_token == "cs-token"

    def test_clicksign_env_default_sandbox(self):
        from app.services.signature_provider import SignatureProviderConfig

        config = SignatureProviderConfig()
        with patch("app.services.signature_provider.resolve_credential", return_value=None):
            assert config.clicksign_env == "sandbox"

    def test_d4sign_token_resolved(self):
        from app.services.signature_provider import SignatureProviderConfig

        config = SignatureProviderConfig(org_id="org-1")
        with patch("app.services.signature_provider.resolve_credential", return_value="d4-tok"):
            assert config.d4sign_token == "d4-tok"

    def test_no_credentials_returns_none(self):
        from app.services.signature_provider import SignatureProviderConfig

        config = SignatureProviderConfig()
        with patch("app.services.signature_provider.resolve_credential", return_value=None):
            assert config.clicksign_token is None
            assert config.docusign_integration_key is None
            assert config.d4sign_token is None

    def test_org_id_passed_to_resolver(self):
        from app.services.signature_provider import SignatureProviderConfig

        config = SignatureProviderConfig(org_id="org-42")
        with patch("app.services.signature_provider.resolve_credential", return_value="val") as mock:
            _ = config.clicksign_token
            mock.assert_called_with("clicksign_api_token", "org-42")


# ---------------------------------------------------------------------------
# _enviar_interno (internal mock signing)
# ---------------------------------------------------------------------------

class TestEnviarInterno:

    def test_returns_dry_run(self):
        from app.services.signature_provider import _enviar_interno

        result = _enviar_interno("contrato.pdf", [{"nome": "Joao", "email": "j@t.com"}])

        assert result["provedor"] == "interno"
        assert result["dry_run"] is True
        assert "external_id" in result
        assert result["external_id"].startswith("interno_")
        assert "link_assinatura" in result
        assert "noctus.app" in result["link_assinatura"]


# ---------------------------------------------------------------------------
# enviar_para_assinatura — provider dispatch
# ---------------------------------------------------------------------------

class TestEnviarParaAssinatura:

    @pytest.mark.asyncio
    async def test_unknown_provider_uses_interno(self):
        from app.services.signature_provider import enviar_para_assinatura, SignatureProviderConfig

        config = SignatureProviderConfig()
        result = await enviar_para_assinatura(
            provedor="unknown",
            documento_nome="doc.pdf",
            documento_url=None,
            signatarios=[{"nome": "Ana", "email": "a@t.com"}],
            config=config,
        )

        assert result["provedor"] == "interno"
        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_clicksign_no_token_fallback(self):
        """ClickSign without token should fall back to internal."""
        from app.services.signature_provider import enviar_para_assinatura, SignatureProviderConfig

        config = SignatureProviderConfig()
        with patch("app.services.signature_provider.resolve_credential", return_value=None):
            result = await enviar_para_assinatura(
                provedor="clicksign",
                documento_nome="contrato.pdf",
                documento_url=None,
                signatarios=[{"nome": "Test", "email": "t@t.com"}],
                config=config,
            )

        assert result["provedor"] == "interno"
        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_docusign_no_key_fallback(self):
        """DocuSign without integration key should fall back to internal."""
        from app.services.signature_provider import enviar_para_assinatura, SignatureProviderConfig

        config = SignatureProviderConfig()
        with patch("app.services.signature_provider.resolve_credential", return_value=None):
            result = await enviar_para_assinatura(
                provedor="docusign",
                documento_nome="contrato.pdf",
                documento_url=None,
                signatarios=[{"nome": "Test", "email": "t@t.com"}],
                config=config,
            )

        assert result["provedor"] == "interno"
        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_d4sign_no_token_fallback(self):
        """D4Sign without token should fall back to internal."""
        from app.services.signature_provider import enviar_para_assinatura, SignatureProviderConfig

        config = SignatureProviderConfig()
        with patch("app.services.signature_provider.resolve_credential", return_value=None):
            result = await enviar_para_assinatura(
                provedor="d4sign",
                documento_nome="contrato.pdf",
                documento_url=None,
                signatarios=[{"nome": "Test", "email": "t@t.com"}],
                config=config,
            )

        assert result["provedor"] == "interno"
        assert result["dry_run"] is True

    @pytest.mark.asyncio
    async def test_docusign_with_key_returns_envelope(self):
        """DocuSign with integration key returns demo-mode envelope."""
        from app.services.signature_provider import enviar_para_assinatura, SignatureProviderConfig

        config = SignatureProviderConfig(org_id="org-1")
        with patch("app.services.signature_provider.resolve_credential", return_value="my-docusign-key"):
            result = await enviar_para_assinatura(
                provedor="docusign",
                documento_nome="contrato.pdf",
                documento_url=None,
                signatarios=[{"nome": "Joao", "email": "j@t.com"}],
                config=config,
            )

        assert result["provedor"] == "docusign"
        assert result["dry_run"] is False
        assert "external_id" in result
        assert "docusign.net" in result["link_assinatura"]
