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

import re
import tempfile
from typing import Any, Callable

GitFn = Callable[..., tuple[int, str, str]]

TRAILER = "Noc-Branch"
PICKED_MARK = "(cherry picked from commit "
REGEN_MARK = "(kb-counts regen on "
_REC, _FLD = "\x1e", "\x1f"

#: Append-only, `merge=union` ledgers — every agent appends to them, so a
#: "last touched by an unapproved rider" edge on these paths is not a code
#: dependency (merge-tree replays them conflict-free by the union driver).
_DEPENDENCY_EXEMPT_PREFIXES = ("project-history/",)

# Matches an entire `<!-- kb-counts:start:X -->…<!-- kb-counts:end:X -->`
# marker block, regardless of region name. Local copy of `kb_sync`'s marker
# SYNTAX (never its FILE LIST — that single source is `.gitattributes`, read
# via `git check-attr`, see `_kb_counts_attributed`) so this module's only
# real dependency stays the injected `git` callable (module docstring), not
# `settings.REPO_ROOT` / a `kb_sync` import.
_ANY_REGION_RE = re.compile(
    r"<!-- kb-counts:start:[A-Za-z0-9_-]+ -->.*?<!-- kb-counts:end:[A-Za-z0-9_-]+ -->",
    re.DOTALL,
)


def _mask_kb_counts_regions(text: str) -> str:
    """Blank every `kb-counts` marker block (markers + content) with a
    single stable placeholder. Comparing masked before/after text of the
    SAME file across one commit answers "did this edit change anything
    OTHER than the auto-derived counts?" without recomputing what the
    counts WERE at that point in history (they are a function of the
    CURRENT tree, not of a historical commit)."""
    return _ANY_REGION_RE.sub("<!-- kb-counts: region -->", text)


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


# ── derived-file regen-only touches ─────────────────────────────────────────
def _kb_counts_attributed(git: GitFn, sha: str, paths: list[str]) -> set[str]:
    """Subset of `paths` carrying the `merge=kb-counts` git attribute, as of
    `sha`'s tree. THE single source — `.gitattributes`, the SAME declarative
    surface `scripts/hooks/merge-kb-counts.sh` reads (KB §
    PATTERNS/common/auto-generated-merge-drivers.md) — read via `git
    check-attr --source=<sha>`, never a hand-copied filename list. Two wins
    over a bare `_regions()` walk: pattern-aware (a future GLOB entry in
    `.gitattributes` resolves correctly, not just today's 3 literal lines),
    and historically precise (`--source` reads THAT commit's
    `.gitattributes`, never whatever the runner's working checkout
    currently has checked out)."""
    if not paths:
        return set()
    rc, out, _e = git("check-attr", f"--source={sha}", "merge", "--", *paths)
    if rc != 0:
        return set()
    hits: set[str] = set()
    for line in out.splitlines():
        path, sep, value = line.partition(": merge: ")
        if sep and value.strip() == "kb-counts":
            hits.add(path)
    return hits


def _is_regen_only_touch(git: GitFn, sha: str, path: str) -> bool:
    """True iff `sha`'s ENTIRE change to `path` lives inside a `kb-counts`
    marker block — the pre-commit hook's auto-derived-counts refresh
    (`noctus.dev.kb_sync --update-kb-counts`), which folds into nearly
    every commit that touches `KNOWLEDGE-BASE/` or `products/`. Caller must
    already know `path` is `merge=kb-counts`-attributed (see
    `_kb_counts_attributed`) — a NON-attributed file is never regen-only,
    however small its diff.

    Masked-content equality (not a diff-hunk parse, not recomputing what the
    counts WERE at that point in history — they are a function of the
    CURRENT tree) answers "did this commit change anything other than the
    counts" from the two blobs alone: prose changed in the SAME file still
    fails the equality check (couples normally), counts-only churn passes.
    Fail-closed: a missing parent (root commit) or a missing blob on either
    side (file created/deleted this commit) is NEVER regen-only —
    refuse-not-null, never a false "no dependency". KB §
    PATTERNS/devops/ship-consent-riders.md § The cut.
    """
    rc, parent, _e = git("rev-parse", f"{sha}^")
    if rc != 0 or not parent.strip():
        return False
    rc_p, old, _ep = git("show", f"{parent.strip()}:{path}")
    rc_n, new, _en = git("show", f"{sha}:{path}")
    if rc_p != 0 or rc_n != 0:
        return False
    return _mask_kb_counts_regions(old) == _mask_kb_counts_regions(new)


