"""`noctus.dev.check_framework_deps` — audit product frontend dep parity.

Behaviour-preserving native port of ``scripts/check-framework-deps.py``,
extended with a DERIVED transitive-dep category (see below).

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

Seed-organ transitive deps (the blind-spot fix, 2026-07-20)
    ``FRAMEWORK_DEPS`` is a hand-curated literal — someone has to remember to
    add a new entry every time an organ promoted into ``@noctusai/lib``
    brings a new peer dep. It didn't happen for the ``KanbanBoard``/
    ``KanbanCard`` organ (commit ``3cb424b0``, needs ``@dnd-kit/core`` +
    ``@dnd-kit/sortable`` + ``@dnd-kit/utilities``) — the checker reported
    "clean" over a live fleet-wide ``vite build`` breakage because the audit
    never looked past the hand list.

    ``_derive_organ_transitive_deps`` closes that blind spot for the
    ``@noctusai/lib`` barrel specifically: it statically scans
    ``seed/lib/frontend/src/**/*.ts*`` for external package imports and
    UNIONS the result into the audited requirement set (see
    ``_required_deps``). A new organ with a new peer dep is caught the next
    time this tool runs — no one has to remember to edit a list.

    Scope, honestly stated: only ``seed/lib/frontend/src`` (the
    ``@noctusai/lib`` package — "seed organs" in the strict sense) is
    scanned. ``seed/framework/frontend/src`` (``@noctusai/seed`` — layout /
    auth-provider / app-shell plumbing, a different consumption shape than
    an opt-in barrel component) is NOT scanned; its deps remain covered by
    the hand-curated ``FRAMEWORK_DEPS`` list only. That is the named manual
    remainder — see ``_derive_organ_transitive_deps``'s docstring.
"""
from __future__ import annotations

import json
import logging
import re
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

# The ``@noctusai/lib`` package source tree — the seed-organ transitive-dep
# scan scope. See module docstring "Seed-organ transitive deps" for why
# ``seed/framework/frontend/src`` is deliberately NOT included.
ORGAN_SOURCE_DIR = "seed/lib/frontend/src"

# Default donor for --fix — a known-clean product (verbatim from the script).
_DONOR_SLUG = "erp-imobiliario"

# Matches `import ... from "spec"` / `export ... from "spec"`, capturing an
# optional leading `type` keyword (whole-declaration type-only import/
# re-export — erased before bundling, never needs to resolve at build time)
# and the module specifier. `[^;]*?` is non-greedy and spans newlines (real
# char class, not `.`) so multi-line `import {\n  A,\n  B,\n} from "pkg"`
# statements match too.
_IMPORT_SPEC_RE = re.compile(
    r"\b(?:import|export)\s+(type\s+)?[^;]*?\bfrom\s+['\"]([^'\"]+)['\"]"
)

# Comment stripping runs BEFORE `_IMPORT_SPEC_RE` — a JSDoc block containing
# the prose word "import" (e.g. "must NOT import external packages...", a
# real comment found in the seed lib) is a false anchor: `[^;]*?` has no
# semicolon to stop at inside a multi-line comment, so it lazily extends
# straight through the comment to the NEXT real `from "spec"` on the line
# after the comment closes — attributing that import's specifier to the
# wrong (comment-text) anchor and losing its `type` prefix in the process.
# Stripping comments first removes the false anchor entirely.
_BLOCK_COMMENT_RE = re.compile(r"/\*.*?\*/", re.S)
_LINE_COMMENT_RE = re.compile(r"//[^\n]*")


def _strip_comments(text: str) -> str:
    """Best-effort ``/* */`` + ``//`` comment stripper (not string-literal
    aware — a `//` inside a string, e.g. a URL, would be truncated). Scoped
    to import/export-statement scanning only, where that's a non-issue in
    practice (import specifiers here are always package/relative paths).
    """
    text = _BLOCK_COMMENT_RE.sub(" ", text)
    return _LINE_COMMENT_RE.sub("", text)


# Specifiers that resolve to something other than an installable npm
# package: relative paths, the product's own `@/...` source alias, and the
# seed's own self-referencing `@noctusai/...` aliases.
_LOCAL_SPECIFIER_PREFIXES = (".", "@/", "@noctusai/")


def _package_name_from_specifier(spec: str) -> str | None:
    """Normalize an import specifier to its installable npm package name.

    ``@scope/name/sub/path`` -> ``@scope/name``; ``name/sub/path`` -> ``name``.
    Returns ``None`` for relative / alias specifiers (see
    ``_LOCAL_SPECIFIER_PREFIXES``) — those are not npm packages.
    """
    if spec.startswith(_LOCAL_SPECIFIER_PREFIXES):
        return None
    parts = spec.split("/")
    if spec.startswith("@") and len(parts) >= 2:
        return "/".join(parts[:2])
    return parts[0]


