#!/usr/bin/env python3
"""Audit that every product's frontend package.json lists every dep
in FRAMEWORK_DEPS (the list defined in seed/framework/frontend/vite.config.factory.ts).

Why: Vite's resolve.dedupe forces those deps to resolve from the product's
own node_modules. If any FRAMEWORK_DEP is imported by the seed source but
missing from a product's package.json, `npm run build` fails inside the
container with `Rollup failed to resolve import "<dep>"`.

Usage:
  python3 scripts/check-framework-deps.py            # audit + exit 1 on drift
  python3 scripts/check-framework-deps.py --fix      # auto-add missing deps
"""
import json
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent

# Source of truth — extracted from seed/framework/frontend/vite.config.factory.ts
# Update this list if FRAMEWORK_DEPS evolves over there.
FRAMEWORK_DEPS = [
    "react", "react-dom", "react-router-dom",
    "@tanstack/react-query", "zustand", "sonner",
    "lucide-react",
    "@radix-ui/react-tooltip", "@radix-ui/react-hover-card", "@radix-ui/react-collapsible",
    "@supabase/supabase-js",
    "clsx", "tailwind-merge",
]


def audit() -> tuple[dict[str, list[str]], int]:
    """Return ({slug: [missing_deps]}, total_missing_count)."""
    drift: dict[str, list[str]] = {}
    total = 0
    for pkg_path in sorted(REPO.glob("products/*/frontend/package.json")):
        slug = pkg_path.parent.parent.name
        pkg = json.loads(pkg_path.read_text())
        all_deps = {**pkg.get("dependencies", {}), **pkg.get("devDependencies", {})}
        missing = [d for d in FRAMEWORK_DEPS if d not in all_deps]
        if missing:
            drift[slug] = missing
            total += len(missing)
    return drift, total


def fix(drift: dict[str, list[str]]) -> int:
    """Borrow missing deps from a known-clean product (erp-imobiliario)."""
    if not drift:
        return 0
    donor = json.loads((REPO / "products/erp-imobiliario/frontend/package.json").read_text())
    donor_deps = {**donor.get("dependencies", {}), **donor.get("devDependencies", {})}
    fixed = 0
    for slug, missing in drift.items():
        pkg_path = REPO / "products" / slug / "frontend" / "package.json"
        pkg = json.loads(pkg_path.read_text())
        deps = pkg.setdefault("dependencies", {})
        for m in missing:
            version = donor_deps.get(m, "*")
            deps[m] = version
            fixed += 1
        pkg["dependencies"] = dict(sorted(deps.items()))
        pkg_path.write_text(json.dumps(pkg, indent=4) + "\n")
    return fixed


def main() -> int:
    fix_mode = "--fix" in sys.argv
    drift, total = audit()
    if not drift:
        print(f"✓ All {len(list(REPO.glob('products/*/frontend/package.json')))} products list every FRAMEWORK_DEP")
        return 0

    print(f"✗ {total} missing FRAMEWORK_DEPS across {len(drift)} product(s):")
    for slug, missing in drift.items():
        print(f"  {slug}: {', '.join(missing)}")

    if fix_mode:
        n = fix(drift)
        print(f"\n--fix: added {n} dep entries. Re-run without --fix to confirm.")
        return 0
    print("\nRun with --fix to auto-add missing deps.")
    return 1


if __name__ == "__main__":
    sys.exit(main())
