"""noctus.dev.smoke_fleet — MCP exposure of the post-fleet-up smoke test.

MCP-first: `scripts/smoke-fleet.sh` was a bash one-off. Behaviour-preserving
port: hit `/api/health` on every backend, sample the frontend (core + seed),
aggregate pass/fail. The script's `exit 0` (every backend 200) / `exit 1`
(≥1 failed) becomes `status="healthy"|"degraded"` + `exit_code` 0|1.

Registry source = the `BEGIN_PRODUCTS_REGISTRY`…`END_PRODUCTS_REGISTRY`
block in `start.sh` (single source of truth — same as the script's awk).
Each entry is `slug:name:backend_port:frontend_port`.

The HTTP layer is injectable (`fetch_status`) so the colocated test stubs
it — no real network. Default fetcher uses urllib with the script's
behaviour: any non-200 / connection error → "FAIL" (mirrors the script's
`|| echo "FAIL"`).
"""
from __future__ import annotations

import pathlib
import re
import urllib.error
import urllib.request
from typing import Any, Callable

from settings import REPO_ROOT
from workspace import resolve_caller_root

# Frontend smoke sample — verbatim from smoke-fleet.sh
# (`for entry in "core:5173" "seed:8100"`). slug → frontend port.
FRONTEND_SAMPLE: list[tuple[str, str]] = [("core", "5173"), ("seed", "8100")]

_REG_BEGIN = "# BEGIN_PRODUCTS_REGISTRY"
_REG_END = "# END_PRODUCTS_REGISTRY"
# matches `  "core:Core:8000:5173"` style registry lines
_ENTRY_RE = re.compile(r'"([^"]+)"')


def parse_registry(start_sh_text: str) -> list[tuple[str, str, str, str]]:
    """Parse the start.sh PRODUCTS registry block — same single source of
    truth the script's awk reads. Returns (slug, name, bport, fport)."""
    out: list[tuple[str, str, str, str]] = []
    capture = False
    for line in start_sh_text.splitlines():
        if line.startswith(_REG_BEGIN):
            capture = True
            continue
        if line.startswith(_REG_END):
            break
        if not capture:
            continue
        m = _ENTRY_RE.search(line)
        if not m:
            continue
        parts = m.group(1).split(":")
        if len(parts) >= 4:
            out.append((parts[0], parts[1], parts[2], parts[3]))
    return out


def _default_fetch_status(url: str) -> str:
    """Mirror `curl -fsS -o /dev/null -w "%{http_code}" ... || echo FAIL`:
    return the HTTP status string, or "FAIL" on any error / non-2xx."""
    try:
        req = urllib.request.Request(url, method="GET")
        with urllib.request.urlopen(req, timeout=5) as resp:
            return str(resp.status)
    except urllib.error.HTTPError as exc:  # got a response, non-2xx
        return str(exc.code)
    except Exception:  # connection refused / timeout / DNS — script's FAIL
        return "FAIL"


def smoke_fleet(
    host: str = "localhost",
    fetch_status: Callable[[str], str] | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
) -> dict[str, Any]:
    """Hit /api/health on every backend + sample frontends; aggregate.

    Preserves smoke-fleet.sh semantics exactly:
      • backend OK ⇔ status == "200"; any other → fail, increment `fails`.
      • `fails > 0` ⇒ exit 1 / status="degraded"; else exit 0 /
        status="healthy".
      • frontend sample (core:5173, seed:8100) is reported, NOT counted
        toward pass/fail (the script only sums backend fails).
      • empty registry ⇒ the script's `exit 1` + ERRO message.
    """
    fetch = fetch_status or _default_fetch_status
    if repo_root is not None:
        root = pathlib.Path(repo_root)
    elif worktree_path:
        root = pathlib.Path(resolve_caller_root(worktree_path))
    else:
        root = pathlib.Path(REPO_ROOT)
    start_sh = root / "start.sh"
    if not start_sh.exists():
        return {
            "ok": False,
            "error": f"start.sh not found at {start_sh}",
            "status": "error",
            "exit_code": 1,
        }
    registry = parse_registry(start_sh.read_text())
    if not registry:
        return {
            "ok": False,
            "error": "PRODUCTS array vazio. start.sh ainda nao escaneado?",
            "status": "error",
            "exit_code": 1,
        }

    backends: list[dict[str, Any]] = []
    fails = 0
    for slug, _name, bport, _fport in registry:
        url = f"http://{host}:{bport}/api/health"
        status = fetch(url)
        ok = status == "200"
        if not ok:
            fails += 1
        backends.append(
            {"slug": slug, "port": bport, "url": url, "status": status, "ok": ok}
        )

    frontends: list[dict[str, Any]] = []
    for slug, fport in FRONTEND_SAMPLE:
        url = f"http://{host}:{fport}"
        status = fetch(url)
        frontends.append(
            {
                "slug": slug,
                "port": fport,
                "url": url,
                "status": status,
                "ok": status == "200",
            }
        )

    healthy = fails == 0
    return {
        "ok": True,
        "status": "healthy" if healthy else "degraded",
        "exit_code": 0 if healthy else 1,
        "total": len(registry),
        "passed": len(registry) - fails,
        "failed": fails,
        "backends": backends,
        "frontends": frontends,
    }


def register(server) -> None:
    @server.tool(
        name="noctus.dev.smoke_fleet",
        description=(
            "Post-fleet-up smoke test (port of scripts/smoke-fleet.sh). "
            "Hits /api/health on every backend in the start.sh PRODUCTS "
            "registry + samples the core/seed frontends; aggregates "
            "pass/fail. status='healthy' (every backend 200, exit 0) | "
            "'degraded' (≥1 failed, exit 1). Run AFTER ./start.sh; "
            "idempotent. Pass worktree_path when called from inside a git "
            "worktree. See KB § PATTERNS/containerization.md."
        ),
    )
    def _smoke_fleet(
        host: str = "localhost",
        worktree_path: str | None = None,
    ) -> dict:
        return smoke_fleet(host=host, worktree_path=worktree_path)


__all__ = [
    "smoke_fleet",
    "parse_registry",
    "FRONTEND_SAMPLE",
    "register",
]
