"""Vista CRM integration — fetch real estate property metadata.

Queries the agency's CRM API by property code (e.g. ``ONE5555``) and
returns a structured :class:`PropertyData` with the title, description,
and optional metadata used to auto-populate YouTube video metadata.

The Vista tenant endpoint and key are configured via ``CRM_BASE_URL`` /
``CRM_API_KEY`` or the Vista aliases ``VISTA_BASE_URL`` / ``VISTA_API_KEY``.
Vista authenticates with a ``key`` query parameter and expects explicit
fields inside a URL-encoded JSON ``pesquisa`` parameter.
"""
from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import httpx

logger = logging.getLogger(__name__)

# Product code format: ONE followed by 3–6 digits
PRODUCT_CODE_PATTERN = re.compile(r"^ONE\d{3,6}$")


class CRMServiceError(Exception):
    """Transport or auth failure against the CRM API."""


class CRMNotConfigured(CRMServiceError):
    """CRM_BASE_URL or CRM_API_KEY is missing in .env."""


@dataclass
class PropertyData:
    """Structured property metadata from the CRM."""

    product_code: str
    title: str  # e.g. "Apartamento 3 quartos — Moema, São Paulo"
    description: str  # Full text for YouTube description
    address: str | None = None
    price: str | None = None  # formatted, e.g. "R$ 1.200.000"
    bedrooms: int | None = None
    area_sqm: float | None = None
    thumbnail_url: str | None = None  # property photo for reference


def validate_product_code(code: str) -> bool:
    """Check if a product code matches the expected format."""
    return bool(PRODUCT_CODE_PATTERN.match(code))


