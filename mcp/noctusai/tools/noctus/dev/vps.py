"""noctus.vps.* — operate the running fleet on the VPS over SSH.

The deploy LAYER is `deploy_pull` (git sync) + `deploy_image` (image deploy with
C2 rollback). This is the OPERATE layer: inspect + bounce the running containers.
Consolidates the ad-hoc `ssh noctus-vps docker …` ops (ps / logs / inspect /
restart / health / disk) into safe, tested, confirm-gated MCP tools.

Methodology (deliberate): VPS ops SSH from the **local** MCP runtime — the
production SSH key never enters a cloud CI system. CI only builds + pushes
images (the deliver layer); deploy + operation live here.

Safety: read ops are free; mutating ops (restart / recreate / prune) are
confirm-gated. Every op emits a FIXED docker command from a safe allowlist
(ps/inspect/logs/images/system/stats/restart + compose up + image-prune-dangling)
— never rm / rmi -a / kill / down / exec-arbitrary (a colocated test asserts no
banned token is emitted). IO is injectable (`run_remote`) for zero-SSH tests.
"""
from __future__ import annotations

import shlex
import subprocess
from typing import Any, Callable

DEFAULT_HOST = "noctus-vps"
DEFAULT_COMPOSE = "projects/production-deploy-migration/deploy/fleet/docker-compose.prod.yml"
DEFAULT_REPO_DIR = "/opt/noctus/noctusai"
CONTAINER_PREFIX = "noctus-"  # product + infra containers

# Tokens the module must NEVER emit (asserted by the colocated test). Mutations
# are done via `restart`, `compose up`, and `image prune -f` (dangling only) —
# none of these destroy a tagged/running image or tear the fleet down.
_BANNED_TOKENS = ("rmi", "rm ", " rm", "kill", "down", "prune -a", "prune --all", "system prune", "exec")


def _run_remote_default(ssh_host: str, cmd: list[str]) -> tuple[int, str, str]:
    remote = " ".join(shlex.quote(c) for c in cmd)
    r = subprocess.run(["ssh", ssh_host, remote], capture_output=True, text=True)
    return r.returncode, (r.stdout or ""), (r.stderr or "")


def _runner(run_remote, ssh_host):
    return run_remote or (lambda cmd: _run_remote_default(ssh_host, cmd))


def _err(msg: str) -> dict[str, Any]:
    return {"ok": False, "status": "error", "exit_code": 1, "error": msg}


def _need_confirm(action: str, target: str) -> dict[str, Any]:
    return {"ok": False, "status": "needs_confirm", "exit_code": 1,
            "message": f"{action} '{target}' is a production mutation — pass confirm=True to proceed."}


# ── read ops ──────────────────────────────────────────────────────
def ps(ssh_host: str = DEFAULT_HOST, all: bool = False,
       run_remote: Callable | None = None) -> dict[str, Any]:
    """Running noctus containers: name · image · status · health."""
    run = _runner(run_remote, ssh_host)
    args = ["ps", "--format", "{{.Names}}\t{{.Image}}\t{{.Status}}"]
    if all:
        args.insert(1, "-a")
    rc, out, err = run(["docker", *args])
    if rc != 0:
        return _err(f"docker ps failed on '{ssh_host}': {err.strip()}")
    rows = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) >= 3 and parts[0].startswith(CONTAINER_PREFIX):
            status = parts[2]
            health = "healthy" if "(healthy)" in status else "unhealthy" if "(unhealthy)" in status else (
                "starting" if "(health: starting)" in status else "")
            rows.append({"name": parts[0], "image": parts[1], "status": status, "health": health})
    return {"ok": True, "status": "ok", "exit_code": 0, "count": len(rows), "containers": rows}


def health(ssh_host: str = DEFAULT_HOST, run_remote: Callable | None = None) -> dict[str, Any]:
    """Fleet health rollup — per-container health + an overall verdict."""
    r = ps(ssh_host=ssh_host, run_remote=run_remote)
    if not r["ok"]:
        return r
    containers = r["containers"]
    unhealthy = [c["name"] for c in containers if c["health"] == "unhealthy"]
    starting = [c["name"] for c in containers if c["health"] == "starting"]
    healthy = [c["name"] for c in containers if c["health"] == "healthy"]
    ok = not unhealthy
    return {"ok": True, "status": "healthy" if ok else "degraded", "exit_code": 0 if ok else 1,
            "healthy": healthy, "starting": starting, "unhealthy": unhealthy,
            "summary": f"{len(healthy)} healthy / {len(starting)} starting / {len(unhealthy)} unhealthy"}


