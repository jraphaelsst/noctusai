"""The ``register()`` ModuleRegistration seam contract for ``youtube``.

Validates the Phase 8 module exposes exactly the shape ``app/main.py``'s
assembly loop consumes — and that the external URL surface is preserved
post-modularization (zero route-path drift from W2.1 → Phase 8).
"""
from __future__ import annotations


def test_register_returns_module_registration_shape():
    from app.main import ModuleRegistration
    from app.modules.youtube import register

    reg = register()
    assert isinstance(reg, ModuleRegistration)
    assert isinstance(reg.routers, list) and reg.routers, "routers non-empty"
    assert isinstance(reg.standard_routers, tuple)


def test_standard_routers_is_empty():
    """The youtube module needs no extra seed standard_routers — the W2.1
    base (health / notificacoes / team) already covers it."""
    from app.modules.youtube import register

    assert register().standard_routers == ()


def test_register_carries_five_routers():
    """videos · upload · dashboard · youtube-tab-settings · oauth-callback."""
    from app.modules.youtube import register

    reg = register()
    assert len(reg.routers) == 5

    prefixes = sorted(getattr(r, "prefix", "") for r in reg.routers)
    assert prefixes == [
        "/api/dashboard",
        "/api/settings",
        "/api/videos",
        "/api/videos/upload",
        "/api/youtube/oauth",
    ]