class CRMService:
    """Fetch property metadata from the real estate CRM.

    Constructed from config values. Missing configuration raises at
    construction time; callers already treat that as "CRM disabled" and
    fall back to manual title entry or the product code.
    """

    def __init__(self, *, base_url: str, api_key: str):
        if not base_url:
            raise CRMNotConfigured(
                "CRM_BASE_URL/VISTA_BASE_URL is empty — CRM integration disabled."
            )
        if not api_key:
            raise CRMNotConfigured(
                "CRM_API_KEY/VISTA_API_KEY is empty — CRM integration disabled."
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_property(self, product_code: str) -> PropertyData | None:
        """Fetch property data by code.

        Returns ``None`` when the code doesn't exist (404 or empty
        response). Raises :class:`CRMServiceError` on transport/auth
        failures so callers can surface the issue.

        Uses Vista's confirmed live shape:
        ``GET /imoveis/detalhes?imovel=<code>&pesquisa=<json>&key=<key>``.
        """
        if not validate_product_code(product_code):
            logger.warning("invalid product code format: %s", product_code)
            return None

        pesquisa = {
            "fields": [
                "Codigo",
                "TituloSite",
                "TipoImovel",
                "Categoria",
                "Cidade",
                "Bairro",
                "Endereco",
                "ValorVenda",
                "ValorLocacao",
                "Dormitorios",
                "Suites",
                "Vagas",
                "AreaPrivativa",
                "AreaTotal",
                "DescricaoWeb",
                "Observacoes",
            ]
        }
        url = f"{self._base_url}/imoveis/detalhes"
        params = {
            "imovel": product_code,
            "pesquisa": json.dumps(pesquisa, separators=(",", ":")),
            "key": self._api_key,
        }
        headers = {"Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise CRMServiceError(
                f"Vista API request failed: {exc}"
            ) from exc

        if response.status_code == 404:
            logger.info("Vista: property %s not found (404)", product_code)
            return None

        if response.status_code == 401:
            raise CRMServiceError(
                "Vista API returned 401 — check CRM_API_KEY/VISTA_API_KEY in .env"
            )

        if response.status_code >= 400:
            raise CRMServiceError(
                f"Vista API error {response.status_code}: "
                f"{response.text[:200]}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise CRMServiceError(
                f"Vista API returned non-JSON response: {exc}"
            ) from exc

        if data in (None, [], {}):
            logger.info("Vista: property %s returned an empty payload", product_code)
            return None
        if isinstance(data, list):
            first = next((item for item in data if isinstance(item, dict)), None)
            if first is None:
                logger.info(
                    "Vista: property %s returned a list without object items",
                    product_code,
                )
                return None
            data = first
        if not isinstance(data, dict):
            raise CRMServiceError(
                f"Vista API returned unsupported payload type: {type(data).__name__}"
            )

        return self._map_response(product_code, data)

    def _map_response(
        self, product_code: str, data: dict
    ) -> PropertyData:
        """Map Vista's ``/imoveis/detalhes`` payload to PropertyData."""
        title = (
            data.get("TituloSite")
            or _join_present(
                data.get("TipoImovel") or data.get("Categoria"),
                data.get("Bairro"),
                data.get("Cidade"),
            )
            or f"Imovel {product_code}"
        )

        description = (
            data.get("DescricaoWeb")
            or data.get("Observacoes")
            or data.get("Descricao")
            or ""
        )

        address = _join_present(
            data.get("Endereco"),
            data.get("Bairro"),
            data.get("Cidade"),
        )

        price = (
            data.get("ValorVenda")
            or data.get("ValorLocacao")
        )
        price = _format_brl(price)

        bedrooms = (
            data.get("Dormitorios")
            or data.get("dormitorios")
        )
        if bedrooms is not None:
            try:
                bedrooms = int(bedrooms)
            except (ValueError, TypeError):
                bedrooms = None

        area = (
            data.get("AreaPrivativa")
            or data.get("AreaTotal")
        )
        if area is not None:
            try:
                area = float(area)
            except (ValueError, TypeError):
                area = None

        thumbnail = _first_photo_url(data.get("fotos"))

        return PropertyData(
            product_code=product_code,
            title=title,
            description=description,
            address=address,
            price=str(price) if price else None,
            bedrooms=bedrooms,
            area_sqm=area,
            thumbnail_url=thumbnail,
        )


    async def update_property_video_url(
        self,
        product_code: str,
        video_url: str,
        *,
        field_name: str = "Tour360",
    ) -> bool:
        """Push a video URL onto a Vista property — best-effort write.

        Returns ``True`` if Vista accepted the write, ``False`` on any
        failure (4xx, 5xx, network, malformed response). Never raises;
        the caller treats this as a fire-and-forget side effect that
        must not block the WhatsApp post-upload notification.

        ``field_name`` is the Vista field to populate. For this tenant
        (one-consultoria) the only video-ish field exposed by
        ``/imoveis/detalhes`` is ``Tour360``; other tenants may have a
        dedicated ``UrlVideo`` / ``LinkYoutube`` / etc. Pass an override
        if discovery reveals a better target.

        Endpoint contract — derived from the Vista REST docs (see
        ``KB § INTEGRATIONS/vista.md``). The exact route + method varies
        per tenant API-key permissions: read-only keys return 404 on the
        write routes. We try the documented ``PUT /imoveis/alterar``;
        observed 404 on the one-consultoria tenant means writes aren't
        provisioned for that key. Operator should request an elevated
        key from Vista support to enable this path.
        """
        if not validate_product_code(product_code):
            logger.info(
                "Vista update skipped: invalid product code %s", product_code
            )
            return False
        if not video_url:
            return False

        url = f"{self._base_url}/imoveis/alterar"
        params = {"imovel": product_code, "key": self._api_key}
        payload = {field_name: video_url}
        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.put(
                    url, params=params, json=payload, headers=headers
                )
        except httpx.HTTPError as exc:
            logger.warning(
                "Vista update_property_video_url transport error for %s: %s",
                product_code,
                exc,
            )
            return False

        if response.status_code >= 400:
            logger.warning(
                "Vista update_property_video_url for %s returned %d: %s",
                product_code,
                response.status_code,
                response.text[:200],
            )
            return False

        try:
            data = response.json()
        except Exception:
            # Empty or non-JSON 2xx body — Vista sometimes returns
            # 200 with no body on success. Treat as a soft success.
            logger.info(
                "Vista update_property_video_url for %s succeeded (empty body)",
                product_code,
            )
            return True

        # Vista's error shape is ``{"status": 4xx, "message": [...]}`` even
        # on 200 with payload errors. Defensive check.
        if isinstance(data, dict) and isinstance(data.get("status"), int):
            if data["status"] >= 400:
                logger.warning(
                    "Vista update_property_video_url for %s returned soft error %s: %s",
                    product_code,
                    data["status"],
                    data.get("message"),
                )
                return False

        logger.info(
            "Vista update_property_video_url for %s succeeded", product_code
        )
        return True


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


def _first_photo_url(value: Any) -> str | None:
    """Pick the best property photo URL from Vista's ``fotos`` payload.

    Selection logic:

      1. Walk every photo entry; prefer ones marked ``Destaque`` (Vista's
         "featured" flag — the agent flagged this as the best shot).
      2. For the chosen entry, prefer ``FotoGrande`` (typically 1920×1080+)
         over ``FotoMedia`` over ``Foto`` over ``FotoPequena``. YouTube
         thumbnails should be ≥1280×720 — picking the larger variants
         avoids a blurry default.
      3. Return ``None`` if the payload has no photos or none expose any
         of the recognised URL fields. Caller treats this as "use YT's
         auto-generated frame".

    Vista's payload shape is inconsistent — sometimes ``fotos`` is a list,
    sometimes an object keyed by photo id, sometimes a JSON string. We
    handle the first two and bail on anything else.
    """
    if isinstance(value, list):
        photos = value
    elif isinstance(value, dict):
        photos = list(value.values())
    else:
        return None
    if not photos:
        return None

    dict_photos = [p for p in photos if isinstance(p, dict)]
    if not dict_photos:
        return None

    # Featured first, then any remaining in source order.
    featured = sorted(
        dict_photos,
        key=lambda p: str(p.get("Destaque") or "").lower() not in {"sim", "true", "1"},
    )

    # Highest-resolution variant available for the chosen photo. Walk
    # every featured entry until one yields a usable URL — Vista sometimes
    # has placeholder entries with all-empty URL fields.
    url_priority = ("FotoGrande", "FotoMedia", "Foto", "FotoPequena")
    for entry in featured:
        for field in url_priority:
            url = entry.get(field)
            if isinstance(url, str) and url.strip():
                return url.strip()
    return None


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
