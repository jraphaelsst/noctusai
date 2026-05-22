"""noctus.dev.deploy_pull — the §2a safe-pull drill, codified as a tool.

The VPS checkout is PRODUCTION (KB § GUIDES/production-deploy.md § 2a). Code
reaches it ONLY by a fast-forward pull of *promoted* commits; deploy-local
secrets (tunnel config.yml, creds *.json, root .env) are filled in-place and
MUST survive every pull. The hand-run drill is inspect → decide → backup →
ff-only → verify; doing it by hand keeps the destructive commands
(`reset --hard`, `checkout -- <deploy-local>`, `clean -fdx`) one fat-finger
away. This tool runs the drill over SSH and — BY CONSTRUCTION — never emits any
of them: it only ever calls a fixed allowlist of git subcommands plus a tar
backup. The dangerous moves are unreachable, not merely avoided.

Safety model (mirrors the §2a safety-net stack):
  • INSPECT (always, read-only): current HEAD, fetch (refs only), the
    deploy-local M/?? set, incoming commits + files.
  • DECIDE (deterministic — replaces the human eyeball): FF-ability
    (HEAD ancestor of target?) ∧ overlap (incoming files ∩ deploy-local set)
    ∧ rebuild decision (does the diff touch product runtime / Dockerfile /
    compose / edge config?).
  • confirm-GATE (the 412 pattern): without `confirm`, returns the PLAN only
    (dry-run) — no HEAD move. With `confirm` but a non-FF or an overlap, it
    REFUSES (status=blocked) — the safety net is the refusal. Only a clean,
    overlap-free FF proceeds.
  • BACKUP before any HEAD move (C1): `git tag -f backup/predeploy-<utc>` +
    `tar` the deploy-local files to <backup_dir> OUTSIDE the repo
    (/opt/noctus/backups — a backup inside the tracked tree is a git-add
    footgun).
  • ACT: `git merge --ff-only <target>` — advances or refuses, never merges.
  • VERIFY: HEAD == target sha ∧ deploy-local set still present.

IO is injectable (`run_remote`, `now`) so the colocated test drives every path
— up-to-date / planned / blocked-non-FF / blocked-overlap / deployed — with
zero real SSH, and asserts the destructive-command allowlist holds.
"""
from __future__ import annotations

import datetime as _dt
import re
import shlex
import subprocess
from typing import Any, Callable

from deploy_state import DEPLOY_LOCAL_FILES

# git subcommands the tool is allowed to run remotely. The drill NEVER needs
# reset/checkout/clean/push — keeping them off this list makes a destructive
# sync structurally impossible (a colocated test asserts no call ever carries
# a banned token).
_ALLOWED_GIT = frozenset(
    {"rev-parse", "fetch", "status", "log", "diff", "merge-base", "tag", "merge"}
)
_BANNED_TOKENS = ("reset", "checkout", "restore", "clean", "--hard", "--force", "push")

# A changed path triggers a container rebuild iff it is served by a running
# product container. Docs / projects / KB / mcp-toolkit changes do NOT
# (validation-freshness, KB § PATTERNS/containerization.md § 12b).
_RUNTIME_PRODUCT = re.compile(r"^products/([^/]+)/(?:backend|frontend)/")
_RUNTIME_FLEET = re.compile(
    r"(?:^|/)(?:Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|Caddyfile|config\.yml)$|^seed/"
)


def _rebuild_decision(files: list[str]) -> dict[str, Any]:
    """Derive — never eyeball — whether the incoming diff needs a rebuild and
    of which products. Per-product runtime path → that product; a Dockerfile /
    compose / edge-config / seed change → fleet-wide."""
    products: set[str] = set()
    reasons: list[str] = []
    fleet = False
    for f in files:
        m = _RUNTIME_PRODUCT.match(f)
        if m:
            products.add(m.group(1))
            reasons.append(f)
            continue
        if _RUNTIME_FLEET.search(f):
            fleet = True
            reasons.append(f)
    return {
        "needed": bool(products) or fleet,
        "products": sorted(products),
        "fleet_wide": fleet,
        "reasons": reasons[:20],
    }


def _parse_status_paths(status_short: str) -> list[str]:
    """Repo-relative paths from `git status --short` — the deploy-local M/??
    set to preserve. Each line is 'XY <path>'."""
    out: list[str] = []
    for line in (status_short or "").splitlines():
        if len(line) > 3:
            out.append(line[3:].strip().strip('"'))
    return out


