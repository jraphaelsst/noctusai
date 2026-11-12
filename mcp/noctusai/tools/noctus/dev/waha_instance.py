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
import shlex
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

from ._vps_ssh import (  # noqa: F401 - re-exported for the owner-hand path
    _OWNER_HAND_SCOPE,
    OWNER_HAND_RUNNER_REFUSAL,
    OWNER_HAND_LIVE_SCOPE,
    OWNER_HAND_TEST_SCOPE,
    _owner_scope_problem,
    run_remote,
)

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
    out = {k: pol[k] for k in _POLICY_KEYS}
    if inst.get("edge_deny_writes"):
        out["webhook_relay"] = relay_base(inst)  # the ONLY webhook base a read-only line may register
    return json.dumps(out, separators=(",", ":"))


def relay_base(inst: dict) -> str:
    return f"http://waha-{inst['name']}:3001"


READ_ONLY_REL = "seed/lib/backend/noctusai_lib/integrations/whatsapp/read_only_lines.py"


def read_only_aliases(inst: dict) -> list[str]:
    """Every host:port a read-only line answers on (service + container names, API + relay ports)."""
    n = inst["name"]
    names = [f"waha-{n}", f"noctus-waha-{n}", f"waha-{n}-core", f"noctus-waha-{n}-core"]
    return sorted(f"{h}:{p}" for h in names for p in (3000, 3001))


def render_read_only_lines(spec: dict) -> str:
    """Generated seed module: the strictest-wins read-only host set derived from the declared instances."""
    rows = {}
    for inst in spec["instances"]:
        if inst["line_policy"]["send"] == "disabled":
            for host in read_only_aliases(inst):
                rows[host] = json.loads(line_policy_json(inst))
    body = "".join(f"    {h!r}: {v!r},\n" for h, v in sorted(rows.items()))
    # hosts that resolve from the PRODUCT network (noctus-net): only the edge names. The `-core` names sit on a private
    # network, are matched by name and must NOT count as "unresolvable aliases" in the seed (that would fail every
    # unrelated host closed).
    resolvable = sorted({h for inst in spec["instances"] if inst["line_policy"]["send"] == "disabled"
                         for h in (f"waha-{inst['name']}", f"noctus-waha-{inst['name']}")})
    return (
        '"""GENERATED from deploy/fleet/waha-instances.yml by noctus.dev.waha_instance action=\'render\' -- DO NOT EDIT.\n\n'
        "Every host:port (every container/service alias, ports 3000 and 3001) of a `send: disabled` line, with its declared\n"
        "policy. The seed resolves these STRICTEST-WINS and never lets `\"*\"` apply to them. check_waha_instances_render_sync\n"
        "fails when this file differs from the render. KB § CONTEXT/INTEGRATIONS/whatsapp.md § 6a.\n"
        '"""\n'
        "READ_ONLY_LINES: dict[str, dict] = {" + ("\n" + body if body else "") + "}\n"
        f"RESOLVABLE_FROM_PRODUCT_NETWORK: tuple[str, ...] = {tuple(resolvable)!r}\n"
    )


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
    for opt in ("edge_deny_writes", "dashboard", "personal"):
        if opt in inst and not isinstance(inst[opt], bool):
            raise ValueError(f"instances[{i}] ({name}): `{opt}` must be a boolean")
    if pol["send"] == "disabled" and "personal" not in inst:
        raise ValueError(f"instances[{i}] ({name}): a `send: disabled` line must declare `personal: true|false` explicitly "
                         "(a personal number is provisioned by the owner by hand; it is never a default)")
    inst.setdefault("personal", False)
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


