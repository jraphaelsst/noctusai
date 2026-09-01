"""Parse the platform `start.sh PRODUCTS` registry into a CORS origins list.

The `start.sh` file at the repository root carries the single source of
truth for product → frontend port mapping, in a block bounded by
``# BEGIN_PRODUCTS_REGISTRY`` / ``# END_PRODUCTS_REGISTRY`` sentinels:

    PRODUCTS=(
        "core:Core:8000:5173"
        "erp-imobiliario:ERP Imobiliario:8001:8080"
        ...
    )

Each entry is ``slug:Display Name:backend_port:frontend_port``.

Per-product ``config.py`` files previously hardcoded the relevant frontend
ports in their ``cors_origins`` string. That diverges from the registry as
soon as a new product joins the fleet — for a cross-product concern, the
right per-product code count is **zero**.

This module exposes two functions:

- :func:`parse_products_registry` — parse the ``PRODUCTS=(...)`` block.
- :func:`derive_cors_origins` — assemble the canonical origins list,
  optionally filtered to a single product's frontend.

Consumers opt in via a sentinel string on their ``cors_origins`` setting
(see :mod:`noctusai_lib.config.settings`):

- ``"@registry:all"`` — union of every product frontend (SSO-bridge shape).
- ``"@registry:own:<slug>"`` — just that product's frontend port.

Both forms automatically include localhost alt ports (``5173`` and
``3000``) so plain dev shells without registered ports keep working.

**Deploy-aware.** :func:`derive_cors_origins` also emits each in-scope
product's *production* origin, resolved from the same ``PRODUCT_URL_*`` env
scheme the nav layer uses (:mod:`noctusai_lib.config.product_urls`). With no
override set (local dev) it is a no-op — the result stays localhost-only. On
a deploy it means ``@registry:all`` auto-allows every product's prod origin
(+ the apex via ``PRODUCT_URL_CORE``) with **no hand-maintained
``CORS_ORIGINS``** — the localhost-only-in-prod gap that broke apex login
2026-05-22.

See ``KB § PATTERNS/environment.md § CORS_ORIGINS cascade``.
"""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Iterable, List, Optional, TypedDict

logger = logging.getLogger(__name__)


# Sentinels in start.sh that bracket the PRODUCTS array.
_REGISTRY_BEGIN = "# BEGIN_PRODUCTS_REGISTRY"
_REGISTRY_END = "# END_PRODUCTS_REGISTRY"

# Matches `"slug:Display Name:8000:5173"` (display may contain spaces).
_ENTRY_RE = re.compile(
    r'"\s*(?P<slug>[a-z0-9][a-z0-9-]*)'
    r'\s*:\s*(?P<display>[^:"]*?)'
    r'\s*:\s*(?P<backend_port>\d+)'
    r'\s*:\s*(?P<frontend_port>\d+)\s*"'
)

# Universal localhost alt origins — common dev shells that aren't pinned in
# the PRODUCTS registry (Vite default 5173 + Next/React default 3000). Kept
# in `http://localhost:<port>` form because that's the exact spelling the
# browser sends in the `Origin` header.
LOCALHOST_ALT_PORTS: tuple[int, ...] = (5173, 3000)


class ProductEntry(TypedDict):
    """Parsed row from ``start.sh PRODUCTS``."""

    slug: str
    display: str
    backend_port: int
    frontend_port: int


def _default_start_sh() -> Optional[Path]:
    """Best-effort lookup for the platform's ``start.sh``.

    The seed-lib lives at ``seed/lib/backend/noctusai_lib/config/``; walking
    four parents up lands on the repo root, where ``start.sh`` lives. In
    worktrees and template workspaces the layout is identical (symlinked
    surfaces preserve the directory shape).

    Returns ``None`` if no candidate exists — callers fall back to the
    universal localhost alt ports.
    """
    here = Path(__file__).resolve()
    # noctusai_lib/config/cors_registry.py → up 4 = seed/lib/backend → up = seed → up = root.
    # Concrete: parents[0]=config, [1]=noctusai_lib, [2]=backend, [3]=lib, [4]=seed, [5]=repo-root.
    for candidate in (here.parents[5] / "start.sh",):
        if candidate.exists():
            return candidate
    return None


