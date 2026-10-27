"""Vertical-seed overlays for `noctus.dev.scaffold_product(overlay=...)`.

An overlay (`templates/product-<name>/`) is applied ON TOP of `templates/product-seed`: it carries only the vertical's
organ bindings, never a copy of the base. `overlay.json` is the manifest. Application is deterministic and LOUD:

* files are copied over the scaffolded product; a file that already exists in the base must be declared in the manifest's
  `replaces` (an undeclared collision is a refusal, not an overwrite);
* `backend/app/main.py` and `frontend/src/App.tsx` are patched at named anchors -- a missing anchor FAILS the scaffold
  (the base template changed under the overlay; fix the overlay, never skip the patch);
* each overlay organ's migration is rendered with `expected_organ_migration` (the logic `render_organ_migration` uses),
  numbered after the base chain in `OrganSpec.requires` order, then one `status_pagina` migration for the overlay pages.

Market products scaffolded from an overlay stay `deploy_scope='dev'`: an agent never takes a new product to prod
(`KB § PATTERNS/devops/prod-exposure-consent.md`).

KB § PATTERNS/architect/vertical-seed.md · KB § GUIDES/new-product.md § Market products from a vertical seed
"""
from __future__ import annotations

import json
import re
import shutil
from pathlib import Path
from typing import Any

from .scaffold_migration import _format_number

#: Files of an overlay directory that are bookkeeping, not product content.
_NOT_COPIED = {"overlay.json", "OVERLAY.md"}
_MIGRATION_RE = re.compile(r"^(\d+)_")


class OverlayError(ValueError):
    """The overlay cannot be applied (unknown, malformed, or the base drifted from its anchors)."""


def load_overlay(overlay_dir: Path) -> dict[str, Any]:
    manifest = overlay_dir / "overlay.json"
    if not manifest.is_file():
        raise OverlayError(f"overlay manifest not found: {manifest}")
    data = json.loads(manifest.read_text(encoding="utf-8"))
    for key in ("name", "organs", "base_organs", "pages", "groups", "deploy_scope"):
        if key not in data:
            raise OverlayError(f"{manifest}: missing key {key!r}")
    if data["deploy_scope"] != "dev":
        raise OverlayError(f"{manifest}: an overlay product scaffolds to deploy_scope='dev' only (got {data['deploy_scope']!r})")
    return data


def organ_render_order(organs: list[str], base_organs: list[str]) -> list[str]:
    """`organs` ordered so every `OrganSpec.requires` dependency is rendered first (stable w.r.t. the listed order).

    A dependency that is neither an overlay organ nor a base organ is an error: its tables would not exist.
    """
    try:
        from noctusai_seed.organs import ORGAN_REGISTRY
    except ImportError as exc:
        raise OverlayError(f"cannot import noctusai_seed.organs: {exc}") from exc
    for name in organs:
        if name not in ORGAN_REGISTRY:
            raise OverlayError(f"unknown organ {name!r}; registered: {sorted(ORGAN_REGISTRY)}")
    ordered: list[str] = []
    remaining = list(organs)
    available = set(base_organs)
    while remaining:
        progressed = False
        for name in list(remaining):
            missing = [d for d in ORGAN_REGISTRY[name].requires if d not in available]
            if any(d in remaining for d in missing):
                continue  # wait for an overlay dependency
            if missing:
                raise OverlayError(f"organ {name!r} requires {missing}, which neither the overlay nor the base template provides")
            ordered.append(name)
            available.add(name)
            remaining.remove(name)
            progressed = True
        if not progressed:
            raise OverlayError(f"organ dependency cycle among {remaining}")
    return ordered


def preflight(overlay_dir: Path) -> dict[str, Any]:
    """Validate the overlay BEFORE the product directory is created. Returns the manifest + the render order."""
    manifest = load_overlay(overlay_dir)
    manifest["order"] = organ_render_order(manifest["organs"], manifest["base_organs"])
    return manifest


