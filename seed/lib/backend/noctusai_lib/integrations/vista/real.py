"""Vista REST adapter — the higher-level `VistaCRMAdapter` Real impl.

Lifted 2026-05-20 from
``products/social-wiring/backend/app/services/crm_service.py``
(``CRMService``) via ``social-wiring-vista-seed-lift``. The logic is
ported VERBATIM — same Vista wire shape (``GET /imoveis/detalhes?
imovel=<code>&pesquisa=<json>&key=<key>``), same field list, same
``_map_response`` normalization, same ``update_property_video_url``
best-effort write semantics.

Why a second adapter at this layer (when the module already ships the
lower-level `VistaClient`):

- ``VistaClient`` is endpoint-shape (raw Vista payloads + showcase
  DTOs + 7-class error hierarchy + paginated listing). Useful for the
  ERP showcase + MCP server.
- ``VistaRESTAdapter`` is property-by-code-shape (returns a domain
  ``PropertyData``). Useful for social-wiring's YouTube fan-out.

The two will eventually converge — once a second domain-shape consumer
arrives we can refactor ``VistaRESTAdapter`` to compose ``VistaClient`` +
``vista_imovel_to_showcase`` + a showcase-to-PropertyData mapper. For
now we keep the port verbatim to minimize behavioral risk.
"""

from __future__ import annotations

import json
import logging
from typing import Any

import httpx

from noctusai_lib.domain.real_estate import (
    Imovel,
    ImovelPage,
    PropertyData,
    validate_product_code,
)
from noctusai_lib.integrations.vista.calibration import calibrator
from noctusai_lib.integrations.vista.client import (
    VistaClient,
    VistaConfigError,
    VistaError,
    VistaNotFound,
    extract_items,
)
from noctusai_lib.integrations.vista.imovel_normalizer import vista_to_imovel

logger = logging.getLogger(__name__)


# Alias the existing seed names to the adapter-layer vocabulary the
# `social-wiring-vista-seed-lift` brief uses. Importers can use either
# name interchangeably (same class objects, same hierarchy).
VistaNotConfigured = VistaConfigError


