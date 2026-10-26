"""noctus.dev.waha_instance -- one WAHA Core container per WhatsApp number, declared as data.

WAHA CORE allows exactly one session per container, so "a million numbers" = N containers. The instances are
DATA (`deploy/fleet/waha-instances.yml`); `deploy/fleet/compose.waha.yml` is RENDERED from it (never hand-copied
blocks -- KB § PATTERNS/devops/product-lockfile-and-slug-drift.md). Actions:

  render  offline: declared -> compose text (--write refreshes the committed file)
  list    declared vs running vs health vs RSS (SSH, read-only)
  plan    the service + the .env.fleet key NAMES to generate on the VPS (values never cross the wire)
  apply   confirm=True: `compose up -d --no-deps waha-<name>` for ONE instance (dry-run default)
  remove  confirm=True: refuses when the session is WORKING unless force=True; snapshots the volume first

KB § CONTEXT/INTEGRATIONS/whatsapp.md § One WAHA per number.
"""
from __future__ import annotations

import json
import re
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

from ._vps_ssh import run_remote

DATA_REL = "deploy/fleet/waha-instances.yml"
COMPOSE_REL = "deploy/fleet/compose.waha.yml"
VPS_REPO = "/opt/noctus/noctusai"
VPS_FLEET = f"{VPS_REPO}/deploy/fleet"
_NAME_RE = re.compile(r"^[a-z][a-z0-9]{0,23}(-[a-z0-9]+)*$")


def _root(repo_root, worktree_path) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    return Path(resolve_caller_root(worktree_path)) if worktree_path else Path(REPO_ROOT)


def env_keys(name: str) -> dict[str, str]:
    """The three .env.fleet key NAMES of an instance (never values)."""
    up = name.upper().replace("-", "_")
    return {
        "api_key": f"WAHA_{up}_API_KEY",
        "hmac_secret": f"WAHA_{up}_HMAC_SECRET",
        "dashboard_password": f"WAHA_{up}_DASHBOARD_PASSWORD",
    }


def parse_instances(text: str) -> dict:
    """declared YAML -> validated spec. ValueError on anything the renderer cannot express faithfully."""
    import yaml

    data = yaml.safe_load(text) or {}
    for k in ("image", "platform", "engine", "mem_limit", "node_heap_mb"):
        if not data.get(k):
            raise ValueError(f"{DATA_REL}: missing `{k}`")
    if str(data["image"]).endswith(":latest") or ":" not in str(data["image"]):
        raise ValueError(f"{DATA_REL}: image must be pinned to a version tag, got {data['image']!r}")
    insts = data.get("instances")
    if not isinstance(insts, list) or not insts:
        raise ValueError(f"{DATA_REL}: no non-empty `instances:` list")
    seen: set[str] = set()
    for i, inst in enumerate(insts):
        name = str((inst or {}).get("name") or "")
        if not _NAME_RE.match(name):
            raise ValueError(f"instances[{i}]: bad name {name!r} (lowercase alnum/dash)")
        if name in seen:
            raise ValueError(f"instances[{i}]: duplicate name {name!r}")
        seen.add(name)
        if not inst.get("product"):
            raise ValueError(f"instances[{i}] ({name}): missing `product`")
        inst.setdefault("session", "default")
    return data


def _service(spec: dict, inst: dict) -> str:
    n = inst["name"]
    k = env_keys(n)
    return f"""  waha-{n}:
    # {inst['product']}'s own WhatsApp number (session `{inst.get('session')}`). Internal only: http://waha-{n}:3000
    image: {spec['image']}
    platform: {spec['platform']}
    container_name: noctus-waha-{n}
    environment:
      WHATSAPP_DEFAULT_ENGINE: {spec['engine']}
      WHATSAPP_API_KEY: ${{{k['api_key']}:?generate {k['api_key']} in .env.fleet on the VPS}}
      WHATSAPP_HOOK_HMAC_KEY: ${{{k['hmac_secret']}:?generate {k['hmac_secret']} in .env.fleet on the VPS}}
      WAHA_DASHBOARD_USERNAME: admin
      WAHA_DASHBOARD_PASSWORD: ${{{k['dashboard_password']}:?generate {k['dashboard_password']} in .env.fleet on the VPS}}
      WHATSAPP_SWAGGER_USERNAME: admin
      WHATSAPP_SWAGGER_PASSWORD: ${{{k['dashboard_password']}:?generate {k['dashboard_password']} in .env.fleet on the VPS}}
      WHATSAPP_NOWEB_STORE_ENABLED: "true"
      WHATSAPP_NOWEB_STORE_FULL_SYNC: "true"
      WHATSAPP_START_SESSION: {inst.get('session')}
      NODE_OPTIONS: --max-old-space-size={spec['node_heap_mb']}
    expose:
      - "3000"
    volumes:
      - waha_{n.replace('-', '_')}:/app/.sessions
    networks:
      - noctus-net
    mem_limit: {spec['mem_limit']}
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "node -e \\"fetch('http://localhost:3000/ping').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\\""]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s
"""