def _deploy_local_patterns() -> list[str]:
    """The deploy-local gitignore-style patterns (the deploy_state constant —
    durable, can't be lost to an archive). These are what C1 backs up; they are
    resolved to concrete files on the remote."""
    return [e["pattern"] for e in DEPLOY_LOCAL_FILES if e.get("pattern")]


def _resolve_remote_files(runner, repo_dir: str, patterns: list[str]) -> list[str]:
    """Resolve gitignore-style patterns to concrete repo-relative files on the
    remote. A root-level concrete name (`.env`) passes through; a path glob
    (`**/tunnel/*.json`) is resolved with `find -path` — robust, no reliance on
    the remote shell's globstar. tar later uses --ignore-failed-read for absent
    ones."""
    resolved: list[str] = []
    for p in patterns:
        if "*" not in p and "/" not in p:
            resolved.append(p)  # root-level concrete file, e.g. .env
            continue
        suffix = p.replace("**/", "")  # tunnel/config.yml | tunnel/*.json
        script = (
            f"cd {shlex.quote(repo_dir)} && "
            f"find . -path {shlex.quote('./*/' + suffix)} -type f 2>/dev/null"
        )
        _rc, out, _e = runner(["sh", "-c", script])
        for line in out.splitlines():
            line = line.strip()
            if line.startswith("./"):
                line = line[2:]
            if line:
                resolved.append(line)
    return resolved


def _default_run_remote(ssh_host: str, cmd: list[str]) -> tuple[int, str, str]:
    """Run `cmd` (a list) on the remote via SSH; (rc, stdout, stderr). The list
    is shell-quoted into one remote command string."""
    remote = " ".join(shlex.quote(c) for c in cmd)
    r = subprocess.run(["ssh", ssh_host, remote], capture_output=True, text=True)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _git(runner, repo_dir: str, *args) -> tuple[int, str, str]:
    """Run a git subcommand remotely — but ONLY if it is on the safe allowlist.
    This is the structural guarantee that the tool can never run a destructive
    sync command, even if the calling code is wrong."""
    sub = args[0] if args else ""
    if sub not in _ALLOWED_GIT:
        raise ValueError(
            f"deploy_pull: git '{sub}' is not on the safe allowlist {sorted(_ALLOWED_GIT)}"
        )
    return runner(["git", "-C", repo_dir, *args])