def parse_products_registry(start_sh: Optional[Path] = None) -> List[ProductEntry]:
    """Parse the ``PRODUCTS=(...)`` array out of ``start.sh``.

    Args:
        start_sh: Path to the platform ``start.sh``. Defaults to the
            best-effort lookup (:func:`_default_start_sh`).

    Returns:
        List of :class:`ProductEntry` dicts. Empty list when the file is
        missing, the sentinels aren't found, or no entries match. Malformed
        rows (wrong field count, non-numeric ports) are skipped silently —
        the regex only matches well-shaped rows, so a typo surfaces as an
        absent product rather than a crash. (Callers can detect "registry
        seems empty" themselves if that becomes a real concern.)
    """
    if start_sh is None:
        start_sh = _default_start_sh()
    if start_sh is None or not start_sh.exists():
        return []

    text = start_sh.read_text(encoding="utf-8")

    begin_idx = text.find(_REGISTRY_BEGIN)
    end_idx = text.find(_REGISTRY_END)
    if begin_idx == -1 or end_idx == -1 or end_idx < begin_idx:
        return []

    block = text[begin_idx:end_idx]
    out: List[ProductEntry] = []
    for match in _ENTRY_RE.finditer(block):
        out.append(
            ProductEntry(
                slug=match.group("slug"),
                display=match.group("display").strip(),
                backend_port=int(match.group("backend_port")),
                frontend_port=int(match.group("frontend_port")),
            )
        )
    return out


def _localhost_origins(ports: Iterable[int]) -> List[str]:
    return [f"http://localhost:{port}" for port in ports]


def _pattern_origin(slug: str) -> str:
    """`PRODUCT_URL_PATTERN` applied to `slug`, ignoring any per-product override.

    Deliberately NOT `resolve_product_url`: that one short-circuits on
    `PRODUCT_URL_<SLUG>` because its job is to name the ONE canonical URL. An
    allowlist has the opposite job — see the call site.

    Returns `""` when no pattern is configured (plain dev), so the caller's
    dedupe drops it.
    """
    pattern = os.environ.get("PRODUCT_URL_PATTERN")
    if not pattern:
        return ""
    return (
        pattern.replace("{slug}", slug)
        .replace("{slug_underscored}", slug.replace("-", "_"))
        .rstrip("/")
    )



#: Opt-in for the legacy native (uvicorn + vite) path. Exported by
#: ``./start.sh native``; unset everywhere else, including every container.
NATIVE_DEV_ENV = "NOCTUS_NATIVE_DEV"


def _native_dev() -> bool:
    """True only when ``NOCTUS_NATIVE_DEV=1`` — i.e. `./start.sh native`.

    An EXPLICIT opt-in rather than an inferred "looks like dev" check, on
    purpose. Inferring it (say, from the absence of ``PRODUCT_URL_*``) would
    silently widen the allowlist in any environment that happens not to set
    that scheme, which is precisely the dead-origin regression the
    house-port-vs-frontend-port fixes closed. A mode that only one entry point
    turns on cannot leak into the house or prod shape.
    """
    return os.environ.get(NATIVE_DEV_ENV, "") == "1"


