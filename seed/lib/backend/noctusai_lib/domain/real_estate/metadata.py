"""Build YouTube-ready metadata from a `PropertyData`.

Ported verbatim from
``products/social-wiring/backend/app/services/crm_service.py``
(lifted 2026-05-20 via ``social-wiring-vista-seed-lift``).
"""

from __future__ import annotations

from typing import Any

from noctusai_lib.domain.real_estate.imovel import Imovel
from noctusai_lib.domain.real_estate.types import PropertyData


def _join_present(*parts: Any) -> str | None:
    values = [str(part).strip() for part in parts if str(part or "").strip()]
    return ", ".join(values) if values else None


def _format_brl(value: Any) -> str | None:
    if value in (None, ""):
        return None
    if isinstance(value, str):
        cleaned = value.strip()
        if cleaned.startswith("R$"):
            return cleaned
        try:
            value = float(cleaned.replace(".", "").replace(",", "."))
        except ValueError:
            return cleaned
    if isinstance(value, (int, float)):
        return f"R$ {value:,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    return str(value)


def imovel_to_property_data(imovel: Imovel) -> PropertyData:
    """Map the canonical `Imovel` listing to the narrower `PropertyData`
    YouTube-metadata carrier.

    `Imovel` is already CRM-agnostic (§ ``imovel.py`` docstring), so this
    works whether the `Imovel` came from a live Vista call or a stored
    mirror row (`social_wiring.imoveis`) reconstituted via
    ``Imovel(**row)`` — same shape either way, since the row IS a
    flattened `Imovel` (see ``imoveis_service._imovel_to_row``).

    Mirrors the field priority of
    ``noctusai_lib.integrations.vista.real.VistaRESTAdapter._map_response``
    (the live-Vista mapper) so switching the source does not change what a
    consumer sees. That mapper is intentionally left untouched — see its
    module docstring on minimizing behavioural risk to the live path —
    duplicating these two small formatters here rather than importing its
    private ``_join_present``/``_format_brl`` (N=2; not yet worth a shared
    module, see `KB § PATTERNS/architect/project-execution.md` recurrence
    rule — triage, not MUST-formalize).
    """
    title = (
        imovel.titulo
        or _join_present(imovel.categoria, imovel.bairro, imovel.cidade)
        or f"Imovel {imovel.codigo}"
    )

    raw = imovel.vista_raw or {}
    description = (
        raw.get("DescricaoWeb")
        or raw.get("Observacoes")
        or raw.get("Descricao")
        or ""
    )

    address = _join_present(imovel.endereco_completo, imovel.bairro, imovel.cidade)

    price = _format_brl(imovel.valor_venda or imovel.valor_locacao)

    area = imovel.area_privativa or imovel.area_total

    thumbnail = imovel.foto_destaque or (imovel.fotos[0] if imovel.fotos else None)

    return PropertyData(
        product_code=imovel.codigo,
        title=title,
        description=description,
        address=address,
        price=price,
        bedrooms=imovel.dormitorios,
        area_sqm=float(area) if area is not None else None,
        thumbnail_url=thumbnail,
    )


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
