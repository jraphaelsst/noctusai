"""`task_branch action='train'` -- merge-all-before-integrating (owner rule 2026-10-24).

Each `task_branch integrate` costs 30-40 min of merged-tip gates on a loaded
host; integrating N ready branches serially is N x that. A TRAIN merges every
ready `feat/<slug>` into ONE `train-<name>` task branch (`git merge --no-ff`,
least-conflict-first), so the merged-tip gate judges exactly what ships and
ONE `integrate` lands them all. KB § PATTERNS/architect/branching-dispatch.md.

Safety shape (mirrors `primary_ff`'s carve-out): `merge` stays BANNED inside
`task_branch._git`; this module runs two fixed argv shapes through the injected
runner -- `git merge --no-ff --no-edit -m <msg> feat/<slug>` -- and never
`--abort`/`reset`/`checkout`. A conflict is NEVER auto-resolved and NEVER
aborted: the merge is left in progress in the train worktree for a dedicated,
honest resolution commit; re-running the train skips already-merged slugs.

Membership is recorded in git itself, in the merge-commit subject
(`train(<name>): merge feat/<slug>`), so `integrate` of the train derives its
riders with no side state (`parse_train_riders`) and flips each rider's pointer
+ cleans its worktree (`task_branch._train_riders_after_integrate`).
"""
from __future__ import annotations

import os
import re
from itertools import combinations
from typing import Any, Callable

TRAIN_PREFIX = "train-"
_RIDER_RE = re.compile(r"^train\([^)]*\): merge (?:feat/)?(\S+)\s*$")
# A conflict resolved with a bare `git commit -m "<custom>"` replaces our subject;
# git's own default merge subject still names the branch, so accept it too.
_GIT_DEFAULT_RE = re.compile(r"^Merge branch 'feat/([^']+)'")


def is_train_slug(slug: str | None) -> bool:
    return bool(slug) and str(slug).startswith(TRAIN_PREFIX)


def train_slug(name: str | None, today: str) -> str:
    """`train-<name>` (idempotent when `name` already carries the prefix)."""
    name = (name or today).strip()
    return name if name.startswith(TRAIN_PREFIX) else f"{TRAIN_PREFIX}{name}"


def merge_subject(train: str, slug: str) -> str:
    return f"train({train[len(TRAIN_PREFIX):] if is_train_slug(train) else train}): merge feat/{slug}"


def parse_train_riders(subjects: list[str]) -> list[str]:
    """Rider slugs from merge-commit subjects, in merge order, de-duplicated."""
    out: list[str] = []
    for s in reversed([s for s in subjects if s.strip()]):  # git log is newest-first
        m = _RIDER_RE.match(s.strip()) or _GIT_DEFAULT_RE.match(s.strip())
        if m and m.group(1) not in out:
            out.append(m.group(1))
    return out


def overlap_files(files_by_slug: dict[str, set[str]]) -> dict[str, list[str]]:
    """{file: [slugs touching it]} for files touched by >= 2 slugs."""
    seen: dict[str, list[str]] = {}
    for slug, files in files_by_slug.items():
        for f in files:
            seen.setdefault(f, []).append(slug)
    return {f: sorted(s) for f, s in sorted(seen.items()) if len(s) >= 2}


def order_least_conflict_first(files_by_slug: dict[str, set[str]]) -> list[str]:
    """Slugs ordered by ascending path-overlap with the others (ties: name), so
    the likeliest-to-conflict branches merge LAST on top of a settled tree."""
    score = {s: 0 for s in files_by_slug}
    for a, b in combinations(files_by_slug, 2):
        n = len(files_by_slug[a] & files_by_slug[b])
        score[a] += n
        score[b] += n
    return sorted(files_by_slug, key=lambda s: (score[s], s))