def _copy_overlay_files(overlay_dir: Path, target: Path, replaces: set[str]) -> list[str]:
    copied: list[str] = []
    for src in sorted(overlay_dir.rglob("*")):
        if not src.is_file() or src.name in _NOT_COPIED or "__pycache__" in src.parts:
            continue
        rel = src.relative_to(overlay_dir).as_posix()
        dest = target / rel
        if dest.exists() and rel not in replaces:
            raise OverlayError(f"overlay file {rel} collides with the base template and is not declared in `replaces`")
        if rel in replaces and not dest.exists():
            raise OverlayError(f"overlay declares it replaces {rel}, which the base template does not have")
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copyfile(src, dest)
        copied.append(rel)
    return copied


def _sub_once(text: str, pattern: str, repl: str, *, what: str, flags: int = 0, count: int = 1) -> str:
    new, n = re.subn(pattern, lambda _m: repl, text, flags=flags)
    if n != count:
        raise OverlayError(f"anchor not found in the base template ({what}): expected {count} match(es), got {n}")
    return new


def _patch_main(target: Path) -> None:
    path = target / "backend" / "app" / "main.py"
    text = path.read_text(encoding="utf-8")
    text = _sub_once(
        text, r"from noctusai_seed\.organs import mount_finance\n",
        "from app.erp_organs import ERP_ORGANS\n"
        "from app.erp_scheduler import configure as configure_scheduler, start_background, stop_background\n",
        what="main.py: mount_finance import",
    )
    text = _sub_once(
        text, r"    # Finance organ .*?    organs=\[\n        mount_finance\(\n.*?\n        \)\n    \],\n",
        "    # ERP organs (finance, parties, items, inventory, purchasing, contracts, quotes): one-call seed mounts in\n"
        "    # `app/erp_organs.py`; tables rendered by `noctus.dev.render_organ_migration` (pinned by tests/test_erp_wiring.py).\n"
        "    # Daily jobs (finance recurrences, contracts billing) register in `app/erp_scheduler.py` and only fire where\n"
        "    # NOCTUS_SCHEDULERS_ENABLED is set.\n"
        "    organs=ERP_ORGANS,\n"
        "    lifespan_startup=start_background,\n"
        "    lifespan_shutdown=stop_background,\n",
        what="main.py: organs=[mount_finance(...)] block", flags=re.DOTALL,
    )
    text = _sub_once(text, r"\napp = create_product_app\(", "\nconfigure_scheduler()\n\napp = create_product_app(", what="main.py: create_product_app call")
    path.write_text(text, encoding="utf-8")


def _nav_group(group_key: str, label: str, icon: str, items: list[dict[str, Any]], *, with_route: bool) -> str:
    rows = "\n".join(
        f'      {{ name: "{p["name"]}", href: "/{p["route"]}", icon: {p["icon"]}{(", route: " + json.dumps(p["route"])) if with_route else ""} }},'
        for p in items
    )
    return (
        "  {\n"
        f'    key: "{group_key}",\n'
        f'    label: "{label}",\n'
        f"    icon: {icon},\n"
        "    defaultOpen: true,\n"
        "    items: [\n"
        f"{rows}\n"
        "    ],\n"
        "  },\n"
    )


