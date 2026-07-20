"""noctus.dev.release — the dev→main (bless) + main→prod (promote) gates as a tool.

`main` is sacred (KB § PATTERNS/branching-and-merging.md § 0). Two deliberate,
consent-gated hops sit between everyday `dev` work and the live VPS:

  • Gate 1 — BLESS  : fast-forward `main` to the `dev` tip (a reviewed release).
                      `sha=` is NOT accepted here — bless always means "the
                      WHOLE dev-validated state", never a partial slice
                      (KB § PATTERNS/architect/git-branch-model.md); passing it
                      is REFUSED loudly (2026-07-20 — it used to be a SILENT
                      no-op that still blessed the dev tip while the caller
                      believed their pin had taken effect).
  • Gate 2 — PROMOTE: fast-forward `prod` to a blessed `main` sha — and FIRST
                      snapshot the *current* prod onto `prod-backup` (instant
                      rollback pointer). The VPS pulls `origin/prod` afterwards
                      via `noctus.dev.deploy_pull`. `sha=` IS accepted here —
                      pin promote to an earlier-blessed main sha instead of
                      main's current tip.

This tool is the ONLY sanctioned path that sets `NOCTUS_ALLOW_MAIN_PUSH=1` (the
pre-push hook's override) — and it does so ONLY for its own confirm-gated push.
Every other push to `main`/`prod` stays blocked by `scripts/hooks/pre-push`. So
you stop managing the env var by hand: dry-run → review the plan → confirm=True.

Safety model (mirrors deploy_pull / the §2a stack):
  • INSPECT (always, read-only): fetch refs, resolve the four branch tips,
    compute fast-forward-ability + the commit list each hop would ship.
  • DECIDE (deterministic): a hop proceeds ONLY as a clean fast-forward
    (target's current tip is an ancestor of the source). Never a force.
  • confirm-GATE (412 pattern): without `confirm`, returns the PLAN only — no
    ref moves. A non-FF (or a `sha` not contained in `main`) is REFUSED, not
    forced — the refusal IS the safety net.
  • BY CONSTRUCTION it only runs a safe git allowlist (fetch / rev-parse /
    merge-base / rev-list / log / push) and never carries reset/checkout/clean/
    --force/--force-with-lease (a colocated test asserts this across a confirmed
    bless AND a confirmed promote).

IO is injectable (`run`, `now`) so the colocated test drives every path with
zero real git and asserts both the allowlist and the NOCTUS_ALLOW_MAIN_PUSH
discipline (set on main/prod pushes, NEVER on the prod-backup snapshot push).
"""
from __future__ import annotations

import shlex
import subprocess
from typing import Any, Callable

# git subcommands the tool may run. It pushes ref-specs (`<sha>:refs/heads/X`),
# never checks out / resets / forces — keeping those off the list makes a
# destructive or history-rewriting release structurally impossible.
_ALLOWED_GIT = frozenset({"fetch", "rev-parse", "merge-base", "rev-list", "log", "diff", "push"})
_BANNED_TOKENS = (
    "reset", "checkout", "restore", "clean", "--hard", "--force",
    "--force-with-lease", "-D", "branch",
)

# Reuse the deploy_pull rebuild oracle so a promote tells you whether the VPS
# pull will need a container rebuild — DRY, one source of truth.
from tools.noctus.dev.deploy_pull import _rebuild_decision  # noqa: E402


