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
    ops.pass trip.pass probe.pass   0600 secrets for `noctus.dev.supabase_breaker` / `breaker-trip.sh` / `host-probe.sh`
    compose.redis-auth.prod.yml   COMMITTED override (no secrets): one `env_file` + `networks`
                         entry per roster service; applied per service during the rollout.

Users:
  default      OFF. The whole point.
  healthcheck  nopass, `+ping` only (container healthcheck; reveals liveness, nothing else).
  <service>    key patterns = the app families actually used by the seed seam (APP_KEY_FAMILIES,
               each cites its code), `~<slug>:*` for its own future namespace, `%RW~noctus:breaker:<slug>:*`,
               `%R~noctus:breaker:fleet` READ-ONLY. Commands `+@all -@dangerous -@admin`.
  trip         ONLY `SETNX`/`GET`/`EXISTS` on `noctus:breaker:fleet` (the off-host watchdog's forced
               command). Cannot DEL: a compromised watchdog key can trip, never re-arm.
  probe        `%R~noctus:breaker:fleet`, `EXISTS`/`PING` only (the read-only host probe; never `trip`).
  ops          breaker keys + audit list only (`noctus:breaker:*`): GET/MGET/SET/DEL/RPUSH/LRANGE/
               EXISTS/TTL/SMEMBERS/SREM (per-product index sets, NO scan) + `acl|log`. Re-arm (DEL) lives here and nowhere else.

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
OVERRIDES_ENV = "REDIS_ACL_GENERATION_OVERRIDES"

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

# `ltrim` enforces the 1000-row audit cap after RPUSH; `sadd` lists a key ops trips by hand in the product's
# index. No SCAN/KEYS: key names are bearer secrets elsewhere and SCAN ignores key patterns. `status` enumerates via
# each product's own index SET `noctus:breaker:<slug>:index` (SMEMBERS) + the fleet key. `script|kill` /
# `function|kill` let ops stop a runaway Lua script (the EVAL freeze) without CONFIG/SHUTDOWN.
OPS_COMMANDS = (
    "-@all +get +mget +set +del +rpush +ltrim +lrange +llen +exists +ttl +pttl +smembers +sadd +srem +sismember +scard +ping +hello +auth "
    "+client|setname +acl|log +acl|whoami +script|kill +function|kill"
)
#: Slugs that would turn `~<slug>:*` / the user name into something other than "this product".
RESERVED_SLUGS = frozenset({"noctus", "default", "ops", "trip", "probe", "healthcheck", "redis", "limits", "limiter",
                            "nai", "rt", "llm", "wa", "queue", "conversation", "ratelimit", "download", "quota"})
# SETNX, not SET: it cannot take EX/PX/XX, so a stolen trip key can never expire or overwrite an existing trip.
TRIP_COMMANDS = "-@all +setnx +get +exists +ping +hello +auth +client|setname"
HEALTHCHECK_COMMANDS = "-@all +ping"
# Read-only host probe (off-host watchdog's host-probe.sh): "is the fleet breaker tripped?" and nothing else.
# Deliberately NOT `trip`: that identity can SETNX, a probe must never be able to write.
PROBE_COMMANDS = "-@all +exists +ping +hello +auth"


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
            if name in RESERVED_SLUGS or name in {p.split(":")[0].rstrip("*") for p, _ in APP_KEY_FAMILIES}:
                raise ValueError(f"service name {name!r} is reserved (would alias an ACL user or a shared key family)")
            roster.append(name)
    if not roster:
        raise ValueError("derived roster is empty (no live service loads the root .env)")
    return sorted(roster)


# ── secrets ───────────────────────────────────────────────────────────────

_MASTER_RE = re.compile(r"^[0-9a-f]{64}$")
_GEN_RE = re.compile(r"^[0-9]{1,6}$")


def _gen(generation, user: str) -> str:
    """`generation` is one string (all users) or {"*": default, "<user>": override}."""
    if isinstance(generation, str):
        return generation
    return generation.get(user, generation.get("*", "1"))


def parse_generation_overrides(text: str) -> dict[str, str]:
    """`core=2, ops=3` -> {"core": "2", "ops": "3"}; strict (rotate ONE user without touching the rest)."""
    out: dict[str, str] = {}
    for part in (text or "").split(","):
        part = part.strip()
        if not part:
            continue
        user, sep, val = part.partition("=")
        if not sep or not _SLUG_RE.match(user.strip()) and user.strip() not in {"ops", "trip"} or not _GEN_RE.match(val.strip()):
            raise ValueError(f"bad {OVERRIDES_ENV} entry {part!r} (expected <user>=<digits>)")
        out[user.strip()] = val.strip()
    return out


def derive_password(master: str, user: str, generation="1") -> str:
    if not _MASTER_RE.match(master or ""):
        raise ValueError(f"{MASTER_ENV} (master) must be exactly 64 lowercase hex chars (generate: openssl rand -hex 32)")
    msg = f"noctus-redis-acl:v{_gen(generation, user)}:{user}".encode()
    return hmac.new(master.encode(), msg, hashlib.sha256).hexdigest()


def _hash(pw: str) -> str:
    return hashlib.sha256(pw.encode()).hexdigest()


# ── renderers (pure) ──────────────────────────────────────────────────────

