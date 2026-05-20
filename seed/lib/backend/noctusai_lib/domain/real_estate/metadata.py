"""Build YouTube-ready metadata from a `PropertyData`.

Ported verbatim from
``products/social-wiring/backend/app/services/crm_service.py``
(lifted 2026-05-20 via ``social-wiring-vista-seed-lift``).
"""

from __future__ import annotations

from noctusai_lib.domain.real_estate.types import PropertyData


def build_youtube_metadata(
    prop: PropertyData, product_code: str
) -> dict[str, str | list[str]]:
    """Build YouTube video metadata from CRM property data.

    Returns a dict with ``title``, ``description``, and ``tags`` ready
    to populate an upload job.
    """
    title = f"{product_code} — {prop.title}"[:100]

    desc_parts = [prop.title]
    if prop.address:
        desc_parts.append(f"📍 {prop.address}")
    if prop.price:
        desc_parts.append(f"💰 {prop.price}")
    if prop.bedrooms:
        desc_parts.append(f"🛏️ {prop.bedrooms} quartos")
    if prop.area_sqm:
        desc_parts.append(f"📐 {prop.area_sqm:.0f}m²")
    if prop.description:
        desc_parts.append("")
        desc_parts.append(prop.description)
    desc_parts.append("")
    desc_parts.append("—")
    desc_parts.append("Enviado pelo Social Wiring.")

    description = "\n".join(desc_parts)[:5000]

    tags = [product_code]
    if prop.address:
        tags.append(prop.address)
    tags.extend(["imóvel", "real estate", "imobiliária"])

    return {
        "title": title,
        "description": description,
        "tags": tags,
    }
