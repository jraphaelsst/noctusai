"""Real estate domain value objects.

`PropertyData` is the structured metadata for a real estate property.
Fields mirror Vista CRM's ``/imoveis/detalhes`` payload — the source
of truth for the social-wiring product. Other CRMs map to/from this
shape at the adapter boundary.

Shape is preserved verbatim from
``products/social-wiring/backend/app/services/crm_service.py``
(lifted 2026-05-20 via ``social-wiring-vista-seed-lift``).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class PropertyData:
    """Structured property metadata from a real estate CRM."""

    product_code: str
    title: str  # e.g. "Apartamento 3 quartos — Moema, São Paulo"
    description: str  # Full text for YouTube description
    address: str | None = None
    price: str | None = None  # formatted, e.g. "R$ 1.200.000"
    bedrooms: int | None = None
    area_sqm: float | None = None
    thumbnail_url: str | None = None  # property photo for reference