def parse_instances_text(text: str) -> dict:
    return parse_instances(text)


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
#: paths x dot-segment, %2e/%2f, `logout%3F/start`, `start%3F`, `%0D%0A`, `%5c` and X-HTTP-Method-Override spellings) have not run -- no docker daemon in the S1 environment; S6 runs them on the
#: throwaway probe line before the personal number is paired. — 2026-11-10
_EDGE_CONF = """\
resolver 127.0.0.11 valid=10s ipv6=off;
map "$$request_method $$uri" $$wa_write {
  default 1;
  "~* ^POST /api/sessions/[^/]+/start$$" 0;
  "~* ^(GET|HEAD|OPTIONS) /api/(send|reaction|starttyping|stoptyping|forwardmessage|[^/]+/presence)" 1;
  "~* ^(GET|HEAD|OPTIONS) /" 0;
}
server {
  listen 3000;
  client_max_body_size 2m;
  # smuggling spellings in the PATH (encoded control chars, `?` `#` `/` `%`, backslash; the query string is not judged, the
  # seed judges the path only) are refused BEFORE the decision is taken:
  # the decision is on the decoded $$uri, and `logout%3F/start` decodes to a path the core reads as the legacy logout.
  if ($$request_uri ~* "^[^?]*(%(0[0-9a-f]|1[0-9a-f]|2[0356f]|3f|5c|7f)|\\x5c)") { return 400; }
  proxy_set_header X-HTTP-Method-Override "";
  proxy_set_header X-HTTP-Method "";
  proxy_set_header X-Method-Override "";
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
  if ($$request_uri ~* "^[^?]*(%(0[0-9a-f]|1[0-9a-f]|2[0356f]|3f|5c|7f)|\\x5c)") { return 400; }
  proxy_set_header X-HTTP-Method-Override "";
  proxy_set_header X-HTTP-Method "";
  proxy_set_header X-Method-Override "";
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


def _personal_label(inst: dict) -> str:
    """The container label vps_exec trusts from the LIVE inventory: a branch cannot un-stamp a running container."""
    return '    labels:\n      noctus.line.personal: "true"\n' if inst.get("personal") else ""


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
{_personal_label(inst)}    healthcheck:
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
    labels = _personal_label(inst)
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
{labels}    healthcheck:
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


# The owner-hand scope + its runner refusal live in _vps_ssh (the ssh chokepoint itself); re-exported here.


def _sh(host: str, cmd: str, timeout: float = 90):
    why = _owner_scope_problem()
    if why:
        return 1, "", why  # refused before any subprocess
    return run_remote(host, cmd, timeout=timeout)


class _GrantScope:
    """Enter the owner-hand scope of a grant for one `_apply`/`_provision` call (a TEST scope already set is kept)."""

    def __init__(self, grant):
        self.grant, self.token = grant, None

    def __enter__(self):
        if self.grant is not None and _OWNER_HAND_SCOPE.get() is not OWNER_HAND_TEST_SCOPE:  # LIVE -> the grant
            self.token = _OWNER_HAND_SCOPE.set(self.grant)
        return self

    def __exit__(self, *exc):
        if self.token is not None:
            _OWNER_HAND_SCOPE.reset(self.token)
        return False


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


def policy_noweb(inst: dict) -> dict:
    """The `noweb` block WAHA must hold for this line (camelCase wire keys): from the DECLARED policy."""
    pol = inst["line_policy"]
    return {"markOnline": pol["mark_online"], "store": {"enabled": True, "fullSync": pol["full_sync"]}}


#: Both scripts run INSIDE the core container (its API key never leaves it). WAHA takes config only on
#: `POST /api/sessions` (create, start:false) or `PUT /api/sessions/{s}`; `/start` takes none and NOWEB's markOnline
#: defaults to TRUE -- so provisioning is the step that makes a read-only line's first pairing silent. No single quote may
#: appear in either (each is wrapped in one for the remote shell).
_READ_JS = (
    'const H={"X-Api-Key":process.env.WHATSAPP_API_KEY};const S=process.env.POLICY_SESSION;'
    '(async()=>{const r=await fetch((process.env.POLICY_BASE||"http://localhost:3000")+"/api/sessions/"+S,{headers:H});'
    'if(r.status===404){console.log(JSON.stringify({exists:false}));return;}'
    'const j=await r.json();const c=j.config||{};'
    'console.log(JSON.stringify({exists:true,noweb:c.noweb||null,webhooks:(c.webhooks||[]).map(w=>w.url)}));'
    '})().catch(e=>{console.log("ERR "+e.message);process.exit(3);});'
)
_PROVISION_JS = (
    'const H={"X-Api-Key":process.env.WHATSAPP_API_KEY,"Content-Type":"application/json"};'
    'const nw=JSON.parse(process.env.POLICY_NOWEB);const S=process.env.POLICY_SESSION;const RELAY=process.env.POLICY_RELAY||"";'
    '(async()=>{const u=(process.env.POLICY_BASE||"http://localhost:3000")+"/api/sessions";let r=await fetch(u+"/"+S,{headers:H});'
    'if(r.status===404){r=await fetch(u,{method:"POST",headers:H,body:JSON.stringify({name:S,start:false,config:{noweb:nw}})});}'
    'else{const j=await r.json();const c=j.config||{};const o=c.noweb||{};c.noweb=Object.assign({},o,nw);'
    'c.noweb.store=Object.assign({},o.store||{},nw.store);'
    # tighten webhooks too: only the declared relay may stay registered
    'if(RELAY){c.webhooks=(c.webhooks||[]).filter(w=>w.url&&w.url.startsWith(RELAY+"/"));}'
    'r=await fetch(u+"/"+S,{method:"PUT",headers:H,body:JSON.stringify({config:c})});}'
    'if(r.status>=300){console.log("ERR "+r.status);process.exit(2);}'
    'r=await fetch(u+"/"+S,{headers:H});const j=await r.json();const c=j.config||{};'
    'console.log(JSON.stringify({noweb:c.noweb||null,webhooks:(c.webhooks||[]).map(w=>w.url)}));'
    '})().catch(e=>{console.log("ERR "+e.message);process.exit(3);});'
)

#: policy fields that LOOSEN when they go from false to true (markOnline broadcasts presence, fullSync pulls history)
_NOWEB_FIELDS = (("markOnline", lambda n: n.get("markOnline")),
                 ("store.fullSync", lambda n: (n.get("store") or {}).get("fullSync")))


def _loosening(want: dict, ceiling: dict | None, label: str) -> list[str]:
    """Fields where `want` is looser (true) than `ceiling` (false). A missing ceiling field is not a loosening."""
    out = []
    for name, get in _NOWEB_FIELDS:
        if ceiling is not None and get(ceiling) is False and get(want) is True:
            out.append(f"{name}: wants true but {label} has false")
    return out


def _noweb_matches(got, want: dict) -> bool:
    return (isinstance(got, dict) and got.get("markOnline") is want["markOnline"]
            and isinstance(got.get("store"), dict) and got["store"].get("enabled") is True
            and got["store"].get("fullSync") is want["store"]["fullSync"])


PERSONAL_REFUSAL = ("personal line: refused for this caller -- an agent may provision/apply a personal line (with every "
                    "check below) but never remove it, and an owner-hand grant must cover this exact line, host and "
                    "policy; the owner can also run the step by hand, in a Terminal.app window: "
                    "PATH=/usr/bin:/bin:/usr/sbin:/sbin:$PATH mcp/noctusai/.venv/bin/python "
                    "mcp/noctusai/cli.py --waha-instance-owner-hand <provision|apply> <line>")
# A PERSONAL line (owner decision 2026-11-12, superseding D49 of 2026-11-10; option (b) of keep / agents-with-QR-human /
# remove-all-checks): an AGENT caller may provision/apply it through this tool. It runs the SAME checks as the owner-hand
# path (`waha_owner_hand.personal_line_checks`: strict shadow shape, the VPS yml + rendered compose hashing identical to
# this checkout, `noctus.line.personal=true` on core AND edge, the core off noctus-net), keeps the edge-before-QR order,
# and writes an audit row (who, line, host, policy hash) BEFORE anything touches the VPS (fail closed) plus an outcome
# row. The human consent step is the owner's phone scanning the QR: nothing here pairs a number or connects Google.
# `remove` stays refused for agents (PERSONAL_REFUSAL). The CLI-only owner-hand path stays as an alternative; a grant
# passed that does not cover the line still refuses (never falls through to the agent path).
# The host precondition stays OPEN: NOC-REMEDIATE[personal-core-host-exec-authz] (see vps_exec).


class _AgentRun:
    """One agent provision/apply of a personal line: the shared checks + its audit rows (one run per top-level call; a
    provision nested inside apply re-runs the checks but writes no second `agent_started` row)."""

    def __init__(self, spec: dict, name: str, host: str, sh, action: str, root: "Path | str"):
        self.spec, self.name, self.host, self.sh, self.action, self.root = spec, name, host, sh, action, root
        self.run_id: "str | None" = None
        self.policy_hash: "str | None" = None

    def store_problem(self) -> "str | None":
        """Runs BEFORE any remote read of a line this checkout declares personal: the audit store + runner seam."""
        from . import waha_owner_hand as oh

        return oh.agent_store_problem(self.host, self.root, self.sh)

    def check(self, write_audit: bool) -> "str | None":
        """None = cleared to act (and, with write_audit, its `agent_started` row is durable); else the refusal."""
        from . import waha_owner_hand as oh

        why = self.store_problem()
        if why:
            return why
        chk = oh.personal_line_checks(self.spec, _inst(self.spec, self.name), self.name, self.host, self.sh)
        if chk["problem"]:
            return chk["problem"]
        self.policy_hash = chk["policy_hash"]
        if write_audit and self.run_id is None:
            run_id = oh._new_id()
            _res, why = oh.agent_audit(self.root, self.action, self.name, self.host, self.policy_hash,
                                       oh.AGENT_STARTED, run_id)
            if why:
                return why + ": refused before touching the VPS (fail closed)"
            self.run_id = run_id
        return None

    def finish(self, res: dict) -> dict:
        """After the action: verify the live labels (apply), write the outcome row; a no-op when nothing was started."""
        if self.run_id is None:
            return res
        from . import waha_owner_hand as oh

        if self.action == "apply" and res.get("ok"):
            lab = oh._live_label_problems(_inst(self.spec, self.name), self.host, self.sh)
            if lab:
                res = {**res, "ok": False, "status": "label_drift", "label_problems": lab}
        outcome = str(res.get("status") or ("ok" if res.get("ok") else "error"))
        audit, why = oh.agent_audit(self.root, self.action, self.name, self.host, self.policy_hash, outcome, self.run_id)
        res = {**res, "agent_personal": True, "policy_hash": self.policy_hash, "audit_run_id": self.run_id}
        if why:
            res["audit_warning"] = f"the outcome row was not durable: {why}"
        return res


def _owner_allows(grant, inst: dict, host: str, vps_inst: "dict | None" = None) -> bool:
    """True only for the owner-hand grant covering this line, host and policy (this checkout's AND the VPS's)."""
    if grant is None:
        return False
    from .waha_owner_hand import grant_covers
    return grant_covers(grant, inst, host, vps_inst)


def _vps_instance(name: str, host: str, sh) -> "tuple[dict | None, str]":
    """The instance as the VPS's OWN checkout of waha-instances.yml declares it: (inst, "") or (None, why)."""
    rc, text, err = sh(host, f"cat {VPS_FLEET}/waha-instances.yml")
    if rc != 0:
        return None, f"cannot read the VPS's own waha-instances.yml ({err.strip()[-120:]}): the ceiling is unknown"
    try:
        return _inst(parse_instances_text(text), name), ""
    except ValueError as exc:
        return None, f"the VPS checkout does not declare line {name!r} ({exc}): deploy_pull first"