def suggest_tests(files: list[str], exists: Callable[[str], bool]) -> list[str]:
    """Narrow test targets for OVERLAP files (docs-only overlap => none)."""
    out: list[str] = []

    def add(p: str) -> None:
        if p not in out:
            out.append(p)

    for f in files:
        m = re.match(r"^(products/[^/]+)/backend/", f)
        if m and exists(f"{m.group(1)}/backend/tests"):
            add(f"{m.group(1)}/backend/tests")
        m = re.match(r"^(products/[^/]+)/frontend/", f)
        if m and exists(f"{m.group(1)}/frontend"):
            add(f"{m.group(1)}/frontend (vitest on the overlapped components)")
        if f.startswith("mcp/noctusai/tools/") and f.endswith(".py"):
            stem = os.path.basename(f)[:-3]
            cand = f"mcp/noctusai/tests/test_{stem}.py"
            if exists(cand):
                add(cand)
        if f.startswith("mcp/noctusai/tests/") and f.endswith(".py"):
            add(f)
        if f.startswith("seed/") and f.endswith(".py"):
            add("seed (pytest on the overlapped module's colocated tests)")
    return out


def _worktree_for_branch(task_branch_mod, git, branch: str) -> str | None:
    rc, out, _e = git("worktree", "list", "--porcelain")
    for wt in task_branch_mod._parse_worktrees(out if rc == 0 else ""):
        if wt.get("branch") == f"refs/heads/{branch}":
            return wt.get("path")
    return None


def _changed_files(git, dev: str, branch: str) -> set[str]:
    rc, out, _e = git("diff", "--name-only", f"{dev}...{branch}")
    return {ln.strip() for ln in out.splitlines() if ln.strip()} if rc == 0 else set()


