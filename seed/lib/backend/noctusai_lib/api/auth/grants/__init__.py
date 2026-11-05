"""Platform grants — the control plane delivers a credential to a product.

``GrantDelivery`` (sender: Protocol + Fake + Real HTTP + factory) lives in
``delivery``; the receiver router is ``noctusai_seed.platform_grants_router``.
See ``KB § PATTERNS/backend/platform-grants.md``.
"""

from noctusai_lib.api.auth.grants.delivery import (
    DeliveredCall,
    FakeGrantDelivery,
    GrantDelivery,
    GrantDeliveryError,
    GrantPayload,
    HttpGrantDelivery,
    make_grant_delivery,
)

__all__ = [
    "DeliveredCall",
    "FakeGrantDelivery",
    "GrantDelivery",
    "GrantDeliveryError",
    "GrantPayload",
    "HttpGrantDelivery",
    "make_grant_delivery",
]
