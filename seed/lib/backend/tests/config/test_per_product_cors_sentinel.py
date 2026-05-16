"""Cross-product regression for the ``@registry:own:<slug>`` rollout.

The CORS-REGISTRY-ROLLOUT project (2026-05-11) migrated every product's
``cors_origins`` default from a hand-enumerated comma-string to the
``@registry:own:<slug>`` sentinel resolved by
:mod:`noctusai_lib.config.cors_registry`.

This module pins two invariants per product so future drift fails loudly:

1. **Class default carries the sentinel.** Each product's ``Settings``
   subclass declares ``cors_origins: str = "@registry:own:<slug>"`` —
   verified by reading ``Settings.model_fields['cors_origins'].default``
   directly. This bypass is intentional: the runtime value is read from
   ``ROOT/.env`` (local-dev-only, gitignored), but the *class-level*
   default is the production / CI / fresh-clone source of truth.

2. **Resolution yields the expected set.** Setting the sentinel as the
   live value on :class:`BaseAppSettings` (the env-file-bypass shape)
   resolves to ``{localhost:5173, localhost:3000, localhost:<frontend_port>}``
   where ``<frontend_port>`` is the value pinned in ``start.sh PRODUCTS``.

CORE is excluded — it uses ``@registry:all`` (SSO-bridge shape, separate
test at the bottom of :mod:`test_cors_registry`).

PERSONAL-FINANCE joined this list 2026-05-11 (PF-CORS-REGISTRY follow-up,
after PF-AUTH-MIG and CORS-ROLLOUT both merged — PF's config.py was the
last hand-enumerated holdout).

If a new product joins the fleet, add it to ``PRODUCT_SLUGS`` and the
suite will enforce the sentinel + resolution pair automatically.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

import pytest

from noctusai_lib.config.cors_registry import (
    LOCALHOST_ALT_PORTS,
    parse_products_registry,
)
from noctusai_lib.config.settings import BaseAppSettings


# Products migrated by CORS-REGISTRY-ROLLOUT (2026-05-11) + PF-CORS-REGISTRY
# (2026-05-11 follow-up). CORE excluded — uses ``@registry:all``.
#
# ``media-scheduling`` was REMOVED here 2026-05-16: it was consolidated into
# ``imobi-scheduling`` by commit ``b91043f`` (the ms-merge), so
# ``products/media-scheduling/`` no longer exists and its ``app/config.py``
# is gone — the sentinel test was failing with ``FileNotFoundError`` on a
# product that is not part of the fleet. Root fix is to align the slug set
# with the real product set, not to special-case the missing file. (The
# ``youtube-crawler``/``mailing``/``imobi-scheduling`` slugs remain valid
# until the social-wiring-absorption Wave-4 teardown removes those products;
# they are scrubbed there in lock-step with ``start.sh``/the core
# product-registration migration.)
PRODUCT_SLUGS: tuple[str, ...] = (
    "adconnect",
    "daily-life",
    "dev-team",
    "erp-imobiliario",
    "imobi-scheduling",
    "mailing",
    "personal-finance",
    "seed",
    "therapy-platform",
    "youtube-crawler",
)


# Resolve `products/` once. This file lives at
# `seed/lib/backend/tests/config/test_per_product_cors_sentinel.py`, so
# parents[0]=config, [1]=tests, [2]=backend, [3]=lib, [4]=seed, [5]=repo-root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_PRODUCTS_DIR = _REPO_ROOT / "products"


@pytest.fixture(scope="module")
def registry_by_slug() -> dict[str, int]:
    """Live ``start.sh`` → ``{slug: frontend_port}`` lookup."""
    return {entry["slug"]: entry["frontend_port"] for entry in parse_products_registry()}


def _import_product_settings(slug: str):
    """Import ``products/<slug>/backend/app/config.py`` and return its
    Settings class (not instance — we want the *class default*, not the
    env-resolved runtime value).

    Imports under a unique synthetic module name per slug so multiple
    products' ``app.config`` modules coexist in ``sys.modules`` without
    one shadowing the next.
    """
    config_path = _PRODUCTS_DIR / slug / "backend" / "app" / "config.py"
    mod_name = f"_cors_rollout_test.{slug.replace('-', '_')}.app_config"
    spec = importlib.util.spec_from_file_location(mod_name, config_path)
    assert spec is not None and spec.loader is not None, (
        f"Could not build import spec for {config_path}"
    )
    module = importlib.util.module_from_spec(spec)
    sys.modules[mod_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(mod_name, None)
        raise
    # Each product names its class `Settings` / `<X>Settings` etc.; we want
    # the class defined IN THIS MODULE (not the re-imported `ProductSettings`
    # from `noctusai_seed`). Filter by `__module__` so we never pick up the
    # framework base class that the product imports for inheritance.
    candidates = [
        attr
        for attr in vars(module).values()
        if (
            isinstance(attr, type)
            and issubclass(attr, BaseAppSettings)
            and attr.__module__ == module.__name__
            and "cors_origins" in getattr(attr, "model_fields", {})
        )
    ]
    assert candidates, (
        f"No product-local BaseAppSettings subclass found in {slug}/app/config.py"
    )
    # If multiple product-local subclasses exist (rare), return the deepest in
    # the MRO — typically there's exactly one.
    candidates.sort(key=lambda c: len(c.__mro__), reverse=True)
    return candidates[0]


@pytest.mark.parametrize("slug", PRODUCT_SLUGS)
def test_class_default_is_registry_own_sentinel(slug: str) -> None:
    """Every migrated product's class default for ``cors_origins`` is the
    ``@registry:own:<slug>`` sentinel.

    Reads ``Settings.model_fields['cors_origins'].default`` — bypasses
    ``ROOT/.env`` loading so a local dev artifact can't mask a regression.
    """
    settings_cls = _import_product_settings(slug)
    field = settings_cls.model_fields["cors_origins"]
    assert field.default == f"@registry:own:{slug}", (
        f"{slug}: class default is {field.default!r}, expected '@registry:own:{slug}'. "
        "Did someone hand-enumerate origins back into config.py? "
        "Drive cross-product CORS off `start.sh PRODUCTS` via the sentinel."
    )


@pytest.mark.parametrize("slug", PRODUCT_SLUGS)
def test_sentinel_resolves_to_expected_origin_set(
    slug: str, registry_by_slug: dict[str, int]
) -> None:
    """The sentinel resolves to ``{localhost:5173, localhost:3000, localhost:<own_frontend>}``.

    Pins the post-migration shape: localhost alts (always) + this product's
    own frontend port from ``start.sh PRODUCTS``. Backend ports are NOT
    included — the browser never sends the backend's own port as Origin
    for cross-origin XHR. If a future change to ``cors_registry.derive_cors_origins``
    breaks this contract, this test fails for every product.
    """
    assert slug in registry_by_slug, (
        f"{slug} not in start.sh PRODUCTS — registry drift. "
        "Sentinel resolution would fall back to alts-only."
    )
    frontend_port = registry_by_slug[slug]

    # Direct instantiation with the sentinel — bypasses .env loading because
    # an explicit kwarg wins over env_file in pydantic-settings.
    s = BaseAppSettings(cors_origins=f"@registry:own:{slug}")
    resolved = set(s.cors_origins_list)

    expected = {f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS} | {
        f"http://localhost:{frontend_port}",
    }
    assert resolved == expected, (
        f"{slug}: resolved={sorted(resolved)} expected={sorted(expected)}"
    )
