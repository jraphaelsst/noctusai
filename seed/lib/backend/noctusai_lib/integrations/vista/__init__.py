"""Vista CRM integration — typed HTTP client + normalizers + showcase DTOs.

Single canonical home for Vista API access across the platform. Both the
ERP showcase (`products/erp-imobiliario/backend/app/routers/vista_showcase.py`
+ service) and the in-repo MCP server (`mcp/vista/`) import from here.

**FORMALIZED 2026-05-03** from two parallel ports
(`products/erp-imobiliario/backend/app/integrations/vista/` +
`mcp/vista/`) at N=2 → triage time. The `_detect_unavailable_field` bug
(silent JSON-escaped-body match failure) had been fixed in both copies
the same day, surfacing the real cost of the duplication. See
`KB § PATTERNS/accept-with-rationale.md § Vista client formalization`
for the historical entry, and `KB § INTEGRATIONS/vista.md § 5` for the
full Vista contract this module implements.

**Fake + factory added 2026-05-16** (`social-wiring-absorption` Wave 1)
to complete the canonical Protocol+Fake+Real+factory IO-module shape —
previously only the Real client (`VistaClient`) shipped, forcing every
network-free consumer to hand-roll a stub. The Real client's behavior
was verified unchanged against the validated workspace usage (live
`/imoveis/detalhes?imovel=ONE10121`, showcase normalizers) — no
functional reconcile was needed; the gap was solely the missing
Fake + factory.

Public surface:

- `VistaClient` — async typed Real client + 7-class error hierarchy
- `FakeVistaClient` — deterministic in-memory dev/test stand-in
- `make_vista_client(...)` — Fake/Real factory (the single seam)
- `extract_items` — normalize Vista's dict-keyed-by-id envelope
- `VistaCallResult` — successful-request carrier
- 4 mappers: `vista_imovel_to_showcase`, `vista_imovel_detalhes_to_showcase`,
  `vista_usuario_to_showcase`, `vista_agencia_to_showcase`
- 4 showcase DTOs: `ShowcaseImovel`, `ShowcaseImovelDetalhes`,
  `ShowcaseUsuario`, `ShowcaseAgencia`
- Constants: `DEFAULT_TIMEOUT_SECONDS`, `DEFAULT_PAGE_SIZE`, `PAGINATION_KEYS`
"""
from noctusai_lib.domain.real_estate import PropertyData

from .adapter_factory import get_vista_adapter
from .client import (
    DEFAULT_PAGE_SIZE,
    DEFAULT_TIMEOUT_SECONDS,
    PAGINATION_KEYS,
    VistaCallResult,
    VistaClient,
    VistaConfigError,
    VistaError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
    extract_items,
)
from .factory import make_vista_client
from .fake import FakeVistaClient
from .fake_adapter import FakeVistaAdapter
from .normalizers import (
    vista_agencia_to_showcase,
    vista_imovel_detalhes_to_showcase,
    vista_imovel_to_showcase,
    vista_usuario_to_showcase,
)
from .protocol import VistaCRMAdapter
from .real import VistaNotConfigured, VistaRESTAdapter
from .types import (
    ShowcaseAgencia,
    ShowcaseImovel,
    ShowcaseImovelDetalhes,
    ShowcaseUsuario,
)

__all__ = [
    # Constants
    "DEFAULT_TIMEOUT_SECONDS",
    "DEFAULT_PAGE_SIZE",
    "PAGINATION_KEYS",
    # Client + result carrier + factory
    "VistaClient",
    "FakeVistaClient",
    "make_vista_client",
    "VistaCallResult",
    "extract_items",
    # 7-class error hierarchy (catch-order matters — leaves before parent)
    "VistaError",
    "VistaConfigError",
    "VistaUpstreamError",
    "VistaPermissionDenied",
    "VistaNotFound",
    "VistaFieldNotAvailable",
    "VistaTimeout",
    # Normalizers
    "vista_imovel_to_showcase",
    "vista_imovel_detalhes_to_showcase",
    "vista_usuario_to_showcase",
    "vista_agencia_to_showcase",
    # Showcase DTOs
    "ShowcaseImovel",
    "ShowcaseImovelDetalhes",
    "ShowcaseUsuario",
    "ShowcaseAgencia",
    # High-level CRM adapter layer (social-wiring-vista-seed-lift 2026-05-20).
    # Property-by-code adapter on top of the low-level client; returns the
    # cross-CRM domain shape `PropertyData` from `noctusai_lib.domain.real_estate`.
    "VistaCRMAdapter",
    "FakeVistaAdapter",
    "VistaRESTAdapter",
    "get_vista_adapter",
    "VistaNotConfigured",
    # Re-exported for ergonomics — callers building a Fake or asserting on
    # `get_property` results don't need a second import.
    "PropertyData",
]