def derive_cors_origins(
    start_sh: Optional[Path] = None,
    include_localhost_alts: bool = True,
    include_all_frontends: bool = True,
    own_slug: Optional[str] = None,
    include_prod_origins: bool = True,
) -> List[str]:
    """Return the canonical CORS origins list derivable from ``start.sh``.

    **Deploy-aware.** Alongside the localhost dev origins, this also emits the
    **production** origin of each in-scope product, resolved from the same
    ``PRODUCT_URL_*`` env scheme the nav layer uses
    (:func:`noctusai_lib.config.product_urls.resolve_product_url`). A product
    contributes a prod origin **only** when an override is configured
    (``PRODUCT_URL_<SLUG>`` or ``PRODUCT_URL_PATTERN``); with none set (local
    dev) the resolver raises and the product is skipped — so the dev result
    is byte-for-byte the historical localhost-only list (back-compat).

    This is what lets ``@registry:all`` work in production with **no
    hand-maintained ``CORS_ORIGINS``**: set the ``PRODUCT_URL_*`` scheme on the
    deploy and core's SSO-bridge allowlist auto-includes every product's prod
    origin (and the apex, via ``PRODUCT_URL_CORE``), including future ones.

    The returned list is **deduplicated** and preserves first-seen order
    (localhost alts, then registry localhost frontends, then prod origins).

    Args:
        start_sh: Path to the platform ``start.sh``. Defaults to the
            best-effort lookup.
        include_localhost_alts: Append the universal localhost alt origins
            (``http://localhost:5173`` + ``http://localhost:3000``).
        include_all_frontends: When ``True``, include every registered
            product frontend (SSO-bridge shape — core hosts the bridge
            and must allow inbound XHR from every product). When ``False``,
            only ``own_slug``'s frontend is included (if any).
        own_slug: Limit to this product's frontend port. Used by
            ``"@registry:own:<slug>"`` sentinel. Required when
            ``include_all_frontends=False`` and a registry-derived port
            is wanted at all.
        include_prod_origins: When ``True`` (default), also emit each
            in-scope product's env-resolved production origin (a no-op in dev
            where no ``PRODUCT_URL_*`` is set). Set ``False`` to force the
            pure localhost shape regardless of environment.

    Returns:
        List of origin strings. Dev: ``http://localhost:<port>`` only. Deploy
        (``PRODUCT_URL_*`` set): the localhost set plus each in-scope product's
        ``https://…`` prod origin. Empty list only when
        ``include_localhost_alts=False``, the registry is empty/unreachable,
        and no prod overrides resolve.
    """
    entries = parse_products_registry(start_sh)

    out: List[str] = []
    seen: set[str] = set()

    def _add(origin: str) -> None:
        # The empty guard is load-bearing, not defensive noise: `_pattern_origin`
        # returns "" when no pattern is configured, and an empty string in a CORS
        # allowlist is not inert — it is a list entry that matches nothing and
        # shows up in every assertion about this function's output.
        if origin and origin not in seen:
            seen.add(origin)
            out.append(origin)

    if include_localhost_alts:
        for origin in _localhost_origins(LOCALHOST_ALT_PORTS):
            _add(origin)

    # In-scope slugs: every registered product (SSO-bridge shape) or just
    # own_slug (single-product shape). Drives BOTH the localhost house origins
    # and the deploy-aware prod origins below, so the two stay in lockstep.
    if include_all_frontends:
        in_scope = [entry["slug"] for entry in entries]
    elif own_slug is not None:
        in_scope = [own_slug]
    else:
        in_scope = []

    # localhost HOUSE origins (registry order; filtered to in-scope). The
    # single-container house model serves on the backend_port — that is what the
    # container publishes and what the browser sends as the Origin header. The
    # frontend_port is vestigial (pre-house 2-container era); emitting it would
    # allow-list a DEAD localhost origin (the house-port-vs-frontend-port family,
    # same as the url_base migration 037 + the dev-CORS-band .env.example fix).
    for entry in entries:
        if entry["slug"] in in_scope:
            _add(f"http://localhost:{entry['backend_port']}")

    # localhost NATIVE-DEV origins — the vite ports, ONLY under `start.sh native`.
    #
    # The comment above is right that `frontend_port` is dead in the house
    # model: one container serves API + SPA on `backend_port`, so the browser's
    # Origin IS the backend port and no preflight crosses origins at all. But
    # `./start.sh native` (uvicorn + vite, the documented legacy hot-reload
    # path) is still shipped, and THERE the SPA is served by vite on
    # `frontend_port`. Omitting it made every authed page of every product fail
    # in that mode: the OPTIONS preflight came back 400 "Disallowed CORS
    # origin" from both core and the product's own backend, so the UI loaded
    # and then showed "Servidor indisponivel" everywhere. Measured on igig
    # 2026-09-01; prod was verified unaffected (core preflight from
    # https://igig.noctusai.com returns 200).
    #
    # Gated on the explicit `NOCTUS_NATIVE_DEV=1` opt-in so the house/prod
    # shape is byte-for-byte unchanged (every existing assertion about this
    # function still holds) and no DEAD origin is ever allow-listed in a
    # deployed image — the regression the house-port-vs-frontend-port family
    # fixed. Only `./start.sh native` sets it.
    if _native_dev():
        for entry in entries:
            if entry["slug"] in in_scope:
                _add(f"http://localhost:{entry['frontend_port']}")

    # deploy-aware prod origins. Unioned (deduped) from TWO sources so the
    # result is correct in BOTH dev and the slim prod image:
    #   (a) registry slugs resolved via the PRODUCT_URL_* scheme — needs a
    #       parseable start.sh (present in dev / a full checkout).
    #   (b) the PRODUCT_URL_<SLUG> env vars READ DIRECTLY — registry-independent.
    #       The slim PROD image ships NO start.sh, so (a) yields nothing there;
    #       the env vars are then the only source of truth for the deployed
    #       products. Without (b), `@registry:all` collapses to localhost-only
    #       inside the container — the 2026-05-22 cutover failure.
    # No-op in dev with no PRODUCT_URL_* set (resolver raises ∧ no env keys).
    if include_prod_origins:
        # Lazy, SAME-LAYER import (config → config): keeps module import cheap,
        # avoids bootstrap-order coupling (mirrors settings.py's lazy import of
        # this module), and stays a downward-clean dependency.
        from noctusai_lib.config.product_urls import resolve_product_url

        if include_all_frontends:
            # (a) registry-derived slugs (covers pattern-only products in dev)
            for slug in in_scope:
                try:
                    _add(resolve_product_url(slug))
                except ValueError:
                    logger.debug(
                        "derive_cors_origins: no prod URL override for slug=%s; "
                        "skipping (dev or unconfigured)",
                        slug,
                    )
                # (a2) ALSO the pattern-derived origin, even when an explicit
                # `PRODUCT_URL_<SLUG>` already answered above.
                #
                # `resolve_product_url` short-circuits on the override, which is
                # correct for "the ONE canonical URL to link to" and wrong here:
                # this is an ALLOWLIST, and several products are served at BOTH
                # names by `deploy/tunnel/ingress.yml` (`social.` AND
                # `social-wiring.`, `erp.` AND `erp-imobiliario.`). Emitting only
                # the override leaves the other live hostname blocked — measured
                # 2026-08-19, right after the registry fix: `p-studio.` and
                # `igig.` came back 200 while `social-wiring.` and
                # `erp-imobiliario.` still answered 400 with no allow-origin.
                #
                # A user who reaches the product by its long name would hit the
                # same opaque "Failed to fetch" the registry gap caused. An
                # allowlist is a SET of origins we serve, not a preference order.
                _add(_pattern_origin(slug))
            # (b) explicit PRODUCT_URL_<SLUG> env overrides — registry-free, so
            # this is what makes the SSO-bridge allowlist work in the container.
            for env_key, env_val in os.environ.items():
                if (
                    env_key.startswith("PRODUCT_URL_")
                    and env_key != "PRODUCT_URL_PATTERN"
                    and env_val
                ):
                    _add(env_val.rstrip("/"))
        elif own_slug is not None:
            # Single-product shape: resolve own_slug directly (env-based, needs
            # no registry — works in the container too).
            try:
                _add(resolve_product_url(own_slug))
            except ValueError:
                logger.debug(
                    "derive_cors_origins: no prod URL override for own_slug=%s; "
                    "skipping (dev or unconfigured)",
                    own_slug,
                )
            # ALSO the pattern-derived origin — the same reason as the
            # `include_all_frontends` branch above, which is where this was
            # first fixed and where the fix wrongly STOPPED (2026-08-19).
            #
            # `resolve_product_url` short-circuits on `PRODUCT_URL_<SLUG>`, and
            # for two products that override is the SHORT hostname: social-wiring
            # is served at `social.` AND `social-wiring.`, erp-imobiliario at
            # `erp.` AND `erp-imobiliario.` (`deploy/tunnel/ingress.yml`). Adding
            # only the override left the slug-named alias returning 400 with no
            # allow-origin — measured in prod 2026-08-21, right after a deploy
            # that was believed to have fixed exactly this.
            #
            # It only ever showed on those two: `igig` and `p-studio` have
            # slug == subdomain, so the override and the pattern agree and the
            # missing line was invisible. An allowlist is a SET of the origins we
            # serve, not a preference order.
            _add(_pattern_origin(own_slug))

    return out


__all__ = [
    "LOCALHOST_ALT_PORTS",
    "ProductEntry",
    "derive_cors_origins",
    "parse_products_registry",
]
