"""The `InvoiceProvider` seam. Fake and Focus both satisfy it."""
from __future__ import annotations

from typing import Mapping, Optional, Protocol, runtime_checkable

from .types import (
    CertificateInfo,
    CompanyRequest,
    InvoiceEvent,
    InvoiceKind,
    InvoiceRequest,
    InvoiceResult,
    NfseMode,
    ProviderCompany,
)


@runtime_checkable
class InvoiceProvider(Protocol):
    name: str

    def verify_credentials(self) -> None:
        """Return None when the account credential works; raise otherwise."""
        ...

    def ensure_company(self, request: CompanyRequest) -> ProviderCompany: ...

    def upload_certificate(
        self,
        company_ref: str,
        *,
        pfx: bytes,
        password: str,
        expected_cnpj: Optional[str] = None,
    ) -> CertificateInfo:
        """Forward the A1 certificate. `pfx` and `password` live only for the call."""
        ...

    def set_nfse_mode(self, company_ref: str, mode: NfseMode) -> ProviderCompany: ...

    def issue(self, request: InvoiceRequest) -> InvoiceResult:
        """Idempotent on `request.ref`: a re-issue returns the existing document."""
        ...

    def get(
        self, kind: InvoiceKind, ref: str, *, company_ref: Optional[str] = None
    ) -> InvoiceResult: ...

    def cancel(
        self,
        kind: InvoiceKind,
        ref: str,
        *,
        reason: str,
        company_ref: Optional[str] = None,
    ) -> InvoiceResult: ...

    def fetch_document(self, url: str) -> bytes: ...

    def parse_webhook(
        self, headers: Mapping[str, str], body: bytes, *, token: Optional[str]
    ) -> InvoiceEvent: ...