def _patch_app(target: Path, manifest: dict[str, Any]) -> None:
    path = target / "frontend" / "src" / "App.tsx"
    text = path.read_text(encoding="utf-8")
    pages = manifest["pages"]
    icons = []
    for p in pages:
        if p["icon"] not in icons:
            icons.append(p["icon"])
    # Anchor on the import itself, not on whichever icon happens to be last: the base template's icon list
    # changes (Settings joined it with the SectionTabsPage settings), and an icon it already imports must
    # not be imported twice.
    lucide = re.search(r'import \{ (.*?) \} from "lucide-react";', text)
    if lucide is None:
        raise OverlayError("anchor not found in the base template (App.tsx: lucide import)")
    imported = [n.strip() for n in lucide.group(1).split(",") if n.strip()]
    merged = imported + [i for i in icons if i not in imported]
    text = _sub_once(text, re.escape(lucide.group(0)), f'import {{ {", ".join(merged)} }} from "lucide-react";',
                     what="App.tsx: lucide import")
    lazies = "".join(f'const {p["file"]} = lazy(() => import("@/pages/{p["file"]}"));\n' for p in pages)
    anchor = 'const Financeiro = lazy(() => import("@/pages/Financeiro"));\n'
    if text.count(anchor) != 1:
        raise OverlayError("anchor not found in the base template (App.tsx: Financeiro lazy import)")
    text = text.replace(anchor, anchor + "// ERP organ pages (templates/product-erp overlay).\n" + lazies)
    group_chunks: list[tuple[str, list[dict[str, Any]]]] = []
    for gkey, glabel in manifest["groups"].items():
        group_chunks.append((gkey, [p for p in pages if p["group"] == gkey]))
    def _groups(with_route: bool) -> str:
        return "".join(
            _nav_group(gkey, manifest["groups"][gkey], items[0]["icon"], items, with_route=with_route)
            for gkey, items in group_chunks if items
        )
    hits = list(re.finditer(r"\n  \},\n\];\n", text))
    if len(hits) != 2:
        raise OverlayError(f"anchor not found in the base template (App.tsx: NAV_GROUPS / NAV_FALLBACK ends): expected 2, got {len(hits)}")
    # Insert from the END so the earlier offset stays valid: second array = fallback (no `route`), first = NAV_GROUPS.
    for hit, with_route in ((hits[1], False), (hits[0], True)):
        cut = hit.start() + len("\n  },\n")
        text = text[:cut] + _groups(with_route) + text[cut:]
    route_anchor = '    { path: "/financeiro/*", component: Financeiro },\n'
    if text.count(route_anchor) != 1:
        raise OverlayError("anchor not found in the base template (App.tsx: /financeiro route)")
    routes = "".join(f'    {{ path: "/{p["route"]}", component: {p["file"]} }},\n' for p in pages)
    text = text.replace(route_anchor, route_anchor + routes)
    path.write_text(text, encoding="utf-8")


def _status_pagina_sql(schema: str, pages: list[dict[str, Any]]) -> str:
    values = ",\n".join(f"    ('{p['route']}', 'producao')" for p in pages)
    return (
        "-- status_pagina -- the ERP overlay's nav pages. Every nav-listed route needs a matching row, or\n"
        "-- `filterNavByPageStatus` hides it from EVERYONE (KB § PATTERNS/frontend/status-pagina-dev-visibility.md).\n"
        "-- Forward-only + idempotent.\n"
        f"INSERT INTO {schema}.status_pagina (nome_pagina, status) VALUES\n{values}\n"
        "ON CONFLICT (nome_pagina) DO NOTHING;\n"
    )


def _render_migrations(target: Path, schema: str, manifest: dict[str, Any]) -> list[str]:
    from noctusai_lib.testing.organs import expected_organ_migration

    migrations = target / "backend" / "migrations"
    highest = max((int(m.group(1)) for p in migrations.glob("*.sql") if (m := _MIGRATION_RE.match(p.name))), default=0)
    written: list[str] = []
    for organ in manifest["order"]:
        highest += 1
        path = migrations / f"{_format_number(highest)}_{organ}.sql"
        path.write_text(expected_organ_migration(organ, schema, 1), encoding="utf-8")
        written.append(path.name)
    highest += 1
    path = migrations / f"{_format_number(highest)}_status_pagina_erp.sql"
    path.write_text(_status_pagina_sql(schema, manifest["pages"]), encoding="utf-8")
    written.append(path.name)
    return written


def apply_overlay(target: Path, overlay_dir: Path, *, schema: str, manifest: dict[str, Any] | None = None) -> dict[str, Any]:
    """Apply the overlay to a freshly copied product (run BEFORE placeholder substitution). Raises `OverlayError`."""
    manifest = manifest or preflight(overlay_dir)
    copied = _copy_overlay_files(overlay_dir, target, set(manifest.get("replaces", [])))
    _patch_main(target)
    _patch_app(target, manifest)
    migrations = _render_migrations(target, schema, manifest)
    return {
        "overlay": manifest["name"],
        "deploy_scope": manifest["deploy_scope"],
        "organs": manifest["order"],
        "files": copied,
        "migrations": migrations,
    }
