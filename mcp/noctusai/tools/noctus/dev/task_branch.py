"""noctus.dev.task_branch — the self-branching-mode per-task lifecycle as a tool.

Self-branching mode (KB § PATTERNS/self-branching-mode.md): in a multi-terminal
world there is no single architect on top — every terminal-agent is a *peer*,
and a peer can't cheaply know whether a sibling is active in the SAME checkout.
So the safe default for any **writing** task is to self-isolate: do the work in
a per-task `git worktree` off `origin/dev`, then integrate straight to
`origin/dev` — NEVER switching the shared primary checkout's branch out from
under a sibling (the §9a "2-days-of-chaos" failure mode). This tool runs that
lifecycle so it is one call, not a hand-typed ritual:

  • start     : fetch → `git worktree add <wt> -b feat/<slug> origin/dev`.
  • integrate : (in the worktree) fetch → rebase onto origin/dev → FF-push
                HEAD → origin/dev, with fetch-rebase-RETRY on the concurrent-
                push race. A rebase conflict is ABORTED (worktree restored
                clean) and surfaced loudly — never auto-resolved, never left
                half-rebased. This is KB § branching-and-merging § 10.2 Option A
                with `dev` substituted for the integration ref.
  • cleanup   : `git worktree remove <wt>` (refuses if dirty — no --force) →
                prune → `git branch -d feat/<slug>` (refuses if unmerged — `-d`
                not `-D`). A precise teardown of ONE named task worktree; the
                heuristic bulk-sweep of stale agent worktrees is the sibling
                noctus.dev.cleanup_stale_worktrees.
  • status    : read-only — list the active self-branch worktrees + each one's
                ahead/behind vs origin/dev.

Safety model (mirrors release / deploy_pull):
  • INSPECT (always, read-only first): fetch refs, resolve origin/dev, compute
    ff-ability + the commit lists each hop would move.
  • confirm-GATE (412 pattern): every WRITE action returns the PLAN only
    without `confirm`; `confirm=True` executes. `status` never writes.
  • BY CONSTRUCTION it only runs a safe git allowlist and carries NO banned
    token (reset / checkout / switch / restore / clean / merge / --force /
    --force-with-lease / -f / -D). It can create a worktree+branch and delete a
    *merged* branch (`-d`), but can never force, reset, or rewrite history.
  • DEV-ONLY PUSH BOUNDARY (this tool's defining guard): every push destination
    MUST be `dev`. A refspec targeting main/prod (or anything else) is REFUSED,
    structurally — the tool can never touch the sacred release/prod lines, and
    never sets NOCTUS_ALLOW_MAIN_PUSH (a colocated test asserts both). Engineers
    and peer-agents land on `dev`; main/prod move only via noctus.dev.release.

IO is injectable (`run`) so the colocated test drives every path with zero real
git and asserts the allowlist, the dev-only-push boundary, and the rebase-retry.
"""
from __future__ import annotations

import subprocess
from typing import Any, Callable

# git subcommands the tool may run. `worktree` (add/remove/list/prune) + `branch`
# (only `-d`, the merged-only delete) + `rebase` are what distinguish this from
# release's read-mostly set; force/reset/checkout stay OFF the list so a
# history-rewriting or branch-switching action is structurally impossible.
_ALLOWED_GIT = frozenset(
    {"fetch", "rev-parse", "merge-base", "rev-list", "log", "diff", "status",
     "worktree", "rebase", "push", "branch"}
)
_BANNED_TOKENS = (
    "reset", "checkout", "switch", "restore", "clean", "merge", "cherry-pick",
    "--hard", "--force", "--force-with-lease", "-f", "-D",
)