def run_train(
    *, tb, git, runner, remote: str, dev_branch: str, branch_prefix: str,
    worktrees_dir: str, primary_root: str, slugs: list[str] | None,
    name: str | None, order: str, confirm: bool, today: str,
    start_fn: Callable[..., dict[str, Any]], exists: Callable[[str], bool],
) -> dict[str, Any]:
    """The `train` action. `tb` is the task_branch module (lazy, cycle-free)."""
    base: dict[str, Any] = {"ok": True, "action": "train", "remote": remote}
    git("fetch", remote, "--quiet")
    dev = tb._resolve(git, f"{remote}/{dev_branch}")
    if not dev:
        return {**base, "ok": False, "status": "error", "exit_code": 1,
                "error": f"cannot resolve {remote}/{dev_branch} (fetch failed?)."}

    # Candidates: committed-not-integrated feat/* branches (dry-run listing).
    rc, wl, _e = git("worktree", "list", "--porcelain")
    cands: list[dict[str, Any]] = []
    for wt in tb._parse_worktrees(wl if rc == 0 else ""):
        br = wt.get("branch", "")
        pre = f"refs/heads/{branch_prefix}"
        if not br.startswith(pre) or worktrees_dir not in wt.get("path", ""):
            continue
        s = br[len(pre):]
        if is_train_slug(s):
            continue
        head = wt.get("head") or ""
        ahead = len(tb._commits(git, dev, head)) if head else 0
        if ahead == 0 and tb._is_ancestor(git, head, dev):
            continue
        cands.append({"slug": s, "ahead": ahead, "head": head[:9],
                      "dirty": tb._is_dirty_excluding_gitignored(
                          runner, tb._absolute_wt_path(wt["path"], primary_root))})
    if not slugs:
        return {**base, "status": "candidates", "exit_code": 0, "dev_sha": dev,
                "candidates": cands,
                "message": (f"{len(cands)} committed-not-integrated branch(es). Pass slugs=[...] "
                            "(+ confirm=True) to merge them into one train, then integrate the "
                            "train ONCE.")}

    slugs = list(dict.fromkeys(slugs))
    problems: list[dict[str, str]] = []
    files_by_slug: dict[str, set[str]] = {}
    for s in slugs:
        b = f"{branch_prefix}{s}"
        if is_train_slug(s):
            problems.append({"slug": s, "reason": "a train cannot ride another train"})
            continue
        if not tb._resolve(git, b):
            problems.append({"slug": s, "reason": f"branch {b} does not exist"})
            continue
        wt = _worktree_for_branch(tb, git, b)
        if wt and tb._is_dirty_excluding_gitignored(runner, tb._absolute_wt_path(wt, primary_root)):
            problems.append({"slug": s, "reason": "worktree has uncommitted changes -- commit "
                                                  "(or discard) before it rides the train"})
            continue
        files_by_slug[s] = _changed_files(git, dev, b)
    if problems:
        return {**base, "ok": False, "status": "refused", "exit_code": 1, "refused": problems,
                "message": "train refused: " + "; ".join(f"{p['slug']}: {p['reason']}" for p in problems)}

    ordered = order_least_conflict_first(files_by_slug) if order == "auto" else slugs
    overlaps = overlap_files(files_by_slug)
    tslug = train_slug(name, today)
    tbranch = f"{branch_prefix}{tslug}"
    plan = {**base, "train": tslug, "train_branch": tbranch, "order": ordered,
            "order_mode": order, "overlap_files": overlaps,
            "suggested_tests": suggest_tests(sorted(overlaps), exists)}
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": (f"would start/reuse {tbranch} off {remote}/{dev_branch} and merge "
                            f"--no-ff in order: {', '.join(ordered)}. Pass confirm=True.")}

    started = start_fn(tslug)
    if started.get("status") not in {"started"}:
        return {**plan, "ok": False, "status": "error", "exit_code": 1, "start": started,
                "error": f"could not start/reuse the train branch: {started.get('error') or started.get('status')}"}
    twt = tb._absolute_wt_path(f"{worktrees_dir}/{tslug}", primary_root)
    if os.path.exists(os.path.join(twt, ".git")):
        rc, gd, _e = runner(["git", "rev-parse", "--git-dir"], cwd=twt)
        gdir = gd.strip() if rc == 0 else ""
        gdir = gdir if os.path.isabs(gdir) else os.path.join(twt, gdir)
        if gdir and os.path.exists(os.path.join(gdir, "MERGE_HEAD")):
            return {**plan, "ok": False, "status": "conflict", "exit_code": 1, "merged": [],
                    "worktree": twt,
                    "message": ("a merge is already in progress in the train worktree: resolve it "
                                "(commit the resolution) then re-run the train -- merged slugs "
                                "are skipped.")}

    merged: list[str] = []
    skipped: list[str] = []
    for s in ordered:
        b = f"{branch_prefix}{s}"
        if tb._is_ancestor(git, b, tbranch):
            skipped.append(s)
            continue
        rc, out, err = runner(
            ["git", "merge", "--no-ff", "--no-edit", "-m", merge_subject(tslug, s), b], cwd=twt)
        if rc != 0:
            rc2, cout, _ce = git("diff", "--name-only", "--diff-filter=U", cwd=twt)
            files = [ln.strip() for ln in cout.splitlines() if ln.strip()] if rc2 == 0 else []
            return {**plan, "ok": False, "status": "conflict", "exit_code": 1, "slug": s,
                    "files": files, "merged": merged, "skipped": skipped, "worktree": twt,
                    "detail": (err or out or "")[-300:],
                    "message": (f"conflict merging feat/{s} into {tbranch}; merge LEFT IN PROGRESS "
                                f"in {twt}. Resolve, commit the resolution as its own honest "
                                "commit (plain `git commit` keeps the train merge subject, which is "
                                "how integrate finds the riders), then re-run the train (merged slugs are skipped).")}
        merged.append(s)
    return {**plan, "status": "merged", "exit_code": 0, "merged": merged, "skipped": skipped,
            "worktree": twt,
            "message": (f"merged {len(merged)} (skipped {len(skipped)}) into {tbranch}. Run the "
                        "suggested_tests on overlap_files, then ONE integrate of "
                        f"slug='{tslug}' -- it flips each rider's pointer and cleans its worktree.")}