def _provision(spec: dict, name: str, host: str, confirm: bool, *, _test_sh=None, _owner_grant=None,
               root: "Path | str | None" = None, _agent: "_AgentRun | None" = None) -> dict:
    """Create/align the session config from the policy against the CORE, then READ IT BACK (explicit, idempotent).

    The caller's checkout is NOT trusted: provisioning may only TIGHTEN, compared with BOTH the running config and the
    VPS's own checkout of waha-instances.yml (a branch with `mark_online: true` cannot write itself onto the live core).
    A `personal: true` line: with `_owner_grant` (CLI-only owner-hand path) the grant must cover this line, host and
    policy hash on BOTH checkouts, else REFUSED; without one the caller is an agent and goes through `_AgentRun` (the
    shared personal-line checks + an audit row before any write).

    `_test_sh` is a TEST-ONLY injection point for the remote runner: it is absent from the public function and the MCP
    schema, and must never be passed by production code. `_owner_grant` and `_agent` are absent from both as well."""
    sh = _test_sh or _sh
    top = _agent is None and _owner_grant is None
    agent = _AgentRun(spec, name, host, sh, "provision", root or REPO_ROOT) if top else _agent
    with _GrantScope(_owner_grant):
        res = _provision_in_scope(spec, name, host, confirm, _test_sh=_test_sh, _owner_grant=_owner_grant,
                                  _agent=agent)
    return agent.finish(res) if top else res


