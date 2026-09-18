"""noctus.dev's catalog-scope guard — shared by `deploy_image` + `migrate_product`.

THE INCIDENT (2026-09-17, real, in production). A prod deploy ran
`noctus.dev.deploy_image product='erp-imobiliario' confirm=True` and then
applied migrations to `erp`. `erp-imobiliario` is `ativo=false,
deploy_scope='dev'` in the product catalog — CLAUDE.md §1 is explicit:
"The product catalog IS the working guide — ativo+live ⇒ work in prod,
ativo+dev ⇒ dev only, inativo ⇒ don't touch"
(`KB § PATTERNS/architect/product-working-scope.md`). `deploy_image`
reported `status: "deployed"`, healthy, swap-verified — because none of
its existing gates (snapshot-verify, PROD-PIN ancestry, swap-verify) ask
"should this product be touched at all?", only "did the touch land
cleanly?". The mistake surfaced only afterwards, when
`noctus.dev.deploy_verify` classified `erp` as `skipped_inactive` — a
rule `deploy_verify` and `predeploy_check` already honour that the actual
deploy/migrate ACTIONS did not.

This module is that missing gate, factored out once and shared by both
actions rather than re-derived per-tool (§1: grep for the existing
mechanism before designing one). It does NOT re-read the catalog itself —
it composes `deploy_verify._resolve_live_products` (the SAME
`ativo=true AND deploy_scope='live'` + `core` roster
`noctus.dev.deploy_verify` and `noctus.dev.refresh_build_scope` already
resolve, with the SAME live-catalog → `deploy/fleet/build-scope.txt`
fallback → `unavailable` chain), so there is exactly one catalog-roster
resolution in the codebase, not two drifting ones.

FAIL-CLOSED, BY CONSTRUCTION. When the catalog is unreachable AND the
checked-in `build-scope.txt` fallback is unavailable too,
`_resolve_live_products` returns `live=None` ("unavailable"). This module
treats that the same as "not in scope" — `in_scope=False`. A caller that
"cannot tell" whether a product is live must never be treated as "may
proceed" (CLAUDE.md §1, no silent errors): the exact failure mode this
guard exists to close is a confident-looking green over information the
tool never actually had.

Each action (`deploy_image`, `migrate_product`) calls `check_catalog_scope`
and, if `in_scope` is False, refuses BEFORE doing anything else —
`status='refused_catalog_scope'`, `exit_code=1`, and the resolved
`catalog_scope` verdict riding on the returned payload EVERY time (never
only on the refusal path — same convention `migrate_product`'s
`stale_tree` key already established for the 2026-09-17 stale-tree
refusal). The documented escape hatch is `allow_inactive: bool = False`
on both tools (same shape as `deploy_image`'s own `skip_ancestry_check`
and `migrate_product`'s own `allow_stale_tree`) — legitimate for a
deliberate, supervised reactivation of a dormant product, never for
routing around the gate out of impatience; using it still leaves
`catalog_scope`/`allow_inactive` visible on the result, so a bypass is
never silent either.

THE STALE-GHCR CASE — no new code needed here, and deliberately none
added. The incident also noted `erp-imobiliario`'s `:latest` was built
from an older revision (`2b1ffcd1`), because `build-scope.txt` derives
from `deploy_scope='live'`, so an inactive product's image is BY
CONSTRUCTION never rebuilt at the prod tip. `deploy_image`'s existing
PROD-PIN ancestry guard (`_prod_ancestor_check`) does not — and must
not — turn this into a blanket "baked revision must equal the prod
tip" check: staleness relative to the prod tip is the DOCUMENTED NORMAL
steady state for a genuinely `ativo+live` product too (a product's own
image only rebuilds when ITS OWN files, or `seed/`, changed —
`build-and-push.yml`'s changed-only scoping; see `deploy_verify.py`'s own
"raw sha inequality is the WRONG drift predicate" reasoning). Asserting
equality-with-tip would refuse ordinary, healthy re-deploys of live
products that simply haven't changed since the last prod promote. The
catalog-scope guard here closes the actual hole: an `inativo`/`dev`-scope
product can no longer reach the deploy path AT ALL, so its permanently
un-rebuilt image can never be pulled onto prod in the first place — the
ancestry guard's existing, narrower "not ahead of prod" scope stays
correct and sufficient for every product that IS allowed to deploy.

KB § PATTERNS/architect/product-working-scope.md ·
KB § PATTERNS/devops/prod-deploy-safety-gates.md
"""
from __future__ import annotations

