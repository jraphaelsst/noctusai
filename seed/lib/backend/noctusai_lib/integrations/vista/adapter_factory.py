"""Factory for the higher-level `VistaCRMAdapter` — Fake or Real, by flag.

Mirrors the canonical Protocol+Fake+Real+factory shape used elsewhere
in the seed (`integrations/google_calendar`, `google_maps`). The
factory is the single seam consumers reach for; products never
instantiate the adapter directly.

This is the *adapter-layer* factory (`VistaCRMAdapter` →
`get_property(code) -> PropertyData | None`). The *client-layer*
factory `make_vista_client` (in ``factory.py``) is a separate seam for
the lower-level endpoint surface (paginated listings, showcase DTOs,
typed-error hierarchy).
"""

from __future__ import annotations

from noctusai_lib.domain.real_estate import PropertyData
from noctusai_lib.integrations.vista.fake_adapter import FakeVistaAdapter
from noctusai_lib.integrations.vista.protocol import VistaCRMAdapter
from noctusai_lib.integrations.vista.real import VistaRESTAdapter


def get_vista_adapter(
    *,
    base_url: str | None = None,
    api_key: str | None = None,
    fake: bool = False,
    fake_data: dict[str, PropertyData] | None = None,
) -> VistaCRMAdapter:
    """Return a `VistaCRMAdapter` wired for the supplied credentials.

    - ``fake=True`` → `FakeVistaAdapter` (in-memory; dev/test default).
      Pre-seed with ``fake_data={code: PropertyData}``.
    - ``base_url`` + ``api_key`` non-empty → `VistaRESTAdapter`
      (real Vista REST).
    - missing ``base_url`` ∨ missing ``api_key`` (and ``fake=False``)
      raises ``VistaNotConfigured`` — same contract as the source
      ``CRMService.__init__``. Callers that want a silent "Vista
      disabled" fall-through should pass ``fake=True``.
    """
    if fake:
        return FakeVistaAdapter(fake_data)
    return VistaRESTAdapter(base_url=base_url or "", api_key=api_key or "")
