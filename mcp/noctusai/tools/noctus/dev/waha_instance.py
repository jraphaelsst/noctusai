"""noctus.dev.waha_instance -- one WAHA Core container per WhatsApp number, declared as data.

WAHA CORE allows exactly one session per container, so "a million numbers" = N containers. The instances are
DATA (`deploy/fleet/waha-instances.yml`); `deploy/fleet/compose.waha.yml` is RENDERED from it (never hand-copied
blocks -- KB § PATTERNS/devops/product-lockfile-and-slug-drift.md). Actions:

  render  offline: declared -> compose text (--write refreshes the committed file). Also `env=<name>`-style output via
          `plan`: the product env contract incl. `<PRODUCT>_WAHA_LINE_POLICY`.
  list    declared vs running vs health vs RSS (SSH, read-only)
  plan    the service + the .env.fleet key NAMES to generate on the VPS (values never cross the wire)
  apply   confirm=True: `compose up -d --no-deps waha-<name>` for ONE instance (dry-run default)
  remove  confirm=True: refuses when the session is WORKING unless force=True; snapshots the volume first

Line policy v1 (KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a): every instance DECLARES `line_policy` (send/mark_online/
full_sync/auto_repair -- the platform ceiling) and may set `edge_deny_writes` (a deny proxy in front of WAHA) and
`dashboard: false`. `send: disabled` REQUIRES both `edge_deny_writes: true` and `dashboard: false`.

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


def env_keys(name: str, *, dashboard: bool = True) -> dict[str, str]:
    """The .env.fleet key NAMES of an instance (never values). No dashboard => no dashboard password key."""
    up = name.upper().replace("-", "_")
    keys = {"api_key": f"WAHA_{up}_API_KEY", "hmac_secret": f"WAHA_{up}_HMAC_SECRET"}
    if dashboard:
        keys["dashboard_password"] = f"WAHA_{up}_DASHBOARD_PASSWORD"
    return keys


def inst_keys(inst: dict) -> dict[str, str]:
    return env_keys(inst["name"], dashboard=inst.get("dashboard", True))


_POLICY_KEYS = ("send", "mark_online", "full_sync", "auto_repair")


def line_policy_json(inst: dict) -> str:
    """The `<PRODUCT>_WAHA_LINE_POLICY` env value of an instance -- byte-identical to the seed's
    `LinePolicy.as_json()` (a test pins the parity)."""
    pol = inst["line_policy"]
    return json.dumps({k: pol[k] for k in _POLICY_KEYS}, separators=(",", ":"))


def _validate_policy(i: int, name: str, inst: dict) -> None:
    pol = inst.get("line_policy")
    if not isinstance(pol, dict):
        raise ValueError(f"instances[{i}] ({name}): missing `line_policy` -- every line DECLARES its policy "
                         "(send/mark_online/full_sync/auto_repair); an undeclared line is refused, not defaulted")
    unknown = sorted(set(pol) - set(_POLICY_KEYS))
    missing = [k for k in _POLICY_KEYS if k not in pol]
    if unknown or missing:
        raise ValueError(f"instances[{i}] ({name}): line_policy unknown={unknown} missing={missing}")
    if pol["send"] not in ("enabled", "disabled"):
        raise ValueError(f"instances[{i}] ({name}): line_policy.send must be enabled|disabled, got {pol['send']!r}")
    for k in ("mark_online", "full_sync", "auto_repair"):
        if not isinstance(pol[k], bool):
            raise ValueError(f"instances[{i}] ({name}): line_policy.{k} must be a boolean")
    for opt in ("edge_deny_writes", "dashboard"):
        if opt in inst and not isinstance(inst[opt], bool):
            raise ValueError(f"instances[{i}] ({name}): `{opt}` must be a boolean")
    inst.setdefault("edge_deny_writes", False)
    inst.setdefault("dashboard", True)
    if pol["send"] == "disabled" and not (inst["edge_deny_writes"] and inst["dashboard"] is False):
        raise ValueError(f"instances[{i}] ({name}): `send: disabled` requires `edge_deny_writes: true` and "
                         "`dashboard: false` -- a read-only line is enforced at the edge too, and the dashboard "
                         "can send")
    if pol["send"] == "enabled" and inst["edge_deny_writes"]:
        raise ValueError(f"instances[{i}] ({name}): `edge_deny_writes: true` contradicts `send: enabled`")
    if inst["edge_deny_writes"]:
        up = inst.get("webhook_upstream")
        if not isinstance(up, str) or not re.match(r"^https?://[A-Za-z0-9._-]+(:\d+)?(/[A-Za-z0-9._~/-]*)?$", up):
            raise ValueError(f"instances[{i}] ({name}): `edge_deny_writes: true` requires `webhook_upstream: http://<product>:<port>` "
                             "(the edge relays the core's webhooks there; the core has no route to the product)")


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
        _validate_policy(i, name, inst)
    return data


EDGE_IMAGE = "nginx:1.27-alpine"

#: nginx edge of a read-only line. ONE decision table, mirrored by the seed's `is_whatsapp_write` (a test pins parity
#: on a path matrix, normalising dot-segments the way nginx does): on a `send: disabled` line only
#: `POST /api/sessions/{n}/start` and plain reads pass; a read on a send-class path (WAHA still serves some sends on GET),
#: logout/stop/restart/PUT-config/DELETE and every unknown non-read endpoint are 403. `~*` = case-insensitive (WAHA's
#: router is). The decision is taken on `$uri` (decoded, dot-resolved, slashes merged) and THAT is what is forwarded
#: (`$uri$is_args$args`), never the raw request line, so what was judged is what is sent. `$$` is compose's escape for `$`.
#: Port 3001 is the WEBHOOK RELAY: the core lives on a private network and cannot reach the product, so it POSTs its
#: webhooks to `http://waha-<n>:3001/<path>` and the edge forwards them to the declared `webhook_upstream`.
#: NOC-REMEDIATE[edge-live-verification]: `nginx -t` and the live curl matrix (every verb x the send/presence/session
#: paths x dot-segment and %2e/%2f spellings) have not run -- no docker daemon in the S1 environment; S6 runs them on the
#: throwaway probe line before the personal number is paired. — 2026-11-10
_EDGE_CONF = """\
resolver 127.0.0.11 valid=10s ipv6=off;
map "$$request_method $$uri" $$wa_write {
  default 1;
  "~* ^POST /api/sessions/[^/]+/start$$" 0;
  "~* ^(GET|HEAD|OPTIONS) /api/(send|reaction|starttyping|stoptyping|forwardmessage)" 1;
  "~* ^(GET|HEAD|OPTIONS) /" 0;
}
server {
  listen 3000;
  client_max_body_size 2m;
  location / {
    if ($$wa_write) { return 403 '{"error":"line_write_refused","detail":"this line is read-only (send: disabled)"}'; }
    set $$up http://waha-{name}-core:3000;
    proxy_pass $$up$$uri$$is_args$$args;
    proxy_set_header Host $$host;
    proxy_read_timeout 60s;
  }
}
server {
  listen 3001;
  client_max_body_size 2m;
  location / {
    if ($$request_method != POST) { return 405; }
    set $$hook {webhook_upstream};
    proxy_pass $$hook$$uri$$is_args$$args;
    proxy_set_header Host $$host;
    proxy_read_timeout 30s;
  }
}
"""


def core_service(inst: dict) -> str:
    """The compose service name of the WAHA container itself (behind the edge when there is one)."""
    return f"waha-{inst['name']}-core" if inst.get("edge_deny_writes") else f"waha-{inst['name']}"


def services_of(inst: dict) -> list[str]:
    n = inst["name"]
    return [core_service(inst), f"waha-{n}"] if inst.get("edge_deny_writes") else [f"waha-{n}"]


def _edge_service(inst: dict) -> str:
    n = inst["name"]
    conf = _EDGE_CONF.replace("{name}", n).replace("{webhook_upstream}", inst["webhook_upstream"].rstrip("/"))
    body = "".join("        " + ln + "\n" if ln else "\n" for ln in conf.splitlines())
    return f"""  waha-{n}:
    # EDGE DENY for {inst['product']}'s read-only line `{n}` (send: disabled): http://waha-{n}:3000 is THIS proxy; it 403s every
    # write to WhatsApp and forwards the rest to {core_service(inst)}. Products talk to the proxy, never to the core.
    image: {EDGE_IMAGE}
    container_name: noctus-waha-{n}
    depends_on:
      - {core_service(inst)}
    environment:
      EDGE_CONF: |
{body.rstrip(chr(10))}
    command: ["/bin/sh", "-c", "printf '%s' \\"$$EDGE_CONF\\" > /etc/nginx/conf.d/default.conf && exec nginx -g 'daemon off;'"]
    expose:
      - "3000"
      - "3001"
    networks:
      - noctus-net
      - waha_{n.replace('-', '_')}_edge
    mem_limit: 64m
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "wget -q -O /dev/null http://localhost:3000/ping || exit 1"]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 10s
"""


def _service(spec: dict, inst: dict) -> str:
    n = inst["name"]
    k = inst_keys(inst)
    edge = inst.get("edge_deny_writes", False)
    dash = inst.get("dashboard", True)
    svc = core_service(inst)
    # an edge line's core is reachable ONLY through its edge: a private network, never noctus-net
    core_net = f"waha_{n.replace('-', '_')}_edge" if edge else "noctus-net"
    where = f"internal only; reach it through the edge `waha-{n}`" if edge else f"Internal only: http://waha-{n}:3000"
    if dash:
        ui = f"""      WAHA_DASHBOARD_USERNAME: admin
      WAHA_DASHBOARD_PASSWORD: ${{{k['dashboard_password']}:?generate {k['dashboard_password']} in .env.fleet on the VPS}}
      WHATSAPP_SWAGGER_USERNAME: admin
      WHATSAPP_SWAGGER_PASSWORD: ${{{k['dashboard_password']}:?generate {k['dashboard_password']} in .env.fleet on the VPS}}
