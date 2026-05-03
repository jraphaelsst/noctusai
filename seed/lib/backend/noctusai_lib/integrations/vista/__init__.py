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

Public surface:

- `VistaClient` — async typed client + 7-class error hierarchy
- `extract_items` — normalize Vista's dict-keyed-by-id envelope
- `VistaCallResult` — successful-request carrier
- 4 mappers: `vista_imovel_to_showcase`, `vista_imovel_detalhes_to_showcase`,
  `vista_usuario_to_showcase`, `vista_agencia_to_showcase`
- 4 showcase DTOs: `ShowcaseImovel`, `ShowcaseImovelDetalhes`,
  `ShowcaseUsuario`, `ShowcaseAgencia`
- Constants: `DEFAULT_TIMEOUT_SECONDS`, `DEFAULT_PAGE_SIZE`, `PAGINATION_KEYS`
"""
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
from .normalizers import (
    vista_agencia_to_showcase,
    vista_imovel_detalhes_to_showcase,
    vista_imovel_to_showcase,
    vista_usuario_to_showcase,
)
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
    # Client + result carrier
    "VistaClient",
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
]
