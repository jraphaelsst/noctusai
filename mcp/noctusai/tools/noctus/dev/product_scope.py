"""The ACTIVE product set — which products the dev process touches at all.

WHY (2026-09-22). The catalog (`public.products.ativo`) already says which products
are asleep, and the BUILD/DEPLOY side honours it (`build-scope.txt`,
`_catalog_scope_guard`). But every TEST/CHECK surface — the CI matrices in
`test.yml`, the pre-commit keepers, `gate_sweep`, `run_all_tests` — enumerated
products by walking `products/*`. A dormant product (`therapy-platform`,
`erp-imobiliario`, …) was therefore re-tested on every `seed/**` change, and every
red it produced blocked live work and cost a fix-and-rerun on code nobody was
working on. The catalog said "asleep"; the gates never asked.

TWO GENERATED FILES, ONE CATALOG READ (`build_scope._active_catalog_rows`):
  `deploy/fleet/build-scope.txt`  — `ativo AND deploy_scope='live'` + core → IMAGES
  `deploy/fleet/active-scope.txt` — `ativo` (any scope)            + core → GATES
`live ⊆ active` by construction. A product absent from `active-scope.txt` is
ASLEEP: no CI job, keeper, hook, or sweep checks it. Reactivating it in the admin
UI + `--refresh-build-scope` puts it back into every gate in one step — that is
the "product treatment" a woken product earns.

FAIL TOWARD COVERAGE. If `active-scope.txt` is missing, `filter_active` returns its
input unchanged and logs a WARNING — every product is checked, as before this file
existed. Losing the file must never silently switch gates OFF.

Depth: `KB § PATTERNS/architect/product-working-scope.md`.
"""
from __future__ import annotations

import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from settings import REPO_ROOT

logger = logging.getLogger(__name__)

ACTIVE_SCOPE_REL = Path("deploy") / "fleet" / "active-scope.txt"
ACTIVE_SCOPE_PATH = REPO_ROOT / ACTIVE_SCOPE_REL

#: `core` is the platform shell — no `public.products` row, always active. Same
#: documented non-product member as `build_scope.ALWAYS_BUILD`.
ALWAYS_ACTIVE = ("core",)


def _scope_path(root: Path | None) -> Path:
    return (root / ACTIVE_SCOPE_REL) if root is not None else ACTIVE_SCOPE_PATH


def _parse(text: str) -> list[str]:
    return sorted({
        ln.strip() for ln in text.splitlines()
        if ln.strip() and not ln.lstrip().startswith("#")
    })


def read_active_scope(root: Path | None = None) -> list[str] | None:
    """The active slugs, or None when the file does not exist (caller decides)."""
    path = _scope_path(root)
    if not path.exists():
        return None
    return _parse(path.read_text(encoding="utf-8"))


def filter_active(slugs: Iterable[str], root: Path | None = None) -> list[str]:
    """Keep only ACTIVE slugs. Missing scope file ⇒ keep all + WARNING (never silent)."""
    slugs = list(slugs)
    active = read_active_scope(root)
    if active is None:
        logger.warning(
            "%s is missing — checking EVERY product (dormant ones included). "
            "Regenerate: python mcp/noctusai/cli.py --refresh-build-scope",
            _scope_path(root),
        )
        return slugs
    keep = set(active)
    return [s for s in slugs if s in keep]


def is_active(slug: str, root: Path | None = None) -> bool:
    return bool(filter_active([slug], root))


def dormant_slugs(root: Path | None = None) -> list[str]:
    """On-disk `products/*` dirs that are asleep (empty when the scope file is missing)."""
    base = (root if root is not None else REPO_ROOT) / "products"
    on_disk = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    active = read_active_scope(root)
    if active is None:
        return []
    return [s for s in on_disk if s not in set(active)]


def _render(slugs: list[str], *, dormant: list[str], catalog_only: list[str], stamp: str) -> str:
    return f"""\
# active-scope.txt — WHICH PRODUCTS THE DEV PROCESS TOUCHES. One slug per line.
#
# 🔴 GENERATED — do not hand-edit. Regenerate (writes this AND build-scope.txt):
#     python mcp/noctusai/cli.py --refresh-build-scope
#
# DERIVED FROM THE CATALOG:
#     SELECT slug FROM public.products WHERE ativo = true      (any deploy_scope)
# ∩ products/* on disk, plus `core` (platform shell, not a `products` row).
#
# A product NOT listed here is ASLEEP: CI test jobs, pre-commit keepers, gate_sweep
# and run_all_tests skip it entirely. Wake it = set ativo=true in /admin/products,
# then regenerate — every gate picks it up again, no workflow edit needed.
# Consumers: KB § PATTERNS/architect/product-working-scope.md § 4c.
#
# build-scope.txt (the `live` subset) is always ⊆ this file.
#
# Last refresh: {stamp}
# Asleep (on disk, ativo=false): {", ".join(dormant) or "none"}
# Active in catalog but no products/<slug>/ dir: {", ".join(catalog_only) or "none"}

""" + "\n".join(slugs) + "\n"


def refresh_active_scope(write: bool = True, _active: list[str] | None = None,
                         root: Path | None = None) -> dict:
    """Regenerate `active-scope.txt`. `_active` is the test seam (skip the network)."""
    if _active is None:
        from .build_scope import _active_catalog_rows
        try:
            _active = [slug for slug, _scope in _active_catalog_rows()]
        except RuntimeError as exc:
            return {"ok": False, "status": "error", "error": str(exc)}

    base = (root if root is not None else REPO_ROOT) / "products"
    on_disk = sorted(p.name for p in base.iterdir() if p.is_dir()) if base.is_dir() else []
    slugs = sorted((set(_active) & set(on_disk)) | set(ALWAYS_ACTIVE))
    dormant = [s for s in on_disk if s not in slugs]
    catalog_only = sorted(set(_active) - set(on_disk))

    path = _scope_path(root)
    existing = _parse(path.read_text(encoding="utf-8")) if path.exists() else None
    changed = existing != slugs
    result = {"ok": True, "slugs": slugs, "dormant": dormant,
              "catalog_only": catalog_only, "path": str(path), "changed": changed}
    if not write:
        return {**result, "status": "would-write" if changed else "in-sync"}
    if not changed:
        return {**result, "status": "in-sync"}
    stamp = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_render(slugs, dormant=dormant, catalog_only=catalog_only, stamp=stamp),
                    encoding="utf-8")
    return {**result, "status": "written"}


__all__ = [
    "ACTIVE_SCOPE_PATH",
    "ACTIVE_SCOPE_REL",
    "ALWAYS_ACTIVE",
    "dormant_slugs",
    "filter_active",
    "is_active",
    "read_active_scope",
    "refresh_active_scope",
]