from typing import Any, Callable

from . import deploy_verify as _deploy_verify

#: Shared status key both `deploy_image` and `migrate_product` return on
#: refusal — same naming convention as `migrate_product`'s existing
#: `'refused_stale_tree'`.
REFUSED_STATUS = "refused_catalog_scope"


def check_catalog_scope(
    product: str,
    live_products_fn: Callable[[], list[str]] | None = None,
) -> dict[str, Any]:
    """Resolve whether `product` is `ativo=true AND deploy_scope='live'`
    (or `core`, the one documented non-catalog member) — by delegating to
    `deploy_verify._resolve_live_products`, never a second hand-rolled
    catalog query. `live_products_fn` is the same injection seam
    `deploy_verify` exposes (test-only; the real default resolves against
    the live Supabase catalog, falling back to the checked-in
    `deploy/fleet/build-scope.txt` snapshot).

    Returns::

        {
            "in_scope": bool,
            "live_products": list[str] | None,   # sorted, or None if unresolvable
            "catalog_source": "live_catalog" | "build_scope_fallback" | "unavailable",
            "catalog_warning": str | None,
            "detail": str,   # human-readable, no tool-specific remedy text
                              # (the caller composes the full refusal message)
        }

    Fail-closed: `catalog_source == 'unavailable'` (neither the live
    catalog nor the fallback file could be read) resolves `in_scope=False`
    — "cannot tell" is never "allowed".
    """
    live, source, warning = _deploy_verify._resolve_live_products(live_products_fn)
    if live is None:
        return {
            "in_scope": False,
            "live_products": None,
            "catalog_source": source,
            "catalog_warning": warning,
            "detail": (
                f"catalog scope for {product!r} is UNVERIFIABLE ({warning}) — "
                "treated as NOT in scope (fail-closed: an unanswerable question "
                "is never silently 'yes')."
            ),
        }
    in_scope = product in live
    return {
        "in_scope": in_scope,
        "live_products": sorted(live),
        "catalog_source": source,
        "catalog_warning": warning,
        "detail": (
            f"{product!r} is {'in' if in_scope else 'NOT in'} the catalog's live "
            f"set (ativo=true AND deploy_scope='live', plus core) — "
            f"catalog_source={source}."
        ),
    }


def catalog_scope_refusal_reason(
    product: str,
    catalog_scope: dict[str, Any],
    *,
    action: str,
    escape_hatch: str,
    untouched_clause: str,
) -> str:
    """The shared refusal-message body — same wording shape from both
    `deploy_image` and `migrate_product`, differing only in the verb
    (`action`), the escape-hatch kwarg name (`escape_hatch`), and what
    exactly stayed untouched (`untouched_clause`)."""
    return (
        f"CATALOG-SCOPE GUARD: refusing to {action} {product!r} — "
        f"{catalog_scope['detail']} The product catalog IS the working guide "
        "(CLAUDE.md §1 · KB § PATTERNS/architect/product-working-scope.md): "
        "ativo=true AND deploy_scope='live' is the only combination that means "
        "'work in prod' — anything else means don't touch it here. This is the "
        "2026-09-17 incident: erp-imobiliario (ativo=false, deploy_scope='dev') "
        f"was deployed to prod anyway. {untouched_clause} If you are "
        "deliberately waking a dormant product (a supervised reactivation — "
        f"never a routine {action}), pass {escape_hatch}=True; see the tool's "
        "docstring — this is almost always wrong."
    )


__all__ = ["check_catalog_scope", "catalog_scope_refusal_reason", "REFUSED_STATUS"]