def _default_run_local(cmd: list[str], cwd: str | None = None) -> tuple[int, str, str]:
    """Run `cmd`; (rc, stdout, stderr). `cwd` targets a worktree for the
    worktree-local ops (rebase / push / status); None ⇒ repo root for the
    repo-global ops (fetch / worktree add|remove|list|prune / branch -d).
    REPO_ROOT is imported lazily so module import stays light and the test
    (which injects `run`) never pays the settings import cost."""
    from settings import REPO_ROOT  # lazy: avoids import-time noctusai_lib cost

    r = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd or str(REPO_ROOT))
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _assert_push_targets_dev(args: tuple[str, ...], dev_branch: str) -> None:
    """A push refspec's DESTINATION must be `dev` — the tool's defining safety
    boundary. Refuses main/prod/any-other dst, structurally."""
    if not args or args[0] != "push":
        return
    for tok in args:
        if ":refs/heads/" in tok:
            dst = tok.split(":refs/heads/", 1)[1]
            if dst != dev_branch:
                raise ValueError(
                    f"task_branch: push destination '{dst}' is not '{dev_branch}'. "
                    "This tool integrates ONLY to dev; main/prod move via noctus.dev.release."
                )


def _git(runner, *args, cwd: str | None = None, dev_branch: str = "dev") -> tuple[int, str, str]:
    """Run a git subcommand — ONLY if on the safe allowlist AND carrying no
    banned token AND (for a push) targeting `dev`. The structural guarantee the
    tool can never force/rewrite/switch, and can never push off `dev`."""
    sub = args[0] if args else ""
    if sub not in _ALLOWED_GIT:
        raise ValueError(
            f"task_branch: git '{sub}' is not on the safe allowlist {sorted(_ALLOWED_GIT)}"
        )
    for tok in args:
        if tok in _BANNED_TOKENS:
            raise ValueError(f"task_branch: banned token '{tok}' in git {list(args)}")
    _assert_push_targets_dev(args, dev_branch)
    return runner(["git", *args], cwd=cwd)


def _resolve(git, ref: str) -> str | None:
    rc, out, _e = git("rev-parse", ref)
    return out.strip() if rc == 0 and out.strip() else None


def _is_ancestor(git, a: str, b: str) -> bool:
    """True iff commit `a` is an ancestor of (or equal to) `b`."""
    rc, _o, _e = git("merge-base", "--is-ancestor", a, b)
    return rc == 0


def _commits(git, a: str, b: str, cwd: str | None = None) -> list[str]:
    rc, out, _e = git("log", "--oneline", f"{a}..{b}", cwd=cwd)
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def _parse_worktrees(porcelain: str) -> list[dict[str, str]]:
    """Parse `git worktree list --porcelain` into [{path, head, branch}]."""
    blocks: list[dict[str, str]] = []
    cur: dict[str, str] = {}
    for line in porcelain.splitlines():
        if not line.strip():
            if cur:
                blocks.append(cur)
                cur = {}
            continue
        if line.startswith("worktree "):
            cur = {"path": line[len("worktree "):].strip()}
        elif line.startswith("HEAD "):
            cur["head"] = line[len("HEAD "):].strip()
        elif line.startswith("branch "):
            cur["branch"] = line[len("branch "):].strip()
    if cur:
        blocks.append(cur)
    return blocks


