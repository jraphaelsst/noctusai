"""High-level Vista CRM adapter Protocol.

Contract: take a property `code` (e.g. ``ONE10010``), return a
domain-shape `PropertyData` (cross-CRM vocabulary) or ``None`` when
the property doesn't exist.

This sits one layer ABOVE the low-level `VistaClient`/`FakeVistaClient`
already shipped by this module:

- `VistaClient`           — typed async HTTP client, endpoint-aware
                            (`detalhes_imovel`, `listar_imoveis`, …),
                            raw Vista payloads + showcase DTOs.
- `VistaCRMAdapter`       — domain-shape facade: one method
                            `get_property(code) -> PropertyData | None`.
                            Real impl composes `VistaClient`.

The adapter layer exists so consumers that only need
"property metadata by code" (social-wiring's YouTube fan-out, future
WhatsApp intake) don't reach into the lower-level endpoint surface;
the low-level client stays for full-Vista consumers (ERP showcase,
calibration, MCP server).
"""

from __future__ import annotations

from typing import Optional, Protocol

from noctusai_lib.domain.real_estate import Imovel, ImovelPage, PropertyData


class VistaCRMAdapter(Protocol):
    """Adapter contract for the domain-shape CRM facade — async.

    Two methods, two return shapes, on purpose:

    - `get_property` → `PropertyData`, the 8-field YouTube-metadata carrier.
      Kept as-is; its consumers (the YouTube fan-out) want exactly that.
    - `list_imoveis` / `get_imovel` → `Imovel`, the full canonical listing.

    **Why `list_imoveis` was added (2026-08-03, roadmap P2.0b).** The seam
    previously exposed `get_property` alone — nothing list-shaped crossed it.
    That is fine for by-code lookups and useless for a catalog sync, so any
    consumer needing to walk the catalog had to reach *past* the adapter to
    the low-level `VistaClient`, which is a structural fork of the Fake+Real
    boundary: such a consumer cannot be tested against `FakeVistaAdapter`
    because the Fake has no equivalent. Widening the Protocol keeps the
    seam honest — and per `KB § PATTERNS/backend/seed-fake-real-adapter.md`
    both sides ship it in the same commit, never Protocol-only.
    """

    async def get_property(self, code: str) -> PropertyData | None:
        ...

    async def get_imovel(self, code: str) -> Optional[Imovel]:
        """Full canonical listing for one code, or ``None`` if absent."""
        ...

    async def list_imoveis(
        self, *, page: int = 1, page_size: int = 50, with_detalhes: bool = False
    ) -> ImovelPage:
        """One page of the catalog.

        `with_detalhes` costs one extra HTTP call per imóvel and is what
        populates `caracteristicas` + `FinalidadeStatus`-derived
        `finalidades`, both of which are detalhes-only on the wire.
        """
        ...

