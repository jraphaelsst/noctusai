"""noctus.dev.redis_acl -- derive prod Redis's ACL file + per-service creds from the live roster.

**Why (2026-11-10, security review F3 of the Supabase request breaker).** Prod Redis
(`noctus-redis`) ran with no auth on `noctus-net`, a network every container shares -- n8n
(public UI, Redis node, Code node) and WAHA included. It is about to become the authority
for the fleet-wide breaker (`noctus:breaker:fleet`): anyone on the network could SET it (fleet
DoS) or DEL a trip (silently disarm a runaway). This tool makes the lockdown DERIVED, never a
hand-kept list (keeper `check_hardcoded_product_slug_set`):

  roster  = services of `deploy/fleet/docker-compose.prod.yml` that load the root `.env`
            (`env_file: ../../.env`)  INTERSECT  `deploy/fleet/build-scope.txt` (live products).
            An asleep product gets NO Redis user.
  secrets = ONE master (`REDIS_ACL_MASTER_SECRET`, a `.env.fleet` name; value never committed).
            password(user) = HMAC-SHA256(master, "noctus-redis-acl:v<gen>:<user>") hex.
  outputs (all under `deploy/fleet/redis-auth/`, gitignored except the override):
    users.acl            what Redis loads (`--aclfile`): HASHES only (`#<sha256>`), never plaintext
    env/<service>.env    per-service REDIS_URL + REDIS_USERNAME + REDIS_PASSWORD (+ REQUIRE_AUTH)
    ops.pass trip.pass   0600 secrets for `noctus.dev.supabase_breaker` / `breaker-trip.sh`
    compose.redis-auth.prod.yml   COMMITTED override (no secrets): one `env_file` + `networks`
                         entry per roster service; applied per service during the rollout.

Users:
  default      OFF. The whole point.
  healthcheck  nopass, `+ping` only (container healthcheck; reveals liveness, nothing else).
  <service>    key patterns = the app families actually used by the seed seam (APP_KEY_FAMILIES,
               each cites its code), `~<slug>:*` for its own future namespace, `%RW~noctus:breaker:<slug>:*`,
               `%R~noctus:breaker:fleet` READ-ONLY. Commands `+@all -@dangerous -@admin`.
  trip         ONLY `SET`/`GET`/`EXISTS` on `noctus:breaker:fleet` (the off-host watchdog's forced
               command). Cannot DEL: a compromised watchdog key can trip, never re-arm.
  ops          breaker keys + audit list only (`noctus:breaker:*`): GET/MGET/SET/DEL/RPUSH/LRANGE/
               SCAN/EXISTS/TTL + `acl|log`. Re-arm (DEL) lives here and nowhere else.

Never returns a secret in the payload. Offline: `render` writes files, `check` diffs the committed
override against the derived roster. The live rollout is by the guardian session, per
`KB § PATTERNS/devops/redis-acl-lockdown.md`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

COMPOSE_REL = "deploy/fleet/docker-compose.prod.yml"
SCOPE_REL = "deploy/fleet/build-scope.txt"
OUT_DIR_REL = "deploy/fleet/redis-auth"
OVERRIDE_REL = "deploy/fleet/compose.redis-auth.prod.yml"
MASTER_ENV = "REDIS_ACL_MASTER_SECRET"
GENERATION_ENV = "REDIS_ACL_GENERATION"

#: The ACL'd Redis (infra compose service `redis-acl`) lives ONLY on this internal network.
DATA_NET = "noctus-data"
REDIS_HOST = "noctus-redis-acl"
REDIS_URL = f"redis://{REDIS_HOST}:6379/0"

BREAKER_PREFIX = "noctus:breaker:"
FLEET_KEY = f"{BREAKER_PREFIX}fleet"
AUDIT_KEY = f"{BREAKER_PREFIX}audit"

#: Key families every product process may use, with the code that creates them. Shared names (not
#: per-product) -- see KB for the isolation limit. Adding a Redis-using seed feature means adding its
#: prefix HERE (the aclfile test fails closed on drift: a denied key shows as an ACL LOG entry).
APP_KEY_FAMILIES: tuple[tuple[str, str], ...] = (
    ("nai_session:*", "auth session store (noctusai_lib/api/auth/session/redis_store.py)"),
    ("noctus:quota:*", "quota (noctusai_lib/integrations/quota/redis_backend.py)"),
    ("rt:*", "realtime SSE bus streams (noctusai_lib/realtime/bus.py)"),
    ("llm:*", "LLM response cache (noctusai_lib/integrations/llm/cache.py)"),
    ("LIMITS*", "slowapi/limits counters, Lua INCR+EXPIRE (noctusai_lib/api/rate_limit.py)"),
    ("queue:conversation_*", "chatbot buffer stream + due ZSETs (domain/chatbot/buffer.py)"),
    ("conversation:memory:*", "chatbot memory lists (domain/chatbot/buffer.py + openai_orchestrator.py)"),
    ("wa:dedup:*", "WhatsApp webhook dedup (integrations/whatsapp/dedup.py)"),
    ("wa:lid_phone:*", "WhatsApp LID->phone cache (integrations/whatsapp/lid_auth.py)"),
    ("ratelimit:conversation:*", "social-wiring conversation limiter (modules/scheduling/conversation_rate_limit.py)"),
    ("download:cache:*", "social-wiring youtube download cache (modules/youtube/services/download_cache.py)"),
)

#: Per-service command exceptions (data, not code). NOC-REMEDIATE[redis-keys-scan]: social-wiring's
#: download-cache orphan sweep uses KEYS (blocking) -- switch it to scan_iter, then drop this. -- 2026-11-10
EXTRA_COMMANDS: dict[str, tuple[str, ...]] = {"social-wiring": ("+keys",)}

#: Commands a product user gets: everything except the dangerous/admin categories (FLUSHALL, CONFIG,
#: DEBUG, KEYS, SHUTDOWN, ACL, CLIENT KILL/LIST ...) and the scripting category (SCRIPT FLUSH/KILL, FUNCTION *
#: are neither admin nor dangerous -- found by a live probe). Only the Lua surface `limits` uses stays:
#: EVAL/EVALSHA/SCRIPT LOAD/EXISTS, which run under the CALLER's key permissions.
PRODUCT_COMMANDS = "+@all -@dangerous -@admin -@scripting +eval +evalsha +script|load +script|exists"

OPS_COMMANDS = (
    "-@all +get +mget +set +del +rpush +lrange +llen +exists +ttl +pttl +scan +ping +hello +auth "
    "+client|setname +acl|log +acl|whoami"
)
TRIP_COMMANDS = "-@all +set +get +exists +ping +hello +auth +client|setname"
HEALTHCHECK_COMMANDS = "-@all +ping"


def _resolve_root(repo_root: str | None, worktree_path: str | None) -> Path:
    if repo_root is not None:
        return Path(repo_root)
    if worktree_path:
        return Path(resolve_caller_root(worktree_path))
    return Path(REPO_ROOT)


# ── roster ────────────────────────────────────────────────────────────────

_SLUG_RE = re.compile(r"^[a-z][a-z0-9\-]{0,40}$")


def derive_roster(compose_text: str, scope_text: str) -> list[str]:
    """Live services that load the root `.env` (the Redis-capable ones), sorted.

    Raises ValueError on an empty roster or an unsafe slug (it goes into an ACL line).
    """
    import yaml

    data = yaml.safe_load(compose_text) or {}
    live = {ln.strip() for ln in scope_text.splitlines() if ln.strip() and not ln.lstrip().startswith("#")}
    roster: list[str] = []
    for name, svc in (data.get("services") or {}).items():
        env_files = (svc or {}).get("env_file") or []
        if isinstance(env_files, str):
            env_files = [env_files]
        if any(str(e).endswith(".env") for e in env_files) and name in live:
            if not _SLUG_RE.match(name):
                raise ValueError(f"service name {name!r} is not an ACL-safe slug")
            roster.append(name)
    if not roster:
        raise ValueError("derived roster is empty (no live service loads the root .env)")
    return sorted(roster)


# ── secrets ───────────────────────────────────────────────────────────────

def derive_password(master: str, user: str, generation: str = "1") -> str:
    if not master or len(master) < 32:
        raise ValueError(f"{MASTER_ENV} must be set and >= 32 chars (generate: openssl rand -hex 32)")
    msg = f"noctus-redis-acl:v{generation}:{user}".encode()
    return hmac.new(master.encode(), msg, hashlib.sha256).hexdigest()


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── renderers (pure) ──────────────────────────────────────────────────────

def _key_patterns(patterns: list[str]) -> str:
    return " ".join(patterns)


def render_aclfile(roster: list[str], master: str, generation: str = "1") -> str:
    """The aclfile Redis loads. Passwords appear ONLY as sha256 hashes. NO comments: Redis rejects them in an
    aclfile (found by running the rendered file through a real redis-server). `client|setinfo` is omitted from the
    explicit lists (absent before Redis 7.2; redis-py swallows its refusal); products get it via +@all on 7.2+."""
    lines = [
        "user default off",
        f"user healthcheck on nopass resetkeys resetchannels {HEALTHCHECK_COMMANDS}",
    ]
    fams = [p for p, _ in APP_KEY_FAMILIES]
    for slug in roster:
        pats = [f"~{p}" for p in fams] + [f"~{slug}:*", f"%RW~{BREAKER_PREFIX}{slug}:*", f"%R~{FLEET_KEY}"]
        cmds = " ".join((PRODUCT_COMMANDS, *EXTRA_COMMANDS.get(slug, ())))
        lines.append(
            f"user {slug} on #{_hash(derive_password(master, slug, generation))} resetkeys resetchannels "
            f"{_key_patterns(pats)} {cmds}"
        )
    lines.append(
        f"user trip on #{_hash(derive_password(master, 'trip', generation))} resetkeys resetchannels "
        f"%RW~{FLEET_KEY} {TRIP_COMMANDS}"
    )
    lines.append(
        f"user ops on #{_hash(derive_password(master, 'ops', generation))} resetkeys resetchannels "
        f"~{BREAKER_PREFIX}* {OPS_COMMANDS}"
    )
    return "\n".join(lines) + "\n"


def render_service_env(slug: str, master: str, generation: str = "1") -> str:
    return (
        f"# GENERATED by noctus.dev.redis_acl for {slug} -- gitignored, 0600.\n"
        f"REDIS_URL={REDIS_URL}\n"
        f"REDIS_USERNAME={slug}\n"
        f"REDIS_PASSWORD={derive_password(master, slug, generation)}\n"
        "REDIS_REQUIRE_AUTH=true\n"
    )


def render_override(roster: list[str]) -> str:
    """The COMMITTED compose override: no secrets, one block per roster service."""
    out = [
        "# GENERATED by noctus.dev.redis_acl (python mcp/noctusai/cli.py --redis-acl render) -- do not hand-edit.",
        "# Derived from docker-compose.prod.yml services that load the root .env  INTERSECT  build-scope.txt.",
        "# Applied ONLY during/after the Redis lockdown rollout, as a second -f:",
        "#   docker compose -f docker-compose.prod.yml -f compose.redis-auth.prod.yml up -d <service>",
        "# Removing the second -f is the one-line rollback for a service (env_file + network drop away).",
        "# The env files it names are written on the VPS by the same tool (gitignored, 0600).",
        "# KB § PATTERNS/devops/redis-acl-lockdown.md",
        "",
        "services:",
    ]
    for slug in roster:
        out += [
            f"  {slug}:",
            "    env_file:",
            f"      - ./redis-auth/env/{slug}.env",
            "    networks:",
            f"      - {DATA_NET}",
        ]
    out += ["", "networks:", f"  {DATA_NET}:", f"    name: {DATA_NET}", "    external: true", ""]
    return "\n".join(out)


# ── io ────────────────────────────────────────────────────────────────────

def _read_master(root: Path, env: dict[str, str] | None, env_file: str | None) -> tuple[str, str]:
    env = os.environ if env is None else env
    master = env.get(MASTER_ENV, "")
    gen = env.get(GENERATION_ENV, "1") or "1"
    if not master:
        p = Path(env_file) if env_file else root / "deploy/fleet/.env.fleet"
        if p.is_file():
            for ln in p.read_text(encoding="utf-8").splitlines():
                m = re.match(rf"^\s*({MASTER_ENV}|{GENERATION_ENV})\s*=\s*(.*?)\s*$", ln)
                if m:
                    val = m.group(2).strip("'\"")
                    if m.group(1) == MASTER_ENV:
                        master = val
                    elif val:
                        gen = val
    return master, gen


def _load(root: Path) -> list[str]:
    return derive_roster((root / COMPOSE_REL).read_text(encoding="utf-8"),
                         (root / SCOPE_REL).read_text(encoding="utf-8"))


def _write_secret(path: Path, text: str, mode: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, mode)
    with os.fdopen(fd, "w", encoding="utf-8") as fh:
        fh.write(text)
    os.chmod(path, mode)


def _check(root: Path) -> dict:
    roster = _load(root)
    want = render_override(roster)
    p = root / OVERRIDE_REL
    have = p.read_text(encoding="utf-8") if p.is_file() else None
    ok = have == want
    return {"ok": ok, "action": "check", "status": "in_sync" if ok else "drift", "roster": roster,
            "override_present": have is not None,
            **({} if ok else {"fix": "python mcp/noctusai/cli.py --redis-acl render"})}


def _render(root: Path, write: bool, env: dict[str, str] | None, env_file: str | None) -> dict:
    roster = _load(root)
    override = render_override(roster)
    result: dict = {"ok": True, "action": "render", "roster": roster, "users": ["default(off)", "healthcheck", *roster, "trip", "ops"],
                    "key_families": [p for p, _ in APP_KEY_FAMILIES], "written": []}
    if write:
        (root / OVERRIDE_REL).write_text(override, encoding="utf-8")
        result["written"].append(OVERRIDE_REL)
        master, gen = _read_master(root, env, env_file)
        try:
            out = root / OUT_DIR_REL
            _write_secret(out / "users.acl", render_aclfile(roster, master, gen), 0o644)
            for slug in roster:
                _write_secret(out / "env" / f"{slug}.env", render_service_env(slug, master, gen), 0o600)
            _write_secret(out / "ops.pass", derive_password(master, "ops", gen) + "\n", 0o600)
            _write_secret(out / "trip.pass", derive_password(master, "trip", gen) + "\n", 0o600)
        except ValueError as e:
            return {"ok": False, "action": "render", "status": "error", "error": str(e), "written": result["written"]}
        result["written"] += [f"{OUT_DIR_REL}/users.acl", f"{OUT_DIR_REL}/env/<service>.env x{len(roster)}",
                              f"{OUT_DIR_REL}/ops.pass", f"{OUT_DIR_REL}/trip.pass"]
    result["status"] = "written" if write else "planned"
    return result


def redis_acl(
    action: str = "check",
    *,
    write: bool = False,
    env_file: str | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    """action='check' (override in sync with the derived roster; offline) | 'render' (plan; write=True
    writes the committed override + the gitignored aclfile/env/pass files; needs REDIS_ACL_MASTER_SECRET)."""
    root = _resolve_root(repo_root, worktree_path)
    try:
        if action == "check":
            return _check(root)
        if action == "render":
            return _render(root, write, env, env_file)
    except (ValueError, OSError) as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    return {"ok": False, "action": action, "error": f"unknown action {action!r} -- expected 'check' or 'render'"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.redis_acl",
        description=(
            "Prod Redis ACL lockdown, DERIVED (KB § PATTERNS/devops/redis-acl-lockdown.md). Roster = live "
            "services loading the root .env (compose x build-scope.txt). action='check' (default, offline): the "
            "committed deploy/fleet/compose.redis-auth.prod.yml matches the derived roster. action='render': "
            "plan; write=True writes the override + gitignored users.acl (sha256 hashes only) / per-service env / "
            "ops+trip pass files from REDIS_ACL_MASTER_SECRET (env or .env.fleet). Never returns a secret. "
            "Never touches the VPS."
        ),
    )
    def _redis_acl(action: str = "check", write: bool = False, env_file: str = "", worktree_path: str = "") -> dict:
        return redis_acl(action, write=write, env_file=env_file or None, worktree_path=worktree_path or None)


__all__ = ["redis_acl", "register", "derive_roster", "derive_password", "render_aclfile",
           "render_service_env", "render_override", "APP_KEY_FAMILIES"]
