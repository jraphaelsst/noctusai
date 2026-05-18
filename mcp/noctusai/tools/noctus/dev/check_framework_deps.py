"""`noctus.dev.check_framework_deps` — audit product frontend dep parity.

Behaviour-preserving native port of ``scripts/check-framework-deps.py``.

Why
    Vite's ``resolve.dedupe`` (set in
    ``seed/framework/frontend/vite.config.factory.ts``) forces ``FRAMEWORK_DEPS``
    to resolve from each product's OWN ``node_modules``. If any framework dep
    is imported by the seed source but missing from a product's
    ``package.json``, the container ``npm run build`` fails with
    ``Rollup failed to resolve import "<dep>"``. This tool audits every
    ``products/*/frontend/package.json`` for parity and can auto-fix by
    borrowing pinned versions from a known-clean donor product.

The ``FRAMEWORK_DEPS`` list is the source of truth extracted from
``vite.config.factory.ts`` — kept verbatim from the original script. Update
it here if ``FRAMEWORK_DEPS`` evolves over there (the original script carried
the same maintenance note).
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

logger = logging.getLogger(__name__)

# Source of truth — extracted from seed/framework/frontend/vite.config.factory.ts.
# Kept verbatim from scripts/check-framework-deps.py. Update if FRAMEWORK_DEPS
# evolves over there.
FRAMEWORK_DEPS: list[str] = [
    "react", "react-dom", "react-router-dom",
    "@tanstack/react-query", "zustand", "sonner",
    "lucide-react",
    "@radix-ui/react-tooltip", "@radix-ui/react-hover-card", "@radix-ui/react-collapsible",
    "@supabase/supabase-js",
    "clsx", "tailwind-merge",
]

# Default donor for --fix — a known-clean product (verbatim from the script).
_DONOR_SLUG = "erp-imobiliario"


def _audit(root: Path) -> tuple[dict[str, list[str]], int, int]:
    """Return ({slug: [missing_deps]}, total_missing, product_count).

    Identical logic to the original ``audit()``: iterate sorted
    ``products/*/frontend/package.json``, union ``dependencies`` +
    ``devDependencies``, collect FRAMEWORK_DEPS not present.
    """
    drift: dict[str, list[str]] = {}
    total = 0
    pkg_paths = sorted(root.glob("products/*/frontend/package.json"))
    for pkg_path in pkg_paths:
        slug = pkg_path.parent.parent.name
        pkg = json.loads(pkg_path.read_text())
        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        missing = [d for d in FRAMEWORK_DEPS if d not in all_deps]
        if missing:
            drift[slug] = missing
            total += len(missing)
    return drift, total, len(pkg_paths)


def _fix(root: Path, drift: dict[str, list[str]]) -> int:
    """Borrow missing deps from the donor product. Returns entries added.

    Identical logic to the original ``fix()`` — versions sourced from the
    donor's union deps (``"*"`` fallback), written back sorted with 4-space
    indent + trailing newline.
    """
    if not drift:
        return 0
    donor = json.loads(
        (root / "products" / _DONOR_SLUG / "frontend" / "package.json").read_text()
    )
    donor_deps = {
        **donor.get("dependencies", {}),
        **donor.get("devDependencies", {}),
    }
    fixed = 0
    for slug, missing in drift.items():
        pkg_path = root / "products" / slug / "frontend" / "package.json"
        pkg = json.loads(pkg_path.read_text())
        deps = pkg.setdefault("dependencies", {})
        for m in missing:
            deps[m] = donor_deps.get(m, "*")
            fixed += 1
        pkg["dependencies"] = dict(sorted(deps.items()))
        pkg_path.write_text(json.dumps(pkg, indent=4) + "\n")
    return fixed


def check_framework_deps(
    repo_root: Path | None = None,
    *,
    worktree_path: str | Path | None = None,
    fix: bool = False,
) -> dict:
    """Audit every product frontend ``package.json`` for FRAMEWORK_DEPS parity.

    Behaviour-preserving native port of ``scripts/check-framework-deps.py``.
    ``fix=False`` (default) is the read-only audit (the script's exit-1-on-
    drift becomes ``status="drift"``). ``fix=True`` mirrors ``--fix`` —
    borrows missing pinned versions from the donor product and writes the
    package.json files back.

    Args:
        repo_root: repo-root override (test seam). Wins over
            ``worktree_path``.
        worktree_path: caller-aware path resolution (same contract as the
            sibling dev tools).
        fix: when ``True``, auto-add missing deps from the donor product
            (``erp-imobiliario``). Mirrors the script's ``--fix``.

    Returns:
        ```
        {
          "products_audited": int,
          "drift": {"<slug>": ["<missing dep>", ...], ...},
          "total_missing": int,
          "fixed": int,                # entries written (0 unless fix=True)
          "status": "clean"|"drift"|"fixed",
          "exit_code": 0 | 1,          # verbatim shell exit (1 on drift, no fix)
        }
        ```
        ``status``/``exit_code`` mirror the script's ``main()``: clean → 0;
        drift + no fix → exit 1 (``status="drift"``); drift + fix → exit 0
        (``status="fixed"``).
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT

    drift, total, count = _audit(root)

    if not drift:
        logger.info(
            "check_framework_deps: all %d products list every FRAMEWORK_DEP",
            count,
        )
        return {
            "products_audited": count,
            "drift": {},
            "total_missing": 0,
            "fixed": 0,
            "status": "clean",
            "exit_code": 0,
        }

    fixed = 0
    if fix:
        fixed = _fix(root, drift)
        logger.info(
            "check_framework_deps: --fix added %d dep entries across %d product(s)",
            fixed, len(drift),
        )
        return {
            "products_audited": count,
            "drift": drift,
            "total_missing": total,
            "fixed": fixed,
            "status": "fixed",
            "exit_code": 0,
        }

    logger.warning(
        "check_framework_deps: %d missing FRAMEWORK_DEPS across %d product(s)",
        total, len(drift),
    )
    return {
        "products_audited": count,
        "drift": drift,
        "total_missing": total,
        "fixed": 0,
        "status": "drift",
        "exit_code": 1,
    }


def register(server) -> None:
    """Register the framework-deps audit MCP tool."""

    @server.tool(
        name="noctus.dev.check_framework_deps",
        description=(
            "Audit that every product's frontend package.json lists every "
            "FRAMEWORK_DEP (the vite.config.factory.ts resolve.dedupe set). A "
            "missing framework dep makes the product's container `npm run "
            "build` fail with `Rollup failed to resolve import`. Read-only by "
            "default (status=drift + exit_code 1 on drift); fix=True borrows "
            "pinned versions from erp-imobiliario and rewrites package.json. "
            "Port of scripts/check-framework-deps.py. Pass worktree_path when "
            "called from inside a git worktree."
        ),
    )
    def _check_framework_deps(
        worktree_path: str | None = None,
        fix: bool = False,
    ) -> dict:
        return check_framework_deps(worktree_path=worktree_path, fix=fix)