def logs(container: str, lines: int = 80, ssh_host: str = DEFAULT_HOST,
         grep: str | None = None, run_remote: Callable | None = None) -> dict[str, Any]:
    """Tail a container's logs (read-only)."""
    if not container:
        return _err("container required")
    run = _runner(run_remote, ssh_host)
    rc, out, err = run(["docker", "logs", "--tail", str(int(lines)), container])
    combined = (out or "") + (err or "")  # docker logs writes app stderr too
    if rc != 0 and not combined.strip():
        return _err(f"docker logs {container} failed: {err.strip()}")
    text = combined
    if grep:
        text = "\n".join(ln for ln in combined.splitlines() if grep in ln)
    return {"ok": True, "status": "ok", "exit_code": 0, "container": container,
            "lines": text.splitlines()[-int(lines):]}


def inspect(container: str, ssh_host: str = DEFAULT_HOST,
            run_remote: Callable | None = None) -> dict[str, Any]:
    """Inspect a container: image id · health · state · port · started-at."""
    if not container:
        return _err("container required")
    run = _runner(run_remote, ssh_host)
    tmpl = ("{{.Image}}|{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}|"
            "{{.State.StartedAt}}|{{range $p,$_ := .Config.ExposedPorts}}{{$p}} {{end}}")
    rc, out, err = run(["docker", "inspect", "-f", tmpl, container])
    if rc != 0 or not out.strip():
        return _err(f"container '{container}' not found on '{ssh_host}': {err.strip()}")
    f = (out.strip().split("|") + [""] * 5)[:5]
    return {"ok": True, "status": "ok", "exit_code": 0, "container": container,
            "image_id": f[0], "state": f[1], "health": f[2], "started_at": f[3], "ports": f[4].strip()}


def images(ssh_host: str = DEFAULT_HOST, run_remote: Callable | None = None) -> dict[str, Any]:
    """List noctus images on the box: repo:tag · id · size · age."""
    run = _runner(run_remote, ssh_host)
    rc, out, err = run(["docker", "images", "--format", "{{.Repository}}:{{.Tag}}\t{{.ID}}\t{{.Size}}\t{{.CreatedSince}}"])
    if rc != 0:
        return _err(f"docker images failed: {err.strip()}")
    rows = []
    for line in out.splitlines():
        p = line.split("\t")
        if len(p) >= 4 and ("noctus" in p[0]):
            rows.append({"image": p[0], "id": p[1], "size": p[2], "age": p[3]})
    return {"ok": True, "status": "ok", "exit_code": 0, "count": len(rows), "images": rows}


def disk(ssh_host: str = DEFAULT_HOST, run_remote: Callable | None = None) -> dict[str, Any]:
    """VPS disk pressure: root filesystem use% + docker space (images/containers/cache)."""
    run = _runner(run_remote, ssh_host)
    rc, df, _e = run(["sh", "-c", "df -h / | tail -1"])
    rc2, dsd, _e2 = run(["docker", "system", "df"])
    use_pct = None
    parts = (df or "").split()
    for tok in parts:
        if tok.endswith("%"):
            use_pct = tok
    return {"ok": rc == 0, "status": "ok" if rc == 0 else "error", "exit_code": 0 if rc == 0 else 1,
            "root_use_pct": use_pct, "root_df": (df or "").strip(), "docker_df": (dsd or "").strip()}


def stats(ssh_host: str = DEFAULT_HOST, run_remote: Callable | None = None) -> dict[str, Any]:
    """Per-container CPU/mem (a one-shot `docker stats --no-stream`)."""
    run = _runner(run_remote, ssh_host)
    rc, out, err = run(["docker", "stats", "--no-stream", "--format",
                        "{{.Name}}\t{{.CPUPerc}}\t{{.MemUsage}}\t{{.MemPerc}}"])
    if rc != 0:
        return _err(f"docker stats failed: {err.strip()}")
    rows = [dict(zip(("name", "cpu", "mem", "mem_pct"), line.split("\t")))
            for line in out.splitlines() if line.startswith(CONTAINER_PREFIX)]
    return {"ok": True, "status": "ok", "exit_code": 0, "count": len(rows), "stats": rows}


# ── mutating ops (confirm-gated) ──────────────────────────────────
def restart(container: str, confirm: bool = False, ssh_host: str = DEFAULT_HOST,
            run_remote: Callable | None = None) -> dict[str, Any]:
    """`docker restart` a container — fixes the stale single-file-bind-mount
    case (Caddyfile/config.yml) + a generic bounce. Confirm-gated."""
    if not container:
        return _err("container required")
    if not confirm:
        return _need_confirm("restart", container)
    run = _runner(run_remote, ssh_host)
    rc, out, err = run(["docker", "restart", container])
    if rc != 0:
        return _err(f"docker restart {container} failed: {err.strip()}")
    return {"ok": True, "status": "restarted", "exit_code": 0, "container": container}