def render_compose(spec: dict) -> str:
    out = [
        "# GENERATED from deploy/fleet/waha-instances.yml by noctus.dev.waha_instance action='render' -- DO NOT EDIT.\n"
        "# One WAHA Core container per WhatsApp number. Run from deploy/fleet on the VPS (reads .env.fleet):\n"
        "#   docker compose -f compose.waha.yml up -d --no-deps waha-<name>\n"
        "# KB § CONTEXT/INTEGRATIONS/whatsapp.md § One WAHA per number.\n"
        "name: noctus-waha\n\nservices:\n"
    ]
    out += [_service(spec, i) for i in spec["instances"]]
    out.append("\nnetworks:\n  noctus-net:\n    name: noctus-net\n    external: true\n\nvolumes:\n")
    for i in spec["instances"]:
        n = i["name"]
        out.append(f"  waha_{n.replace('-', '_')}:\n    name: noctus-waha-{n}\n")
    return "".join(out)


def load_spec(root: Path) -> dict:
    p = root / DATA_REL
    if not p.is_file():
        raise ValueError(f"{DATA_REL} not found under {root}")
    return parse_instances(p.read_text(encoding="utf-8"))


def _inst(spec: dict, name: str | None) -> dict:
    for i in spec["instances"]:
        if i["name"] == name:
            return i
    raise ValueError(f"instance {name!r} is not declared in {DATA_REL}")


def _sh(host: str, cmd: str, timeout: float = 90):
    return run_remote(host, cmd, timeout=timeout)


def _list(spec: dict, host: str) -> dict:
    rows = []
    for inst in spec["instances"]:
        n = inst["name"]
        c = f"noctus-waha-{n}"
        fmt = "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{end}}"
        rc, out, _ = _sh(host, f"docker inspect -f '{fmt}' {c}")
        row = {"name": n, "container": c, "declared": True, "running": False, "health": None, "rss_mb": None,
               "session_status": None}
        if rc == 0:
            state, _, health = out.strip().partition("|")
            row.update(running=state == "running", health=health or None)
            rc2, mem, _ = _sh(host, f"docker stats --no-stream --format '{{{{.MemUsage}}}}' {c}")
            if rc2 == 0:
                row["rss_mb"] = mem.strip().split("/")[0].strip()
            row["session_status"] = _session_status(host, c, n)
        rows.append(row)
    return {"ok": True, "action": "list", "instances": rows}


def _session_status(host: str, container: str, name: str) -> str | None:
    """Session status via the container itself; the api key is read INSIDE the container, never echoed."""
    cmd = (f"docker exec {container} sh -c 'node -e \"fetch(\\\"http://localhost:3000/api/sessions/default\\\","
           "{headers:{\\\"X-Api-Key\\\":process.env.WHATSAPP_API_KEY}}).then(r=>r.json()).then(j=>console.log(j.status))"
           ".catch(()=>console.log(\\\"unreachable\\\"))\"'")
    rc, out, _ = _sh(host, cmd)
    return out.strip() or None if rc == 0 else None


def _plan(spec: dict, name: str) -> dict:
    inst = _inst(spec, name)
    k = env_keys(name)
    return {
        "ok": True, "action": "plan", "name": name, "status": "planned",
        "service": _service(spec, inst), "service_dns": f"http://waha-{name}:3000",
        "env_fleet_keys_to_generate_on_vps": list(k.values()),
        "product_env_contract": {
            "note": f"{inst['product'].upper()}_WAHA_* in the root .env; the HMAC value is the SAME secret as {k['hmac_secret']}",
            f"{inst['product'].upper()}_WAHA_BASE_URL": f"http://waha-{name}:3000",
            f"{inst['product'].upper()}_WAHA_SESSION": inst["session"],
        },
        "generate_cmd": "for k in " + " ".join(k.values()) + "; do grep -q \"^$k=\" .env.fleet || "
                        "echo \"$k=$(openssl rand -hex 32)\" >> .env.fleet; done   # back up .env.fleet first; never print values",
    }