def _provision_in_scope(spec: dict, name: str, host: str, confirm: bool, *, _test_sh=None, _owner_grant=None,
                        _agent: "_AgentRun | None" = None) -> dict:
    """The body of `_provision`, inside the owner-hand scope of its grant."""
    sh = _test_sh or _sh
    inst = _inst(spec, name)
    want = policy_noweb(inst)
    core = f"noctus-{core_service(inst)}"
    refuse = lambda why, **kw: {"ok": False, "action": "provision", "status": "refused", "name": name,  # noqa: E731
                                "error": why, **kw}

    if inst.get("personal") and not _owner_allows(_owner_grant, inst, host):
        why = PERSONAL_REFUSAL if _agent is None else _agent.store_problem()
        if why:  # before ANY remote read
            return refuse(why, needs_owner_by_hand=True) if _agent is None else refuse(why)
    vps_inst, why = _vps_instance(name, host, sh)
    if vps_inst is None:
        return refuse(why)
    vps_want = policy_noweb(vps_inst)
    bad = _loosening(want, vps_want, "the VPS checkout")
    if bad:
        return refuse("REFUSED, loosening vs the VPS's own waha-instances.yml: " + "; ".join(bad))

    if (inst.get("personal") or vps_inst.get("personal")) and not _owner_allows(_owner_grant, inst, host, vps_inst):
        if _agent is None:
            return refuse(PERSONAL_REFUSAL, needs_owner_by_hand=True)
        why = _agent.check(write_audit=confirm)
        if why:
            return refuse(why)

    probe = f"docker exec -e POLICY_SESSION={shlex.quote(inst['session'])} {core} node -e '{_READ_JS}'"
    rc, out, err = sh(host, probe, timeout=60)
    try:
        running = json.loads(out.strip().splitlines()[-1]) if rc == 0 else None
    except (ValueError, IndexError):
        running = None
    if running is None:
        return refuse(f"cannot read the running config from {core}: {(out.strip() or err.strip())[-160:]}")
    bad = _loosening(want, running.get("noweb") if running.get("exists") else None, "the running session")
    if bad:
        return refuse("REFUSED, loosening vs the running session: " + "; ".join(bad))

    relay = relay_base(inst) if inst.get("edge_deny_writes") else ""
    plan = {"ok": True, "action": "provision", "name": name, "status": "planned", "core": core, "expect_noweb": want,
            "running": running,
            "steps": ["create (start:false) or PUT merged config on the core (foreign webhooks dropped)",
                      "read the config back from the core: noweb == policy and every webhook under the relay"]}
    if not confirm:
        plan["note"] = "DRY RUN -- pass confirm=True; run BEFORE the edge fronts the core and BEFORE any QR scan"
        return plan
    cmd = (f"docker exec -e POLICY_NOWEB={shlex.quote(json.dumps(want, separators=(',', ':')))} "
           f"-e POLICY_SESSION={shlex.quote(inst['session'])} -e POLICY_RELAY={shlex.quote(relay)} "
           f"{core} node -e '{_PROVISION_JS}'")
    rc, out, err = sh(host, cmd, timeout=120)
    if rc != 0:
        return {"ok": False, "action": "provision", "status": "error", "name": name,
                "error": (out.strip() or err.strip())[-400:]}
    try:
        got = json.loads(out.strip().splitlines()[-1])
    except (ValueError, IndexError):
        return {"ok": False, "action": "provision", "status": "error", "name": name,
                "error": f"unparseable read-back: {out.strip()[-200:]}"}
    hooks = got.get("webhooks") or []
    foreign = [u for u in hooks if relay and not str(u).startswith(relay + "/")]
    ok = _noweb_matches(got.get("noweb"), want) and not foreign
    return {"ok": ok, "action": "provision", "status": "verified" if ok else "drift", "name": name,
            "expect_noweb": want, "read_back": got.get("noweb"), "webhooks": hooks, "foreign_webhooks": foreign}


