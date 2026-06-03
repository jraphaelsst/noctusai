"""
Middleware namespace shortcut for Orbity.

Re-exports everything from the shared package so product code can
``from app.middleware import CorrelationIdMiddleware`` etc. without
reaching into ``noctusai_lib.api.middleware`` directly. Mirrors the
4-product convention (core, ERP, PF, therapy).

The seed's ``create_product_app(...)`` already wires the middleware
chain via the lib — this module exists for downstream imports and as
the canonical place to layer product-specific middleware on top.
"""
from noctusai_lib.api.middleware import *  # noqa: F401,F403
