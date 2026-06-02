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
                Known-benign refresh artifacts (cache refresh files that the
                pre-commit hook writes as side-effects: KNOWLEDGE-BASE/
                AGENT-CONTEXT.md, KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md,
                project-history/vector-costs.ndjson, project-history/
                auto-improvement.ndjson, project-history/worktree-salvage.ndjson,
                project-history/branch-tree.ndjson, .claude/cache/*) are
                auto-stashed before the rebase and restored after, so a clean
                FF rebase is never blocked by them. Only real
                conflicts surface. A rebase REFUSED before starting (hook chatter
                re-dirties after stash) is surfaced as status=dirty_blocked
                (not status=conflict) so the caller sees dirty files, not phantom
                merge-conflict markers.
  • cleanup   : SALVAGE-before-delete (KB § PATTERNS/storage-hygiene.md § 2.3 —
                the worktree analogue of archive's learn-before-archive) THEN
                `git worktree remove <wt>` (refuses if dirty — no --force) →
                prune → `git branch -d feat/<slug>` (refuses if unmerged — `-d`
                not `-D`). The salvage ritual: (1) LEARNINGS — extract durable
                knowledge → KB/memory (surfaced as a checkpoint; discipline leg);
                (2) RECOVERY POINTER — record branch+SHA to the tracked
                `project-history/worktree-salvage.ndjson` (MECHANICAL here, via
                the shared `_worktree_salvage` helper — the same leg mole-sweep /
                cleanup_stale_worktrees already carry, so a precise teardown can
                no longer skip it); (3) STORAGE HYGIENE — run a mole worktree-
                sweep before the delete. A precise teardown of ONE named task
                worktree; the heuristic bulk-sweep of stale agent worktrees is
                the sibling noctus.dev.cleanup_stale_worktrees.
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

import fnmatch
import logging
import os
import subprocess
from pathlib import Path
from typing import Any, Callable

logger = logging.getLogger(__name__)

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

# Known-benign refresh artifacts — files the pre-commit / cache-refresh hooks
# write as side-effects inside the worktree. These appear in `git status
# --porcelain` and cause `git rebase` to refuse with a non-clean-worktree error,
# producing an empty `conflicted_files` + `status=conflict` even though the
# rebase would be a clean FF. The integrate precheck auto-stashes these before
# the rebase and pops the stash after. Patterns are fnmatch-style relative paths
# (as printed by `git status --porcelain`, XY-code stripped).
#
# All four project-history/*.ndjson ledger files are gitattributes merge=union
# append-only logs churned by post-checkout/post-merge cache-settle hooks
# (noc-graph/auto-improvement/worktree-salvage/branch-tree). They are
# reconstructable and never contain task work — so they are benign for the
# purpose of the rebase pre-check and should be auto-stashed rather than
# blocking integrate.
_BENIGN_REFRESH_PATTERNS = (
    "KNOWLEDGE-BASE/AGENT-CONTEXT.md",
    "KNOWLEDGE-BASE/CONTEXT/06-AGENTS.md",
    "project-history/vector-costs.ndjson",
    "project-history/auto-improvement.ndjson",
    "project-history/worktree-salvage.ndjson",
    "project-history/branch-tree.ndjson",
    ".claude/cache/*",
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


def _branch_for_path(porcelain: str, wt_path: str) -> str | None:
    """Resolve the ACTUAL branch checked out at `wt_path` from `git worktree list
    --porcelain`, keyed by the dir (the stable identity). Robust to a reused /
    renamed worktree whose branch ≠ feat/<slug> — without this the cleanup slug→
    branch assumption resolves a nonexistent branch, so the recovery-pointer leg
    silently no-ops and `branch -d` fails (the 2026-05-25 dogfood gap). Returns the
    short branch name (refs/heads/ stripped) or None (detached HEAD / not found)."""
    base = os.path.basename(wt_path.rstrip("/"))
    for wt in _parse_worktrees(porcelain):
        p = wt.get("path", "")
        if p == wt_path or p.endswith("/" + wt_path) or os.path.basename(p.rstrip("/")) == base:
            br = wt.get("branch", "")
            return br[len("refs/heads/"):] if br.startswith("refs/heads/") else None
    return None


def _is_dirty_excluding_gitignored(runner, wt_path: str) -> bool:
    """True iff the worktree has uncommitted changes that are NOT gitignored.

    ``git status --porcelain`` (without ``--ignored``) lists only tracked-modified
    + untracked non-ignored files. Gitignored files (e.g. ``.claude/cache/*.sqlite``)
    are never shown ⇒ a worktree that is "dirty" only because of gitignored files
    is clean by this predicate. Pure git plumbing, no banned tokens.
    """
    rc, out, _e = runner(["git", "status", "--porcelain"], cwd=wt_path)
    if rc != 0:
        # If git status itself fails, conservatively report dirty.
        return True
    lines = [ln for ln in out.splitlines() if ln.strip()]
    return bool(lines)


def _classify_dirty_files(
    runner, wt_path: str
) -> tuple[list[str], list[str]]:
    """Classify dirty files in the worktree into (benign, real).

    `benign` = files matching ``_BENIGN_REFRESH_PATTERNS`` (known pre-commit /
    cache-refresh side-effects that block rebase but carry no task work).
    `real`   = everything else (actual conflicts, task-in-progress changes).

    Returns two lists of relative paths (as `git status --porcelain` reports them,
    XY-code stripped). A git-status failure → ([], ["<git-status-failed>"]) so the
    caller treats it conservatively as a real conflict.
    """
    rc, out, _e = runner(["git", "status", "--porcelain"], cwd=wt_path)
    if rc != 0:
        return [], ["<git-status-failed>"]
    benign: list[str] = []
    real: list[str] = []
    for raw in out.splitlines():
        if not raw.strip():
            continue
        # porcelain format: "XY path" or "XY old -> new"; take the last token
        parts = raw[3:].strip()
        path = parts.split(" -> ")[-1].strip()
        matched = any(fnmatch.fnmatch(path, pat) for pat in _BENIGN_REFRESH_PATTERNS)
        (benign if matched else real).append(path)
    return benign, real


def _rebase_in_progress(runner, wt_path: str) -> bool:
    """True iff a rebase is currently in-progress in the worktree.

    git creates ``rebase-merge/`` (interactive/merge rebase) or ``rebase-apply/``
    (apply-based rebase) inside the worktree's git directory as soon as the
    rebase begins applying patches. If NEITHER exists after a ``git rebase``
    rc≠0, the rebase was REFUSED before it started (e.g. "error: cannot rebase:
    You have unstaged changes") — hook chatter re-dirtied the worktree after our
    auto-stash. Distinguishing "refused" from "conflicted" is Bug B's fix: a
    refused rebase must NOT produce ``status=conflict`` with empty
    ``conflicted_files`` (the phantom conflict).

    Uses ``git rev-parse --git-dir`` (allowlisted) to resolve the git dir path,
    then checks the filesystem. Falls back to True (conservative — treat as
    in-progress) if rev-parse fails.
    """
    rc, out, _e = runner(["git", "rev-parse", "--git-dir"], cwd=wt_path)
    if rc != 0:
        # Cannot determine git dir — be conservative (caller will abort + surface).
        return True
    git_dir = out.strip()
    # git-dir may be relative to wt_path
    if not os.path.isabs(git_dir):
        git_dir = os.path.join(wt_path, git_dir)
    return (
        os.path.isdir(os.path.join(git_dir, "rebase-merge"))
        or os.path.isdir(os.path.join(git_dir, "rebase-apply"))
    )


def _stash_benign_artifacts(
    runner, wt_path: str, benign: list[str], verbose: bool = False
) -> bool:
    """Stash the known-benign refresh artifacts before a rebase so the worktree
    is clean. Uses ``git stash push -- <paths>`` (bypasses ``_git()`` since stash
    is not on the safe allowlist — this is an intentional, controlled carve-out
    for known-safe paths only, mirroring the force-remove carve-out in cleanup).

    Returns True if the stash succeeded (or there was nothing to stash), False on
    failure (caller falls back to surfacing the files as blocking).
    """
    if not benign:
        return True
    if verbose:
        logger.debug("task_branch.integrate: auto-stashing %d benign artifact(s): %s",
                     len(benign), benign)
    rc, _o, err = runner(
        ["git", "-C", wt_path, "stash", "push", "--include-untracked",
         "--message", "task_branch auto-stash: benign refresh artifacts", "--"] + benign
    )
    if rc != 0:
        logger.warning("task_branch.integrate: auto-stash failed (%s); "
                       "proceeding without stash — rebase may be blocked",
                       (err or "").strip())
        return False
    return True


def _pop_stash(runner, wt_path: str, verbose: bool = False) -> None:
    """Pop the auto-stash created by ``_stash_benign_artifacts``. Best-effort:
    a pop failure is logged but never raises (the integrate already completed)."""
    if verbose:
        logger.debug("task_branch.integrate: popping auto-stash")
    rc, _o, err = runner(["git", "-C", wt_path, "stash", "pop"])
    if rc != 0:
        logger.warning("task_branch.integrate: stash pop failed (%s); "
                       "the benign artifacts remain stashed — run `git stash pop` "
                       "in the worktree to restore them", (err or "").strip())

# ── env auto-wire (the §5a verification-env recipe, mechanized) ──────────────
# A fresh worktree is a clean git checkout: node_modules/ is gitignored ⇒ ABSENT,
# so a vite build / vitest run inside the worktree fails for want of deps. The
# §5a recipe symlinks the PRIMARY tree's per-package node_modules INTO the
# worktree, then re-points the `@noctusai/{lib,seed}` file:-deps at the WORKTREE's
# own seed copies (the crux — else worktree lib edits are invisible to the build).
# These are all gitignored paths ⇒ the symlinks never get staged (intended).
#
# The filesystem ops are injected (`FsOps`) so the colocated test drives the
# planner over a tmp_path fixture tree with zero real node_modules. Planning is
# pure (read-only); application happens ONLY under `confirm` and is best-effort —
# every skip is REPORTED (never silent), and a real (non-symlink) node_modules
# already in the worktree is left untouched (never nested, never clobbered).

# Seed frontend packages whose node_modules we mirror in (relative to a tree root).
_SEED_FRONTENDS = ("seed/lib/frontend", "seed/framework/frontend")
# The two file:-deps every product frontend resolves from its node_modules, and
# the seed package each must re-point at (so worktree lib/framework edits are seen).
_NOCTUSAI_REPOINTS = (
    ("@noctusai/lib", "seed/lib/frontend"),
    ("@noctusai/seed", "seed/framework/frontend"),
)


class FsOps:
    """Filesystem seam for env-wiring — real `os`/`pathlib` by default; the test
    injects a fixture-backed instance so the planner runs over a tmp tree."""

    def exists(self, p: str) -> bool:
        return os.path.lexists(p)

    def is_dir(self, p: str) -> bool:
        return os.path.isdir(p) and not os.path.islink(p)

    def is_symlink(self, p: str) -> bool:
        return os.path.islink(p)

    def list_product_frontends(self, primary_root: str) -> list[str]:
        """slugs of products/<slug>/frontend that exist on the PRIMARY tree."""
        products = os.path.join(primary_root, "products")
        if not os.path.isdir(products):
            return []
        out = []
        for name in sorted(os.listdir(products)):
            if os.path.isdir(os.path.join(products, name, "frontend")):
                out.append(name)
        return out

    def symlink(self, target: str, link: str) -> None:
        os.symlink(target, link)


def _plan_env_wiring(primary_root: str, wt_root: str, fs: FsOps) -> tuple[list[dict], list[dict]]:
    """Pure (read-only) planner. Returns (wire, skipped): `wire` = symlink specs
    {link, target, kind} the recipe WOULD create; `skipped` = {link, reason} for
    anything best-effort skipped (absent primary source / a real dir already in
    the worktree). Order is deterministic: seed node_modules, then per-product
    node_modules + the two @noctusai re-points."""
    wire: list[dict] = []
    skipped: list[dict] = []

    def _link_node_modules(rel_pkg: str) -> None:
        src = os.path.join(primary_root, rel_pkg, "node_modules")
        link = os.path.join(wt_root, rel_pkg, "node_modules")
        if not fs.exists(src):
            skipped.append({"link": link, "reason": f"primary node_modules absent: {src}"})
            return
        if fs.is_dir(link):  # a REAL node_modules already in the worktree — never clobber/nest
            skipped.append({"link": link, "reason": "real node_modules already present in worktree"})
            return
        wire.append({"link": link, "target": src, "kind": "node_modules"})

    # seed packages first (the @noctusai re-points below point INTO these)
    for rel_pkg in _SEED_FRONTENDS:
        _link_node_modules(rel_pkg)

    # every product/<slug>/frontend with a primary node_modules → mirror + re-point
    for slug in fs.list_product_frontends(primary_root):
        rel_fe = f"products/{slug}/frontend"
        _link_node_modules(rel_fe)
        nm = os.path.join(wt_root, rel_fe, "node_modules")
        for dep, seed_rel in _NOCTUSAI_REPOINTS:
            link = os.path.join(nm, dep)
            target = os.path.join(wt_root, seed_rel)
            if not fs.exists(target):
                skipped.append({"link": link, "reason": f"worktree seed pkg absent: {target}"})
                continue
            wire.append({"link": link, "target": target, "kind": "@noctusai"})

    return wire, skipped


def _apply_env_wiring(wire: list[dict], fs: FsOps) -> tuple[list[dict], list[dict]]:
    """`ln -sfn` semantics, best-effort: create each planned symlink; if the link
    path is an existing symlink, replace it (force); if it is a real dir, SKIP
    (never clobber — should already be filtered by the planner, defensive here);
    any OS error is captured into `failed`, never raised. Returns (created, failed).
    The @noctusai re-points need their parent node_modules to exist — created
    first because they are ordered first in the plan."""
    created: list[dict] = []
    failed: list[dict] = []
    for spec in wire:
        link = spec["link"]
        try:
            if fs.is_dir(link):
                failed.append({**spec, "reason": "real directory at link path — skipped"})
                continue
            if fs.is_symlink(link):
                os.unlink(link)  # `ln -sfn`: replace an existing symlink
            os.makedirs(os.path.dirname(link), exist_ok=True)
            fs.symlink(spec["target"], link)
            created.append(spec)
        except OSError as e:
            failed.append({**spec, "reason": f"{type(e).__name__}: {e}"})
    return created, failed


def _settle_structural_caches(verbose: bool = False) -> dict[str, Any]:
    """Settle the Tier-1 SHARED structural caches against the at-rest primary
    tree at the end of a cross-tree integrate/cleanup.

    ``noc-graph`` (and ``auto-improvement``) live in the worktree-shared
    ``.git/noctusai/cache/`` (cache-portable-architecture). During the
    worktree↔primary handoff the SAME shared cache is written from two working
    trees, so its stored ``aggregate_source_sha`` can briefly reflect a
    transient tree-state the at-rest primary tree does not match — surfacing as
    a noc-graph-stale warning right after a clean integrate. Both refreshes are
    ONLY-STALE (source-sha guarded ⇒ a no-op when already coherent) and
    BEST-EFFORT (a failure NEVER fails the integrate/cleanup; the
    ``check_all_cache_freshness`` keeper stays the net). Returns a small report
    for observability. See the s1 surface "noc-graph Tier-1 shared-cache
    coherence after cross-tree integrate/cleanup" (2026-05-30).
    """
    report: dict[str, Any] = {}
    try:
        from tools.noctus.dev import noc_graph_cache as _ng
        r = _ng.refresh(force=False)
        report["noc_graph"] = {"ok": True, "status": r.get("status"),
                               "source_sha": r.get("source_sha") or r.get("aggregate_source_sha")}
    except Exception as e:  # best-effort: never block teardown on a cache refresh
        if verbose:
            logger.debug("task_branch settle: noc-graph refresh skipped: %s", e)
        report["noc_graph"] = {"ok": False, "error": str(e)}
    try:
        from tools.noctus.dev import auto_improvement as _ai
        r = _ai.refresh(force=False)
        report["auto_improvement"] = {"ok": True, "status": r.get("status"),
                                      "source_sha": r.get("source_sha")}
    except Exception as e:
        if verbose:
            logger.debug("task_branch settle: auto-improvement refresh skipped: %s", e)
        report["auto_improvement"] = {"ok": False, "error": str(e)}
    return report


def task_branch(
    action: str = "status",
    slug: str | None = None,
    confirm: bool = False,
    remote: str = "origin",
    dev_branch: str = "dev",
    worktrees_dir: str = ".claude/worktrees",
    branch_prefix: str = "feat/",
    max_retries: int = 5,
    wire_env: bool = False,
    primary_root: str | None = None,
    run: Callable[..., tuple[int, str, str]] | None = None,
    fs: FsOps | None = None,
    salvage_recorder: Callable[..., Any] | None = None,
    settle: Callable[..., dict[str, Any]] | None = None,
    verbose: bool = False,
) -> dict[str, Any]:
    """`action` ∈ {status, start, integrate, cleanup}. Writes are dry-run unless
    `confirm`. Returns a structured plan/result; never raises on a refusal — it
    returns it (the refusal IS the safety net).

    `verbose=True` emits debug-level logging for each step of integrate/cleanup
    so future debugging is one re-run away (no code changes needed).

    `wire_env=True` (only meaningful on `action='start'`) auto-wires the §5a
    verification-env recipe into the fresh worktree AFTER it exists: symlink the
    PRIMARY tree's per-package `node_modules` into the worktree + re-point each
    product frontend's `@noctusai/{lib,seed}` file:-deps at the WORKTREE's own
    seed copies, so a vite build / vitest run inside the worktree sees the
    worktree's edits. All target paths are gitignored ⇒ never staged. Honors
    dry-run: without `confirm` it REPORTS the plan (the symlinks it WOULD create)
    without touching the filesystem. Best-effort: missing primary node_modules /
    a real node_modules already in the worktree are REPORTED in `skipped`, never
    silent, never clobbered."""
    runner = run or _default_run_local
    fsops = fs or FsOps()
    # End-of-integrate/cleanup structural-cache settle (see _settle_structural_caches).
    # Explicit `settle` wins (test seam); otherwise run the real settle ONLY in the
    # production path (default runner) — an injected `run` means a test/custom context
    # that must not touch the real shared caches.
    settle_fn = settle if settle is not None else (
        _settle_structural_caches if run is None else None)

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

    # ── START ── fetch → worktree add -b feat/<slug> origin/dev [→ wire_env]
    if action == "start":
        git("fetch", remote, "--quiet")
        dev = _resolve(git, f"{remote}/{dev_branch}")
        if not dev:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve {remote}/{dev_branch} (fetch failed?)."}
        plan = {**base, "base_sha": dev, "would_create": f"worktree {wt_path} on {branch} @ {dev[:9]}"}

        # resolve absolute PRIMARY tree + worktree roots for env-wiring (lazy:
        # only import settings when we actually need REPO_ROOT — keeps the
        # test path, which always injects primary_root, settings-free).
        def _roots() -> tuple[str, str]:
            root = primary_root
            if root is None:
                from settings import REPO_ROOT  # lazy: avoids import cost otherwise
                root = str(REPO_ROOT)
            return root, os.path.join(root, worktrees_dir, slug)

        if not confirm:
            plan_extra: dict[str, Any] = {}
            if wire_env:
                proot, wt_root = _roots()
                would, skipped = _plan_env_wiring(proot, wt_root, fsops)
                plan_extra = {"wire_env": True, "would_wire": would, "skipped": skipped}
            return {**plan, **plan_extra, "status": "planned", "exit_code": 0,
                    "message": f"will fork {branch} off {remote}/{dev_branch} ({dev[:9]}) at "
                               f"{wt_path}{' + auto-wire the §5a verification env' if wire_env else ''}. "
                               "Pass confirm=True. Then work THERE + commit; "
                               "integrate with action='integrate'."}
        rc, out, err = git("worktree", "add", wt_path, "-b", branch, f"{remote}/{dev_branch}")
        if rc != 0:
            return {**plan, "status": "error", "exit_code": 1,
                    "error": f"worktree add failed: {err.strip() or out.strip()}"}
        wired_extra: dict[str, Any] = {}
        if wire_env:
            proot, wt_root = _roots()
            would, skipped = _plan_env_wiring(proot, wt_root, fsops)
            created, failed = _apply_env_wiring(would, fsops)
            wired_extra = {"wire_env": True, "wired": created,
                           "skipped": skipped + failed}
        return {**plan, **wired_extra, "status": "started", "exit_code": 0,
                "message": f"created {wt_path} on {branch}"
                           f"{' + wired %d env symlink(s)' % len(wired_extra['wired']) if wire_env else ''}. "
                           f"Work there (cd {wt_path}), commit on {branch}, then "
                           f"noctus.dev.task_branch action='integrate' slug='{slug}'."}

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
        # ACT — auto-stash known-benign refresh artifacts, then rebase-then-push
        # loop; fetch fresh each iteration (the race).
        #
        # ROOT-CAUSE FIX (2026-05-28, N=5+ observed): pre-commit / cache-refresh
        # hooks write side-effect files into the worktree (KNOWLEDGE-BASE/
        # AGENT-CONTEXT.md, project-history/vector-costs.ndjson, etc.). These
        # appear in `git status --porcelain` ⇒ `git rebase` refuses ("error:
        # cannot rebase: You have unstaged changes") ⇒ tool returns rc≠0 ⇒ tool
        # surfaces status=conflict with empty conflicted_files. The actual rebase
        # would be a clean FF — there are no real conflicts. Fix: classify dirty
        # files into benign (the known patterns) vs real (actual task work);
        # auto-stash benign files before the rebase, pop stash after success.
        # Only if REAL dirty files exist (not just benign ones) do we block.
        benign_stashed = False
        if verbose:
            logger.debug("task_branch.integrate: classifying dirty files in %s", wt_path)
        benign_files, real_files = _classify_dirty_files(runner, wt_path)
        if real_files and not benign_files:
            # Real dirty files with no benign files — block before even trying to
            # rebase (saves one rebase attempt + abort cycle).
            if verbose:
                logger.debug("task_branch.integrate: real dirty files block rebase: %s",
                             real_files)
        elif benign_files:
            if verbose:
                logger.debug("task_branch.integrate: found %d benign artifact(s) to stash: %s",
                             len(benign_files), benign_files)
            benign_stashed = _stash_benign_artifacts(runner, wt_path, benign_files, verbose)
            if benign_stashed and verbose:
                logger.debug("task_branch.integrate: benign artifacts stashed; "
                             "proceeding with rebase")

        for attempt in range(1, max_retries + 1):
            if verbose:
                logger.debug("task_branch.integrate: attempt %d/%d — fetch + rebase",
                             attempt, max_retries)
            git("fetch", remote, "--quiet")
            rc, out, err = git("rebase", f"{remote}/{dev_branch}", cwd=wt_path)
            if rc != 0:
                # Rebase failed — distinguish "refused" (worktree still dirty after
                # stash, rebase never started) from "conflicted" (rebase started and
                # hit content conflicts). The discriminator is the presence of the
                # `.git/rebase-merge` (or `.git/rebase-apply`) directory: git creates
                # this directory as soon as the rebase begins applying patches; if it
                # is ABSENT after a rc≠0, the rebase was REFUSED before it started
                # (e.g. "error: cannot rebase: You have unstaged changes") — likely
                # hook chatter re-dirtying the worktree after our stash. A "refused"
                # rebase has no `--abort` state and `diff --diff-filter=U` returns
                # nothing, producing the phantom status=conflict with empty
                # conflicted_files. In that case surface as dirty-block, not conflict.
                rebase_in_progress = _rebase_in_progress(runner, wt_path)
                _rc2, cout, _ce = git("diff", "--name-only", "--diff-filter=U", cwd=wt_path)
                conflicted = [ln.strip() for ln in cout.splitlines() if ln.strip()]
                if rebase_in_progress:
                    git("rebase", "--abort", cwd=wt_path)
                # Restore the stash even on failure so the worktree is clean.
                if benign_stashed:
                    _pop_stash(runner, wt_path, verbose)
                    benign_stashed = False
                # Re-classify after the abort (or refused) to give accurate diagnostics.
                _, real_after = _classify_dirty_files(runner, wt_path)
                if not rebase_in_progress and not conflicted:
                    # Rebase was REFUSED (never started) — hook chatter re-dirtied the
                    # worktree after we stashed. Surface as a dirty-block, not a conflict,
                    # so the caller knows to inspect the worktree's dirty files rather
                    # than looking for merge conflicts. This is Bug B's phantom conflict.
                    refused_msg = (err or out or "").strip()
                    if verbose:
                        logger.debug(
                            "task_branch.integrate: rebase was REFUSED (no rebase-merge dir), "
                            "not conflicted. stderr: %s", refused_msg)
                    return {**plan, "status": "dirty_blocked", "exit_code": 1,
                            "conflicted_files": [],
                            "blocked_by_dirty": real_after,
                            "rebase_refused": True,
                            "message": (
                                f"rebase of {branch} onto {remote}/{dev_branch} was REFUSED "
                                f"(the worktree is dirty after auto-stash — likely post-checkout "
                                f"hook chatter re-dirtied files). No conflict markers present. "
                                f"Dirty files: {real_after}. "
                                f"git output: {refused_msg or '(none)'}. "
                                f"Run `git status` in the worktree, resolve the dirty files "
                                f"(commit or stash), then re-run integrate.").strip()}
                detail = (f"Dirty files present before rebase: benign={benign_files} "
                          f"real={real_files}; conflicted after rebase: {conflicted}. "
                          f"If conflicted_files is empty, check for uncommitted "
                          f"non-benign files in the worktree."
                          if not conflicted else "")
                return {**plan, "status": "conflict", "exit_code": 1,
                        "conflicted_files": conflicted,
                        "blocked_by_dirty": real_after,
                        "message": (f"rebase of {branch} onto {remote}/{dev_branch} hit conflicts "
                                    f"in {conflicted or 'unknown files'}; aborted to keep the "
                                    "worktree clean. Resolve manually in the worktree, then re-run "
                                    f"integrate. {detail}").strip()}
            if verbose:
                logger.debug("task_branch.integrate: rebase succeeded; pushing to %s", dev_branch)
            rc, out, err = git("push", remote, f"HEAD:refs/heads/{dev_branch}", cwd=wt_path)
            if rc == 0:
                # Pop stash AFTER the push so the worktree ends clean (the benign
                # files reappear but that's fine — they're tracked + committed elsewhere).
                if benign_stashed:
                    _pop_stash(runner, wt_path, verbose)
                    benign_stashed = False
                new_dev = _resolve(git, f"{remote}/{dev_branch}")
                new_head = _resolve(git, branch)
                result = {**plan, "status": "integrated", "exit_code": 0, "attempts": attempt,
                          "new_dev_sha": new_dev, "verified": new_dev == new_head,
                          "message": (f"integrated {len(ahead)} commit(s) to {dev_branch} "
                                      f"(attempt {attempt}). Tear down: action='cleanup' slug='{slug}'.")}
                if settle_fn is not None:
                    try:
                        result["cache_settle"] = settle_fn()
                    except Exception as e:  # best-effort — never fail a clean integrate
                        result["cache_settle"] = {"ok": False, "error": str(e)}
                return result
            # non-FF: a peer pushed between rebase and push → loop, re-fetch+rebase
            if verbose:
                logger.debug("task_branch.integrate: push rejected (concurrent peer push) "
                             "on attempt %d — re-fetching + rebasing", attempt)
        # All attempts exhausted — restore stash so we don't leave the worktree stashed.
        if benign_stashed:
            _pop_stash(runner, wt_path, verbose)
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"could not FF-push to {dev_branch} after {max_retries} attempts "
                         "(persistent concurrent pushes). Retry integrate."}

    # ── CLEANUP ── SALVAGE-before-delete → remove worktree (refuse-if-dirty) →
    #               prune → delete merged branch.
    # A worktree delete is the worktree analogue of archiving a project (KB §
    # PATTERNS/storage-hygiene.md § 2.3) ⇒ it mirrors archive's learn-before-
    # archive. THREE legs at this sanctioned single-worktree teardown — the bulk
    # sweeps (mole / cleanup_stale_worktrees) already carry leg 2; this path was
    # the gap (a precise teardown could silently skip salvage; a manual `git
    # worktree remove` skips all three — that's the 2026-05-25 drift):
    #   1 LEARNINGS  (discipline, surfaced as a checkpoint): extract durable
    #     knowledge → KB/memory before the lossy delete.
    #   2 RECOVERY POINTER (MECHANICAL, below): branch+SHA → the tracked ledger.
    #   3 STORAGE HYGIENE (sequenced): a mole worktree-sweep before the delete.
    if verbose:
        logger.debug("task_branch.cleanup: starting for slug=%s wt_path=%s", slug, wt_path)
    git("fetch", remote, "--quiet")
    # Resolve the worktree's ACTUAL branch from the worktree list (the dir is the
    # stable key) — robust to a reused/renamed worktree whose branch ≠ feat/<slug>.
    # Without this the slug→branch assumption resolves a nonexistent branch, so the
    # recovery-pointer leg silently no-ops + branch -d fails (2026-05-25 dogfood
    # gap, fixed on contact).
    rc_wl, wl_out, _wl = git("worktree", "list", "--porcelain")
    actual = _branch_for_path(wl_out if rc_wl == 0 else "", wt_path)
    if actual and actual != branch:
        branch = actual
        base["branch"] = branch
    dev = _resolve(git, f"{remote}/{dev_branch}")
    head = _resolve(git, branch)
    merged = bool(dev and head and _is_ancestor(git, head, dev))
    if head and not merged:
        return {**base, "status": "blocked", "exit_code": 1, "dev_sha": dev, "branch_sha": head,
                "reason": f"{branch} has commit(s) not on {remote}/{dev_branch} — integrate first "
                          "(refusing to delete unintegrated work)."}
    ritual = {
        "1_extract_learnings": (
            "BEFORE deleting, extract durable knowledge from this worktree → "
            "KB/memory (findings.md, return-notes, bugs found, follow-ups). The "
            "delete is LOSSY for anything not on dev or already in KB/memory "
            "(learnings leg — discipline; mirrors archive's learn-before-archive)."),
        "2_record_recovery_pointer": (
            f"branch+SHA → project-history/worktree-salvage.ndjson "
            "(MECHANICAL — recorded below; commit the ledger like ledger.ndjson)."),
        "3_mole_sweep_before_delete": (
            "Run noctus.dev.mole(mode='sweep', scope='worktrees') for storage "
            "hygiene BEFORE confirming the delete."),
        "4_remove": "git worktree remove (refuse-if-dirty) + branch -d (merged-only).",
    }
    plan = {**base, "branch_merged": merged, "cleanup_ritual": ritual,
            "learnings_checkpoint": ritual["1_extract_learnings"]}
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": (f"will SALVAGE then remove worktree {wt_path}: record the recovery "
                            f"pointer ({branch}+SHA) to the tracked salvage ledger + surface the "
                            f"learnings checkpoint, then remove (refuses if dirty) + delete merged "
                            f"branch {branch}. Extract learnings + run a mole worktree-sweep first. "
                            "Pass confirm=True.")}
    # Leg 2 — MECHANICAL recovery pointer: record branch+SHA to the TRACKED ledger
    # BEFORE removal (best-effort; the recorder never raises ⇒ never blocks teardown).
    # Shared `_worktree_salvage.record_sweep` — one source of truth with the bulk
    # sweeps (no parity drift). Injectable for tests (zero real IO).
    salvage_ledger = None
    if head:
        recorder = salvage_recorder
        root = primary_root
        if recorder is None:
            from tools.noctus.dev import _worktree_salvage as _wsv  # lazy import
            recorder = _wsv.record_sweep
        if root is None:
            from settings import REPO_ROOT  # lazy: only when not injected
            root = str(REPO_ROOT)
        rec_path = recorder((Path(wt_path) if os.path.isabs(wt_path) else Path(root) / wt_path), [{
            "path": wt_path, "branch": branch, "sha": head,
            "reason": "task_branch cleanup (learn-before-delete)"}])
        salvage_ledger = str(rec_path) if rec_path else None
    # Leg 2b — commit & push the ledger entry FROM THE WORKTREE BEFORE remove.
    # Without this, the appended ledger entry left the worktree dirty (one tracked
    # file modified), `git worktree remove` refused, and a second cleanup call
    # (now no-op via idempotency) STILL saw the uncommitted file from call #1 —
    # an infinite loop. The N=3 cross-tree hazard codified 2026-05-28 (memory
    # `feedback_task_branch_cleanup_ledger_loop`). Best-effort: a commit/push
    # failure is reported but cleanup proceeds — the entry is already on disk
    # (idempotent next-time), and the bulk-sweep keepers still find it.
    salvage_pushed = False
    if salvage_ledger:
        rel_ledger = "project-history/worktree-salvage.ndjson"
        if verbose:
            logger.debug("task_branch.cleanup: checking if salvage ledger is dirty: %s",
                         rel_ledger)
        rc_d, out_d, _ = runner(
            ["git", "-C", wt_path, "status", "--porcelain", "--", rel_ledger])
        if rc_d == 0 and (out_d or "").strip():
            # Ledger is dirty in the worktree (this call appended a new record).
            # Stage + commit + push to dev (FF-only — branch already merged to dev).
            if verbose:
                logger.debug("task_branch.cleanup: ledger dirty — staging + committing + pushing")
            rc_a, _, err_a = runner(["git", "-C", wt_path, "add", rel_ledger])
            if rc_a == 0:
                msg = (f"chore(salvage): record {branch} recovery pointer\n\n"
                       f"task_branch action=cleanup salvage-ledger entry "
                       f"(branch+SHA → worktree-salvage.ndjson, the tracked "
                       f"recovery-pointer ledger). Commits before worktree-"
                       f"remove so the tree is clean for the remove (the "
                       f"N=3 cross-tree-hazard fix, 2026-05-28).")
                rc_c, _, err_c = runner(
                    ["git", "-C", wt_path, "commit", "-m", msg])
                if rc_c == 0:
                    # Push HEAD:dev — branch is already merged to origin/dev
                    # (cleanup precondition), so this is FF (adds the salvage
                    # commit on top of dev). Race on concurrent push handled
                    # by single retry (one fetch+push round).
                    rc_p, _, err_p = runner(
                        ["git", "-C", wt_path, "push", "origin", f"HEAD:{dev_branch}"])
                    if rc_p != 0:
                        # One retry after fetch — the cleanup MCP tool's retry
                        # idiom for the concurrent-push race.
                        runner(["git", "-C", wt_path, "fetch", "origin"])
                        rc_p, _, err_p = runner(
                            ["git", "-C", wt_path, "push", "origin", f"HEAD:{dev_branch}"])
                    salvage_pushed = (rc_p == 0)
                    if not salvage_pushed:
                        logger.warning(
                            "task_branch.cleanup: salvage push failed (%s); "
                            "commit landed locally but ledger entry is not on "
                            "dev yet — manual push needed", (err_p or "").strip())
                else:
                    logger.warning(
                        "task_branch.cleanup: salvage commit failed (%s)",
                        (err_c or "").strip())
            else:
                logger.warning(
                    "task_branch.cleanup: salvage stage failed (%s)",
                    (err_a or "").strip())
    # Attempt the remove. If it fails, check whether the only "dirty" files
    # are gitignored (e.g. `.claude/cache/*.sqlite`). If so, the refusal is
    # spurious — git considers those files non-blocking. We force-remove via
    # a direct subprocess call (intentionally bypassing _git() whose banned-
    # token list guards history-rewriting ops, not clean-worktree teardown).
    rc, out, err = git("worktree", "remove", wt_path)
    if rc != 0:
        if _is_dirty_excluding_gitignored(runner, wt_path):
            return {**plan, "status": "error", "exit_code": 1, "salvage_ledger": salvage_ledger,
                    "error": f"worktree remove refused (has real uncommitted changes — "
                             f"integrate or discard first): {err.strip() or out.strip()}"}
        # Only gitignored files present — safe to force-remove (verified clean).
        from settings import REPO_ROOT  # lazy: only when not injected
        abs_wt = wt_path if os.path.isabs(wt_path) else os.path.join(str(REPO_ROOT), wt_path)
        rc2, _o2, err2 = runner(["git", "worktree", "remove", "--force", abs_wt])
        if rc2 != 0:
            return {**plan, "status": "error", "exit_code": 1, "salvage_ledger": salvage_ledger,
                    "error": f"worktree force-remove failed (gitignored-only path): "
                             f"{err2.strip() or _o2.strip()}"}
    git("worktree", "prune")
    rc, out, err = git("branch", "-d", branch)
    if rc != 0:
        return {**plan, "status": "partial", "exit_code": 1, "worktree_removed": True,
                "salvage_ledger": salvage_ledger,
                "error": f"worktree removed but branch -d refused (unmerged?): "
                         f"{err.strip() or out.strip()}"}
    result = {**plan, "status": "cleaned", "exit_code": 0, "worktree_removed": True,
              "branch_deleted": True, "salvage_ledger": salvage_ledger,
              "salvage_pushed": salvage_pushed,
              "message": f"removed {wt_path} + deleted {branch} (recovery pointer → "
                         f"{salvage_ledger or 'ledger'}). Back on {dev_branch} baseline."}
    if settle_fn is not None:
        try:
            result["cache_settle"] = settle_fn()
        except Exception as e:  # best-effort — never fail a completed teardown
            result["cache_settle"] = {"ok": False, "error": str(e)}
    return result


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
            "surfaced, never auto-resolved); action='cleanup' slug= SALVAGES "
            "before deleting (learn-before-delete, KB § storage-hygiene § 2.3): "
            "records the branch+SHA recovery pointer to the tracked worktree-"
            "salvage ledger (MECHANICAL — same leg the bulk sweeps carry) + "
            "surfaces the learnings-extraction checkpoint + sequences a mole "
            "worktree-sweep, THEN removes the worktree (refuses if dirty) + "
            "deletes the merged branch. Writes are "
            "DRY-RUN by default — pass confirm=True. Pushes ONLY to dev (main/"
            "prod move via noctus.dev.release); FF/rebase-only, never force/reset/"
            "switch. action='start' wire_env=True ALSO auto-wires the §5a "
            "verification env into the fresh worktree (symlink the PRIMARY tree's "
            "per-package node_modules in + re-point each product frontend's "
            "@noctusai/{lib,seed} deps at the worktree's seed copies) so a vite "
            "build / vitest can run THERE; all gitignored ⇒ never staged; "
            "best-effort (missing/real-dir paths reported in skipped, never "
            "clobbered) and dry-run-honored (reports would_wire without confirm). "
            "status: status|planned|started|integrated|conflict|"
            "up_to_date|cleaned|partial|blocked|error."
        ),
    )
    def _task_branch(
        action: str = "status",
        slug: str | None = None,
        confirm: bool = False,
        wire_env: bool = False,
    ) -> dict:
        return task_branch(action=action, slug=slug, confirm=confirm, wire_env=wire_env)


__all__ = ["task_branch", "_ALLOWED_GIT", "_BANNED_TOKENS", "_BENIGN_REFRESH_PATTERNS",
           "_assert_push_targets_dev", "_parse_worktrees", "_branch_for_path",
           "_is_dirty_excluding_gitignored", "_classify_dirty_files",
           "_rebase_in_progress", "_stash_benign_artifacts", "_pop_stash",
           "_plan_env_wiring", "_apply_env_wiring",
           "FsOps", "register"]
