"""Derive `deploy/fleet/build-scope.txt` — WHICH products get images built.

WHY (2026-08-11). `build-and-push.yml` treated any `seed/**` change as "rebuild the
WHOLE fleet" — all 11 services in `docker-compose.prod.yml`, including the 7 that are
`ativo=false` in the catalog and that we have explicitly decided not to touch. A
one-line package.json edit cost a full 11-product build and churned images nobody
deploys.

TWO DIFFERENT QUESTIONS, two files:
  `deploy/fleet/docker-compose.prod.yml` — what CAN run on the VPS (the fleet)
  `deploy/fleet/build-scope.txt`         — what we MAINTAIN IMAGES FOR (the active set)

The active set is a CATALOG fact, not a repo fact:
    SELECT slug FROM public.products WHERE ativo = true AND deploy_scope = 'live'
plus `core`, the platform shell, which deliberately has no `products` row. Because it
is a catalog fact, it must be DERIVED here rather than hand-maintained in the txt file
— that is the `check_hardcoded_product_slug_set` rule applied to a new surface.

Depth: `KB § PATTERNS/devops/product-lockfile-and-slug-drift.md` ·
`KB § PATTERNS/architect/product-working-scope.md` (what ativo/deploy_scope mean).
"""
from __future__ import annotations

import logging
import os
import re
from datetime import datetime, timezone
from pathlib import Path

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

SCOPE_PATH = REPO_ROOT / "deploy" / "fleet" / "build-scope.txt"
FLEET_COMPOSE = REPO_ROOT / "deploy" / "fleet" / "docker-compose.prod.yml"

#: `core` is the platform shell — it runs in the fleet but is deliberately NOT a
#: `public.products` row, so no catalog query can return it. Naming it here is not a
#: frozen product-slug set (the rule is about deriving the PRODUCT set); it is the one
#: documented non-product member. Kept explicit so its absence is never a silent drop.
ALWAYS_BUILD = ("core",)

_KEY_RE = re.compile(r"^  ([a-z0-9][a-z0-9-]*):\s*$")


def fleet_slugs(compose: Path | None = None) -> list[str]:
    """Service names declared in the prod fleet compose file.

    Scoped to the `services:` block on purpose. A naive "any 2-space-indented key"
    match also swallows `environment:` / `networks:` nested inside a service and the
    entries under the TOP-LEVEL `networks:` (e.g. `noctus-net`) — which would report
    phantom fleet members and make the "excluded (inactive)" line lie.
    """
    path = compose or FLEET_COMPOSE
    if not path.exists():
        return []
    out: list[str] = []
    in_services = False
    for line in path.read_text(encoding="utf-8").splitlines():
        if re.match(r"^services:\s*$", line):
            in_services = True
            continue
        # Any other column-0 key ends the services block (networks:, volumes:, ...).
        if in_services and line and not line[0].isspace() and not line.lstrip().startswith("#"):
            break
        if in_services:
            m = _KEY_RE.match(line)
            if m:
                out.append(m.group(1))
    return sorted(set(out))


def _render(slugs: list[str], *, live_count: int, excluded: list[str], stamp: str) -> str:
    excl = ", ".join(excluded) if excluded else "none"
    return f"""\
# build-scope.txt — WHICH PRODUCTS GET IMAGES BUILT. One slug per line.
#
# 🔴 GENERATED — do not hand-edit. Regenerate with:
#     python mcp/noctusai/cli.py --refresh-build-scope
# (MCP: noctus.dev.refresh_build_scope). Hand-editing reintroduces exactly the
# drift class `check_hardcoded_product_slug_set` exists to prevent.
#
# WHY THIS EXISTS. `build-and-push.yml` used to treat any change under `seed/**` as
# "rebuild the WHOLE fleet", because a shared base moved. With {len(fleet_slugs())} services in
# `docker-compose.prod.yml` that meant a full rebuild for a one-line edit — including
# products that are `ativo=false` in the catalog and that we do not touch.
#
# THIS IS THE BUILD SET, NOT THE FLEET SET:
#   deploy/fleet/docker-compose.prod.yml  — what CAN run on the VPS (the fleet)
#   deploy/fleet/build-scope.txt (here)   — what we MAINTAIN IMAGES FOR
# The fleet file stays the source of truth for `build-and-push.sh`'s ALL_SLUGS and for
# what the VPS runs; this only narrows what a PUSH-triggered build rebuilds. An
# inactive product keeps running its last-built image until it is reactivated.
#
# DERIVED FROM THE CATALOG:
#     SELECT slug FROM public.products WHERE ativo = true AND deploy_scope = 'live'
# plus `core`, the platform shell (deliberately not a `products` row).
# `build-and-push.yml` REFUSES a slug here that is absent from the fleet compose, so a
# stale row fails the build loudly instead of silently skipping a product.
#
# ESCAPE HATCH: a manual `workflow_dispatch` run ignores this file entirely — pass an
# explicit `products` list, or leave it empty to rebuild every fleet slug.
#
# Last refresh: {stamp} — {live_count} live + {len(ALWAYS_BUILD)} platform.
# Excluded (inactive): {excl}

""" + "\n".join(slugs) + "\n"


