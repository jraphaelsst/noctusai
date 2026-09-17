"""E-signature seed IO module — D4Sign only. Protocol + Fake + Real + factory.

Built 2026-09-17 for `projects/signature-integration-CONTRACT.md` (Slice
S-A). Generated documents (a contract PDF) go out for signature and come
back as a signed version — this module is the "provider envelope" leg of
that pipeline; the org-scoped endpoints and the `atendimento_contrato_
assinaturas` table are a different slice's job.

**What ships:**

- `Signatario`, `DocumentoParaAssinar`, `SignatarioRemoto`, `EnvelopeCriado`,
  `EventoAssinatura` value objects + the `SignatureAdapter` Protocol
  (`types.py`).
- `SignatureError` + `ProvedorNaoConfigurado` / `WebhookInvalido` /
  `DocumentoAssinadoIndisponivel` / `ProvedorIndisponivel` /
  `EnvelopeRecusado` (`exceptions.py`).
- `FakeSignatureAdapter` — deterministic, stateful, the default.
- `D4SignAdapter` — the real D4Sign wire calls. Imported lazily (below),
  same pattern `documents/__init__.py` uses for its heavy Real extractors.
- `make_signature_adapter(real=..., org_id=..., resolver=...)` — the
  factory. Fake by default.

**Why D4Sign only.** Contract §0: 7 of 8 sample contracts name D4Sign and
clause 2.13's wording is D4Sign's. ClickSign/DocuSign are not implemented
in this pass — the Protocol admits them later without a shape change.

**Why this is a seed module and not product code (F1).**
`erp-imobiliario`'s `signature_provider.py` posts `{"url": ...}` where
D4Sign's real upload contract is a binary body (the document was never
actually uploaded), and its DocuSign branch returns a random id with
`"dry_run": False` — a mock reporting itself as real. That scaffold is
being replaced by `make_signature_adapter` in a later slice
(replication-to-seed symmetry), not lifted.

🔴 **No silent fallback, anywhere.** `make_signature_adapter(real=True,
...)` never returns a Fake — a missing credential raises
`ProvedorNaoConfigurado` naming which one. `validar_webhook` never
returns `None` — a bad/absent signature raises `WebhookInvalido`.

**Consume recipe:**

    from noctusai_lib.integrations.signature import (
        DocumentoParaAssinar,
        ProvedorNaoConfigurado,
        Signatario,
        make_signature_adapter,
    )

    adapter = make_signature_adapter(real=True, org_id=org_id)
    try:
        envelope = await adapter.criar_envelope(documento, signatarios)
    except ProvedorNaoConfigurado as exc:
        # exc.details["faltando"] names every missing credential key
        ...
"""
from __future__ import annotations

from noctusai_lib.integrations.signature.exceptions import (
    DocumentoAssinadoIndisponivel,
    EnvelopeRecusado,
    ProvedorIndisponivel,
    ProvedorNaoConfigurado,
    SignatureError,
    WebhookInvalido,
)
from noctusai_lib.integrations.signature.factory import (
    PROVEDORES_SUPORTADOS,
    CredentialResolver,
    make_signature_adapter,
)
from noctusai_lib.integrations.signature.fake import FakeSignatureAdapter
from noctusai_lib.integrations.signature.types import (
    DocumentoParaAssinar,
    EnvelopeCriado,
    EventoAssinatura,
    PapelSignatario,
    Signatario,
    SignatarioRemoto,
    SignatureAdapter,
    StatusAssinatura,
)

#: Attribute name → the module it lives in, for the lazy proxy below.
#: `D4SignAdapter` pulls httpx's async client machinery on import, so the
#: Fake-by-default path above must stay importable without it — same
#: rationale as `documents/__init__.py`'s `_LAZY` map.
_LAZY: dict[str, str] = {
    "D4SignAdapter": "noctusai_lib.integrations.signature.real",
}


def __getattr__(name: str):  # pragma: no cover - lazy proxy
    modulo = _LAZY.get(name)
    if modulo is not None:
        import importlib

        return getattr(importlib.import_module(modulo), name)
    raise AttributeError(f"module {__name__!r} has no attribute {name!r}")


__all__ = [
    "CredentialResolver",
    "D4SignAdapter",
    "DocumentoAssinadoIndisponivel",
    "DocumentoParaAssinar",
    "EnvelopeCriado",
    "EnvelopeRecusado",
    "EventoAssinatura",
    "FakeSignatureAdapter",
    "PROVEDORES_SUPORTADOS",
    "PapelSignatario",
    "ProvedorIndisponivel",
    "ProvedorNaoConfigurado",
    "Signatario",
    "SignatarioRemoto",
    "SignatureAdapter",
    "SignatureError",
    "StatusAssinatura",
    "WebhookInvalido",
    "make_signature_adapter",
]
