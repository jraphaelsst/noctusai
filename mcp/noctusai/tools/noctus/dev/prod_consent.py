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
    _find_authorization_evidence,
    _PROD_COMPOSE_REL,
    _PROD_CONSENT_DIR_REL,
    _PROD_INGRESS_REL,
    _canonical_authorization_phrase,
    _git_author_email,
    _prod_exposure_declared_and_baseline,
    _validate_prod_consent_record,
    _verify_authorization_phrase,
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


# `consent_ref` is SINGLE-QUOTED on purpose. A roadmap anchor is normally a
# milestone label like `M5: prod promote`, so the value carries a `: ` — and
# an unquoted YAML scalar containing `: ` is a ScannerError ("mapping values
# are not allowed here"), not a string. The template shipped unquoted from
# introduction (2026-07-20) through 2026-08-09, so every record authored
# faithfully from it failed `_validate_prod_consent_record` at the PARSE
# step — a false negative that reads to the author as "the gate rejected my
# consent" rather than "your YAML is malformed". Quoting is the whole fix;
# it changes nothing about WHO may author the record.
_TEMPLATE = (
    "consented_by: <the user's git-config user.email — REQUIRED>\n"
    "consented_on: <YYYY-MM-DD>\n"
    "consent_ref: '<path/to/roadmap.md>#<milestone text, ALSO marked ✅ on that same line>'\n"
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


def _challenge(slug: str) -> dict:
    """Hand back the exact sentence to ask the user for. Writes nothing."""
    if not slug or not slug.strip():
        return {"ok": False, "action": "challenge", "error": "slug is required"}
    slug = slug.strip()
    phrase = _canonical_authorization_phrase(slug)
    return {
        "ok": True,
        "action": "challenge",
        "slug": slug,
        "phrase": phrase,
        "instructions": (
            f"Ask the user to type this sentence, verbatim, in the "
            f"conversation:\n\n    {phrase}\n\n"
            "Do NOT type it on their behalf, and do not paraphrase when "
            "asking — the gate matches this exact sentence against the "
            "session transcript, which the harness writes and the agent "
            "does not. Once the user has typed it, call action='author' "
            "with the session_id to write the record."
        ),
    }


def _author(
    slug: str,
    session_id: str,
    consent_ref: str,
    repo_root: str | None,
    worktree_path: str | None,
) -> dict:
    """Write `deploy/consent/<slug>.prod.yml` — but ONLY as a transcription
    of a verified in-session authorization.

    Refuses unless the canonical phrase is found in a message the USER
    actually typed. The agent supplies the slug and the session id; it
    cannot supply the evidence.
    """
    import datetime as _dt
    import hashlib
    import json

    if not slug or not slug.strip():
        return {"ok": False, "action": "author", "error": "slug is required"}
    slug = slug.strip()
    if not session_id or not session_id.strip():
        return {
            "ok": False,
            "action": "author",
            "error": (
                "session_id is required — the record must point at the "
                "transcript that carries the user's authorization"
            ),
        }
    session_id = session_id.strip()
    if not consent_ref or not consent_ref.strip():
        return {
            "ok": False,
            "action": "author",
            "error": "consent_ref is required (<roadmap path>#<✅ milestone>)",
        }

    evidence = _find_authorization_evidence(slug, session_id)
    if evidence is None:
        ok, reason = _verify_authorization_phrase(slug, {
            "phrase": _canonical_authorization_phrase(slug),
            "session_id": session_id,
        })
        reason = reason or "no authorizing message found"
        return {
            "ok": False,
            "action": "author",
            "slug": slug,
            "error": f"REFUSED — {reason}",
            "phrase_to_ask_for": _canonical_authorization_phrase(slug),
        }
    evidence_source, evidence_text = evidence

    root = _resolve_root(repo_root, worktree_path)
    email = _git_author_email(root) or ""
    if not email:
        return {
            "ok": False,
            "action": "author",
            "error": "could not resolve git user.email — consented_by would be empty",
        }

    transcripts = sorted(Path.home().glob(f".claude/projects/*/{session_id}.jsonl"))
    digest = hashlib.sha256(transcripts[0].read_bytes()).hexdigest() if transcripts else ""
    today = _dt.date.today().isoformat()
    now = _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()

    # consent_ref is single-quoted: a milestone anchor carries ": ", which
    # is a YAML parse error unquoted (the false negative fixed 2026-08-09).
    body = (
        f"consented_by: {email}\n"
        f"consented_on: {today}\n"
        f"consent_ref: '{consent_ref.strip()}'\n"
        f"dev_validated: true\n"
        f"recorded_by: agent\n"
        f"authorization:\n"
        # The user's OWN words, verbatim — not the agent's restatement.
        f"  phrase: {json.dumps(evidence_text)}\n"
        f"  prompt_source: {evidence_source}\n"
        f"  session_id: {session_id}\n"
        f"  transcript_sha256: {digest}\n"
        f"  recorded_at: {now}\n"
    )
    target_rel = f"{_PROD_CONSENT_DIR_REL}/{slug}.prod.yml"
    target = root / target_rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return {
        "ok": True,
        "action": "author",
        "slug": slug,
        "target_path": target_rel,
        "content": body,
        "next_step": (
            f"Commit {target_rel} ALONE (no other path staged) — the gate "
            "refuses a mixed diff — then register the slug on the three "
            "prod-exposure surfaces in a following commit."
        ),
    }


def prod_consent(
    action: str = "status",
    slug: str | None = None,
    session_id: str | None = None,
    consent_ref: str | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict:
    """`action='status'` — per-product consent dashboard for every slug
    currently declared on the three prod-exposure surfaces (honest
    `missing_pregate` for grandfathered products, never silently hidden).
    `action='request'` — REFUSES to write the record; returns the YAML
    template for the USER to author by hand. `action='challenge'` — returns
    the canonical sentence to ask the user to type. `action='author'` —
    writes the record ONLY when that sentence is verified against the
    harness-written session transcript; refuses otherwise.
    KB § PATTERNS/devops/prod-exposure-consent.md.
    """
    if action == "status":
        return _status(repo_root, worktree_path)
    if action == "request":
        return _request(slug or "", repo_root, worktree_path)
    if action == "challenge":
        return _challenge(slug or "")
    if action == "author":
        return _author(
            slug or "", session_id or "", consent_ref or "", repo_root, worktree_path
        )
    return {
        "ok": False,
        "action": action,
        "error": (
            f"unknown action {action!r} — expected 'status', 'request', "
            "'challenge' or 'author'"
        ),
    }


# ── MCP registration ──────────────────────────────────────────────────────


def register(server) -> None:
    @server.tool(
        name="noctus.dev.prod_consent",
        description=(
            "Prod-exposure consent — sibling of the "
            "check_prod_exposure_consent gate. action='status' returns an "
            "honest per-product dashboard (valid / invalid / "
            "missing_pregate — grandfathered products report honestly, "
            "never silently hidden). action='request' slug=<slug> refuses "
            "to write anything and returns the YAML template for the USER "
            "to hand-author. action='challenge' slug=<slug> returns the "
            "canonical sentence the user must TYPE to authorize prod "
            "exposure. action='author' slug=<slug> session_id=<id> "
            "consent_ref=<roadmap#milestone> writes the record ONLY when "
            "that sentence is found in a message the user actually typed, "
            "verified against the harness-written session transcript — "
            "otherwise it REFUSES. An agent may RECORD the user's "
            "decision; it must never invent one. "
            "KB § PATTERNS/devops/prod-exposure-consent.md."
        ),
    )
    def _prod_consent(
        action: str = "status",
        slug: str = "",
        session_id: str = "",
        consent_ref: str = "",
        worktree_path: str = "",
    ) -> dict:
        return prod_consent(
            action=action,
            slug=slug or None,
            session_id=session_id or None,
            consent_ref=consent_ref or None,
            worktree_path=worktree_path or None,
        )


__all__ = ["prod_consent", "register"]
