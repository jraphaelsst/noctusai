"""Factory for the Vista client — Fake or Real, by flag.

Brings Vista in line with the canonical Protocol+Fake+Real+factory
shape (`integrations/google_calendar` + `google_maps` + `youtube`).
Before this, the module shipped Real (`VistaClient`) only — every
consumer that wanted a network-free Vista hand-rolled a stub. The
factory is the single seam consumers reach for.

`VistaClient` itself keeps the dep-factory leniency contract
(vista.md § 1): construction never raises; an unconfigured client
raises `VistaConfigError` at call time. The factory preserves that —
`use_fake=False` with no credentials yields a *real* client that will
raise `VistaConfigError` on first call, NOT at build time, so the
host app still starts.
"""
from __future__ import annotations

from typing import Any, Optional, Union

from .client import DEFAULT_TIMEOUT_SECONDS, VistaClient
from .fake import FakeVistaClient


def make_vista_client(
    *,
    use_fake: bool = False,
    base_url: Optional[str] = None,
    api_key: Optional[str] = None,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    http_client: Any = None,
    fake_responses: Optional[dict[str, Any]] = None,
    fake_errors: Optional[dict[str, Any]] = None,
    fake_configured: bool = True,
) -> Union[VistaClient, FakeVistaClient]:
    """Build a Vista client.

    - `use_fake=True` → `FakeVistaClient`, optionally pre-seeded with
      `fake_responses` (endpoint → raw Vista payload) and
      `fake_errors` (endpoint → `VistaError` instance to raise).
      `fake_configured=False` makes calls raise `VistaConfigError`
      (covers the unconfigured-tenant branch).
    - `use_fake=False` → real `VistaClient(base_url, api_key, ...)`.
      Missing credentials do NOT raise here (leniency contract) —
      the first call raises `VistaConfigError` instead.

    Both branches return an object with the same domain surface
    (`detalhes_imovel`, `listar_imoveis`, `probe`, …), so consumers
    select via the factory and never branch on environment themselves.
    """
    if use_fake:
        return FakeVistaClient(
            responses=fake_responses,
            errors=fake_errors,
            configured=fake_configured,
        )
    return VistaClient(
        base_url,
        api_key,
        timeout_seconds=timeout_seconds,
        http_client=http_client,
    )


__all__ = ["make_vista_client"]
