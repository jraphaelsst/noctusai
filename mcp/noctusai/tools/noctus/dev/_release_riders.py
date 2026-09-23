"""Rider manifest + release cut + backmerge — the ship-consent half of
`noctus.dev.release` (KB § PATTERNS/devops/ship-consent-riders.md).

Pure functions over an injected `git(*args, stdin=None, env_extra=None)`
callable (release.py's allowlisted `_git`), so every path is testable against
a real temp repo AND a scripted fake.

Vocabulary
----------
rider       a non-merge commit in `main..dev` — something a bless would ship.
exempt      a rider that ships nothing executable (the SAME `_is_docs_only`
            classifier bless already uses for its CI exception): docs +
            `project-history/` + `docs/`. Needs no approval.
approved    a rider whose PROJECT holds a verified ship-consent covering it
            (commit reachable from the consent's recorded dev sha).
on_main     `git cherry` says an equivalent patch is already on main (a prior
            cut) — skipped, never re-picked.
unapproved  attributed to a project with no covering consent.
unattributed  no `Noc-Branch:` trailer and no branch-tree evidence — treated
            as UNAPPROVED (refuse-not-null: "I could not tell whose it is" is
            not "it's approved").
"""
from __future__ import annotations

from typing import Any, Callable

GitFn = Callable[..., tuple[int, str, str]]

TRAILER = "Noc-Branch"
PICKED_MARK = "(cherry picked from commit "
_REC, _FLD = "\x1e", "\x1f"

#: Append-only, `merge=union` ledgers — every agent appends to them, so a
#: "last touched by an unapproved rider" edge on these paths is not a code
#: dependency (merge-tree replays them conflict-free by the union driver).
_DEPENDENCY_EXEMPT_PREFIXES = ("project-history/",)


def is_docs_only(paths: list[str]) -> bool:
    """bless's ONE sanctioned non-executable classifier (skill `noc-ship` step
    0b). Empty is NOT docs-only — an unreadable diff must not buy a pass."""
    return bool(paths) and all(
        p.endswith(".md") or p.startswith(("project-history/", "docs/"))
        for p in paths
    )


# ── reading ──────────────────────────────────────────────────────────────────
def list_riders(git: GitFn, base: str, tip: str) -> tuple[list[dict], str]:
    """Non-merge commits `base..tip`, oldest first, with subject, Noc-Branch
    trailer and changed files — ONE `git log` call. Returns (riders, error)."""
    fmt = (f"--format={_REC}%H{_FLD}%s{_FLD}"
           f"%(trailers:key={TRAILER},valueonly,separator=%x2C)")
    rc, out, err = git("log", "--reverse", "--topo-order", "--no-merges",
                       fmt, "--name-only", f"{base}..{tip}")
    if rc != 0:
        return [], f"git log {base}..{tip} failed: {err.strip() or out.strip()}"
    riders: list[dict] = []
    for rec in out.split(_REC):
        if not rec.strip():
            continue
        head, _, rest = rec.partition("\n")
        parts = head.split(_FLD)
        if len(parts) < 3:
            continue
        sha, subject, trailer = parts[0].strip(), parts[1], parts[2].strip()
        files = [ln.strip() for ln in rest.splitlines() if ln.strip()]
        riders.append({"sha": sha, "subject": subject,
                       "trailer_branch": trailer.split(",")[0].strip() or None,
                       "files": files})
    return riders, ""


def already_on_main(git: GitFn, main: str, dev: str) -> tuple[set[str], str]:
    """`git cherry main dev` — `-` lines are commits whose patch-id already
    exists on main (a previous cut). Full shas. A failed probe is an ERROR,
    never "nothing is on main" (that would re-pick shipped work)."""
    rc, out, err = git("cherry", main, dev)
    if rc != 0:
        return set(), f"git cherry {main[:9]} {dev[:9]} failed: {err.strip() or out.strip()}"
    return {ln[2:].strip() for ln in out.splitlines() if ln.startswith("- ")}, ""


