"""WhatsApp contact-identity resolver — re-export shim.

Promoted to `noctusai_lib.integrations.whatsapp.identity` 2026-09-17
(`community` module 3 seed slice, `KB § CONTEXT/INTEGRATIONS/whatsapp.md`):
this file was pure WAHA shape with zero social-wiring domain, so the body
moved to the seed verbatim. This shim exists only so `social-wiring`'s
existing import (`from app.services.whatsapp_identity import
resolve_identity`, `app/routers/whatsapp_router.py`) and its test suite
keep working with byte-equivalent behaviour and zero call-site churn —
social-wiring is a LIVE product. Deletable in a later, separate step once
call sites are re-pointed directly at the seed module.
"""

from __future__ import annotations

from noctusai_lib.integrations.whatsapp.identity import (
    ResolvedIdentity,
    build_lids_map_from_list,
    resolve_identity,
)

__all__ = [
    "ResolvedIdentity",
    "build_lids_map_from_list",
    "resolve_identity",
]
