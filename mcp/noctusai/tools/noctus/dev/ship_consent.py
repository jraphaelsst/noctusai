"""noctus.dev.ship_consent — per-PROJECT approval to carry work to production.

Owner mandate (2026-09-22): an agent deploying to prod must NOT carry other
agents' in-flight / unapproved work. `release stage=bless` used to FF `main`
to the WHOLE `dev` tip, so every integrated commit from every agent shipped.
The approval unit is the PROJECT/ROADMAP (a branch-tree pointer's `project`,
default = the branch name); this tool records that approval, and
`noctus.dev.release stage=manifest|bless` reads it.

Actions
-------
challenge  Return the canonical sentence the USER must type. Writes nothing.
author     Append an approval row to `ship-consent.ndjson` (origin/ledgers) —
           REFUSES unless that exact sentence is found in a message the human
           actually wrote, verified against the harness-written session
           transcript (the SAME evidence layer `noctus.dev.prod_consent` uses:
           `compliance._human_authored_transcript_texts`). The agent supplies
           the project + session id; it cannot supply the evidence.
list       Per-project consent state (latest approval, revocations).
revoke     Append a revocation row. Needs no transcript evidence: withdrawing
           an approval can only ever ship LESS, never more — but it requires a
           reason, recorded verbatim.

Coverage decision (documented in KB § PATTERNS/devops/ship-consent-riders.md):
an approval covers the project's commits REACHABLE FROM the `origin/dev` sha
recorded at consent time. A commit integrated after that sha needs a fresh
approval — consent is to what the user could see, not to future work.

The ledger is append-only. Since 2026-09-24 it lives on the orphan
`origin/ledgers` branch, written by git plumbing through `_ledger_store` (never a
commit on dev; KB § PATTERNS/common/ledger-store.md). It was the LAST ledger to
move. `release` dual-reads `origin/ledgers` ∪ dev's legacy copy, so an approval
counts as soon as it is published.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from settings import LEDGER_ROOT, REPO_ROOT

from tools.noctus.dev._ledger_store import LedgerStoreError, merge_ndjson_text, open_ledger
from tools.noctus.dev.compliance import _human_authored_transcript_texts

LEDGER_REL = "project-history/ship-consent.ndjson"
LEDGER_PATH: Path = LEDGER_ROOT / LEDGER_REL   # legacy dev copy (dual-read) + the Fake's file
LEDGER_NAME = "ship-consent.ndjson"

ACTIONS = ("challenge", "author", "list", "revoke")

Runner = Callable[..., tuple[int, str, str]]


def canonical_phrase(project: str) -> str:
    """The EXACT sentence the user types to approve shipping `project`.

    Exact-match (whitespace/case-normalised) only — no intent heuristic. The
    prod_consent gate widened to a directive tier because a product's FIRST
    exposure is a one-off decision; a ship approval recurs on every release,
    so an operational "ship it" must not silently double as approval of a
    whole project's backlog. The project slug is embedded so an unrelated
    "yes, go ahead" can never be repurposed.
    """
    return f"I approve shipping project {project} to production."


def _norm(s: str) -> str:
    return " ".join(s.split()).casefold()


def _run(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(REPO_ROOT))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def find_phrase(project: str, session_id: str, home: Path | None = None) -> tuple[str | None, str]:
    """Return `(prompt_source, "")` when the canonical phrase for `project`
    appears in a HUMAN-authored message of `session_id`, else `(None, why)`.
    A missing/unreadable transcript is a refusal with its own reason — never
    read as "no consent needed"."""
    entries, detail = _human_authored_transcript_texts(session_id, home=home)
    if detail:
        return None, detail
    want = _norm(canonical_phrase(project))
    for source, text in reversed(entries):  # latest statement is operative
        if want in _norm(text):
            return source, ""
    return None, (
        f"the sentence {canonical_phrase(project)!r} was not found in any of the "
        f"{len(entries)} human-authored message(s) of session {session_id}. If the "
        "user typed it in the turn you are in, the transcript is flushed at turn "
        "end — re-run `author` next turn. Never hand-write the ledger row."
    )


def verify_row(row: dict, home: Path | None = None) -> tuple[bool, str]:
    """Re-verify an `author` row's evidence at USE time (release reads the
    ledger from git, where a hand-appended row would otherwise be trusted).
    Same shape as `_validate_prod_consent_record` re-verifying its phrase."""
    project = str(row.get("project") or "")
    session_id = str(row.get("session_id") or "")
    if not project or not session_id:
        return False, "row lacks project/session_id"
    source, why = find_phrase(project, session_id, home=home)
    return (source is not None), why


# ── ledger IO ────────────────────────────────────────────────────────────────
def parse_rows(text: str) -> list[dict]:
    rows: list[dict] = []
    for line in (text or "").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rec = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(rec, dict):
            rows.append(rec)
    return rows


def read_rows(runner: Runner | None = None, from_dev: bool = True,
              ledger_path: Path | None = None) -> list[dict]:
    """The S2 DUAL-READ: origin/ledgers (+ this clone's spooled rows) ∪ dev's
    legacy copy (``from_dev``; the local file when origin/dev is unavailable
    or ``from_dev=False``). Exact-duplicate rows collapse."""
    run = runner or _run
    path = ledger_path or LEDGER_PATH
    dev_text = None
    if from_dev:
        rc, out, _e = run(["git", "show", f"origin/dev:{LEDGER_REL}"])
        if rc == 0:
            dev_text = out
    if dev_text is None:
        dev_text = path.read_text(encoding="utf-8") if path.exists() else ""
    try:
        store_text = open_ledger(LEDGER_NAME, path).read_text()
    except LedgerStoreError as exc:
        import logging
        logging.getLogger(__name__).warning(
            "ship_consent: origin/ledgers unreadable (%s) — dev copy only", exc)
        store_text = ""
    return parse_rows(merge_ndjson_text(dev_text, store_text))


def effective_approvals(rows: list[dict], project: str) -> list[dict]:
    """Every `author` row for `project` written AFTER its latest `revoke`."""
    last_revoke = ""
    for r in rows:
        if r.get("project") == project and r.get("action") == "revoke":
            last_revoke = max(last_revoke, str(r.get("ts") or ""))
    return [r for r in rows
            if r.get("project") == project and r.get("action") == "author"
            and str(r.get("ts") or "") > last_revoke]


def _append(row: dict, ledger_path: Path, *, message: str, publish: bool) -> dict:
    """Append through `_ledger_store` (origin/ledgers). ``publish=False`` spools
    the row locally; `release` only counts it once published."""
    return open_ledger(LEDGER_NAME, ledger_path).append(
        [json.dumps(row, ensure_ascii=False)], message=message, publish=publish)


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).replace(microsecond=0).isoformat()


# ── actions ──────────────────────────────────────────────────────────────────
def _challenge(project: str) -> dict:
    phrase = canonical_phrase(project)
    return {
        "ok": True, "action": "challenge", "project": project, "phrase": phrase,
        "instructions": (
            "Ask the user to type this sentence, verbatim:\n\n    " + phrase + "\n\n"
            "Do not type it for them or paraphrase it. It approves shipping the "
            "project's commits that are on origin/dev at the moment `author` "
            "records it; later commits need a fresh approval. Then call "
            "action='author' project=<slug> session_id=<this session>."
        ),
    }


def _author(project: str, session_id: str, dev_sha: str | None, runner: Runner,
            home: Path | None, push_dev: bool, ledger_path: Path) -> dict:
    if not session_id:
        return {"ok": False, "action": "author",
                "error": "session_id is required — the row must point at the "
                         "transcript carrying the user's approval"}
    source, why = find_phrase(project, session_id, home=home)
    if source is None:
        return {"ok": False, "action": "author", "project": project,
                "error": f"REFUSED — {why}", "phrase_to_ask_for": canonical_phrase(project)}
    if not dev_sha:
        runner(["git", "fetch", "origin", "--quiet"])
        rc, out, err = runner(["git", "rev-parse", "origin/dev"])
        if rc != 0 or not out.strip():
            return {"ok": False, "action": "author",
                    "error": f"cannot resolve origin/dev: {err.strip()}"}
        dev_sha = out.strip()
    rc, email, _e = runner(["git", "config", "user.email"])
    transcripts = sorted((home or Path.home()).glob(f".claude/projects/*/{session_id}.jsonl"))
    digest = hashlib.sha256(transcripts[0].read_bytes()).hexdigest() if transcripts else ""
    row = {
        "ts": _now(), "action": "author", "project": project, "dev_sha": dev_sha,
        "phrase": canonical_phrase(project), "prompt_source": source,
        "session_id": session_id, "transcript_sha256": digest,
        "consented_by": email.strip() if rc == 0 else "", "recorded_by": "agent",
    }
    push = _append(row, ledger_path, publish=push_dev,
                   message=f"ship-consent approve {project} @ {dev_sha[:9]}")
    return {"ok": True, "action": "author", "row": row,
            "ledger_path": f"origin/ledgers:{LEDGER_NAME}",
            "covers": f"{project} commits reachable from {dev_sha[:9]}",
            "push": push}


def _revoke(project: str, reason: str, runner: Runner, push_dev: bool,
            ledger_path: Path) -> dict:
    if not reason or not reason.strip():
        return {"ok": False, "action": "revoke", "error": "reason is required"}
    row = {"ts": _now(), "action": "revoke", "project": project,
           "reason": reason.strip(), "recorded_by": "agent"}
    push = _append(row, ledger_path, publish=push_dev, message=f"ship-consent revoke {project}")
    return {"ok": True, "action": "revoke", "row": row, "push": push}


def _list(rows: list[dict], project: str | None) -> dict:
    projects = sorted({str(r.get("project")) for r in rows if r.get("project")})
    if project:
        projects = [p for p in projects if p == project]
    out = []
    for p in projects:
        live = effective_approvals(rows, p)
        latest = max(live, key=lambda r: r.get("ts", "")) if live else None
        revoked = any(r.get("project") == p and r.get("action") == "revoke" for r in rows)
        out.append({
            "project": p,
            "state": "approved" if latest else ("revoked" if revoked else "none"),
            "dev_sha": latest.get("dev_sha") if latest else None,
            "approved_at": latest.get("ts") if latest else None,
            "approvals_live": len(live),
        })
    return {"ok": True, "action": "list", "projects": out}


def ship_consent(
    action: str = "list",
    project: str | None = None,
    session_id: str | None = None,
    dev_sha: str | None = None,
    reason: str | None = None,
    push_dev: bool = True,
    runner: Runner | None = None,
    home: Path | None = None,
    ledger_path: Path | None = None,
) -> dict:
    run = runner or _run
    path = ledger_path or LEDGER_PATH
    if action not in ACTIONS:
        return {"ok": False, "action": action,
                "error": f"unknown action {action!r} — expected one of {', '.join(ACTIONS)}"}
    if action == "list":
        return _list(read_rows(run, from_dev=True, ledger_path=path), (project or "").strip() or None)
    project = (project or "").strip()
    if not project:
        return {"ok": False, "action": action, "error": "project is required"}
    if action == "challenge":
        return _challenge(project)
    if action == "author":
        return _author(project, (session_id or "").strip(), (dev_sha or "").strip() or None,
                       run, home, push_dev, path)
    return _revoke(project, reason or "", run, push_dev, path)


def register(server) -> None:
    @server.tool(
        name="noctus.dev.ship_consent",
        description=(
            "Per-PROJECT approval to ship to production (owner mandate 2026-09-22: "
            "a prod deploy must never carry another agent's unapproved work). "
            "action='challenge' project=<slug> returns the canonical sentence the "
            "USER must type; action='author' project=<slug> session_id=<id> appends "
            "an approval to ship-consent.ndjson (on the orphan origin/ledgers branch, "
            "plumbing-written — never a dev commit, 2026-09-24) ONLY when that "
            "sentence is verified in a human-authored message of the session "
            "transcript (same evidence layer as noctus.dev.prod_consent) — else "
            "REFUSES; the approval covers the project's commits reachable from the "
            "origin/dev sha at consent time (later commits need re-approval). "
            "action='list' shows per-project state; action='revoke' reason=<why> "
            "withdraws. Project = branch-tree pointer `project` (default: branch "
            "name). Consumed by noctus.dev.release stage=manifest|bless. "
            "KB § PATTERNS/devops/ship-consent-riders.md."
        ),
    )
    def _ship_consent(
        action: str = "list",
        project: str = "",
        session_id: str = "",
        dev_sha: str = "",
        reason: str = "",
        push_dev: bool = True,
    ) -> dict:
        return ship_consent(action=action, project=project or None,
                            session_id=session_id or None, dev_sha=dev_sha or None,
                            reason=reason or None, push_dev=push_dev)


__all__ = ["ship_consent", "canonical_phrase", "verify_row", "effective_approvals",
           "parse_rows", "read_rows", "register", "LEDGER_REL"]
