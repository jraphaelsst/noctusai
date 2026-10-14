"""Invoice-organ errors. Messages are generic by construction: provider bodies,
tokens, certificate bytes and passwords NEVER reach an exception message or
`args` (contract 0 - secrets never leave the call)."""
from __future__ import annotations

from typing import Optional

from noctusai_lib.primitives.not_configured import IntegrationNotConfigured


class InvoiceProviderError(Exception):
    """A call to an invoice provider failed (or was refused locally)."""

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        code: Optional[str] = None,
        status: Optional[int] = None,
        retryable: bool = False,
        reasons: Optional[list[str]] = None,
    ) -> None:
        self.provider = provider
        #: Provider refusal reasons (e.g. a cancel-window refusal) - NEVER secrets.
        self.reasons: list[str] = list(reasons or [])
        self.message = message
        self.code = code
        self.status = status
        self.retryable = retryable
        super().__init__(f"[{provider}] {message}")


class InvoiceNotFound(InvoiceProviderError):
    """The provider has no document for this `ref` (HTTP 404)."""

    def __init__(self, provider: str, ref: str) -> None:
        super().__init__(
            provider, "documento fiscal nao encontrado", code="not_found", status=404
        )
        self.ref = ref


class InvoiceCertificateError(InvoiceProviderError):
    """Bad/unreadable certificate file or wrong password. Deliberately one
    generic error: distinguishing the two leaks an oracle."""

    def __init__(self, provider: str = "local") -> None:
        super().__init__(provider, "certificado invalido", code="certificado_invalido")


class InvoiceWebhookAuthError(InvoiceProviderError):
    """Webhook token missing/wrong, or no token configured (fail-closed)."""

    def __init__(self, provider: str) -> None:
        super().__init__(
            provider, "webhook nao autorizado", code="webhook_nao_autorizado", status=401
        )


class InvoiceNotConfigured(InvoiceProviderError, IntegrationNotConfigured):
    """Real provider requested but credentials/guard not satisfied."""

    def __init__(self, provider: str, message: str, *, code: str = "not_configured") -> None:
        super().__init__(provider, message, code=code, status=503)