def recreate(product: str, confirm: bool = False, ssh_host: str = DEFAULT_HOST,
             repo_dir: str = DEFAULT_REPO_DIR, compose_file: str = DEFAULT_COMPOSE,
             run_remote: Callable | None = None) -> dict[str, Any]:
    """`docker compose up -d --force-recreate <product>` — recreate a service on
    its current image (e.g. after a compose/env edit). Confirm-gated."""
    if not product:
        return _err("product required")
    if not confirm:
        return _need_confirm("recreate", product)
    run = _runner(run_remote, ssh_host)
    rc, out, err = run(["docker", "compose", "-f", f"{repo_dir}/{compose_file}",
                        "up", "-d", "--force-recreate", product])
    if rc != 0:
        return _err(f"compose up -d --force-recreate {product} failed: {err.strip() or out.strip()}")
    return {"ok": True, "status": "recreated", "exit_code": 0, "product": product}


def prune(confirm: bool = False, ssh_host: str = DEFAULT_HOST,
          run_remote: Callable | None = None) -> dict[str, Any]:
    """Reclaim space: `docker image prune -f` — removes ONLY dangling (untagged)
    images. Never `-a` and never volumes, so a tagged :previous / a running image
    is NEVER touched (rollback targets stay intact). Confirm-gated."""
    if not confirm:
        return _need_confirm("prune dangling images", "VPS")
    run = _runner(run_remote, ssh_host)
    rc, out, err = run(["docker", "image", "prune", "-f"])
    if rc != 0:
        return _err(f"docker image prune -f failed: {err.strip()}")
    reclaimed = ""
    for line in (out or "").splitlines():
        if "reclaimed" in line.lower():
            reclaimed = line.strip()
    return {"ok": True, "status": "pruned", "exit_code": 0, "reclaimed": reclaimed or out.strip()}


def register(server) -> None:
    @server.tool(name="noctus.vps.ps",
                 description="List noctus containers on the VPS (name/image/status/health) over SSH. Read-only. all=True includes stopped.")
    def _ps(all: bool = False, ssh_host: str = DEFAULT_HOST) -> dict:
        return ps(ssh_host=ssh_host, all=all)

    @server.tool(name="noctus.vps.health",
                 description="Fleet health rollup on the VPS — healthy/starting/unhealthy lists + verdict (status='degraded' if any unhealthy). Read-only.")
    def _health(ssh_host: str = DEFAULT_HOST) -> dict:
        return health(ssh_host=ssh_host)

    @server.tool(name="noctus.vps.logs",
                 description="Tail a container's logs over SSH (read-only). lines=N, optional grep substring filter.")
    def _logs(container: str, lines: int = 80, grep: str | None = None, ssh_host: str = DEFAULT_HOST) -> dict:
        return logs(container, lines=lines, grep=grep, ssh_host=ssh_host)

    @server.tool(name="noctus.vps.inspect",
                 description="Inspect a container: image id / state / health / started-at / ports. Read-only.")
    def _inspect(container: str, ssh_host: str = DEFAULT_HOST) -> dict:
        return inspect(container, ssh_host=ssh_host)

    @server.tool(name="noctus.vps.images",
                 description="List noctus images on the VPS (repo:tag/id/size/age). Read-only.")
    def _images(ssh_host: str = DEFAULT_HOST) -> dict:
        return images(ssh_host=ssh_host)

    @server.tool(name="noctus.vps.disk",
                 description="VPS disk pressure: root fs use% + `docker system df` (images/containers/build-cache). Read-only.")
    def _disk(ssh_host: str = DEFAULT_HOST) -> dict:
        return disk(ssh_host=ssh_host)

    @server.tool(name="noctus.vps.stats",
                 description="Per-container CPU/mem on the VPS (one-shot docker stats). Read-only.")
    def _stats(ssh_host: str = DEFAULT_HOST) -> dict:
        return stats(ssh_host=ssh_host)

    @server.tool(name="noctus.vps.restart",
                 description="Restart a container (stale single-file-mount fix / generic bounce). Confirm-gated production mutation.")
    def _restart(container: str, confirm: bool = False, ssh_host: str = DEFAULT_HOST) -> dict:
        return restart(container, confirm=confirm, ssh_host=ssh_host)

    @server.tool(name="noctus.vps.recreate",
                 description="compose up -d --force-recreate a product on its current image. Confirm-gated production mutation.")
    def _recreate(product: str, confirm: bool = False, ssh_host: str = DEFAULT_HOST) -> dict:
        return recreate(product, confirm=confirm, ssh_host=ssh_host)

    @server.tool(name="noctus.vps.prune",
                 description="Reclaim space: docker image prune -f (DANGLING only — never -a, never tagged/running images). Confirm-gated.")
    def _prune(confirm: bool = False, ssh_host: str = DEFAULT_HOST) -> dict:
        return prune(confirm=confirm, ssh_host=ssh_host)


__all__ = ["ps", "health", "logs", "inspect", "images", "disk", "stats",
           "restart", "recreate", "prune", "_BANNED_TOKENS", "register"]