def _derive_organ_transitive_deps(root: Path) -> list[str]:
    """Statically derive the external packages ``@noctusai/lib`` organs
    actually import — the category ``FRAMEWORK_DEPS`` structurally cannot
    keep up with (see module docstring). Returns ``[]`` when
    ``ORGAN_SOURCE_DIR`` doesn't exist (e.g. a unit-test ``tmp_path`` root
    that only fabricates ``products/``) — a deliberate no-op, not an error,
    so existing FRAMEWORK_DEPS-only callers are unaffected.

    Excludes ``*.test.ts*`` files (test-only deps like
    ``@testing-library/react`` / ``vitest`` never ship in a product's
    build — they're not reachable from the barrel entrypoints) and
    ``import type`` / ``export type`` declarations (erased before bundling).

    Best-effort regex scan, not a full TS/JSX parser — it does not follow
    dynamic ``import()`` expressions. A false negative here silently falls
    back to the ``FRAMEWORK_DEPS`` floor (no regression vs. today); it
    cannot under-report below that floor.
    """
    src_dir = root / ORGAN_SOURCE_DIR
    if not src_dir.is_dir():
        return []
    found: set[str] = set()
    for path in sorted(src_dir.rglob("*.ts*")):
        if ".test." in path.name:
            continue
        text = _strip_comments(path.read_text(encoding="utf-8"))
        for is_type, spec in _IMPORT_SPEC_RE.findall(text):
            if is_type:
                continue
            pkg = _package_name_from_specifier(spec)
            if pkg:
                found.add(pkg)
    return sorted(found)


def _required_deps(root: Path) -> tuple[list[str], list[str]]:
    """Return (required, organ_transitive) — the effective audited
    requirement set (``FRAMEWORK_DEPS`` in declared order, plus any
    derived-only extras appended sorted) and the raw derived list (for
    reporting).
    """
    organ_transitive = _derive_organ_transitive_deps(root)
    extras = [d for d in organ_transitive if d not in FRAMEWORK_DEPS]
    return list(FRAMEWORK_DEPS) + extras, organ_transitive


#: The dependency whose PRESENCE makes a product frontend a framework
#: consumer. Deriving the audit's scope from this — rather than from a
#: hand-listed set of slugs — is deliberate: a slug list is exactly the
#: hand-maintained list this codebase gates against elsewhere
#: (`check_hardcoded_product_slug_set`), and it would go stale the first time
#: a product was absorbed or migrated.
_FRAMEWORK_PACKAGE = "@noctusai/seed"


def _consumes_framework(pkg: dict) -> bool:
    """Does this product's frontend build against the seed framework?

    🔴 WHY THE AUDIT IS SCOPED AT ALL.
    ``FRAMEWORK_DEPS`` exists because ``vite.config.factory.ts`` forces those
    packages into the bundle — see this module's header. A frontend that never
    depends on ``@noctusai/seed`` never runs that factory, so none of those
    packages are forced, and none of them are missing. Auditing it asserts a
    requirement that does not apply to it.

    This is not hypothetical. ``permutas`` was absorbed on 2026-09-04 as a
    create-react-app + Redux + styled-components platform importing neither
    ``@noctusai/seed`` nor ``@noctusai/lib``; the audit reported 12 "missing"
    deps for it, and because this check runs inside every product's CI job it
    turned the whole matrix red — including ``core``, whose own tests passed.
    "Fixing" it by adding the 12 would have bloated a CRA bundle with
    libraries it never imports, to make a gate assert something false.

    A divergent-architecture absorption is therefore OUT of scope until its
    frontend is actually migrated onto the framework — and the day it is, this
    predicate flips on its own, because the migration is precisely the act of
    adding ``@noctusai/seed`` to its dependencies. There is nothing to
    remember to update.
    """
    return _FRAMEWORK_PACKAGE in {
        **pkg.get("dependencies", {}),
        **pkg.get("devDependencies", {}),
    }


