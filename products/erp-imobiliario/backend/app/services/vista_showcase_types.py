"""ERP-specific response shapes for the Vista showcase router.

These wrap Vista data into shapes the frontend expects — they are NOT
Vista-protocol shapes. The Vista-protocol DTOs (`ShowcaseImovel`,
`ShowcaseImovelDetalhes`, `ShowcaseUsuario`, `ShowcaseAgencia`) live in
`noctusai_lib.integrations.vista` (canonical platform home, FORMALIZED
2026-05-03) and are reused by the in-repo Vista MCP server.

The shapes here (`ShowcasePagination`, `ShowcaseEnvelope`,
`ShowcaseTabStatus`, `ShowcaseDiagnostic`) are ERP-showcase-router-specific
response wrappers — only the showcase service + router consume them.
"""
from __future__ import annotations

from typing import Any, Optional

from pydantic import BaseModel, Field


class ShowcasePagination(BaseModel):
    pagina: int = 1
    quantidade: int = 0
    total: Optional[int] = None
    paginas: Optional[int] = None


class ShowcaseEnvelope(BaseModel):
    """Standard envelope returned by every /api/vista-showcase/{tab} endpoint."""

    source: str = "vista"
    tab: str
    live: bool = True
    fetched_at: str
    pagination: Optional[ShowcasePagination] = None
    items: list[Any] = Field(default_factory=list)
    raw_available: bool = True
    warnings: list[str] = Field(default_factory=list)


class ShowcaseTabStatus(BaseModel):
    """Reported by GET /api/vista-showcase/tabs.

    Drives the frontend's sub-tab nav — including 'Permissão pendente'
    placeholders for 401 endpoints and 'Não disponível neste tenant' for
    404 endpoints.
    """

    tab: str
    label: str
    status: str  # "live" | "permission_denied" | "not_found" | "not_configured" | "doc_only"
    endpoint: str
    note: Optional[str] = None


class ShowcaseDiagnostic(BaseModel):
    tenant_base_url: str
    configured: bool
    probes: list[dict] = Field(default_factory=list)


__all__ = [
    "ShowcasePagination",
    "ShowcaseEnvelope",
    "ShowcaseTabStatus",
    "ShowcaseDiagnostic",
]
