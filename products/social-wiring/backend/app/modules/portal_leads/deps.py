"""Config seam for `portal_leads` — the one place vendor config is read.

Why this module exists at all: a receiver needs its webhook secret and its
single-tenant default org in places that are not FastAPI dependencies —
`_resolve_<vendor>_secret` (handed to the seed's `webhook_endpoint`) and
the service factory. Neither can be reached by
`app.dependency_overrides`, so tests reached for
`patch("app.services.app_config_store.resolve_olx_config")` instead.

That is monkeypatching our own code, which this codebase forbids in
tests as well as in production (`KB § PATTERNS/backend/di-test-seam.md`,
`KB § PATTERNS/compliance/testing.md`) — `check_all_products` flags it
high-severity, and it earned two findings here. The objection is not
stylistic: a patched module attribute proves the test's stub works, not
that the wiring does, and it silently keeps passing after the call site
stops using that function at all.

So config resolution goes through a module-level slot populated by
`configure_portal_leads(...)` — the same dep-factory shape the rest of
this backend uses (`KB § PATTERNS/backend/backend.md`). Unset ⇒ the real
`resolve_olx_config`, read at REQUEST time so a DB-side config change
lands without a restart, and so nothing is captured at import.
"""
from __future__ import annotations

from typing import Callable, Optional

from app.services.app_config_store import ImovelWebConfig, OlxConfig

#: Injected providers, one per vendor. `None` ⇒ resolve for real.
#: Module-level rather than FastAPI dependencies because the consumers are
#: not all deps.
#:
#: Two slots rather than one dict keyed by vendor: a test almost always
#: configures ONE pipe, and a dict would make "configured OLX, left ImovelWeb
#: real" express itself as a missing key — which reads as an oversight rather
#: than a decision.
_config_provider: Optional[Callable[[], OlxConfig]] = None
_imovelweb_config_provider: Optional[Callable[[], ImovelWebConfig]] = None


def configure_portal_leads(
    *,
    config_provider: Optional[Callable[[], OlxConfig]] = None,
    imovelweb_config_provider: Optional[Callable[[], ImovelWebConfig]] = None,
) -> None:
    """Install (or with `None`, clear) the config providers.

    The DI seam a test uses instead of patching. Always pair it with
    `reset_portal_leads()` — a leaked provider silently re-configures
    every later test in the session.

    `config_provider` stays the OLX one under its original name so existing
    call sites keep working; ImovelWeb's is explicit. A single positional
    `config` would have to guess which vendor it meant.
    """
    global _config_provider, _imovelweb_config_provider
    _config_provider = config_provider
    _imovelweb_config_provider = imovelweb_config_provider


def reset_portal_leads() -> None:
    """Drop every injected provider. Fixture teardown calls this."""
    configure_portal_leads(config_provider=None, imovelweb_config_provider=None)


def get_olx_config() -> OlxConfig:
    """The resolved OLX config, read fresh on every call.

    Never cached: the secret lives in `app_integration_config` and an
    operator rotating it must not need a redeploy for the receiver to
    start accepting the new one.
    """
    if _config_provider is not None:
        return _config_provider()
    # Imported here, not at module import: `app_config_store` reaches for
    # a DB client, and importing it at module scope would bind that at
    # import time — the exact capture this module exists to avoid.
    from app.services.app_config_store import resolve_olx_config

    return resolve_olx_config()


def get_imovelweb_config() -> ImovelWebConfig:
    """The resolved ImovelWeb config, read fresh on every call.

    Never cached, for the same reason as the OLX one: the secret lives in
    `app_integration_config`, and an operator rotating it must not need a
    redeploy for the receiver to start accepting the new value.
    """
    if _imovelweb_config_provider is not None:
        return _imovelweb_config_provider()
    from app.services.app_config_store import resolve_imovelweb_config

    return resolve_imovelweb_config()


__all__ = [
    "configure_portal_leads",
    "get_imovelweb_config",
    "get_olx_config",
    "reset_portal_leads",
]