def reachable(git: GitFn, base: str, tip: str) -> set[str] | None:
    """Commits in `base..tip`, or None when `tip` does not resolve."""
    rc, out, _e = git("rev-list", f"{base}..{tip}")
    if rc != 0:
        return None
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def reachable_no_merges(git: GitFn, base: str, tip: str) -> set[str] | None:
    rc, out, _e = git("rev-list", "--no-merges", f"{base}..{tip}")
    if rc != 0:
        return None
    return {ln.strip() for ln in out.splitlines() if ln.strip()}


def _patch_ids(git: GitFn, shas: list[str]) -> dict[str, str]:
    """sha → stable patch-id, only for shas that exist locally."""
    if not shas:
        return {}
    rc, out, _e = git("cat-file", "--batch-check", stdin="\n".join(shas) + "\n")
    present = [ln.split()[0] for ln in out.splitlines()
               if rc == 0 and ln.strip() and not ln.rstrip().endswith("missing")]
    if not present:
        return {}
    rc, patches, _e = git("log", "-p", "--no-walk=unsorted", "--format=commit %H", *present)
    if rc != 0 or not patches.strip():
        return {}
    rc, out, _e = git("patch-id", "--stable", stdin=patches)
    if rc != 0:
        return {}
    ids: dict[str, str] = {}
    for ln in out.splitlines():
        bits = ln.split()
        if len(bits) == 2:
            ids[bits[1]] = bits[0]
    return ids


# ── attribution ──────────────────────────────────────────────────────────────
def attribute(git: GitFn, riders: list[dict], pointer_rows: list[dict]) -> None:
    """Fill `branch` + `attribution` on each rider, in place.

    Order: Noc-Branch trailer → branch-tree pointer `commit` (sha prefix) →
    pointer `notes` == subject (the pointer protocol writes the commit
    subject there) → patch-id against pointer commits → unattributed.
    """
    by_commit: list[tuple[str, str]] = []
    by_subject: dict[str, set[str]] = {}
    for row in pointer_rows:
        br = str(row.get("branch") or "")
        c = str(row.get("commit") or "").strip().lower()
        if br and len(c) >= 7:
            by_commit.append((c, br))
        note = str(row.get("notes") or "").strip()
        if br and note:
            by_subject.setdefault(note, set()).add(br)

    pending: list[dict] = []
    for r in riders:
        if r.get("trailer_branch"):
            r["branch"], r["attribution"] = r["trailer_branch"], "trailer"
            continue
        hit = next((br for c, br in by_commit if r["sha"].lower().startswith(c)), None)
        if hit:
            r["branch"], r["attribution"] = hit, "pointer-commit"
            continue
        subj = by_subject.get(r["subject"].strip())
        if subj and len(subj) == 1:
            r["branch"], r["attribution"] = next(iter(subj)), "pointer-subject"
            continue
        r["branch"], r["attribution"] = None, "none"
        pending.append(r)

    if pending and by_commit:
        ids = _patch_ids(git, sorted({c for c, _b in by_commit}) + [r["sha"] for r in pending])
        pid_to_branch: dict[str, str] = {}
        for c, br in by_commit:
            full = next((s for s in ids if s.startswith(c)), None)
            if full:
                pid_to_branch.setdefault(ids[full], br)
        for r in pending:
            br = pid_to_branch.get(ids.get(r["sha"], ""))
            if br:
                r["branch"], r["attribution"] = br, "patch-id"


