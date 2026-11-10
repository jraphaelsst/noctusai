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

from typing import Protocol

from noctusai_lib.domain.real_estate import PropertyData
from noctusai_lib.integrations.vista.fake_adapter import FakeVistaAdapter
from noctusai_lib.integrations.vista.protocol import VistaCRMAdapter
from noctusai_lib.integrations.vista.real import VistaRESTAdapter


class VistaOrgCredentials(Protocol):
    """`get(org_id) -> (base_url, api_key)`; raises `VistaConfigError` when the org has none."""

    def get(self, org_id: str) -> tuple[str, str]:
        ...


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


def get_vista_adapter_for_org(
    resolver: "VistaOrgCredentials", org_id: str, *, rate_per_sec: float | None = None, rate_burst: float | None = None
) -> VistaCRMAdapter:
    """The Real adapter for ONE org, built from its stored credential (`VistaCredentialResolver`).

    The only sanctioned construction path for a multi-tenant product: credentials are per org and live in the
    encrypted `CredentialStore`, never in the process environment. Raises `VistaConfigError` (via the resolver) when
    the org has no record -- there is no fallback.

    PACING: each org gets its OWN rate-limit bucket (`vista:<org_id>`), so one org's batch never starves another's.
    `rate_per_sec` / `rate_burst` set that org's budget; unset = the `vista` bucket defaults (5 rps / burst 10, or the
    process env `NOC_RL_VISTA_RPS|BURST`)."""
    base_url, api_key = resolver.get(org_id)
    return VistaRESTAdapter(
        base_url=base_url, api_key=api_key, rate_bucket=f"vista:{org_id}", rate_per_sec=rate_per_sec, rate_burst=rate_burst,
        pooled=True,
    )
