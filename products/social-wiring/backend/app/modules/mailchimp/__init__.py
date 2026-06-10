"""``mailchimp`` — social-wiring product module for Mailchimp integration.

Slice B of the Mailchimp email-marketing integration. Proxies Mailchimp
Marketing API v3 live (no local mirror) via a per-org encrypted API key
stored in ``social_wiring.mailchimp_connections``.

Seam contract
─────────────
``app/main.py`` iterates ``MODULES`` — a list of zero-arg callables each
returning a ``ModuleRegistration``. This module exposes :func:`register`.
Adding it to the app:

    from app.modules.mailchimp import register as _mailchimp
    MODULES = [..., _mailchimp]

What ``register()`` does
─────────────────────────
Returns the five Mailchimp routers (connection, contacts, segments,
templates, campaigns) under ``/api/mailchimp/...``. No standard_routers
needed beyond what the existing MODULES already request.

Concurrent slice dependency
────────────────────────────
Slice A (seed adapter ``noctusai_lib.integrations.mailchimp``) is built
concurrently. The ``get_mailchimp_client_factory`` DI seam in ``deps.py``
imports the seed factory lazily inside the function body — not at module
level — so the module loads cleanly in the interim tree.
"""
from __future__ import annotations

from typing import Any


def register() -> Any:
    """Return this module's :class:`~app.main.ModuleRegistration`."""
    from app.modules.mailchimp.routers import (
        campaigns,
        connection,
        contacts,
        segments,
        templates,
    )
    from app.main import ModuleRegistration

    return ModuleRegistration(
        routers=[
            connection.router,
            contacts.router,
            segments.router,
            templates.router,
            campaigns.router,
        ],
        standard_routers=(),
    )


__all__ = ["register"]