# ── the manifest ─────────────────────────────────────────────────────────────
def build_manifest(
    git: GitFn,
    main: str,
    dev: str,
    consent_rows: list[dict],
    pointer_rows: list[dict],
    verify: Callable[[dict], tuple[bool, str]],
    project_for_branch: Callable[[str, list[dict]], str],
    effective_approvals: Callable[[list[dict], str], list[dict]],
) -> dict[str, Any]:
    """Group every rider `main..dev` by branch → project → consent state and
    compute the ship set a cut would carry. Read-only."""
    riders, err = list_riders(git, main, dev)
    if err:
        return {"ok": False, "error": err}
    listed = reachable_no_merges(git, main, dev)
    if listed is None or listed != {r["sha"] for r in riders}:
        return {"ok": False, "error": (
            f"rider parse mismatch: git log yielded {len(riders)} commit(s), rev-list "
            f"{'failed' if listed is None else len(listed)} — refusing to judge a "
            "manifest that does not account for every commit")}
    on_main, err = already_on_main(git, main, dev)
    if err:
        return {"ok": False, "error": err}
    attribute(git, riders, pointer_rows)

    projects: dict[str, dict[str, Any]] = {}
    coverage: dict[str, set[str]] = {}
    for r in riders:
        r["project"] = project_for_branch(r["branch"], pointer_rows) if r["branch"] else None
        r["exempt"] = is_docs_only(r["files"])
        p = r["project"]
        if p is None or p in projects:
            continue
        live = effective_approvals(consent_rows, p)
        covered: set[str] = set()
        notes: list[str] = []
        verified = 0
        for row in live:
            ok, why = verify(row)
            if not ok:
                notes.append(f"approval {row.get('ts')} unverified: {why}")
                continue
            verified += 1
            reach = reachable(git, main, str(row.get("dev_sha") or ""))
            if reach is None:
                notes.append(f"approval {row.get('ts')}: dev_sha {row.get('dev_sha')} unresolvable")
                continue
            covered |= reach
        coverage[p] = covered
        projects[p] = {
            "project": p,
            "consent": ("approved" if verified else
                        "unverified" if live else "none"),
            "approval_dev_shas": [row.get("dev_sha") for row in live],
            "notes": notes, "commits": 0, "unapproved": 0,
        }

    for r in riders:
        if r["sha"] in on_main:
            r["state"] = "on_main"
        elif r["exempt"]:
            r["state"] = "exempt"
        elif r["project"] is None:
            r["state"] = "unattributed"
        elif r["sha"] in coverage.get(r["project"], set()):
            r["state"] = "approved"
        else:
            r["state"] = "unapproved"
        if r["project"] in projects:
            projects[r["project"]]["commits"] += 1
            if r["state"] == "unapproved":
                projects[r["project"]]["unapproved"] += 1
    for pr in projects.values():  # approved, but newer commits await re-approval
        if pr["consent"] == "approved" and pr["unapproved"]:
            pr["consent"] = "partial"

    plan = plan_ship_set(riders)
    unapproved = [r for r in riders if r["state"] in ("unapproved", "unattributed")]
    return {
        "ok": True,
        "commits": [{k: r[k] for k in ("sha", "subject", "branch", "project",
                                       "attribution", "state", "exempt")}
                    | {"files": len(r["files"])} for r in riders],
        "projects": sorted(projects.values(), key=lambda x: x["project"]),
        "unapproved_riders": [f"{r['sha'][:9]} [{r['project'] or 'unattributed'}] {r['subject']}"
                              for r in unapproved],
        "all_approved": not unapproved and not plan["deferred"],
        "on_main": sorted(on_main),
        **plan,
    }


def plan_ship_set(riders: list[dict]) -> dict[str, Any]:
    """Walk riders in dev order and decide what a cut carries.

    Ship = approved ∪ exempt (minus on_main). A shipped commit touching a
    (non-ledger) file an EARLIER unshipped rider changed depends on that
    rider: an APPROVED one ⇒ a named dependency (the cut REFUSES — shipping it
    alone would ship a state that never existed on dev); an EXEMPT (docs) one
    ⇒ deferred (it simply waits for the rider), and from then on counts as
    unshipped for later commits.
    """
    unshipped_touch: dict[str, str] = {}
    ship: list[str] = []
    deferred: list[dict] = []
    dependencies: list[dict] = []
    for r in riders:
        if r["state"] == "on_main":
            continue
        deps = sorted({unshipped_touch[f] for f in r["files"]
                       if not f.startswith(_DEPENDENCY_EXEMPT_PREFIXES) and f in unshipped_touch})
        shipping = r["state"] in ("approved", "exempt")
        if shipping and deps:
            if r["state"] == "approved":
                dependencies.append({"commit": r["sha"], "subject": r["subject"],
                                     "project": r["project"], "depends_on": deps,
                                     "files": sorted(f for f in r["files"]
                                                     if unshipped_touch.get(f) in deps)})
            else:
                deferred.append({"commit": r["sha"], "subject": r["subject"],
                                 "depends_on": deps})
            shipping = False
        if shipping:
            ship.append(r["sha"])
        else:
            for f in r["files"]:
                unshipped_touch[f] = r["sha"]
    return {"ship": ship, "deferred": deferred, "dependencies": dependencies}


