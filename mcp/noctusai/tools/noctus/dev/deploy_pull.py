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
import os
import re
import shlex
import socket
import subprocess
import tempfile
from typing import Any, Callable

from deploy_state import DEPLOY_LOCAL_FILES
from ._vps_ssh import run_remote as _throttled_ssh

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
    r"(?:^|/)(?:Dockerfile[^/]*|docker-compose[^/]*\.ya?ml|config\.yml)$|^seed/"
)
# Auto-generated/cosmetic files that match a runtime path but are behaviourally
# a no-op — excluded from the rebuild trigger. The pre-commit stamps
# `_version_static.py` (the git-sha version string) on every commit, so without
# this every deploy_pull would false-flag a fleet rebuild.
_COSMETIC_NONRUNTIME = re.compile(r"_version_static\.py$")
# Paths that LOOK like fleet build inputs but belong to a NON-fleet app.
# `deploy/legacy/` is the standalone one-permutas Django app (legacy.noctusai.com):
# its own Dockerfile header states it "is NOT a noctus-fleet product — it has its
# OWN container shape (it does NOT inherit the noctus-seed-* base images)". It is
# built on the VPS from a separate repo, never from a fleet image.
#
# Without this exclusion `_RUNTIME_FLEET` matches `Dockerfile` ANYWHERE, so
# promoting `deploy/legacy/` on 2026-08-26 made `deploy_verify` report drift for
# EVERY live product against a Dockerfile that is in none of their images
# (verified: `noctus-core` contains only `products/core`). A permanently-red
# fleet gate gets ignored, which is how a real drift later goes unnoticed.
_NON_FLEET_DEPLOY = re.compile(r"^deploy/legacy/")


