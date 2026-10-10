"""`settle_scope_artifacts` — ONE function that makes every artifact DERIVED from
the product scope match it. The scope bot and humans both call this.

WHY (2026-10-10). `sync-product-scope.yml` flipped `active-scope.txt` /
`build-scope.txt` and committed only those two. Every artifact derived from the
scope (Dependabot npm blocks, CI matrices, propagated composes/Dockerfiles) was
left stale, so each owner deactivation turned dev CI red (community / store /
orbity / p-studio sleeps, run 38050340426). A derived list must be regenerated
by the same step that changes its source — in the same commit.

Artifacts settled (each is the regenerator of a `check_*` keeper fed by scope):
  build-scope.txt, active-scope.txt     refresh_build_scope + refresh_active_scope
  .github/dependabot.yml                sync_dependabot_coverage  (check_dependabot_product_coverage)
  .github/workflows/test.yml matrices   sync_ci_matrix_coverage   (check_ci_test_matrix_coverage)
  products/<slug>/docker-compose.yml +
  products/<slug>/backend/Dockerfile    propagate (--propagate --check keeper)

Not scope-derived (deliberately absent): the tunnel ingress snapshot follows
prod-exposure consent, not `ativo`.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT

#: Repo-relative files the settle may touch — the bot `git add`s exactly these.
SETTLED_FILES = (
    "deploy/fleet/active-scope.txt",
    "deploy/fleet/build-scope.txt",
    ".github/dependabot.yml",
    ".github/workflows/test.yml",
)
#: Generated per active product; staged by glob.
SETTLED_GLOBS = ("products/*/docker-compose.yml", "products/*/backend/Dockerfile")


def settle_scope_artifacts(
    root: Path | None = None,
    write: bool = True,
    *,
    live: list[str] | None = None,
    active: list[str] | None = None,
) -> dict:
    """Regenerate scope files then every derived artifact. `live` / `active` are
    the catalog sets (None ⇒ read the catalog; the bot passes its payload)."""
    from .build_scope import refresh_build_scope
    from .ci_matrix_sync import sync_ci_matrix_coverage
    from .dependabot_sync import sync_dependabot_coverage
    from .product_scope import read_active_scope, refresh_active_scope
    from .propagate import propagate_composes, propagate_dockerfiles

    base = root if root is not None else REPO_ROOT
    before = read_active_scope(base) or []
    steps: dict[str, dict] = {}

    steps["build_scope"] = refresh_build_scope(write=write, _live=live, root=root)
    steps["active_scope"] = refresh_active_scope(write=write, _active=active, root=root)
    for name, res in steps.items():
        if not res.get("ok"):
            return {"ok": False, "failed": name, "error": res.get("error"), "steps": steps}

    after = steps["active_scope"]["slugs"]
    # Derived artifacts read the scope FILE just written; in a dry run they would
    # read the old one, so only run them when the file is real.
    if write:
        steps["dependabot"] = sync_dependabot_coverage(root=root, write=True)
        steps["ci_matrix"] = sync_ci_matrix_coverage(root=root, write=True)
        steps["composes"] = propagate_composes(repo_root=str(base))
        steps["dockerfiles"] = propagate_dockerfiles(repo_root=str(base))
    for name in ("dependabot", "ci_matrix", "composes", "dockerfiles"):
        if name in steps and not steps[name].get("ok"):
            return {"ok": False, "failed": name, "error": steps[name].get("error"), "steps": steps}

    return {
        "ok": True,
        "woke": sorted(set(after) - set(before)),
        "slept": sorted(set(before) - set(after)),
        "slugs": after,
        "steps": steps,
    }