def deploy_pull(
    target: str = "origin/prod",
    ssh_host: str = "noctus-vps",
    repo_dir: str = "/opt/noctus/noctusai",
    confirm: bool = False,
    backup_dir: str = "/opt/noctus/backups",
    run_remote: Callable[[list[str]], tuple[int, str, str]] | None = None,
    now: Callable[[], _dt.datetime] | None = None,
) -> dict[str, Any]:
    """The §2a drill as a function. Dry-run unless `confirm`. Returns a
    structured plan/result; status ∈ {up_to_date, planned, blocked, deployed,
    error}. Never raises on a refusal — it returns it (no silent errors)."""
    runner = run_remote or (lambda cmd: _default_run_remote(ssh_host, cmd))
    clock = now or _dt.datetime.utcnow

    def git(*args):
        return _git(runner, repo_dir, *args)

    # ── INSPECT (read-only) ──
    rc, cur, err = git("rev-parse", "HEAD")
    if rc != 0:
        return {
            "ok": False, "status": "error", "exit_code": 1,
            "error": f"cannot read remote HEAD (ssh '{ssh_host}' / repo '{repo_dir}'): "
                     f"{err.strip() or cur.strip()}",
        }
    current_sha = cur.strip()
    git("fetch", "origin", "--quiet")
    _rc, status_short, _e = git("status", "--short")
    deploy_local = _parse_status_paths(status_short)
    rc_t, tgt, err_t = git("rev-parse", target)
    if rc_t != 0:
        return {
            "ok": False, "status": "error", "exit_code": 1,
            "error": f"cannot resolve target '{target}': {err_t.strip() or tgt.strip()}",
        }
    target_sha = tgt.strip()
    _rc, log_out, _e = git("log", "--oneline", f"HEAD..{target}")
    incoming_commits = [ln for ln in log_out.splitlines() if ln.strip()]
    _rc, diff_out, _e = git("diff", "--name-only", f"HEAD..{target}")
    incoming_files = [ln for ln in diff_out.splitlines() if ln.strip()]

    # ── DECIDE (deterministic) ──
    rc_anc, _o, _e = git("merge-base", "--is-ancestor", "HEAD", target)
    is_ff = rc_anc == 0
    overlap = sorted(set(incoming_files) & set(deploy_local))
    rebuild = _rebuild_decision(incoming_files)

    base: dict[str, Any] = {
        "ok": True, "ssh_host": ssh_host, "repo_dir": repo_dir, "target": target,
        "current_sha": current_sha, "target_sha": target_sha,
        "incoming_commits": incoming_commits, "incoming_files": incoming_files,
        "deploy_local_files": deploy_local, "is_fast_forward": is_ff,
        "overlap": overlap, "rebuild": rebuild,
    }

    if current_sha == target_sha:
        return {**base, "status": "up_to_date", "exit_code": 0,
                "message": "VPS HEAD already == target; nothing to pull."}

    # Refusals — the safety net IS the refusal (never force).
    if not is_ff:
        return {**base, "status": "blocked", "exit_code": 1,
                "reason": "non-fast-forward — HEAD is not an ancestor of the target; "
                          "refusing (would not be a clean FF). Diagnose, do not force."}
    if overlap:
        return {**base, "status": "blocked", "exit_code": 1,
                "reason": f"incoming files overlap deploy-local edits {overlap} — refusing; "
                          "resolve deliberately (never reset/checkout-over)."}

    # Dry-run: plan only, no HEAD move.
    if not confirm:
        return {**base, "status": "planned", "exit_code": 0,
                "message": "clean fast-forward available — pass confirm=True to deploy.",
                "would_backup": True, "would_rebuild": rebuild["needed"]}

    # ── BACKUP (C1) ──
    utc = clock().strftime("%Y%m%d-%H%M%S")
    backup_ref = f"backup/predeploy-{utc}"
    git("tag", "-f", backup_ref, "HEAD")
    backup_tar: str | None = None
    resolved = _resolve_remote_files(runner, repo_dir, _deploy_local_patterns())
    if resolved:
        tarpath = f"{backup_dir}/{utc}.tgz"
        runner(["mkdir", "-p", backup_dir])
        runner(["tar", "czf", tarpath, "--ignore-failed-read", "-C", repo_dir, *resolved])
        backup_tar = tarpath

    # ── ACT (ff-only) ──
    rc_m, merge_out, merge_err = git("merge", "--ff-only", target)
    if rc_m != 0:
        return {**base, "status": "blocked", "exit_code": 1,
                "backup_ref": backup_ref, "backup_tar": backup_tar,
                "reason": f"git merge --ff-only refused at apply time: "
                          f"{merge_err.strip() or merge_out.strip()}. Backup is in place; "
                          "diagnose, do not force."}

    # ── VERIFY ──
    _rc, new, _e = git("rev-parse", "HEAD")
    new_sha = new.strip()
    _rc, status2, _e = git("status", "--short")
    preserved = set(deploy_local).issubset(set(_parse_status_paths(status2)))
    verified = new_sha == target_sha

    return {
        **base, "status": "deployed" if verified else "error",
        "exit_code": 0 if verified else 1,
        "new_sha": new_sha, "verified_head": verified,
        "deploy_local_preserved": preserved,
        "backup_ref": backup_ref, "backup_tar": backup_tar,
        "rebuild_required": rebuild["needed"], "rebuild_products": rebuild["products"],
        "message": (
            "deployed via clean fast-forward; "
            + (
                "REBUILD required: " + ", ".join(rebuild["products"] or ["fleet-wide"])
                if rebuild["needed"]
                else "no rebuild needed (docs/non-runtime only)."
            )
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.deploy_pull",
        description=(
            "Run the §2a safe-pull drill on a deploy target over SSH "
            "(inspect → decide → backup → ff-only → verify), codifying "
            "KB § GUIDES/production-deploy.md § 2a. DRY-RUN by default (returns "
            "the plan: incoming commits/files, fast-forward-ability, deploy-local "
            "overlap, and the DERIVED rebuild decision) — pass confirm=True to "
            "actually fast-forward (a production action; the 412-style write "
            "gate). REFUSES on a non-fast-forward or when incoming files overlap "
            "deploy-local edits. BY CONSTRUCTION it only runs a safe git "
            "allowlist + a tar backup — it can never emit reset/checkout/clean/"
            "push. Backs up (git tag + tar to <backup_dir> OUTSIDE the repo) "
            "before any HEAD move. status: up_to_date | planned | blocked | "
            "deployed | error."
        ),
    )
    def _deploy_pull(
        target: str = "origin/prod",
        ssh_host: str = "noctus-vps",
        repo_dir: str = "/opt/noctus/noctusai",
        confirm: bool = False,
    ) -> dict:
        return deploy_pull(target=target, ssh_host=ssh_host, repo_dir=repo_dir, confirm=confirm)


__all__ = ["deploy_pull", "_rebuild_decision", "_ALLOWED_GIT", "_BANNED_TOKENS", "register"]