def _rebuild_decision(files: list[str]) -> dict[str, Any]:
    """Derive — never eyeball — whether the incoming diff needs a rebuild and
    of which products. Per-product runtime path → that product; a Dockerfile /
    compose / edge-config / seed change → fleet-wide. Cosmetic auto-generated
    files (the pre-commit's `_version_static.py` version-stamp, written on EVERY
    commit) are excluded — otherwise every deploy_pull falsely flags a fleet
    rebuild for a no-op version string."""
    products: set[str] = set()
    reasons: list[str] = []
    non_fleet_reasons: list[str] = []
    fleet = False
    for f in files:
        if _COSMETIC_NONRUNTIME.search(f):
            continue  # version-stamp etc. — baked but behaviourally a no-op
        m = _RUNTIME_PRODUCT.match(f)
        if m:
            products.add(m.group(1))
            reasons.append(f)
            continue
        if _NON_FLEET_DEPLOY.match(f):
            # Surfaced, never silently dropped: the legacy app DOES need a
            # rebuild when this changes — but via its own VPS build flow
            # (deploy/legacy/README.md), not a fleet image.
            non_fleet_reasons.append(f)
            continue
        if _RUNTIME_FLEET.search(f):
            fleet = True
            reasons.append(f)
    return {
        "needed": bool(products) or fleet,
        "products": sorted(products),
        "fleet_wide": fleet,
        "reasons": reasons[:20],
        "non_fleet_reasons": non_fleet_reasons[:20],
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
    """Run `cmd` (a list) on the remote via SSH; (rc, stdout, stderr). Routed
    through the shared throttled + circuit-broken chokepoint (`_vps_ssh`) so
    repeated attempts during an edge blip never trip the VPS's fail2ban."""
    return _throttled_ssh(ssh_host, cmd)


# ── auto-resolve the cache-mirror DSN + tunnel (so the mirror leg is not
#    silently skipped every deploy just because no DSN is in the MCP env) ──
_CACHE_DSN_ENV_PATH = "/opt/noctus/noctusai/deploy/fleet/.env.fleet"


def _pick_free_port() -> int:
    """An ephemeral loopback port (avoids colliding with a local Postgres on 5432)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", 0))
        return int(s.getsockname()[1])
    finally:
        s.close()


def _fetch_cache_dsn(ssh_host: str, runner) -> str | None:
    """Read `NOCTUS_CACHE_POSTGRES_DSN` from the VPS fleet env (root-owned, NOT in
    git). Returns the raw DSN (host = docker-internal `noctus-cache-pg:5432`) or None."""
    rc, out, _err = runner([
        "sh", "-c",
        f"grep '^NOCTUS_CACHE_POSTGRES_DSN=' {shlex.quote(_CACHE_DSN_ENV_PATH)} | cut -d= -f2-",
    ])
    dsn = (out or "").strip()
    return dsn if (rc == 0 and dsn.startswith("postgresql")) else None


def _open_cache_tunnel(ssh_host: str, local_port: int) -> Callable[[], None]:
    """Open an SSH tunnel `local_port -> 127.0.0.1:5432` on `ssh_host` via a control
    socket; return a cleanup callable that tears it down. Raises on failure (the
    caller degrades to skip)."""
    ctl = os.path.join(tempfile.gettempdir(), f"noc-mirror-tunnel-{local_port}-{os.getpid()}.sock")
    subprocess.run(
        ["ssh", "-M", "-S", ctl, "-o", "ExitOnForwardFailure=yes",
         "-o", "ConnectTimeout=10", "-o", "BatchMode=yes", "-fN",
         "-L", f"{local_port}:127.0.0.1:5432", ssh_host],
        check=True, capture_output=True, text=True, timeout=25,
    )

    def _cleanup() -> None:
        try:
            subprocess.run(["ssh", "-S", ctl, "-O", "exit", ssh_host],
                           capture_output=True, text=True, timeout=10)
        except Exception:  # noqa: BLE001 — teardown is best-effort
            pass

    return _cleanup


def _resolve_cache_dsn_via_tunnel(
    ssh_host: str,
    runner,
    *,
    _fetch: Callable[..., str | None] | None = None,
    _open: Callable[[str, int], Callable[[], None]] | None = None,
    _port: Callable[[], int] | None = None,
) -> tuple[str | None, Callable[[], None] | None, str | None]:
    """Best-effort: fetch the cache DSN from the VPS + open a loopback tunnel so the
    LOCAL mirror can reach prod pgvector WITHOUT the operator pre-opening one.

    Returns `(dsn, cleanup, reason)`. On ANY failure returns `(None, None, reason)`
    so the deploy degrades to the pre-existing skip behaviour — it NEVER raises into
    the deploy path (the mirror is additive; the code is already deployed). `_fetch`
    / `_open` / `_port` are test seams (inject to run with zero real SSH)."""
    fetch = _fetch or _fetch_cache_dsn
    opener = _open or _open_cache_tunnel
    pick = _port or _pick_free_port
    try:
        raw = fetch(ssh_host, runner)
        if not raw:
            return None, None, (
                f"auto-DSN: NOCTUS_CACHE_POSTGRES_DSN not found in {_CACHE_DSN_ENV_PATH} on {ssh_host}"
            )
        port = pick()
        # Rewrite the docker-internal host (`@noctus-cache-pg:5432/`) to the tunnel
        # endpoint. Match any host to be robust to future host naming.
        dsn = re.sub(r"@[^/@]+:5432/", f"@127.0.0.1:{port}/", raw)
        cleanup = opener(ssh_host, port)
        return dsn, cleanup, None
    except Exception as exc:  # noqa: BLE001 — never break the deploy over the mirror leg
        return None, None, f"auto-DSN tunnel failed ({type(exc).__name__}: {exc})"


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
    mirror_caches: bool = True,
    mirror_dsn: str | None = None,
    mirror_runner: Callable[..., dict[str, Any]] | None = None,
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

    # ── MIRROR (local SQLite caches → prod pgvector) ──
    # Runs LOCALLY (deploy_pull executes on the architect's machine; the mirror
    # reads local .claude/cache/*.sqlite + writes via an SSH tunnel to
    # 127.0.0.1:5432). DSN resolution order: explicit mirror_dsn → env
    # NOCTUS_CACHE_POSTGRES_DSN → AUTO (fetch the DSN from the VPS fleet env +
    # open a loopback tunnel ourselves — so the leg is not silently skipped every
    # deploy just because the MCP server env lacks the DSN, the recurring gap).
    # Surfaces but never silently swallows: if no DSN is reachable, surface
    # skipped with the named cause; if mirror errors, surface + flip status to
    # `partial` (code IS deployed, cache is stale). Auto-resolution NEVER breaks
    # the deploy — it degrades to skip on any failure.
    mirror_result: dict[str, Any] = {"status": "skipped", "reason": "mirror_caches=False"}
    if mirror_caches:
        dsn = mirror_dsn or os.environ.get("NOCTUS_CACHE_POSTGRES_DSN")
        tunnel_cleanup: Callable[[], None] | None = None
        auto_reason: str | None = None
        if not dsn:
            dsn, tunnel_cleanup, auto_reason = _resolve_cache_dsn_via_tunnel(ssh_host, runner)
        if not dsn:
            mirror_result = {
                "status": "skipped",
                "reason": auto_reason or (
                    "no DSN — set NOCTUS_CACHE_POSTGRES_DSN env var or pass "
                    "mirror_dsn= explicitly (e.g. via SSH tunnel: "
                    "ssh -L 5432:127.0.0.1:5432 -fN noctus-vps then "
                    "postgresql://noctus_cache:<pw>@127.0.0.1:5432/noctus_cache)"
                ),
            }
        else:
            try:
                if mirror_runner is None:
                    from tools.noctus.dev.cache_deploy_mirror import mirror_all  # type: ignore[import]
                    runner_fn: Callable[..., dict[str, Any]] = mirror_all
                else:
                    runner_fn = mirror_runner
                mirror_result = runner_fn(confirm=True, dsn=dsn)
                if tunnel_cleanup is not None and isinstance(mirror_result, dict):
                    mirror_result.setdefault("dsn_source", "auto-tunnel")
            except Exception as exc:  # noqa: BLE001
                mirror_result = {
                    "status": "error",
                    "ok": False,
                    "error": f"{type(exc).__name__}: {exc}",
                }
            finally:
                if tunnel_cleanup is not None:
                    tunnel_cleanup()

    mirror_failed = (
        mirror_caches
        and mirror_result.get("status") != "skipped"
        and not mirror_result.get("ok", False)
    )

    status_value = "deployed" if verified else "error"
    if verified and mirror_failed:
        status_value = "partial"

    return {
        **base, "status": status_value,
        "exit_code": 0 if (verified and not mirror_failed) else 1,
        "new_sha": new_sha, "verified_head": verified,
        "deploy_local_preserved": preserved,
        "backup_ref": backup_ref, "backup_tar": backup_tar,
        "rebuild_required": rebuild["needed"], "rebuild_products": rebuild["products"],
        "mirror": mirror_result,
        "message": (
            "deployed via clean fast-forward; "
            + (
                "REBUILD required for "
                + ", ".join(rebuild["products"] or ["fleet-wide"])
                + " — run noctus.dev.deploy_image <product> (C2 atomic redeploy)"
                if rebuild["needed"]
                else "no rebuild needed (docs/non-runtime only)."
            )
            + (
                f" CACHE MIRROR FAILED — code IS deployed, cache is stale: "
                f"{mirror_result.get('error') or mirror_result.get('failures') or 'see mirror.*'}."
                if mirror_failed
                else ""
            )
        ),
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.deploy_pull",
        description=(
            "Run the §2a safe-pull drill on a deploy target over SSH "
            "(inspect → decide → backup → ff-only → verify → cache-mirror), "
            "codifying KB § GUIDES/production-deploy.md § 2a + the cache_deploy_mirror "
            "step. DRY-RUN by default (returns the plan: incoming commits/files, "
            "fast-forward-ability, deploy-local overlap, and the DERIVED rebuild "
            "decision) — pass confirm=True to actually fast-forward (a production "
            "action; the 412-style write gate). REFUSES on a non-fast-forward or "
            "when incoming files overlap deploy-local edits. BY CONSTRUCTION it "
            "only runs a safe git allowlist + a tar backup — it can never emit "
            "reset/checkout/clean/push. Backs up (git tag + tar to <backup_dir> "
            "OUTSIDE the repo) before any HEAD move. After a successful FF, "
            "mirrors local SQLite caches → prod pgvector (unless mirror_caches=False "
            "or no DSN reachable). status: up_to_date | planned | blocked | "
            "deployed | partial (code deployed, cache mirror failed) | error."
        ),
    )
    def _deploy_pull(
        target: str = "origin/prod",
        ssh_host: str = "noctus-vps",
        repo_dir: str = "/opt/noctus/noctusai",
        confirm: bool = False,
        mirror_caches: bool = True,
        mirror_dsn: str | None = None,
    ) -> dict:
        return deploy_pull(
            target=target,
            ssh_host=ssh_host,
            repo_dir=repo_dir,
            confirm=confirm,
            mirror_caches=mirror_caches,
            mirror_dsn=mirror_dsn,
        )


__all__ = ["deploy_pull", "_rebuild_decision", "_ALLOWED_GIT", "_BANNED_TOKENS", "register"]