"""
    else:
        ui = """      WAHA_DASHBOARD_ENABLED: "false"
      WHATSAPP_SWAGGER_ENABLED: "false"
"""
    out = f"""  {svc}:
    # {inst['product']}'s own WhatsApp number (session `{inst.get('session')}`). {where}
    image: {spec['image']}
    platform: {spec['platform']}
    container_name: noctus-{svc}
    environment:
      WHATSAPP_DEFAULT_ENGINE: {spec['engine']}
      WHATSAPP_API_KEY: ${{{k['api_key']}:?generate {k['api_key']} in .env.fleet on the VPS}}
      WHATSAPP_HOOK_HMAC_KEY: ${{{k['hmac_secret']}:?generate {k['hmac_secret']} in .env.fleet on the VPS}}
{ui}      NODE_OPTIONS: --max-old-space-size={spec['node_heap_mb']}
    expose:
      - "3000"
    volumes:
      - waha_{n.replace('-', '_')}:/app/.sessions
    networks:
      - {core_net}
    mem_limit: {spec['mem_limit']}
    restart: unless-stopped
    healthcheck:
      test: ["CMD-SHELL", "node -e \\"fetch('http://localhost:3000/ping').then(r=>process.exit(r.ok?0:1)).catch(()=>process.exit(1))\\""]
      interval: 30s
      timeout: 5s
      retries: 3
      start_period: 40s