class VistaRESTAdapter:
    """Fetch property metadata from the Vista REST API by code.

    Constructed from config values. Missing configuration raises
    ``VistaNotConfigured`` at construction time; callers treat that as
    "Vista disabled" and fall back to manual metadata entry or the bare
    product code.
    """

    def __init__(self, *, base_url: str, api_key: str):
        if not base_url:
            raise VistaNotConfigured(
                "VISTA_BASE_URL is empty — Vista integration disabled."
            )
        if not api_key:
            raise VistaNotConfigured(
                "VISTA_API_KEY is empty — Vista integration disabled."
            )
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key

    async def get_property(self, code: str) -> PropertyData | None:
        """Fetch property data by code.

        Returns ``None`` when the code doesn't exist (404 or empty
        response). Raises :class:`VistaError` on transport/auth failures
        so callers can surface the issue.

        Uses Vista's confirmed live shape:
        ``GET /imoveis/detalhes?imovel=<code>&pesquisa=<json>&key=<key>``.
        """
        if not validate_product_code(code):
            logger.warning("invalid product code format: %s", code)
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
            "imovel": code,
            "pesquisa": json.dumps(pesquisa, separators=(",", ":")),
            "key": self._api_key,
        }
        headers = {"Accept": "application/json"}

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                response = await client.get(url, params=params, headers=headers)
        except httpx.HTTPError as exc:
            raise VistaError(
                f"Vista API request failed: {exc}"
            ) from exc

        if response.status_code == 404:
            logger.info("Vista: property %s not found (404)", code)
            return None

        if response.status_code == 401:
            raise VistaError(
                "Vista API returned 401 — check VISTA_API_KEY in .env"
            )

        if response.status_code >= 400:
            raise VistaError(
                f"Vista API error {response.status_code}: "
                f"{response.text[:200]}"
            )

        try:
            data = response.json()
        except Exception as exc:
            raise VistaError(
                f"Vista API returned non-JSON response: {exc}"
            ) from exc

        if data in (None, [], {}):
            logger.info("Vista: property %s returned an empty payload", code)
            return None
        if isinstance(data, list):
            first = next((item for item in data if isinstance(item, dict)), None)
            if first is None:
                logger.info(
                    "Vista: property %s returned a list without object items",
                    code,
                )
                return None
            data = first
        if not isinstance(data, dict):
            raise VistaError(
                f"Vista API returned unsupported payload type: {type(data).__name__}"
            )

        return self._map_response(code, data)

    # ─── Canonical `Imovel` surface (roadmap P2.0b) ──────────────────────
    #
    # These compose `VistaClient` + the per-tenant `calibrator` rather than
    # hand-rolling httpx and a hardcoded field list the way `get_property`
    # above does. That is deliberate: a hardcoded field list is exactly the
    # Phase-4.5 showcase incident (`KB § INTEGRATIONS/vista.md` § 6), and it
    # is why `get_property` cannot see `BanheiroSocial`, `Caracteristicas`
    # or any field the tenant enabled after that list was written.
    #
    # NOC-REMEDIATE[seed-fork]: `get_property` + `update_property_video_url`
    # still use raw httpx with a frozen 16-field `pesquisa`. They should be
    # re-based onto `VistaClient` + `calibrator` so the adapter has ONE
    # transport. Deferred here rather than done in-flight because those two
    # feed the live YouTube fan-out and a field-set change alters
    # `PropertyData.description` — a behaviour change that wants its own
    # slice, not a drive-by. Named destination: roadmap
    # `social-wiring-imoveis-vista-2026-08`, Phase 2 follow-up.

    def _client(self) -> VistaClient:
        return VistaClient(self._base_url, self._api_key)

    async def get_imovel(self, code: str) -> Imovel | None:
        """Full canonical listing for one code.

        Issues BOTH calls, because neither endpoint is a superset of the
        other: `detalhes` carries `Caracteristicas`/`Numero`/`FinalidadeStatus`,
        while `FotoDestaque`/`BanheiroSocial`/`CodigoImobiliaria` exist only
        on `listar`. Fetching one and calling it complete is the bug this
        method exists to prevent.
        """
        if not validate_product_code(code):
            logger.warning("invalid product code format: %s", code)
            return None

        client = self._client()
        listing = await self._fetch_listing_row(client, code)
        detalhes: dict | None = None
        try:
            fields = await calibrator.get_imovel_detail_fields(client)
            result = await client.detalhes_imovel(code, fields=fields)
            if isinstance(result.data, dict):
                detalhes = result.data
        except VistaNotFound:
            detalhes = None

        if listing is None and detalhes is None:
            return None
        return vista_to_imovel(listing=listing, detalhes=detalhes)

    async def _fetch_listing_row(
        self, client: VistaClient, code: str
    ) -> dict | None:
        """The `listar` row for one code — carries the listar-only fields."""
        fields = await calibrator.get_imovel_list_fields(client)
        try:
            result = await client.listar_imoveis(
                fields=fields, filter_={"Codigo": [code]}, page=1, page_size=1
            )
        except VistaNotFound:
            return None
        items, _ = extract_items(result.data)
        return items[0] if items else None

    async def list_imoveis(
        self, *, page: int = 1, page_size: int = 50, with_detalhes: bool = False
    ) -> ImovelPage:
        """One page of the catalog.

        `with_detalhes=True` costs one extra HTTP call per imóvel. On this
        tenant that is ~1919 extra calls for a full catalog walk — measured
        at ~4–6 min end-to-end at concurrency 4–8. The caller decides;
        the default stays cheap.
        """
        client = self._client()
        fields = await calibrator.get_imovel_list_fields(client)
        result = await client.listar_imoveis(
            fields=fields, page=page, page_size=page_size
        )
        rows, pagination = extract_items(result.data)

        imoveis: list[Imovel] = []
        for row in rows:
            detalhes = None
            if with_detalhes:
                codigo = row.get("Codigo")
                if codigo:
                    try:
                        detail_fields = await calibrator.get_imovel_detail_fields(client)
                        detail_result = await client.detalhes_imovel(
                            codigo, fields=detail_fields
                        )
                        if isinstance(detail_result.data, dict):
                            detalhes = detail_result.data
                    except VistaError as exc:
                        # One imóvel's detail failure must not abort the page —
                        # but it is NOT swallowed: the imóvel is still yielded
                        # from its listar row, and the gap is logged loudly so a
                        # sync reporting "1919 synced" can be trusted.
                        logger.warning(
                            "vista: detalhes failed for %s (%s) — "
                            "yielding listar-only imóvel without caracteristicas",
                            codigo, type(exc).__name__,
                        )
            imoveis.append(vista_to_imovel(listing=row, detalhes=detalhes))

        return ImovelPage(
            items=imoveis,
            total=int(pagination.get("total") or len(imoveis)),
            page=int(pagination.get("pagina") or page),
            pages=int(pagination.get("paginas") or 1),
        )

    def _map_response(self, code: str, data: dict) -> PropertyData:
        """Map Vista's ``/imoveis/detalhes`` payload to PropertyData."""
        title = (
            data.get("TituloSite")
            or _join_present(
                data.get("TipoImovel") or data.get("Categoria"),
                data.get("Bairro"),
                data.get("Cidade"),
            )
            or f"Imovel {code}"
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
            product_code=code,
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
        code: str,
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
        if not validate_product_code(code):
            logger.info(
                "Vista update skipped: invalid product code %s", code
            )
            return False
        if not video_url:
            return False

        url = f"{self._base_url}/imoveis/alterar"
        params = {"imovel": code, "key": self._api_key}
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
                code,
                exc,
            )
            return False

        if response.status_code >= 400:
            logger.warning(
                "Vista update_property_video_url for %s returned %d: %s",
                code,
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
                code,
            )
            return True

        # Vista's error shape is ``{"status": 4xx, "message": [...]}`` even
        # on 200 with payload errors. Defensive check.
        if isinstance(data, dict) and isinstance(data.get("status"), int):
            if data["status"] >= 400:
                logger.warning(
                    "Vista update_property_video_url for %s returned soft error %s: %s",
                    code,
                    data["status"],
                    data.get("message"),
                )
                return False

        logger.info(
            "Vista update_property_video_url for %s succeeded", code
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