def _personal_refusal(inst: dict, name: str, host: str, sh, action: str, owner_grant=None,
                      agent: "_AgentRun | None" = None) -> "dict | None":
    """Refusal payload when the line is personal in ANY of the three sources (this checkout's yml, the VPS's own yml, the
    LIVE container label `noctus.line.personal=true`), or when a source cannot be read (fail closed); None = cleared.
    Nothing is started, stopped or copied before this runs (not the core, not a volume tar), `force` does not bypass it.
    A covering owner-hand grant clears it; else an `agent` run clears it only when the shared personal-line checks pass
    and its audit row is durable; with neither (e.g. `remove`) a personal line is refused."""
    out = lambda why, **kw: {"ok": False, "action": action, "status": "refused", "name": name,  # noqa: E731
                             "error": why, **kw}
    if inst.get("personal") and not _owner_allows(owner_grant, inst, host):  # before ANY remote read
        if agent is None:
            return out(PERSONAL_REFUSAL, needs_owner_by_hand=True)  # nothing at all is touched: not even the core
        why = agent.store_problem()
        if why:
            return out(why)
    # the VPS's own checkout is read first: the strictest of local and VPS wins, unreadable refuses
    vps_inst, why = _vps_instance(name, host, sh)
    if vps_inst is None:
        return out(why)
    personal_ok = _owner_allows(owner_grant, inst, host, vps_inst)
    # the LIVE label is the third source (a core created before the render change / by hand may be personal while both
    # ymls say otherwise): any labelled container of this line counts; an unreadable lookup fails closed
    rc, lab, lerr = sh(host, "docker ps -a --filter label=noctus.line.personal=true --format '{{.Names}}'")
    if rc != 0:
        return out(f"cannot read the live `noctus.line.personal` labels ({lerr.strip()[-120:]}): refused (fail closed)")
    mine = {f"noctus-{core_service(inst)}", core_service(inst), f"noctus-waha-{name}", f"waha-{name}"}
    labelled = bool(mine & {n.strip().lstrip("/") for n in lab.splitlines() if n.strip()})
    if not (inst.get("personal") or vps_inst.get("personal") or labelled) or personal_ok:
        return None
    if agent is None:
        return out(PERSONAL_REFUSAL, needs_owner_by_hand=True)
    why = agent.check(write_audit=True)
    return out(why) if why else None