def _key_patterns(patterns: list[str]) -> str:
    return " ".join(patterns)


def render_aclfile(roster: list[str], master: str, generation="1") -> str:
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
        f"user probe on #{_hash(derive_password(master, 'probe', generation))} resetkeys resetchannels "
        f"%R~{FLEET_KEY} {PROBE_COMMANDS}"
    )
    lines.append(
        f"user ops on #{_hash(derive_password(master, 'ops', generation))} resetkeys resetchannels "
        f"~{BREAKER_PREFIX}* {OPS_COMMANDS}"
    )
    return "\n".join(lines) + "\n"


def render_service_env(slug: str, master: str, generation="1") -> str:
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

def _dotenv_value(raw: str) -> str:
    """dotenv rules: a quoted value is taken verbatim; an unquoted one ends at ` #` (inline comment); a value
    that STARTS with `#` is a comment, never data (the shipped example's `KEY=   # note` must not become a secret)."""
    raw = raw.strip()
    if raw[:1] in ("'", '"'):
        q = raw[0]
        end = raw.find(q, 1)
        return raw[1:end] if end > 0 else raw[1:]
    if raw.startswith("#"):
        raise ValueError("value starts with '#': an inline comment is not a value")
    return re.split(r"\s+#", raw, maxsplit=1)[0].strip()


def _read_master(root: Path, env: dict[str, str] | None, env_file: str | None):
    """-> (master, generation). Raises ValueError on a non-conforming value (never silently adopts one)."""
    env = os.environ if env is None else env
    vals: dict[str, str] = {k: env[k] for k in (MASTER_ENV, GENERATION_ENV, OVERRIDES_ENV) if env.get(k)}
    p = Path(env_file) if env_file else root / "deploy/fleet/.env.fleet"
    if MASTER_ENV not in vals and p.is_file():
        for ln in p.read_text(encoding="utf-8").splitlines():
            m = re.match(rf"^\s*(?:export\s+)?({MASTER_ENV}|{GENERATION_ENV}|{OVERRIDES_ENV})\s*=(.*)$", ln)
            if m:
                try:
                    v = _dotenv_value(m.group(2))
                except ValueError as e:
                    label = "master" if m.group(1) == MASTER_ENV else m.group(1)
                    raise ValueError(f"{m.group(1)} ({label}): {e}") from None
                if v:
                    vals[m.group(1)] = v
    master = vals.get(MASTER_ENV, "")
    if not _MASTER_RE.match(master):
        raise ValueError(f"{MASTER_ENV} (master) missing or not 64 lowercase hex chars (generate: openssl rand -hex 32)")
    gen = vals.get(GENERATION_ENV, "1")
    if not _GEN_RE.match(gen):
        raise ValueError(f"{GENERATION_ENV} must be 1-6 digits, got a non-conforming value")
    overrides = parse_generation_overrides(vals.get(OVERRIDES_ENV, ""))
    return master, ({"*": gen, **overrides} if overrides else gen)


def _load(root: Path) -> list[str]:
    return derive_roster((root / COMPOSE_REL).read_text(encoding="utf-8"),
                         (root / SCOPE_REL).read_text(encoding="utf-8"))


def _ensure_private_dir(d: Path) -> None:
    if d.is_symlink():
        raise ValueError(f"{d} is a symlink - refusing to write secrets through it")
    d.mkdir(mode=0o700, parents=True, exist_ok=True)
    os.chmod(d, 0o700)


def _write_secret(path: Path, text: str, mode: int) -> None:
    """Temp file (O_EXCL|O_NOFOLLOW, born `mode`) in a 0700 dir, then atomic rename: never follows a
    planted symlink, never leaves a half-written or wider-than-`mode` secret."""
    _ensure_private_dir(path.parent)
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


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
    result: dict = {"ok": True, "action": "render", "roster": roster, "users": ["default(off)", "healthcheck", *roster, "trip", "probe", "ops"],
                    "key_families": [p for p, _ in APP_KEY_FAMILIES], "written": []}
    if write:
        (root / OVERRIDE_REL).write_text(override, encoding="utf-8")
        result["written"].append(OVERRIDE_REL)
        master, gen = _read_master(root, env, env_file)
        try:
            out = root / OUT_DIR_REL
            _ensure_private_dir(out)
            _write_secret(out / "users.acl", render_aclfile(roster, master, gen), 0o644)
            for slug in roster:
                _write_secret(out / "env" / f"{slug}.env", render_service_env(slug, master, gen), 0o600)
            _write_secret(out / "ops.pass", derive_password(master, "ops", gen) + "\n", 0o600)
            _write_secret(out / "trip.pass", derive_password(master, "trip", gen) + "\n", 0o600)
            _write_secret(out / "probe.pass", derive_password(master, "probe", gen) + "\n", 0o600)
        except ValueError as e:
            return {"ok": False, "action": "render", "status": "error", "error": str(e), "written": result["written"]}
        result["written"] += [f"{OUT_DIR_REL}/users.acl", f"{OUT_DIR_REL}/env/<service>.env x{len(roster)}",
                              f"{OUT_DIR_REL}/ops.pass", f"{OUT_DIR_REL}/trip.pass", f"{OUT_DIR_REL}/probe.pass"]
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