def task_branch(
    action: str = "status",
    slug: str | None = None,
    confirm: bool = False,
    remote: str = "origin",
    dev_branch: str = "dev",
    worktrees_dir: str = ".claude/worktrees",
    branch_prefix: str = "feat/",
    max_retries: int = 5,
    run: Callable[..., tuple[int, str, str]] | None = None,
) -> dict[str, Any]:
    """`action` ∈ {status, start, integrate, cleanup}. Writes are dry-run unless
    `confirm`. Returns a structured plan/result; never raises on a refusal — it
    returns it (the refusal IS the safety net)."""
    runner = run or _default_run_local

    def git(*args, cwd: str | None = None):
        return _git(runner, *args, cwd=cwd, dev_branch=dev_branch)

    if action not in {"status", "start", "integrate", "cleanup"}:
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"unknown action '{action}' (expected status|start|integrate|cleanup)"}

    wt_path = f"{worktrees_dir}/{slug}" if slug else None
    branch = f"{branch_prefix}{slug}" if slug else None
    base: dict[str, Any] = {"ok": True, "action": action, "remote": remote,
                            "slug": slug, "branch": branch, "worktree": wt_path}

    # ── STATUS ── read-only: list active self-branch worktrees + ahead/behind
    if action == "status":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        rc, out, _e = git("worktree", "list", "--porcelain")
        mine: list[dict[str, Any]] = []
        for wt in _parse_worktrees(out if rc == 0 else ""):
            br = wt.get("branch", "")
            if worktrees_dir not in wt.get("path", ""):
                continue
            if not br.startswith(f"refs/heads/{branch_prefix}"):
                continue
            head = wt.get("head")
            ahead = len(_commits(git, dev, head)) if (dev and head) else None
            behind = len(_commits(git, head, dev)) if (dev and head) else None
            mine.append({
                "slug": br[len(f"refs/heads/{branch_prefix}"):],
                "branch": br[len("refs/heads/"):], "path": wt.get("path"),
                "head": head, "ahead": ahead, "behind": behind,
            })
        return {**base, "status": "status", "exit_code": 0, "dev_sha": dev,
                "active": mine,
                "message": f"{len(mine)} active self-branch worktree(s) vs {remote}/{dev_branch}."}

    if not slug:
        return {**base, "status": "error", "exit_code": 1,
                "error": f"action '{action}' requires slug=."}

    # ── START ── fetch → worktree add -b feat/<slug> origin/dev
    if action == "start":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        if not dev:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve {remote}/{dev_branch} (fetch failed?)."}
        plan = {**base, "base_sha": dev, "would_create": f"worktree {wt_path} on {branch} @ {dev[:9]}"}
        if not confirm:
            return {**plan, "status": "planned", "exit_code": 0,
                    "message": f"will fork {branch} off {remote}/{dev_branch} ({dev[:9]}) at "
                               f"{wt_path}. Pass confirm=True. Then work THERE + commit; "
                               "integrate with action='integrate'."}
        rc, out, err = git("worktree", "add", wt_path, "-b", branch, f"{remote}/{dev_branch}")
        if rc != 0:
            return {**plan, "status": "error", "exit_code": 1,
                    "error": f"worktree add failed: {err.strip() or out.strip()}"}
        return {**plan, "status": "started", "exit_code": 0,
                "message": f"created {wt_path} on {branch}. Work there (cd {wt_path}), commit on "
                           f"{branch}, then noctus.dev.task_branch action='integrate' slug='{slug}'."}

    # ── INTEGRATE ── rebase onto origin/dev → FF-push HEAD→dev (retry on race)
    if action == "integrate":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        head = _resolve(git, branch)
        if not dev or not head:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve {remote}/{dev_branch} or {branch}."}
        ahead = _commits(git, dev, head)
        if not ahead and _is_ancestor(git, head, dev):
            return {**base, "status": "up_to_date", "exit_code": 0, "dev_sha": dev,
                    "message": f"{branch} has nothing {remote}/{dev_branch} lacks — nothing to integrate."}
        behind = _commits(git, head, dev)
        plan = {**base, "dev_sha": dev, "branch_sha": head,
                "ahead": len(ahead), "behind": len(behind), "incoming_commits": ahead[:20]}
        if not confirm:
            return {**plan, "status": "planned", "exit_code": 0,
                    "message": (f"will rebase {branch} onto {remote}/{dev_branch} "
                                f"(behind {len(behind)}) then FF-push {len(ahead)} commit(s) → "
                                f"{dev_branch} (retry on concurrent-push race). Pass confirm=True.")}
        # ACT — rebase-then-push loop; fetch fresh each iteration (the race).
        for attempt in range(1, max_retries + 1):
            git("fetch", remote, "--quiet")
            rc, out, err = git("rebase", f"{remote}/{dev_branch}", cwd=wt_path)
            if rc != 0:
                # surface the conflict loudly, restore a clean worktree — never
                # auto-resolve, never leave a half-rebase behind.
                _rc2, cout, _ce = git("diff", "--name-only", "--diff-filter=U", cwd=wt_path)
                conflicted = [ln.strip() for ln in cout.splitlines() if ln.strip()]
                git("rebase", "--abort", cwd=wt_path)
                return {**plan, "status": "conflict", "exit_code": 1, "conflicted_files": conflicted,
                        "message": (f"rebase of {branch} onto {remote}/{dev_branch} hit conflicts "
                                    f"in {conflicted or 'unknown files'}; aborted to keep the "
                                    "worktree clean. Resolve manually in the worktree, then re-run "
                                    "integrate.")}
            rc, out, err = git("push", remote, f"HEAD:refs/heads/{dev_branch}", cwd=wt_path)
            if rc == 0:
                new_dev = _resolve(git, f"{remote}/{dev_branch}")
                new_head = _resolve(git, branch)
                return {**plan, "status": "integrated", "exit_code": 0, "attempts": attempt,
                        "new_dev_sha": new_dev, "verified": new_dev == new_head,
                        "message": (f"integrated {len(ahead)} commit(s) to {dev_branch} "
                                    f"(attempt {attempt}). Tear down: action='cleanup' slug='{slug}'.")}
            # non-FF: a peer pushed between rebase and push → loop, re-fetch+rebase
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"could not FF-push to {dev_branch} after {max_retries} attempts "
                         "(persistent concurrent pushes). Retry integrate."}

    # ── CLEANUP ── remove worktree (refuse-if-dirty) → prune → delete merged branch
    git("fetch", remote, "--quiet")
    dev = _resolve(git, f"{remote}/{dev_branch}")
    head = _resolve(git, branch)
    merged = bool(dev and head and _is_ancestor(git, head, dev))
    if head and not merged:
        return {**base, "status": "blocked", "exit_code": 1, "dev_sha": dev, "branch_sha": head,
                "reason": f"{branch} has commit(s) not on {remote}/{dev_branch} — integrate first "
                          "(refusing to delete unintegrated work)."}
    plan = {**base, "branch_merged": merged}
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": f"will remove worktree {wt_path} (refuses if dirty) + delete merged "
                           f"branch {branch}. Pass confirm=True."}
    rc, out, err = git("worktree", "remove", wt_path)
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"worktree remove refused (dirty? integrate or discard first): "
                         f"{err.strip() or out.strip()}"}
    git("worktree", "prune")
    rc, out, err = git("branch", "-d", branch)
    if rc != 0:
        return {**plan, "status": "partial", "exit_code": 1, "worktree_removed": True,
                "error": f"worktree removed but branch -d refused (unmerged?): "
                         f"{err.strip() or out.strip()}"}
    return {**plan, "status": "cleaned", "exit_code": 0, "worktree_removed": True, "branch_deleted": True,
            "message": f"removed {wt_path} + deleted {branch}. Back on {dev_branch} baseline."}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.task_branch",
        description=(
            "Run the self-branching-mode per-task git lifecycle (KB § PATTERNS/"
            "self-branching-mode.md): a peer terminal-agent self-isolates any "
            "WRITING task in a per-task worktree off origin/dev, then integrates "
            "straight to origin/dev — never switching the shared checkout under a "
            "sibling (§9a). action='status' (default) lists active self-branch "
            "worktrees + ahead/behind vs origin/dev (read-only); action='start' "
            "slug= forks a worktree on feat/<slug> off origin/dev; action="
            "'integrate' slug= rebases onto origin/dev then FF-pushes to dev "
            "(retry on the concurrent-push race; a rebase conflict is aborted + "
            "surfaced, never auto-resolved); action='cleanup' slug= removes the "
            "worktree (refuses if dirty) + deletes the merged branch. Writes are "
            "DRY-RUN by default — pass confirm=True. Pushes ONLY to dev (main/"
            "prod move via noctus.dev.release); FF/rebase-only, never force/reset/"
            "switch. status: status|planned|started|integrated|conflict|"
            "up_to_date|cleaned|partial|blocked|error."
        ),
    )
    def _task_branch(
        action: str = "status",
        slug: str | None = None,
        confirm: bool = False,
    ) -> dict:
        return task_branch(action=action, slug=slug, confirm=confirm)


__all__ = ["task_branch", "_ALLOWED_GIT", "_BANNED_TOKENS", "_assert_push_targets_dev",
           "_parse_worktrees", "register"]