def _apply(spec: dict, name: str, host: str, confirm: bool, *, _test_sh=None, _owner_grant=None,
           root: "Path | str | None" = None) -> dict:
    """`_test_sh` / `_owner_grant` are TEST-ONLY / owner-hand-only (see `_provision`). Without a grant the caller is an
    agent: a personal line goes through `_AgentRun` (checks + audit), the outcome row and the live-label check after."""
    agent = None if _owner_grant is not None else _AgentRun(spec, name, host, _test_sh or _sh, "apply",
                                                               root or REPO_ROOT)
    with _GrantScope(_owner_grant):
        res = _apply_in_scope(spec, name, host, confirm, _test_sh=_test_sh, _owner_grant=_owner_grant, _agent=agent)
    return agent.finish(res) if agent is not None else res


def _apply_in_scope(spec: dict, name: str, host: str, confirm: bool, *, _test_sh=None, _owner_grant=None,
                    _agent: "_AgentRun | None" = None) -> dict:
    sh = _test_sh or _sh
    p = _plan(spec, name)
    if not confirm:
        p.update(action="apply", note="DRY RUN -- pass confirm=True to `compose up -d --no-deps` this ONE instance "
                                      "(an edge line: core -> provision -> edge, in that order)")
        return p
    inst = _inst(spec, name)
    refused = _personal_refusal(inst, name, host, sh, "apply", _owner_grant, _agent)
    if refused is not None:
        return refused
    rc, _o, err = sh(host, f"cd {VPS_FLEET} && for k in {' '.join(inst_keys(inst).values())}; do "
                            "grep -q \"^$k=.\" .env.fleet || { echo MISSING:$k; exit 3; }; done")
    if rc != 0:
        return {"ok": False, "action": "apply", "status": "blocked",
                "error": f"required .env.fleet keys missing/empty on the VPS (generate them first): {_o.strip() or err.strip()}"}
    up = f"cd {VPS_FLEET} && docker compose -f compose.waha.yml up -d --no-deps "
    if inst.get("edge_deny_writes"):
        # core first (private network), session config from the policy, and ONLY THEN the edge that fronts it
        rc, out, err = sh(host, up + core_service(inst), timeout=300)
        if rc != 0:
            return {"ok": False, "action": "apply", "status": "error", "name": name, "error": err.strip()[-600:]}
        prov = _provision(spec, name, host, True, _test_sh=_test_sh, _owner_grant=_owner_grant, _agent=_agent)
        if not prov["ok"]:
            return {"ok": False, "action": "apply", "status": "provision_failed", "name": name, "provision": prov}
        rc, out, err = sh(host, up + f"waha-{name}", timeout=300)
    else:
        rc, out, err = sh(host, up + " ".join(services_of(inst)), timeout=300)
        if rc == 0 and inst.get("personal"):  # personal live (no edge): still pin markOnline/fullSync off on the core
            prov = _provision(spec, name, host, True, _test_sh=_test_sh, _owner_grant=_owner_grant, _agent=_agent)
            if not prov["ok"]:
                return {"ok": False, "action": "apply", "status": "provision_failed", "name": name, "provision": prov}
    return {"ok": rc == 0, "action": "apply", "status": "applied" if rc == 0 else "error", "name": name,
            "stdout": out.strip()[-600:], "error": None if rc == 0 else err.strip()[-600:]}


