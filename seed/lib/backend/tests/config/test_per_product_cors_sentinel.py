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
   resolves to ``{localhost:5173, localhost:3000, localhost:<house_port>}``
   where ``<house_port>`` is the product's backend port in ``start.sh
   PRODUCTS`` — what the single-container house model serves the SPA on
   (the page origin the browser sends). (Pre-2026-05-25 this emitted the
   vestigial 2-container ``frontend_port``.)

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


# Resolve `products/` once. This file lives at
# `seed/lib/backend/tests/config/test_per_product_cors_sentinel.py`, so
# parents[0]=config, [1]=tests, [2]=backend, [3]=lib, [4]=seed, [5]=repo-root.
_REPO_ROOT = Path(__file__).resolve().parents[5]
_PRODUCTS_DIR = _REPO_ROOT / "products"


# CORS-migrated product slugs are DERIVED from the live ``start.sh``
# registry (the single source of truth) rather than frozen, so the set
# stays correct when products join or are retired without a manual edit.
# ``core`` is excluded (uses the ``@registry:all`` sentinel). Each slug
# is filesystem-guarded: a registry row whose ``backend/app/config.py``
# is absent (e.g. mid-teardown) is skipped instead of
# ``FileNotFoundError``-ing the suite. Root fix landed by
# social-wiring-absorption Wave 4 (2026-05-16), resolving the
# ``check_hardcoded_product_slug_set`` true-positive that previously
# froze ``media-scheduling``/``imobi-scheduling``/``mailing``/
# ``youtube-crawler`` literals here.
def _derive_product_slugs() -> tuple[str, ...]:
    slugs: list[str] = []
    for entry in parse_products_registry():
        slug = entry["slug"]
        if slug == "core":
            continue
        if (_PRODUCTS_DIR / slug / "backend" / "app" / "config.py").is_file():
            slugs.append(slug)
    return tuple(sorted(slugs))


PRODUCT_SLUGS: tuple[str, ...] = _derive_product_slugs()


@pytest.fixture(scope="module")
def registry_by_slug() -> dict[str, int]:
    """Live ``start.sh`` → ``{slug: house_port}`` lookup (the backend port —
    what the single-container house model serves the SPA + API on)."""
    return {entry["slug"]: entry["backend_port"] for entry in parse_products_registry()}


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
    """The sentinel resolves to ``{localhost:5173, localhost:3000, localhost:<own_house_port>}``.

    Pins the post-fix shape: localhost alts (always) + this product's own
    HOUSE port (the backend port in ``start.sh PRODUCTS``) — what the
    single-container house model serves the SPA on, i.e. the page origin the
    browser actually sends. Pre-2026-05-25 this emitted the vestigial
    2-container ``frontend_port``; ``derive_cors_origins`` now emits the house
    port (the house-port-vs-frontend-port family — url_base migration 037, the
    dev-CORS-band ``.env.example`` fix). If a future change to
    ``cors_registry.derive_cors_origins`` breaks this contract, this test
    fails for every product.
    """
    assert slug in registry_by_slug, (
        f"{slug} not in start.sh PRODUCTS — registry drift. "
        "Sentinel resolution would fall back to alts-only."
    )
    house_port = registry_by_slug[slug]

    # Direct instantiation with the sentinel — bypasses .env loading because
    # an explicit kwarg wins over env_file in pydantic-settings.
    s = BaseAppSettings(cors_origins=f"@registry:own:{slug}")
    resolved = set(s.cors_origins_list)

    expected = {f"http://localhost:{p}" for p in LOCALHOST_ALT_PORTS} | {
        f"http://localhost:{house_port}",
    }
    assert resolved == expected, (
        f"{slug}: resolved={sorted(resolved)} expected={sorted(expected)}"
    )
