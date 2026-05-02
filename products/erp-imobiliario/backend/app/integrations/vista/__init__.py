"""Vista CRM integration — read-only adapter for the showcase feature.

Public surface:
- VistaClient — typed HTTP client.
- Vista*Error — typed exception hierarchy.
- normalizers — Vista payload → showcase DTO.

See `products/erp-imobiliario/projects/vista-crm-wiring/VISTA-API.md`.
"""
from app.integrations.vista.client import (
    VistaClient,
    VistaConfigError,
    VistaError,
    VistaFieldNotAvailable,
    VistaNotFound,
    VistaPermissionDenied,
    VistaTimeout,
    VistaUpstreamError,
)

__all__ = [
    "VistaClient",
    "VistaConfigError",
    "VistaError",
    "VistaFieldNotAvailable",
    "VistaNotFound",
    "VistaPermissionDenied",
    "VistaTimeout",
    "VistaUpstreamError",
]