def _audit(root: Path) -> tuple[dict[str, list[str]], int, int, list[str]]:
    """Return ({slug: [missing_deps]}, total_missing, audited_count, skipped).

    Same shape as the original ``audit()``: iterate sorted
    ``products/*/frontend/package.json``, union ``dependencies`` +
    ``devDependencies``, collect required deps not present. The required
    set is ``FRAMEWORK_DEPS`` UNIONED with the derived seed-organ
    transitive deps (``_required_deps``) — a superset, so existing
    FRAMEWORK_DEPS-only callers see a strict widening, never a narrowing.

    Non-consumers are SKIPPED and RETURNED, never silently dropped: a product
    vanishing from a gate's scope without saying so is the silent-error shape
    this codebase forbids. The caller surfaces them as
    ``skipped_non_consumers`` so "why is permutas not audited?" is answerable
    from the output alone.
    """
    required, _organ_transitive = _required_deps(root)
    drift: dict[str, list[str]] = {}
    total = 0
    audited = 0
    skipped: list[str] = []
    pkg_paths = sorted(root.glob("products/*/frontend/package.json"))
    for pkg_path in pkg_paths:
        slug = pkg_path.parent.parent.name
        pkg = json.loads(pkg_path.read_text())
        if not _consumes_framework(pkg):
            skipped.append(slug)
            continue
        audited += 1
        all_deps = {
            **pkg.get("dependencies", {}),
            **pkg.get("devDependencies", {}),
        }
        missing = [d for d in required if d not in all_deps]
        if missing:
            drift[slug] = missing
            total += len(missing)
    return drift, total, audited, sorted(skipped)


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
          "organ_transitive_deps": [str, ...],  # derived from seed/lib/frontend/src
          "manual_only_scope": ["seed/framework/frontend/src (@noctusai/seed)"],
        }
        ```
        ``status``/``exit_code`` mirror the script's ``main()``: clean → 0;
        drift + no fix → exit 1 (``status="drift"``); drift + fix → exit 0
        (``status="fixed"``). ``organ_transitive_deps`` is the LIVE derived
        list this run found under ``ORGAN_SOURCE_DIR`` (``[]`` when that dir
        doesn't exist, e.g. a synthetic test root) — see module docstring
        "Seed-organ transitive deps" for what's derived vs. what stays
        manual (``manual_only_scope``).
    """
    if repo_root is not None:
        root = repo_root
    elif worktree_path is not None:
        root = resolve_caller_root(worktree_path)
    else:
        root = REPO_ROOT

    drift, total, count, skipped_non_consumers = _audit(root)
    organ_transitive_deps = _derive_organ_transitive_deps(root)
    manual_only_scope = ["seed/framework/frontend/src (@noctusai/seed)"]

    if skipped_non_consumers:
        # Surfaced at INFO on every run, clean or not: a product silently
        # leaving a gate's scope is how a real gap hides behind a green tick.
        logger.info(
            "check_framework_deps: %d product frontend(s) do not depend on %s "
            "and are OUT of scope (not framework consumers): %s",
            len(skipped_non_consumers), _FRAMEWORK_PACKAGE,
            ", ".join(skipped_non_consumers),
        )

    if not drift:
        logger.info(
            "check_framework_deps: all %d audited product(s) list every "
            "FRAMEWORK_DEP + derived organ-transitive dep",
            count,
        )
        return {
            "products_audited": count,
            "drift": {},
            "total_missing": 0,
            "fixed": 0,
            "status": "clean",
            "exit_code": 0,
            "organ_transitive_deps": organ_transitive_deps,
            "manual_only_scope": manual_only_scope,
            "skipped_non_consumers": skipped_non_consumers,
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
            "organ_transitive_deps": organ_transitive_deps,
            "manual_only_scope": manual_only_scope,
            "skipped_non_consumers": skipped_non_consumers,
        }

    logger.warning(
        "check_framework_deps: %d missing FRAMEWORK_DEPS/organ-transitive-deps "
        "across %d product(s)",
        total, len(drift),
    )
    return {
        "products_audited": count,
        "drift": drift,
        "total_missing": total,
        "fixed": 0,
        "status": "drift",
        "exit_code": 1,
        "organ_transitive_deps": organ_transitive_deps,
        "manual_only_scope": manual_only_scope,
        "skipped_non_consumers": skipped_non_consumers,
    }


def register(server) -> None:
    """Register the framework-deps audit MCP tool."""

    @server.tool(
        name="noctus.dev.check_framework_deps",
        description=(
            "Audit that every product's frontend package.json lists every "
            "FRAMEWORK_DEP (the vite.config.factory.ts resolve.dedupe set) "
            "PLUS every package @noctusai/lib organs actually import (derived "
            "live from seed/lib/frontend/src — closes the blind spot where a "
            "newly-promoted organ's peer dep, e.g. @dnd-kit/* for KanbanBoard, "
            "escapes a hand-curated list). A missing dep makes the product's "
            "container `npm run build` fail with `Rollup failed to resolve "
            "import`. Read-only by default (status=drift + exit_code 1 on "
            "drift); fix=True borrows pinned versions from erp-imobiliario and "
            "rewrites package.json. seed/framework/frontend/src "
            "(@noctusai/seed) deps stay manual-only (see "
            "manual_only_scope in the result) — not yet scanned. Port of "
            "scripts/check-framework-deps.py. Pass worktree_path when called "
            "from inside a git worktree."
        ),
    )
    def _check_framework_deps(
        worktree_path: str | None = None,
        fix: bool = False,
    ) -> dict:
        return check_framework_deps(worktree_path=worktree_path, fix=fix)