def _mark_regen_only_files(git: GitFn, riders: list[dict]) -> None:
    """Fill `regen_only_files` on each rider, in place — the subset of its
    `files` that are BOTH `merge=kb-counts`-attributed (as of this commit)
    AND, for THIS commit, `_is_regen_only_touch`. `plan_ship_set` reads it
    to skip recording a dependency edge on a pure counts refresh; a
    NON-attributed file (e.g. a hand-authored KB doc with no counts region)
    is untouched by this — its dependency behaviour is unchanged."""
    for r in riders:
        attributed = _kb_counts_attributed(git, r["sha"], r["files"])
        r["regen_only_files"] = (
            {f for f in attributed if _is_regen_only_touch(git, r["sha"], f)}
            if attributed else set()
        )


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
    _mark_regen_only_files(git, riders)

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

    An unshipped rider's touch to a `kb-counts`-attributed file is recorded
    as "the last thing that touched it" (`unshipped_touch[f] = r["sha"]")
    ONLY when that touch was a REAL edit — a rider in `r["regen_only_files"]`
    (set by `_mark_regen_only_files`: `merge=kb-counts`-attributed AND its
    whole diff to that file lives inside the marker block) leaves the
    pointer at whatever it already was, hopping over pure counts churn to
    find the nearest genuine unshipped edit. This is WHY two unrelated
    projects' commits, each carrying nothing but the pre-commit hook's
    auto-count refresh of the SAME derived doc, no longer chain a
    dependency between them (KB § PATTERNS/devops/ship-consent-riders.md §
    The cut) — a PROSE edit to that same file still couples normally, since
    it is never in `regen_only_files`.
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
            regen_only = r.get("regen_only_files") or ()
            for f in r["files"]:
                if f in regen_only:
                    continue
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
    (None when the commit carries no cut mark — i.e. was not made by a cut),
    and whether it is a `regenerate_kb_counts_commit` bookkeeping commit
    (`REGEN_MARK` — never a cherry-pick, so `from` is always None for it;
    `_bless_release_branch`'s foreign-commit check reads `regen` to NOT
    flag it foreign)."""
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
        regen = False
        for ln in body.splitlines():
            ln = ln.strip()
            if ln.startswith(PICKED_MARK) and ln.endswith(")"):
                src = ln[len(PICKED_MARK):-1].strip()
            elif ln.startswith(REGEN_MARK) and ln.endswith(")"):
                regen = True
        rows.append({"sha": sha.strip(), "merge": len(parents.split()) > 1,
                     "from": src, "regen": regen})
    return rows, ""


# ── kb-counts regen commit (keeps `main` self-consistent after a cut) ───────
def _kb_counts_declared_paths(git: GitFn, sha: str) -> list[str]:
    """Every path literally declared `merge=kb-counts` in `.gitattributes`
    at `sha` — parsed straight from the file the merge driver itself reads
    (`scripts/hooks/merge-kb-counts.sh`, KB §
    PATTERNS/common/auto-generated-merge-drivers.md). Literal-line scoped:
    today's `.gitattributes` carries 3 literal entries, no globs; a future
    GLOB entry would need `_kb_counts_attributed`'s pattern-aware
    `check-attr` here too (not silently assumed correct forever — see
    scoped-improvement note in this module's dispatch return)."""
    rc, text, _e = git("show", f"{sha}:.gitattributes")
    if rc != 0:
        return []
    paths: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split()
        if len(parts) >= 2 and "merge=kb-counts" in parts[1:]:
            paths.append(parts[0])
    return paths


def regenerate_kb_counts_commit(
    git: GitFn, tip: str, render: Callable[[str, str], str],
) -> dict[str, Any]:
    """Build ONE extra commit atop `tip` that regenerates every
    `merge=kb-counts`-declared file's counts blocks — keeping `main`
    self-consistent after a cut ships only a SUBSET of dev's riders (a
    cherry-picked rider's own dev-time regen reflected whatever the tree
    looked like on ITS branch, not the cut's actual shipped subset). KB §
    PATTERNS/devops/ship-consent-riders.md § The cut.

    `render(path, current_text) -> new_text` is the DI seam — production
    wires `kb_sync.render_kb_counts` bound against the ambient checkout
    (the best available signal: this module has no working tree for the CUT
    itself, by design — `render_kb_counts`'s renderers walk the repo the
    release tool runs in, which in the standard workflow sits at-or-near
    the dev tip the cut was carved from); tests script a fake.

    No working tree: a THROWAWAY on-disk git index (`GIT_INDEX_FILE`) reads
    `tip`'s tree, gets exactly the changed blobs re-hashed into it, and
    `write-tree`s the result — the real working tree/index is never
    touched. A no-op (nothing changed) returns `tip` unchanged, never an
    empty commit.
    """
    paths = _kb_counts_declared_paths(git, tip)
    if not paths:
        return {"ok": True, "changed": False, "tip": tip}
    updates: dict[str, str] = {}
    for path in paths:
        rc, cur, _e = git("show", f"{tip}:{path}")
        if rc != 0:
            continue  # not present on the cut — nothing to regenerate
        new = render(path, cur)
        if new != cur:
            updates[path] = new
    if not updates:
        return {"ok": True, "changed": False, "tip": tip}
    with tempfile.TemporaryDirectory(prefix="noctus-release-idx-") as tmp:
        index_path = f"{tmp}/index"
        env = {"GIT_INDEX_FILE": index_path}
        rc, _o, err = git("read-tree", tip, env_extra=env)
        if rc != 0:
            return {"ok": False, "error": f"read-tree failed: {err.strip()}"}
        for path, new_text in sorted(updates.items()):
            rc, blob, err = git("hash-object", "-w", "--path", path, "--stdin",
                                stdin=new_text, env_extra=env)
            if rc != 0 or not blob.strip():
                return {"ok": False, "error": f"hash-object failed for {path}: {err.strip()}"}
            rc, _o, err = git("update-index", "--add", "--cacheinfo",
                              f"100644,{blob.strip()},{path}", env_extra=env)
            if rc != 0:
                return {"ok": False, "error": f"update-index failed for {path}: {err.strip()}"}
        rc, tree, err = git("write-tree", env_extra=env)
        if rc != 0 or not tree.strip():
            return {"ok": False, "error": f"write-tree failed: {err.strip()}"}
    msg = (f"chore(release): regenerate kb-counts on the cut\n\n"
          f"{len(updates)} file(s): {', '.join(sorted(updates))}\n"
          f"{REGEN_MARK}{tip})\n")
    rc, new_sha, err = git("commit-tree", tree.strip(), "-p", tip, "-F", "-", stdin=msg)
    if rc != 0 or not new_sha.strip():
        return {"ok": False, "error": f"commit-tree failed: {err.strip()}"}
    return {"ok": True, "changed": True, "tip": new_sha.strip(), "files": sorted(updates)}


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