def _default_run_local(
    cmd: list[str], env_extra: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Run `cmd` locally at the repo root; (rc, stdout, stderr). `env_extra`
    overlays the process env (used to set NOCTUS_ALLOW_MAIN_PUSH on the one
    sanctioned push). REPO_ROOT is imported lazily so module import stays light
    and the test (which injects `run`) never pays the settings import cost."""
    import os

    from settings import REPO_ROOT  # lazy: avoids import-time noctusai_lib cost

    env = os.environ.copy()
    if env_extra:
        env.update(env_extra)
    r = subprocess.run(cmd, capture_output=True, text=True, cwd=str(REPO_ROOT), env=env)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _git(runner, *args, env_extra: dict[str, str] | None = None) -> tuple[int, str, str]:
    """Run a git subcommand — ONLY if on the safe allowlist AND carrying no
    banned token. The structural guarantee the tool can never force/rewrite."""
    sub = args[0] if args else ""
    if sub not in _ALLOWED_GIT:
        raise ValueError(
            f"release: git '{sub}' is not on the safe allowlist {sorted(_ALLOWED_GIT)}"
        )
    for tok in args:
        if tok in _BANNED_TOKENS:
            raise ValueError(f"release: banned token '{tok}' in git {list(args)}")
    return runner(["git", *args], env_extra=env_extra) if env_extra is not None \
        else runner(["git", *args])


def _resolve(git, ref: str) -> str | None:
    rc, out, _e = git("rev-parse", ref)
    return out.strip() if rc == 0 and out.strip() else None


def _is_ancestor(git, a: str, b: str) -> bool:
    """True iff commit `a` is an ancestor of (or equal to) `b` — i.e. b can
    fast-forward from a."""
    rc, _o, _e = git("merge-base", "--is-ancestor", a, b)
    return rc == 0


def _commits(git, a: str, b: str) -> list[str]:
    rc, out, _e = git("log", "--oneline", f"{a}..{b}")
    return [ln for ln in out.splitlines() if ln.strip()] if rc == 0 else []


def release(
    stage: str = "status",
    confirm: bool = False,
    remote: str = "origin",
    dev_branch: str = "dev",
    main_branch: str = "main",
    prod_branch: str = "prod",
    backup_branch: str = "prod-backup",
    sha: str | None = None,
    run: Callable[..., tuple[int, str, str]] | None = None,
    now=None,  # accepted for signature parity / future timestamped tags
) -> dict[str, Any]:
    """`stage` ∈ {status, bless, promote}. Dry-run unless `confirm`. Returns a
    structured plan/result; never raises on a refusal — it returns it."""
    runner = run or _default_run_local

    def git(*args, env_extra=None):
        return _git(runner, *args, env_extra=env_extra)

    if stage not in {"status", "bless", "promote"}:
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"unknown stage '{stage}' (expected status|bless|promote)"}

    # ── INSPECT (read-only) ──
    git("fetch", remote, "--quiet")
    dev = _resolve(git, f"{remote}/{dev_branch}")
    main = _resolve(git, f"{remote}/{main_branch}")
    prod = _resolve(git, f"{remote}/{prod_branch}")
    backup = _resolve(git, f"{remote}/{backup_branch}")
    if not (dev and main):
        return {"ok": False, "status": "error", "exit_code": 1,
                "error": f"cannot resolve {remote}/{dev_branch} or {remote}/{main_branch} "
                         "(fetch failed or branch missing)"}

    base: dict[str, Any] = {
        "ok": True, "remote": remote, "stage": stage,
        "dev_sha": dev, "main_sha": main, "prod_sha": prod, "backup_sha": backup,
    }

    # ── STATUS ── full chain overview, no writes ever
    if stage == "status":
        bless_ff = _is_ancestor(git, main, dev)
        promote_ff = bool(prod) and _is_ancestor(git, prod, main)
        return {
            **base, "status": "status", "exit_code": 0,
            "bless": {  # dev → main
                "ff": bless_ff, "ahead": len(_commits(git, main, dev)),
                "commits": _commits(git, main, dev)[:20],
            },
            "promote": {  # main → prod (ships EVERYTHING main is ahead of prod)
                "ff": promote_ff,
                "ahead": len(_commits(git, prod, main)) if prod else None,
                "commits": _commits(git, prod, main)[:20] if prod else [],
            },
            "prod_backup_trails_prod": (backup == prod) if (backup and prod) else None,
            "message": "chain: feat/* → dev → main (bless) → prod (promote) → VPS (deploy_pull).",
        }

    # ── BLESS (dev → main) ──
    if stage == "bless":
        # REFUSE-NOT-NULL (2026-07-20): sha= previously SILENTLY IGNORED on
        # bless — the caller believed a pin took effect while bless still
        # advanced main to the dev TIP. Bless is a whole-repo-state concept
        # ("this dev-validated state") with no notion of a partial slice
        # (KB § PATTERNS/architect/git-branch-model.md); only promote pins.
        if sha:
            return {**base, "status": "error", "exit_code": 1,
                    "error": (
                        f"release: stage='bless' does not accept sha= (got {sha!r}). "
                        f"Bless always fast-forwards {main_branch} to the CURRENT "
                        f"{dev_branch} tip — there is no partial-bless concept "
                        "(KB § PATTERNS/architect/git-branch-model.md). If you meant to "
                        "pin a specific already-blessed commit for deployment, that is "
                        "promote's job: stage='promote' sha=<main-sha>. This refusal "
                        "replaces a prior SILENT no-op where sha= was accepted by the "
                        "schema but ignored by bless."
                    )}
        if dev == main:
            return {**base, "status": "up_to_date", "exit_code": 0,
                    "message": f"{main_branch} already == {dev_branch}; nothing to bless."}
        if not _is_ancestor(git, main, dev):
            return {**base, "status": "blocked", "exit_code": 1,
                    "reason": f"{main_branch} has commits not in {dev_branch} — not a clean "
                              f"fast-forward. Reconcile on {dev_branch} first (never force main)."}
        incoming = _commits(git, main, dev)
        plan = {**base, "would_advance": f"{main_branch} → {dev[:9]}", "incoming_commits": incoming}
        if not confirm:
            return {**plan, "status": "planned", "exit_code": 0,
                    "message": f"clean FF available: bless {len(incoming)} commit(s) "
                               f"{main_branch} → {dev_branch}. Pass confirm=True to push."}
        # ACT — the sanctioned override push (FF; hook still blocks force/delete)
        rc, out, err = git("push", remote, f"{dev}:refs/heads/{main_branch}",
                           env_extra={"NOCTUS_ALLOW_MAIN_PUSH": "1"})
        if rc != 0:
            return {**plan, "status": "error", "exit_code": 1,
                    "error": f"push to {main_branch} failed: {err.strip() or out.strip()}"}
        new_main = _resolve(git, f"{remote}/{main_branch}")
        return {**plan, "status": "blessed", "exit_code": 0, "new_main_sha": new_main,
                "verified": new_main == dev,
                "message": f"blessed {len(incoming)} commit(s) to {main_branch}. "
                           f"To deploy: noctus.dev.release stage='promote' (ships ALL of "
                           f"{prod_branch}..{main_branch} — review first)."}

    # ── PROMOTE (main → prod, snapshot prod → prod-backup first) ──
    target = None
    if sha:
        target = _resolve(git, sha)
        if not target:
            return {**base, "status": "error", "exit_code": 1,
                    "error": f"cannot resolve sha '{sha}'."}
        if not _is_ancestor(git, target, main):
            return {**base, "status": "blocked", "exit_code": 1,
                    "reason": f"sha {target[:9]} is not contained in {main_branch} — only a "
                              f"blessed {main_branch} sha may be promoted."}
    else:
        target = main
    if not prod:
        return {**base, "status": "error", "exit_code": 1,
                "error": f"cannot resolve {remote}/{prod_branch}."}
    if prod == target:
        return {**base, "status": "up_to_date", "exit_code": 0, "target_sha": target,
                "message": f"{prod_branch} already == target; nothing to promote."}
    if not _is_ancestor(git, prod, target):
        return {**base, "status": "blocked", "exit_code": 1, "target_sha": target,
                "reason": f"{prod_branch} is not an ancestor of the target — not a clean FF. "
                          "Diagnose, do not force."}
    # prod-backup must be able to FF to the *current* prod (we snapshot it there).
    backup_ff = (backup is None) or _is_ancestor(git, backup, prod)
    if not backup_ff:
        return {**base, "status": "blocked", "exit_code": 1, "target_sha": target,
                "reason": f"{backup_branch} ({backup[:9] if backup else '∅'}) is not an ancestor "
                          f"of {prod_branch} ({prod[:9]}) — snapshot would not be a clean FF. "
                          "Realign prod-backup deliberately first."}
    incoming = _commits(git, prod, target)
    _rc, diff_out, _e = git("diff", "--name-only", f"{prod}..{target}")
    changed_files = [ln.strip() for ln in diff_out.splitlines() if ln.strip()]
    rebuild = _rebuild_decision(changed_files)

    plan = {
        **base, "target_sha": target, "incoming_commits": incoming,
        "snapshot": f"{backup_branch} → {prod[:9]} (current prod, pre-promote)",
        "would_advance": f"{prod_branch} → {target[:9]}",
        "large_promote": len(incoming) > 10,  # loud flag — promoting a big backlog
        "rebuild": rebuild,
    }
    if not confirm:
        return {**plan, "status": "planned", "exit_code": 0,
                "message": (f"clean FF available: snapshot {backup_branch}←prod, then promote "
                            f"{len(incoming)} commit(s) {main_branch}→{prod_branch}. "
                            + ("⚠ LARGE promote — review the commit list. " if len(incoming) > 10 else "")
                            + "Pass confirm=True. After: noctus.dev.deploy_pull confirm=True.")}
    # ACT 1 — snapshot current prod onto prod-backup (FF; not a protected branch)
    rc, out, err = git("push", remote, f"{prod}:refs/heads/{backup_branch}")
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "error": f"prod-backup snapshot push failed: {err.strip() or out.strip()}"}
    # ACT 2 — promote (the sanctioned override push; FF only)
    rc, out, err = git("push", remote, f"{target}:refs/heads/{prod_branch}",
                       env_extra={"NOCTUS_ALLOW_MAIN_PUSH": "1"})
    if rc != 0:
        return {**plan, "status": "error", "exit_code": 1,
                "snapshot_done": True,
                "error": f"promote push to {prod_branch} failed: {err.strip() or out.strip()}"}
    new_prod = _resolve(git, f"{remote}/{prod_branch}")
    new_backup = _resolve(git, f"{remote}/{backup_branch}")
    return {**plan, "status": "promoted", "exit_code": 0,
            "new_prod_sha": new_prod, "new_backup_sha": new_backup,
            "verified": new_prod == target and new_backup == prod,
            "message": (f"promoted {len(incoming)} commit(s) to {prod_branch}; "
                        f"{backup_branch} now holds the previous prod ({prod[:9]}). "
                        "Deploy to the VPS: noctus.dev.deploy_pull confirm=True"
                        + (f" (rebuild: {', '.join(rebuild['products']) or 'fleet'})"
                           if rebuild.get("needed") else " (no rebuild — non-runtime).")) }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.release",
        description=(
            "Run the consent-gated release/deploy gates for the sacred-main branch "
            "model (KB § PATTERNS/branching-and-merging.md § 0.2). stage='status' "
            "(default) shows the feat→dev→main→prod chain (SHAs, FF-ability, the "
            "commits each hop would ship) read-only; stage='bless' fast-forwards "
            "main to the dev tip (sha= is NOT accepted here — REFUSED loudly, not "
            "silently ignored: bless is a whole-repo-state concept, no partial slice); "
            "stage='promote' snapshots the current prod onto prod-backup then "
            "fast-forwards prod to a blessed main sha (pass sha= to pin; default = "
            "main tip — which ships ALL of prod..main, flagged large_promote). "
            "DRY-RUN by default — pass confirm=True to push. FF-only "
            "by construction (never force/reset/checkout). It is the ONLY sanctioned "
            "setter of NOCTUS_ALLOW_MAIN_PUSH, and only for its own push. After a "
            "promote, run noctus.dev.deploy_pull to pull origin/prod onto the VPS. "
            "status: status|planned|up_to_date|blocked|blessed|promoted|error."
        ),
    )
    def _release(
        stage: str = "status",
        confirm: bool = False,
        sha: str | None = None,
    ) -> dict:
        return release(stage=stage, confirm=confirm, sha=sha)


__all__ = ["release", "_ALLOWED_GIT", "_BANNED_TOKENS", "register"]