def _live_slugs_from_catalog() -> list[str]:
    """Query the catalog for `ativo = true AND deploy_scope = 'live'`.

    Raises RuntimeError with an actionable message when the Supabase env is absent —
    NEVER returns a guess. A silently-wrong build scope would skip a live product's
    image, which is the exact failure this file exists to prevent.
    """
    url = os.environ.get("SUPABASE_URL")
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise RuntimeError(
            "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY are not set, so the catalog "
            "cannot be read. Export them (or source the .env you use for product "
            "backends) and re-run. Refusing to guess the active product set."
        )
    try:
        from supabase import create_client
    except ImportError as exc:  # pragma: no cover - env-dependent
        raise RuntimeError(f"the `supabase` package is required to read the catalog: {exc}") from exc

    client = create_client(url, key)
    resp = (
        client.table("products")
        .select("slug")
        .eq("ativo", True)
        .eq("deploy_scope", "live")
        .execute()
    )
    return sorted({row["slug"] for row in (resp.data or [])})


def refresh_build_scope(write: bool = True, _live: list[str] | None = None) -> dict:
    """Regenerate `build-scope.txt` from the catalog.

    `_live` is a test seam (skip the network). Returns
    `{ok, status, slugs, excluded, path, changed}`; `status` is
    `written` | `in-sync` | `would-write` | `error`.
    """
    try:
        live = _live if _live is not None else _live_slugs_from_catalog()
    except RuntimeError as exc:
        return {"ok": False, "status": "error", "error": str(exc)}

    fleet = fleet_slugs()
    slugs = sorted(set(live) | set(ALWAYS_BUILD))

    # A live product with no fleet service can never be built — surface, don't drop.
    orphans = [s for s in slugs if fleet and s not in fleet]
    if orphans:
        # `relative_to` raises when tests monkeypatch FLEET_COMPOSE outside REPO_ROOT
        # (same guard as auto_improvement.py) — an error path must never itself crash.
        try:
            where = str(FLEET_COMPOSE.relative_to(REPO_ROOT))
        except ValueError:
            where = str(FLEET_COMPOSE)
        return {
            "ok": False,
            "status": "error",
            "error": (
                f"catalog marks {orphans} live, but they have no service in "
                f"{where} — add the service or fix the catalog. Refusing to write a "
                f"scope file that silently skips them."
            ),
            "slugs": slugs,
        }

    excluded = [s for s in fleet if s not in slugs]
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    rendered = _render(slugs, live_count=len(live), excluded=excluded, stamp=stamp)

    existing = SCOPE_PATH.read_text(encoding="utf-8") if SCOPE_PATH.exists() else ""
    # Compare the SLUGS, not the bytes — the header carries a refresh date, so a
    # byte-compare would rewrite the file (and dirty the tree) on every run.
    changed = _parse_slugs(existing) != slugs

    if not write:
        return {"ok": True, "status": "would-write" if changed else "in-sync",
                "slugs": slugs, "excluded": excluded, "path": str(SCOPE_PATH), "changed": changed}
    if not changed:
        return {"ok": True, "status": "in-sync", "slugs": slugs, "excluded": excluded,
                "path": str(SCOPE_PATH), "changed": False}

    SCOPE_PATH.parent.mkdir(parents=True, exist_ok=True)
    SCOPE_PATH.write_text(rendered, encoding="utf-8")
    return {"ok": True, "status": "written", "slugs": slugs, "excluded": excluded,
            "path": str(SCOPE_PATH), "changed": True}


def _parse_slugs(text: str) -> list[str]:
    """The slug rows of a scope file (comments/blanks stripped)."""
    return sorted({
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    })


def read_build_scope() -> list[str]:
    """The active set as the build workflow sees it."""
    if not SCOPE_PATH.exists():
        return []
    return _parse_slugs(SCOPE_PATH.read_text(encoding="utf-8"))


def register(server) -> None:
    @server.tool(
        name="noctus.dev.refresh_build_scope",
        description=(
            "Regenerate `deploy/fleet/build-scope.txt` — the set of products whose "
            "images a PUSH-triggered `build-and-push.yml` run rebuilds. Derived from "
            "the catalog (`ativo = true AND deploy_scope = 'live'`) plus `core`. Run "
            "after activating/deactivating a product, else a `seed/**` push either "
            "rebuilds a product you retired or skips one you just activated. Needs "
            "SUPABASE_URL + SUPABASE_SERVICE_ROLE_KEY; REFUSES to guess without them. "
            "write=False previews. KB § PATTERNS/devops/product-lockfile-and-slug-drift.md."
        ),
    )
    def _refresh_build_scope(write: bool = True) -> dict:
        return refresh_build_scope(write=write)


__all__ = [
    "SCOPE_PATH",
    "FLEET_COMPOSE",
    "ALWAYS_BUILD",
    "fleet_slugs",
    "read_build_scope",
    "refresh_build_scope",
    "register",
]
