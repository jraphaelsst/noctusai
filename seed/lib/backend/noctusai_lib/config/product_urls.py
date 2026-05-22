"""Environment-aware product URL resolution.

Replaces hardcoded ``http://localhost:<port>`` URLs from
``public.products.url_base`` with deploy-aware URLs. Both backends and any
service that constructs cross-product URLs route through
:func:`resolve_product_url` — same shape across products, including any
future product, by default wiring (the resolver lives in seed-lib so every
product inherits it via ``noctusai_lib.config.product_urls``).

Lives in the ``config`` layer (pure env resolution, no I/O beyond
``os.environ``) so both the ``api`` layer (HTTP routers) and the ``config``
layer (:mod:`noctusai_lib.config.cors_registry`, which derives deploy-aware
CORS origins from the same ``PRODUCT_URL_*`` scheme) can consume it without
an upward dependency.

Resolution order (first non-empty wins):

1. **Per-product env var** ``PRODUCT_URL_<UPPER_SLUG_UNDERSCORED>``. Slugs
   with hyphens become underscores: ``media-scheduling`` →
   ``PRODUCT_URL_MEDIA_SCHEDULING``. Highest priority — a deployment can
   pin a specific product to a specific URL without touching pattern or DB.
2. **Pattern** ``PRODUCT_URL_PATTERN``. Supports two placeholders:
   ``{slug}`` (raw slug) and ``{slug_underscored}``. Examples:

   - ``PRODUCT_URL_PATTERN=https://{slug}.noctus.ai`` →
     ``https://media-scheduling.noctus.ai`` for slug ``media-scheduling``.
   - ``PRODUCT_URL_PATTERN=https://app.noctus.ai/{slug}`` →
     ``https://app.noctus.ai/media-scheduling``.

   One pattern covers a fleet of products with a uniform host scheme;
   per-product env vars override it for the rare exception.
3. **``db_url_base`` fallback** — the value that ``public.products.url_base``
   holds. Typically ``http://localhost:<port>`` for dev (set by
   ``noctus.dev.scaffold_product``'s seed-row migration). For prod, leave
   the column populated with the localhost default and override via env:
   the column is then a "dev local default" rather than authoritative.

When all three sources are absent, raises :class:`ValueError`. Silent-error
shape (returning a hardcoded ``http://localhost:8000`` or ``""``) is
forbidden per platform rule — the caller must surface the gap.

The function performs no I/O beyond env lookups; safe to call per-request
without caching.
"""
from __future__ import annotations

import os


def resolve_product_url(slug: str, *, db_url_base: str | None = None) -> str:
    """Return the deploy-aware URL for a product, given its slug.

    Args:
        slug: The product slug as registered in ``public.products.slug``.
        db_url_base: The value of ``public.products.url_base`` for this
            product, if you've already fetched the row. Used as the final
            fallback when no env override is present.

    Returns:
        The resolved URL with any trailing ``/`` stripped (callers append
        their own paths and double-slashes confuse downstream redirects).

    Raises:
        ValueError: If ``slug`` is empty, OR if no env override is set
            and ``db_url_base`` is None/empty (caller must surface the
            config gap; silent fallback is forbidden).
    """
    if not slug:
        raise ValueError("resolve_product_url: slug must be non-empty")

    upper_slug = slug.replace("-", "_").upper()
    env_var = f"PRODUCT_URL_{upper_slug}"
    per_product = os.environ.get(env_var)
    if per_product:
        return per_product.rstrip("/")

    pattern = os.environ.get("PRODUCT_URL_PATTERN")
    if pattern:
        return (
            pattern.replace("{slug}", slug)
            .replace("{slug_underscored}", slug.replace("-", "_"))
            .rstrip("/")
        )

    if db_url_base:
        return db_url_base.rstrip("/")

    raise ValueError(
        f"Cannot resolve URL for product '{slug}': set {env_var}, "
        "PRODUCT_URL_PATTERN, or ensure public.products.url_base is "
        "populated for this row."
    )