# ── the cut (no working tree: merge-tree + commit-tree) ──────────────────────
def _author_env(git: GitFn, sha: str) -> dict[str, str]:
    rc, out, _e = git("log", "-1", "--format=%an%x00%ae%x00%ad", "--date=raw", sha)
    bits = out.rstrip("\n").split("\x00") if rc == 0 else []
    if len(bits) != 3:
        return {}
    return {"GIT_AUTHOR_NAME": bits[0], "GIT_AUTHOR_EMAIL": bits[1], "GIT_AUTHOR_DATE": bits[2]}


def cherry_pick_chain(git: GitFn, base: str, shas: list[str]) -> dict[str, Any]:
    """Replay `shas` onto `base` WITHOUT a working tree — `git merge-tree
    --write-tree --merge-base=<C^>` is exactly cherry-pick's 3-way merge, and
    `git commit-tree` records it with the original author + message plus the
    `(cherry picked from commit <C>)` mark. Objects written on a dry-run are
    unreachable until pushed (gc reclaims them). A conflict REFUSES, naming
    the commit — never auto-resolved."""
    tip = base
    picked: list[dict] = []
    for sha in shas:
        rc, out, err = git("merge-tree", "--write-tree", f"--merge-base={sha}^", tip, sha)
        if rc != 0:
            return {"ok": False, "conflict": sha, "picked": picked,
                    "detail": (out.strip().splitlines()[1:] or [err.strip()])[:10]}
        tree = out.splitlines()[0].strip()
        rc, msg, err = git("log", "-1", "--format=%B", sha)
        if rc != 0:
            return {"ok": False, "error": f"cannot read message of {sha}: {err.strip()}"}
        body = msg.rstrip("\n") + f"\n\n{PICKED_MARK}{sha})\n"
        rc, new, err = git("commit-tree", tree, "-p", tip, "-F", "-", stdin=body,
                           env_extra=_author_env(git, sha))
        if rc != 0 or not new.strip():
            return {"ok": False, "error": f"commit-tree failed for {sha}: {err.strip()}"}
        tip = new.strip()
        picked.append({"from": sha, "to": tip})
    return {"ok": True, "tip": tip, "picked": picked}


def release_branch_sources(git: GitFn, main: str, release_tip: str) -> tuple[list[dict], str]:
    """For every commit `main..release_tip`: the dev commit it was picked from
    (None when the commit carries no cut mark — i.e. was not made by a cut)."""
    rc, out, err = git("log", "--reverse", f"--format={_REC}%H{_FLD}%P{_FLD}%B",
                       f"{main}..{release_tip}")
    if rc != 0:
        return [], err.strip() or out.strip()
    rows = []
    for rec in out.split(_REC):
        if not rec.strip():
            continue
        sha, parents, body = (rec.split(_FLD, 2) + ["", ""])[:3]
        src = None
        for ln in body.splitlines():
            ln = ln.strip()
            if ln.startswith(PICKED_MARK) and ln.endswith(")"):
                src = ln[len(PICKED_MARK):-1].strip()
        rows.append({"sha": sha.strip(), "merge": len(parents.split()) > 1, "from": src})
    return rows, ""


def backmerge_commit(git: GitFn, dev: str, main: str) -> dict[str, Any]:
    """Build `Merge main into dev` (parents dev, main) with no working tree."""
    rc, out, err = git("merge-tree", "--write-tree", dev, main)
    if rc != 0:
        return {"ok": False, "detail": (out.strip().splitlines()[1:] or [err.strip()])[:10]}
    tree = out.splitlines()[0].strip()
    msg = (f"chore(release): backmerge main into dev\n\n"
           f"Restores dev ⊇ main after a release cut so the next bless can fast-forward.\n"
           f"main={main[:12]} dev={dev[:12]}\n")
    rc, new, err = git("commit-tree", tree, "-p", dev, "-p", main, "-F", "-", stdin=msg)
    if rc != 0 or not new.strip():
        return {"ok": False, "detail": [err.strip()]}
    return {"ok": True, "sha": new.strip(), "tree": tree}