"""
    return out + (_edge_service(inst) if edge else "")


def render_compose(spec: dict) -> str:
    out = [
        "# GENERATED from deploy/fleet/waha-instances.yml by noctus.dev.waha_instance action='render' -- DO NOT EDIT.\n"
        "# One WAHA Core container per WhatsApp number. Run from deploy/fleet on the VPS (reads .env.fleet):\n"
        "#   docker compose -f compose.waha.yml up -d --no-deps waha-<name>   (an edge line: waha-<name>-core waha-<name>)\n"
        "# KB § CONTEXT/INTEGRATIONS/whatsapp.md § One WAHA per number.\n"
        "name: noctus-waha\n\nservices:\n"
    ]
    out += [_service(spec, i) for i in spec["instances"]]
    out.append("\nnetworks:\n  noctus-net:\n    name: noctus-net\n    external: true\n")
    for i in spec["instances"]:
        if i.get("edge_deny_writes"):
            n = i["name"]
            out.append(f"  waha_{n.replace('-', '_')}_edge:\n    name: noctus-waha-{n}-edge\n")
    out.append("\nvolumes:\n")
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
        c = f"noctus-{core_service(inst)}"
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
    k = inst_keys(inst)
    up = inst["product"].upper().replace("-", "_")
    return {
        "ok": True, "action": "plan", "name": name, "status": "planned",
        "service": _service(spec, inst), "service_dns": f"http://waha-{name}:3000",
        "services": services_of(inst), "edge_deny_writes": inst["edge_deny_writes"], "dashboard": inst["dashboard"],
        "env_fleet_keys_to_generate_on_vps": list(k.values()),
        "product_env_contract": {
            "note": f"{inst['product'].upper()}_WAHA_* in the root .env; the HMAC value is the SAME secret as {k['hmac_secret']}",
            f"{up}_WAHA_BASE_URL": f"http://waha-{name}:3000",
            f"{up}_WAHA_SESSION": inst["session"],
            # Line policy v1: the product registers it at boot (register_line_policy) -- WITHOUT it every write is refused.
            f"{up}_WAHA_LINE_POLICY": line_policy_json(inst),
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
    inst = _inst(spec, name)
    rc, _o, err = _sh(host, f"cd {VPS_FLEET} && for k in {' '.join(inst_keys(inst).values())}; do "
                            "grep -q \"^$k=.\" .env.fleet || { echo MISSING:$k; exit 3; }; done")
    if rc != 0:
        return {"ok": False, "action": "apply", "status": "blocked",
                "error": f"required .env.fleet keys missing/empty on the VPS (generate them first): {_o.strip() or err.strip()}"}
    rc, out, err = _sh(host, f"cd {VPS_FLEET} && docker compose -f compose.waha.yml up -d --no-deps {' '.join(services_of(inst))}", timeout=300)
    return {"ok": rc == 0, "action": "apply", "status": "applied" if rc == 0 else "error", "name": name,
            "stdout": out.strip()[-600:], "error": None if rc == 0 else err.strip()[-600:]}


def _remove(spec: dict, name: str, host: str, confirm: bool, force: bool) -> dict:
    inst = _inst(spec, name)
    c = f"noctus-{core_service(inst)}"
    status = _session_status(host, c, name)
    if status == "WORKING" and not force:
        return {"ok": False, "action": "remove", "status": "blocked",
                "error": f"REFUSED -- session of {c} is WORKING (a paired number goes offline); force=True to override"}
    vol = f"noctus-waha-{name}"
    plan = [f"docker run --rm -v {vol}:/v -v /opt/noctus/backups:/b alpine tar czf /b/{vol}-$(date +%Y%m%d%H%M).tgz -C /v .",
            f"cd {VPS_FLEET} && docker compose -f compose.waha.yml rm -sf {' '.join(services_of(inst))}"]
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


__all__ = ["waha_instance", "register", "render_compose", "parse_instances", "env_keys", "inst_keys", "load_spec",
           "line_policy_json", "core_service", "services_of"]