def _remove(spec: dict, name: str, host: str, confirm: bool, force: bool, *, _test_sh=None) -> dict:
    sh = _test_sh or _sh
    inst = _inst(spec, name)
    # BEFORE the session lookup, the core stop and the volume tar; `force=True` does not bypass it (same as apply)
    refused = _personal_refusal(inst, name, host, sh, "remove")
    if refused is not None:
        return refused
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
        rc, _o, err = sh(host, step, timeout=300)
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
                (root / READ_ONLY_REL).write_text(render_read_only_lines(spec), encoding="utf-8")
            return {"ok": True, "action": "render", "written": write, "compose": text,
                    "read_only_lines": render_read_only_lines(spec)}
        if action == "list":
            return _list(spec, ssh_host)
        if action in ("plan", "add"):
            return _plan(spec, name or "")
        if action == "provision":
            return _provision(spec, name or "", ssh_host, confirm, root=root)
        if action == "apply":
            return _apply(spec, name or "", ssh_host, confirm, root=root)
        if action == "remove":
            return _remove(spec, name or "", ssh_host, confirm, force)
    except ValueError as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    return {"ok": False, "action": action, "error": f"unknown action {action!r} -- render|list|plan|provision|apply|remove"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.waha_instance",
        description=(
            "One WAHA Core container per WhatsApp number, declared as data (deploy/fleet/waha-instances.yml -> rendered "
            "compose.waha.yml). action=render (offline; write=True refreshes the file + the seed read-only host set) | list (declared vs running vs health "
            "vs RSS vs session status) | plan/add (the service + the .env.fleet key NAMES to generate on the VPS -- values never "
            "cross the wire) | apply (confirm=True: compose up -d --no-deps for ONE instance; refuses when keys are missing) | "
            "provision (creates/aligns the session config FROM the policy on the core; TIGHTEN-ONLY vs the VPS's own yml and the running "
            "config; a PERSONAL line is allowed for agents only in the two strict shapes (read-only shadow | personal live: send on, no edge, mark_online/full_sync off), with the VPS yml + compose "
            "hashing identical, the personal label on core+edge, and an audit row written first; the QR scan stays the "
            "owner's) | "
            "remove (confirm=True; refuses a WORKING session unless force; snapshots the volume first, never deletes it; "
            "a PERSONAL line is never removed by an agent). "
            "DRY-RUN default. KB § CONTEXT/INTEGRATIONS/whatsapp.md § One WAHA per number."
        ),
    )
    def _waha_instance(action: str = "list", name: str = "", ssh_host: str = "noctus-vps", confirm: bool = False,
                       force: bool = False, write: bool = False, worktree_path: str = "") -> dict:
        return waha_instance(action=action, name=name or None, ssh_host=ssh_host, confirm=confirm, force=force,
                             write=write, worktree_path=worktree_path or None)


__all__ = ["waha_instance", "register", "render_compose", "parse_instances", "env_keys", "inst_keys", "load_spec",
           "line_policy_json", "core_service", "services_of", "render_read_only_lines", "READ_ONLY_REL",
           "relay_base", "policy_noweb"]
