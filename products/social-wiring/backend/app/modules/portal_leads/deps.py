"""Config seam for `portal_leads` — the one place OLX config is read.

Why this module exists at all: the receiver needs the per-CRM webhook
secret and the single-tenant default org in TWO places that are not
FastAPI dependencies — `_resolve_olx_secret` (handed to the seed's
`webhook_endpoint`) and `get_olx_service`. Neither can be reached by
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

from app.services.app_config_store import OlxConfig

#: Injected provider. `None` ⇒ resolve for real. Module-level rather than a
#: FastAPI dependency because the two consumers are not both deps.
_config_provider: Optional[Callable[[], OlxConfig]] = None


def configure_portal_leads(
    *, config_provider: Optional[Callable[[], OlxConfig]] = None
) -> None:
    """Install (or with `None`, clear) the config provider.

    The DI seam a test uses instead of patching. Always pair it with
    `reset_portal_leads()` — a leaked provider silently re-configures
    every later test in the session.
    """
    global _config_provider
    _config_provider = config_provider


def reset_portal_leads() -> None:
    """Drop any injected provider. Fixture teardown calls this."""
    configure_portal_leads(config_provider=None)


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


__all__ = [
    "configure_portal_leads",
    "get_olx_config",
    "reset_portal_leads",
]
