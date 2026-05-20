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

from typing import Protocol

from noctusai_lib.domain.real_estate import PropertyData


class VistaCRMAdapter(Protocol):
    """Adapter contract for "fetch property by code" — async."""

    async def get_property(self, code: str) -> PropertyData | None:
        ...