def _apply(spec: dict, name: str, host: str, confirm: bool) -> dict:
    p = _plan(spec, name)
    if not confirm:
        p.update(action="apply", note="DRY RUN -- pass confirm=True to `compose up -d --no-deps` this ONE instance")
        return p
    _inst(spec, name)
    rc, _o, err = _sh(host, f"cd {VPS_FLEET} && for k in {' '.join(env_keys(name).values())}; do "
                            "grep -q \"^$k=.\" .env.fleet || { echo MISSING:$k; exit 3; }; done")
    if rc != 0:
        return {"ok": False, "action": "apply", "status": "blocked",
                "error": f"required .env.fleet keys missing/empty on the VPS (generate them first): {_o.strip() or err.strip()}"}
    rc, out, err = _sh(host, f"cd {VPS_FLEET} && docker compose -f compose.waha.yml up -d --no-deps waha-{name}", timeout=300)
    return {"ok": rc == 0, "action": "apply", "status": "applied" if rc == 0 else "error", "name": name,
            "stdout": out.strip()[-600:], "error": None if rc == 0 else err.strip()[-600:]}


def _remove(spec: dict, name: str, host: str, confirm: bool, force: bool) -> dict:
    _inst(spec, name)
    c = f"noctus-waha-{name}"
    status = _session_status(host, c, name)
    if status == "WORKING" and not force:
        return {"ok": False, "action": "remove", "status": "blocked",
                "error": f"REFUSED -- session of {c} is WORKING (a paired number goes offline); force=True to override"}
    vol = f"noctus-waha-{name}"
    plan = [f"docker run --rm -v {vol}:/v -v /opt/noctus/backups:/b alpine tar czf /b/{vol}-$(date +%Y%m%d%H%M).tgz -C /v .",
            f"cd {VPS_FLEET} && docker compose -f compose.waha.yml rm -sf waha-{name}"]
    if not confirm:
        return {"ok": True, "action": "remove", "status": "planned", "session_status": status, "steps": plan,
                "note": "DRY RUN -- volume is snapshotted first and NEVER deleted; also drop the instance from waha-instances.yml"}
    for step in plan:
        rc, _o, err = _sh(host, step, timeout=300)
        if rc != 0:
            return {"ok": False, "action": "remove", "status": "error", "error": err.strip()[-400:], "step": step}
    return {"ok": True, "action": "remove", "status": "removed", "volume_kept": vol}


def waha_instance(action: str = "list", name: str | None = None, ssh_host: str = "noctus-vps", confirm: bool = False,
                  force: bool = False, write: bool = False, repo_root: str | None = None,
                  worktree_path: str | None = None) -> dict:
    """See module docstring. DRY-RUN by default; production writes need confirm=True."""
    try:
        root = _root(repo_root, worktree_path)
        spec = load_spec(root)
        if action == "render":
            text = render_compose(spec)
            if write:
                (root / COMPOSE_REL).write_text(text, encoding="utf-8")
            return {"ok": True, "action": "render", "written": write, "compose": text}
        if action == "list":
            return _list(spec, ssh_host)
        if action in ("plan", "add"):
            return _plan(spec, name or "")
        if action == "apply":
            return _apply(spec, name or "", ssh_host, confirm)
        if action == "remove":
            return _remove(spec, name or "", ssh_host, confirm, force)
    except ValueError as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    return {"ok": False, "action": action, "error": f"unknown action {action!r} -- render|list|plan|apply|remove"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.waha_instance",
        description=(
            "One WAHA Core container per WhatsApp number, declared as data (deploy/fleet/waha-instances.yml -> rendered "
            "compose.waha.yml). action=render (offline; write=True refreshes the file) | list (declared vs running vs health "
            "vs RSS vs session status) | plan/add (the service + the .env.fleet key NAMES to generate on the VPS -- values never "
            "cross the wire) | apply (confirm=True: compose up -d --no-deps for ONE instance; refuses when keys are missing) | "
            "remove (confirm=True; refuses a WORKING session unless force; snapshots the volume first, never deletes it). "
            "DRY-RUN default. KB § CONTEXT/INTEGRATIONS/whatsapp.md § One WAHA per number."
        ),
    )
    def _waha_instance(action: str = "list", name: str = "", ssh_host: str = "noctus-vps", confirm: bool = False,
                       force: bool = False, write: bool = False, worktree_path: str = "") -> dict:
        return waha_instance(action=action, name=name or None, ssh_host=ssh_host, confirm=confirm, force=force,
                             write=write, worktree_path=worktree_path or None)


__all__ = ["waha_instance", "register", "render_compose", "parse_instances", "env_keys", "load_spec"]
