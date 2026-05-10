"""
Structured logging namespace shortcut for {{PRODUCT_NAME}}.

Re-exports everything from the shared package so product code can
``from app.logging_config import configure_logging, JSONFormatter``
without reaching into ``noctusai_lib.logging_config`` directly.
Mirrors the 4-product convention (core, ERP, PF, therapy).

The seed's ``create_product_app(...)`` calls ``configure_logging()``
during lifespan startup — this module exists for product code that
needs to suppress a noisy third-party logger or layer a custom
formatter. See ``KB § PATTERNS/logging.md``.
"""
from noctusai_lib.logging_config import *  # noqa: F401,F403
