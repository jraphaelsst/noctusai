"""Invoices - NF-e, NFS-e (municipal) and NFS-e Nacional behind one Protocol.

**What this is.** `InvoiceProvider` (Protocol) + `FakeInvoiceProvider` +
`FocusNFeInvoiceProvider` (httpx, Basic auth) + `make_invoice_provider`
(fake-or-refuse, production-guarded). Lifted from
`products/adconnect/.../nfe_service.py` with its defects fixed (lookups by OUR
`ref`; no silent `pendente`; no raw-exception logging). adconnect is asleep and
untouched; it can migrate onto this organ later.

**Secrets never leave the call.** Certificate bytes, passwords and tokens never
appear in logs, exception messages, `InvoiceResult.raw` or repr.

**Recipe:**

    from noctusai_lib.integrations.invoices import (
        CompanyRequest, InvoiceRequest, InvoiceKind, make_invoice_provider,
    )

    provider = make_invoice_provider(account_token=token, company_tokens=resolver)
    company = provider.ensure_company(CompanyRequest(cnpj=..., legal_name=...))
    provider.upload_certificate(company.ref, pfx=pfx, password=pw)
    result = provider.issue(InvoiceRequest(ref="org-ord-nfse-1", ...))

Depth: `KB § CONTEXT/INTEGRATIONS/invoices.md`.
"""
from __future__ import annotations

from .certificate import inspect_pkcs12
from .credentials import CompanyTokenStore
from .errors import (
    InvoiceCertificateError,
    InvoiceNotConfigured,
    InvoiceNotFound,
    InvoiceProviderError,
    InvoiceWebhookAuthError,
)
from .factory import make_invoice_provider, resolve_invoice_environment
from .fake import FakeInvoiceProvider
from .focus import FocusNFeInvoiceProvider
from .protocol import InvoiceProvider
from .types import (
    Address,
    CertificateInfo,
    CompanyRequest,
    InvoiceEnvironment,
    InvoiceEvent,
    InvoiceItem,
    InvoiceKind,
    InvoiceRequest,
    InvoiceResult,
    InvoiceStatus,
    InvoiceTaker,
    NfseMode,
    ProviderCompany,
)
from .webhook import WEBHOOK_TOKEN_HEADER

__all__ = [
    "Address",
    "CertificateInfo",
    "CompanyRequest",
    "CompanyTokenStore",
    "FakeInvoiceProvider",
    "FocusNFeInvoiceProvider",
    "InvoiceCertificateError",
    "InvoiceEnvironment",
    "InvoiceEvent",
    "InvoiceItem",
    "InvoiceKind",
    "InvoiceNotConfigured",
    "InvoiceNotFound",
    "InvoiceProvider",
    "InvoiceProviderError",
    "InvoiceRequest",
    "InvoiceResult",
    "InvoiceStatus",
    "InvoiceTaker",
    "InvoiceWebhookAuthError",
    "NfseMode",
    "ProviderCompany",
    "WEBHOOK_TOKEN_HEADER",
    "inspect_pkcs12",
    "make_invoice_provider",
    "resolve_invoice_environment",
]
