"""noctus.dev.prod_consent — status dashboard + refuse-not-null template
generator for the prod-exposure consent gate.

Sibling of `check_prod_exposure_consent` (`tools.noctus.dev.compliance`) —
that keeper is the BLOCKING half (fires on a product's first arrival on a
prod-exposure surface without a valid `deploy/consent/<slug>.prod.yml`);
this tool is the OBSERVE + AUTHOR-ASSIST half:

  - `action="status"` — an honest per-product consent dashboard: for every
    slug currently declared on the three prod-exposure surfaces (compose /
    ingress / ALL_SLUGS), report whether a valid `deploy/consent/<slug>.
    prod.yml` exists in HEAD. Products registered BEFORE the gate existed
    report `"missing_pregate"` (grandfathered honestly — not an error, not
    silently hidden).

  - `action="request"` — REFUSES to write the consent file (refuse-not-
    null, per `KB § PATTERNS/common/gate-methodology-sync.md`) and instead
    returns the exact YAML template text for the USER to author, in its
    own isolated commit. An agent calling this tool never produces a
    consent record — it can only ever hand back instructions.

KB § PATTERNS/devops/prod-exposure-consent.md.
"""
from __future__ import annotations

from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

from .compliance import (
    _PROD_BUILD_PUSH_REL,
    _PROD_COMPOSE_REL,
    _PROD_CONSENT_DIR_REL,
    _PROD_INGRESS_REL,
    _prod_exposure_declared_and_baseline,
    _validate_prod_consent_record,
)


def _resolve_root(repo_root: str | None, worktree_path: str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    if worktree_path:
        return Path(resolve_caller_root(worktree_path))
    return Path(REPO_ROOT)


def _status_row(slug: str, root: Path) -> dict:
    result = _validate_prod_consent_record(slug, root)
    consent_rel = f"{_PROD_CONSENT_DIR_REL}/{slug}.prod.yml"
    if result["status"] == "valid":
        data = result["data"] or {}
        return {
            "slug": slug,
            "consent_status": "valid",
            "consent_file": consent_rel,
            "consented_by": data.get("consented_by"),
            "consented_on": data.get("consented_on"),
            "consent_ref": data.get("consent_ref"),
            "detail": "",
        }
    if result["status"] == "missing":
        return {
            "slug": slug,
            "consent_status": "missing_pregate",
            "consent_file": consent_rel,
            "consented_by": None,
            "consented_on": None,
            "consent_ref": None,
            "detail": (
                "no consent record on file (pre-gate) — this product was "
                "registered before check_prod_exposure_consent existed, so "
                "the gate never required one at introduction time. Not an "
                "error; not backfilled automatically (see prod-exposure-"
                "consent.md § scope decisions)."
            ),
        }
    return {
        "slug": slug,
        "consent_status": "invalid",
        "consent_file": consent_rel,
        "consented_by": (result["data"] or {}).get("consented_by") if result["data"] else None,
        "consented_on": (result["data"] or {}).get("consented_on") if result["data"] else None,
        "consent_ref": (result["data"] or {}).get("consent_ref") if result["data"] else None,
        "detail": result["detail"],
    }


def _status(repo_root: str | None, worktree_path: str | None) -> dict:
    root = _resolve_root(repo_root, worktree_path)
    if not (root / "deploy").is_dir():
        return {
            "ok": True,
            "action": "status",
            "products": [],
            "note": "no deploy/ directory in this tree — not a noc checkout",
        }
    declared, _baseline = _prod_exposure_declared_and_baseline(root)
    products = [_status_row(slug, root) for slug in sorted(declared)]
    return {"ok": True, "action": "status", "products": products, "note": None}


_TEMPLATE = (
    "consented_by: <the user's git-config user.email — REQUIRED>\n"
    "consented_on: <YYYY-MM-DD>\n"
    "consent_ref: <path/to/roadmap.md>#<milestone text, ALSO marked ✅ on that same line>\n"
    "dev_validated: true\n"
)


def _request(slug: str, repo_root: str | None, worktree_path: str | None) -> dict:
    if not slug or not slug.strip():
        return {
            "ok": False,
            "action": "request",
            "error": "slug is required",
        }
    slug = slug.strip()
    root = _resolve_root(repo_root, worktree_path)
    target_rel = f"{_PROD_CONSENT_DIR_REL}/{slug}.prod.yml"
    already_exists = (root / target_rel).exists()
    instructions = (
        f"Registering '{slug}' on a prod-exposure surface "
        f"({_PROD_COMPOSE_REL} / {_PROD_INGRESS_REL} / ALL_SLUGS in "
        f"{_PROD_BUILD_PUSH_REL}) IS the production-promotion decision — "
        "the fleet runs :latest, rebuilt from main on every bless→promote "
        "push, so there is NO LATER GATE that reconsiders whether this "
        "product should be public.\n\n"
        f"To authorize it, the USER (not an agent) creates {target_rel} "
        "with the fields below, committed in its OWN isolated commit (no "
        "other path staged alongside it — the pre-commit gate refuses a "
        "mixed diff), BEFORE the commit that registers the slug on the "
        "three surfaces.\n\n"
        "An agent MUST NOT create the consent record on the user's "
        "behalf. KB § PATTERNS/devops/prod-exposure-consent.md."
    )
    return {
        "ok": False,  # refuse-not-null: this action never produces the record
        "action": "request",
        "slug": slug,
        "target_path": target_rel,
        "already_exists": already_exists,
        "template_yaml": _TEMPLATE,
        "instructions": instructions,
    }


def prod_consent(
    action: str = "status",
    slug: str | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict:
    """`action='status'` — per-product consent dashboard for every slug
    currently declared on the three prod-exposure surfaces (honest
    `missing_pregate` for grandfathered products, never silently hidden).
    `action='request'` — REFUSES to write `deploy/consent/<slug>.prod.yml`;
    returns the exact YAML template + instructions for the USER to author
    it themselves, in an isolated commit. KB § PATTERNS/devops/
    prod-exposure-consent.md.
    """
    if action == "status":
        return _status(repo_root, worktree_path)
    if action == "request":
        return _request(slug or "", repo_root, worktree_path)
    return {
        "ok": False,
        "action": action,
        "error": f"unknown action {action!r} — expected 'status' or 'request'",
    }


# ── MCP registration ──────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.prod_consent",
        description=(
            "Prod-exposure consent status + refuse-not-null template "
            "generator — sibling of the check_prod_exposure_consent gate. "
            "action='status' returns an honest per-product consent "
            "dashboard (valid / invalid / missing_pregate — grandfathered "
            "products report honestly, never silently hidden). "
            "action='request' slug=<slug> NEVER writes the consent file — "
            "it refuses and returns the exact deploy/consent/<slug>.prod."
            "yml YAML template + instructions for the USER to author it "
            "themselves, in an isolated commit. An agent MUST NOT create "
            "the consent record on the user's behalf. "
            "KB § PATTERNS/devops/prod-exposure-consent.md."
        ),
    )
    def _prod_consent(
        action: str = "status",
        slug: str = "",
        worktree_path: str = "",
    ) -> dict:
        return prod_consent(
            action=action,
            slug=slug or None,
            worktree_path=worktree_path or None,
        )


__all__ = ["prod_consent", "register"]
