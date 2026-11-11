"""noctus.dev.redis_acl -- derive prod Redis's ACL files + per-service creds from the live roster.

**Why (2026-11-10, security review F3 of the Supabase request breaker).** Prod Redis (`noctus-redis`) ran with no
auth on `noctus-net`, a network every container shares (n8n, WAHA, cloudflared ...) and is about to hold the
fleet-wide breaker (`noctus:breaker:fleet`). Round-3 decision: TWO instances on the internal `noctus-data` net.

  noctus-redis-acl      APP data (sessions, limiter, quota, chatbot, caches). volatile-lru, EVAL allowed for `limits`.
  noctus-breaker-redis  ONLY the breaker keys. `--maxmemory 64mb noeviction`, no scripting for anyone, AOF on:
                        a runaway filling the app Redis can no longer make `SETNX noctus:breaker:fleet` fail
                        with OOM, and a hung Lua script cannot freeze the breaker.

  roster  = services of `deploy/fleet/docker-compose.prod.yml` that load the root `.env` (`env_file: ../../.env`)
            INTERSECT `deploy/fleet/build-scope.txt` (live). An asleep product gets NO Redis user.
  secrets = ONE master (`REDIS_ACL_MASTER_SECRET`, a `.env.fleet` name; value never committed).
            password(user) = HMAC-SHA256(master, "noctus-redis-acl:v<gen>:<user>") hex.
  outputs, all on the VPS and GITIGNORED (nothing here is committed - round 3):
    redis-auth/users.acl          app Redis aclfile (sha256 hashes only)
    redis-auth/breaker-users.acl  breaker Redis aclfile (sha256 hashes only)
    redis-auth/env/<service>.env  REDIS_URL/USERNAME/PASSWORD + REDIS_REQUIRE_AUTH and
                                  NOCTUS_BREAKER_REDIS_URL/USERNAME/PASSWORD
    redis-auth/{ops,ops-app,trip,probe}.pass   0600 secrets for the breaker tool / forced commands
    compose.redis-auth.prod.yml   the override: written ONLY for the services passed to `render --services`.
                                  Cutting a service over = re-render with it; rolling it back = re-render without it.

Users, app Redis:      default OFF; healthcheck (+ping); <service> (app key families, no breaker keys);
                       ops (acl|log + ping only, no keys: verification).
Users, breaker Redis:  default OFF; healthcheck; <service> (RW its own worker/scheduler/gate/audit/index keys,
                       READ-ONLY its `rearm:*` markers and the fleet key); trip (SETNX fleet only: cannot expire,
                       overwrite or DEL); probe (EXISTS fleet only); ops (the only writer of rearm markers, fleet
                       DEL, audit; no SCAN).

Never returns a secret in the payload. Offline. The live rollout is by the guardian session, per
`KB § PATTERNS/devops/redis-acl-lockdown.md`.
"""
from __future__ import annotations

import hashlib
import hmac
import os
import re
import stat
from pathlib import Path

from settings import REPO_ROOT
from workspace import resolve_caller_root

COMPOSE_REL = "deploy/fleet/docker-compose.prod.yml"
SCOPE_REL = "deploy/fleet/build-scope.txt"
OUT_DIR_REL = "deploy/fleet/redis-auth"
OVERRIDE_REL = "deploy/fleet/compose.redis-auth.prod.yml"
#: Durable record of WHICH services are cut over, written by `render --services` (cleared only by an explicit
#: empty `--services`). The deploy guard refuses when it lists services the override no longer lists / is missing.
MARKER_NAME = "cutover.services"
MASTER_ENV = "REDIS_ACL_MASTER_SECRET"
GENERATION_ENV = "REDIS_ACL_GENERATION"
OVERRIDES_ENV = "REDIS_ACL_GENERATION_OVERRIDES"

#: The ACL'd Redis (infra compose service `redis-acl`) lives ONLY on this internal network.
DATA_NET = "noctus-data"
REDIS_HOST = "noctus-redis-acl"
REDIS_URL = f"redis://{REDIS_HOST}:6379/0"
#: The DEDICATED breaker Redis (service `breaker-redis`): breaker keys only, same internal net.
BREAKER_HOST = "noctus-breaker-redis"
BREAKER_URL = f"redis://{BREAKER_HOST}:6379/0"
#: The env names a product reads for the breaker connection (the breaker branch adopts exactly these).
BREAKER_ENV_URL = "NOCTUS_BREAKER_REDIS_URL"
BREAKER_ENV_USERNAME = "NOCTUS_BREAKER_REDIS_USERNAME"
BREAKER_ENV_PASSWORD = "NOCTUS_BREAKER_REDIS_PASSWORD"

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

#: APP Redis, product users: everything except the dangerous/admin categories (FLUSHALL, CONFIG, DEBUG, KEYS,
#: SHUTDOWN, ACL, CLIENT KILL/LIST ...) and the scripting category (SCRIPT FLUSH/KILL, FUNCTION * are neither
#: admin nor dangerous -- found by a live probe). Only the Lua surface `limits` uses stays: EVAL/EVALSHA/SCRIPT
#: LOAD/EXISTS, which run under the CALLER's key permissions.
PRODUCT_COMMANDS = "+@all -@dangerous -@admin -@scripting +eval +evalsha +script|load +script|exists"
#: BREAKER Redis, product users: an explicit allow-list, NO scripting (nothing there needs it).
BREAKER_PRODUCT_COMMANDS = ("-@all +get +mget +set +del +exists +ttl +pttl +sadd +srem +smembers +sismember +scard "
                            "+rpush +ltrim +lrange +llen +ping +hello +auth +client|setname")
#: ops on the BREAKER Redis. `ltrim` keeps the audit cap, `sadd` lists a hand-tripped key in the product's index.
#: No SCAN/KEYS (key names are bearer secrets elsewhere; SCAN ignores key patterns): `status` enumerates via each
#: product's `noctus:breaker:<slug>:index` SET (SMEMBERS) + the fleet key. No scripting: a write-then-loop Lua script
#: cannot be killed (SCRIPT KILL refuses once the script wrote), so nobody gets to start one here.
OPS_COMMANDS = ("-@all +get +mget +set +del +rpush +ltrim +lrange +llen +exists +ttl +pttl +smembers +sadd +srem "
                "+sismember +scard +ping +hello +auth +client|setname +acl|log +acl|whoami")
#: ops on the APP Redis: verification only (`ACL LOG` after a cutover), zero key access.
OPS_APP_COMMANDS = "-@all +acl|log +acl|whoami +ping +hello +auth"
#: Slugs that would turn `~<slug>:*` / the user name into something other than "this product".
RESERVED_SLUGS = frozenset({"noctus", "default", "ops", "trip", "probe", "healthcheck", "redis", "limits", "limiter",
                            "nai", "rt", "llm", "wa", "queue", "conversation", "ratelimit", "download", "quota"})
# SETNX, not SET: it cannot take EX/PX/XX, so a stolen trip key can never expire or overwrite an existing trip.
TRIP_COMMANDS = "-@all +setnx +get +exists +ping +hello +auth +client|setname"
HEALTHCHECK_COMMANDS = "-@all +ping"
# Read-only host probe (off-host watchdog's host-probe.sh): "is the fleet breaker tripped?" and nothing else.
# Deliberately NOT `trip`: that identity can SETNX, a probe must never be able to write.
PROBE_COMMANDS = "-@all +exists +ping +hello +auth"

#: Per-product breaker key shapes on the breaker Redis. Sources always start worker:/scheduler:/gate:; `rearm:*`
#: markers are written ONLY by ops (a product holds READ on them), so a compromised product cannot forge or
#: clear a re-arm.
BREAKER_RW_SUFFIXES = ("worker:*", "scheduler:*", "gate:*", "audit", "index")
BREAKER_RO_SUFFIXES = ("rearm:*",)

# NOC-REMEDIATE[breaker-audit-offhost]: `noctus:breaker:audit` and the per-product audit lists live only on the VPS
# breaker Redis; mirror them off-host (watchdog or a Supabase-independent sink) so an attacker or a disk loss
# cannot erase the trail. ALSO: a product user can DEL / LTRIM / SREM its OWN `audit` and `index` keys (they sit
# inside its RW namespace), so a compromised product can erase its own trail. Fix idea (Redis 7 selectors): split
# the grant so products hold only `+rpush +lrange +llen` on `audit` (a selector `(%RW~...audit +rpush +lrange +llen)`
# beside the generic command list is NOT enough: the generic list would still allow DEL/LTRIM on every pattern, so the
# product command set must move to per-selector command lists) and ops alone trims the cap. Not built now. — 2026-11-10


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


def _pw(master: str, user: str, generation) -> str:
    return _hash(derive_password(master, user, generation))


def render_aclfile(roster: list[str], master: str, generation="1") -> str:
    """APP Redis aclfile. Passwords appear ONLY as sha256 hashes. NO comments: Redis rejects them in an aclfile
    (found by running the rendered file through a real redis-server). `client|setinfo` is omitted from the explicit
    lists (absent before Redis 7.2; redis-py swallows its refusal); products get it via +@all on 7.2+.
    NO breaker keys here: the breaker has its own instance (`render_breaker_aclfile`)."""
    lines = [
        "user default off",
        f"user healthcheck on nopass resetkeys resetchannels {HEALTHCHECK_COMMANDS}",
    ]
    fams = [p for p, _ in APP_KEY_FAMILIES]
    for slug in roster:
        pats = [f"~{p}" for p in fams] + [f"~{slug}:*"]
        cmds = " ".join((PRODUCT_COMMANDS, *EXTRA_COMMANDS.get(slug, ())))
        lines.append(
            f"user {slug} on #{_pw(master, slug, generation)} resetkeys resetchannels "
            f"{_key_patterns(pats)} {cmds}"
        )
    lines.append(f"user ops on #{_pw(master, 'ops-app', generation)} resetkeys resetchannels {OPS_APP_COMMANDS}")
    return "\n".join(lines) + "\n"


def breaker_user_password(master: str, slug: str, generation="1") -> str:
    """A product's password on the BREAKER Redis: distinct from its app password (no credential reuse)."""
    return derive_password(master, f"breaker-{slug}", generation)


def render_breaker_aclfile(roster: list[str], master: str, generation="1") -> str:
    """BREAKER Redis aclfile: breaker keys only, no scripting for anyone."""
    lines = [
        "user default off",
        f"user healthcheck on nopass resetkeys resetchannels {HEALTHCHECK_COMMANDS}",
    ]
    for slug in roster:
        pats = [f"%RW~{BREAKER_PREFIX}{slug}:{sfx}" for sfx in BREAKER_RW_SUFFIXES]
        pats += [f"%R~{BREAKER_PREFIX}{slug}:{sfx}" for sfx in BREAKER_RO_SUFFIXES] + [f"%R~{FLEET_KEY}"]
        lines.append(
            f"user {slug} on #{_hash(breaker_user_password(master, slug, generation))} resetkeys resetchannels "
            f"{_key_patterns(pats)} {BREAKER_PRODUCT_COMMANDS}"
        )
    lines.append(f"user trip on #{_pw(master, 'trip', generation)} resetkeys resetchannels %RW~{FLEET_KEY} {TRIP_COMMANDS}")
    lines.append(f"user probe on #{_pw(master, 'probe', generation)} resetkeys resetchannels %R~{FLEET_KEY} {PROBE_COMMANDS}")
    lines.append(f"user ops on #{_pw(master, 'ops', generation)} resetkeys resetchannels ~{BREAKER_PREFIX}* {OPS_COMMANDS}")
    return "\n".join(lines) + "\n"


def render_service_env(slug: str, master: str, generation="1") -> str:
    return (
        f"# GENERATED by noctus.dev.redis_acl for {slug} -- gitignored, 0600.\n"
        f"REDIS_URL={REDIS_URL}\n"
        f"REDIS_USERNAME={slug}\n"
        f"REDIS_PASSWORD={derive_password(master, slug, generation)}\n"
        "REDIS_REQUIRE_AUTH=true\n"
        f"{BREAKER_ENV_URL}={BREAKER_URL}\n"
        f"{BREAKER_ENV_USERNAME}={slug}\n"
        f"{BREAKER_ENV_PASSWORD}={breaker_user_password(master, slug, generation)}\n"
    )


def render_override(services: list[str]) -> str:
    """The compose override (gitignored, written on the VPS): one block per CUT-OVER service."""
    out = [
        "# GENERATED on the VPS by noctus.dev.redis_acl (render --services ...) -- gitignored, do not hand-edit.",
        "# Lists ONLY the services deliberately cut over to the authenticated Redis. While this file exists every",
        "# toolkit compose call adds it as a second -f and refuses a listed service whose env file is missing.",
        "# Cut a service over = re-render with it; roll it back = re-render WITHOUT it (or `--services ''` to remove).",
        "# Manual compose: docker compose -f docker-compose.prod.yml -f compose.redis-auth.prod.yml up -d <svc>",
        "# KB § PATTERNS/devops/redis-acl-lockdown.md",
        "",
        "services:",
    ]
    for slug in services:
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


def _ensure_private_dir(d: Path, mode: int = 0o700) -> None:
    if d.is_symlink():
        raise ValueError(f"{d} is a symlink - refusing to write secrets through it")
    d.mkdir(mode=mode, parents=True, exist_ok=True)
    os.chmod(d, mode)


def _write_secret(path: Path, text: str, mode: int) -> None:
    """Temp file (O_EXCL|O_NOFOLLOW, born `mode`), then atomic rename: never follows a planted symlink, never
    leaves a half-written or wider-than-`mode` secret. **Ownership survives a re-render**: the operator `chown`s
    `trip.pass`/`probe.pass` to their consumers once; a plain `os.replace` would hand every re-render's file back
    to the renderer and the forced-command user would silently lose access. So the temp file is chowned to the
    existing target's uid/gid before the replace; when the renderer cannot do that (not root), the existing file is
    rewritten IN PLACE (same inode, same owner). The parent dir is created 0700 if absent and otherwise left alone
    (callers own its mode)."""
    parent = path.parent
    if parent.is_symlink():
        raise ValueError(f"{parent} is a symlink - refusing to write secrets through it")
    parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    try:
        st = os.lstat(path)
    except FileNotFoundError:
        st = None
    tmp = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    fd = os.open(tmp, os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW, mode)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(text)
        os.chmod(tmp, mode)
        if st is not None and stat.S_ISREG(st.st_mode):
            try:
                os.chown(tmp, st.st_uid, st.st_gid)
            except PermissionError:
                tmp.unlink(missing_ok=True)
                ifd = os.open(path, os.O_WRONLY | os.O_TRUNC | os.O_NOFOLLOW)
                with os.fdopen(ifd, "w", encoding="utf-8") as fh:
                    fh.write(text)
                os.chmod(path, mode)
                return
        os.replace(tmp, path)
    except BaseException:
        tmp.unlink(missing_ok=True)
        raise


def _normalize_services(services, roster: list[str]) -> list[str]:
    svc = sorted({x.strip() for x in (services.split(",") if isinstance(services, str) else services) if x.strip()})
    unknown = [x for x in svc if x not in roster]
    if unknown:
        raise ValueError(f"--services {unknown} not in the derived roster {roster}")
    return svc


def parse_override_services(text: str) -> list[str]:
    """Service names listed in a rendered override (the block between `services:` and top-level `networks:`)."""
    body = text.split("\nservices:\n", 1)[-1].split("\nnetworks:\n", 1)[0]
    return re.findall(r"^  ([a-z][a-z0-9\-]*):\s*$", body, flags=re.M)


def _read_marker(root: Path) -> list[str]:
    p = root / OUT_DIR_REL / MARKER_NAME
    return [x.strip() for x in p.read_text(encoding="utf-8").splitlines() if x.strip()] if p.is_file() else []


def _pass_file_report(root: Path) -> dict:
    """Mode/owner of the pass files. The renderer cannot `test -r` AS another user, so it reports what it can see:
    the owner uid and whether that owner has read permission; run `sudo -u <user> test -r <file>` for the real check."""
    out: dict = {}
    for name in ("ops", "ops-app", "trip", "probe"):
        p = root / OUT_DIR_REL / f"{name}.pass"
        if not p.is_file():
            out[name] = {"present": False}
            continue
        st = p.stat()
        out[name] = {"present": True, "mode": oct(st.st_mode & 0o777), "uid": st.st_uid, "gid": st.st_gid,
                     "owner_can_read": bool(st.st_mode & 0o400), "group_other_access": bool(st.st_mode & 0o077)}
    return out


def _check(root: Path) -> dict:
    roster = _load(root)
    marker = _read_marker(root)
    p = root / OVERRIDE_REL
    pass_files = _pass_file_report(root)
    bad_pass = [n for n, r in pass_files.items() if r.get("present") and (not r["owner_can_read"] or r["group_other_access"])]
    base = {"action": "check", "roster": roster, "marker": marker, "pass_files": pass_files}
    if not p.is_file():
        if marker:
            return {**base, "ok": False, "status": "drift", "cut_over": [], "marker_without_override": marker,
                    "fix": "re-render the override: python mcp/noctusai/cli.py --redis-acl render --redis-acl-write "
                           f"--redis-acl-services {','.join(marker)}  (or clear the marker with --redis-acl-services '')"}
        return {**base, "ok": not bad_pass, "status": "no_override", "cut_over": [],
                **({"bad_pass_file_modes": bad_pass} if bad_pass else {})}
    listed = parse_override_services(p.read_text(encoding="utf-8"))
    env_dir = root / OUT_DIR_REL / "env"
    missing = [x for x in listed if x not in roster or not (env_dir / f"{x}.env").is_file()]
    unlisted = [x for x in marker if x not in listed]
    ok = not missing and not unlisted and not bad_pass
    return {**base, "ok": ok, "status": "in_sync" if ok else "drift", "cut_over": listed,
            **({} if not missing else {"missing_or_not_in_roster": missing}),
            **({} if not unlisted else {"marker_services_missing_from_override": unlisted}),
            **({} if not bad_pass else {"bad_pass_file_modes": bad_pass}),
            **({} if ok else {"fix": "python mcp/noctusai/cli.py --redis-acl render --redis-acl-write --redis-acl-services <list>"})}


def _render(root: Path, write: bool, env: dict[str, str] | None, env_file: str | None, services) -> dict:
    roster = _load(root)
    svc = None if services is None else _normalize_services(services, roster)
    result: dict = {"ok": True, "action": "render", "roster": roster,
                    "app_users": ["default(off)", "healthcheck", *roster, "ops"],
                    "breaker_users": ["default(off)", "healthcheck", *roster, "trip", "probe", "ops"],
                    "key_families": [p for p, _ in APP_KEY_FAMILIES], "written": [],
                    "cut_over": svc if svc is not None else "unchanged"}
    if write:
        master, gen = _read_master(root, env, env_file)
        try:
            out = root / OUT_DIR_REL
            # 0711: the forced-command / probe users must TRAVERSE to their own pass file (not list the dir).
            _ensure_private_dir(out, 0o711)
            _ensure_private_dir(out / "env")
            _write_secret(out / "users.acl", render_aclfile(roster, master, gen), 0o644)
            _write_secret(out / "breaker-users.acl", render_breaker_aclfile(roster, master, gen), 0o644)
            for slug in roster:
                _write_secret(out / "env" / f"{slug}.env", render_service_env(slug, master, gen), 0o600)
            for name, user in (("ops", "ops"), ("ops-app", "ops-app"), ("trip", "trip"), ("probe", "probe")):
                _write_secret(out / f"{name}.pass", derive_password(master, user, gen) + "\n", 0o600)
            result["written"] += [f"{OUT_DIR_REL}/users.acl", f"{OUT_DIR_REL}/breaker-users.acl",
                                  f"{OUT_DIR_REL}/env/<service>.env x{len(roster)}",
                                  *(f"{OUT_DIR_REL}/{n}.pass" for n in ("ops", "ops-app", "trip", "probe"))]
            ov = root / OVERRIDE_REL
            marker = out / MARKER_NAME
            if svc is not None:
                if svc:
                    ov.write_text(render_override(svc), encoding="utf-8")
                    _write_secret(marker, "\n".join(svc) + "\n", 0o644)
                    result["written"] += [OVERRIDE_REL, f"{OUT_DIR_REL}/{MARKER_NAME}"]
                else:
                    ov.unlink(missing_ok=True)
                    marker.unlink(missing_ok=True)
                    result["written"].append(f"{OVERRIDE_REL} + {MARKER_NAME} (removed: no service is cut over)")
        except ValueError as e:
            return {"ok": False, "action": "render", "status": "error", "error": str(e), "written": result["written"]}
    result["status"] = "written" if write else "planned"
    return result


def redis_acl(
    action: str = "check",
    *,
    write: bool = False,
    services=None,
    env_file: str | None = None,
    repo_root: str | None = None,
    worktree_path: str | None = None,
    env: dict[str, str] | None = None,
) -> dict:
    """action='check' (the host-local override is consistent: every cut-over service is in the roster and has its
    env file; offline) | 'render' (plan; write=True writes both aclfiles, per-service env, pass files, and -- when
    `services` is given -- the override listing exactly those services; `services=[]`/'' removes it; None leaves it)."""
    root = _resolve_root(repo_root, worktree_path)
    try:
        if action == "check":
            return _check(root)
        if action == "render":
            return _render(root, write, env, env_file, services)
    except (ValueError, OSError) as e:
        return {"ok": False, "action": action, "status": "error", "error": str(e)}
    return {"ok": False, "action": action, "error": f"unknown action {action!r} -- expected 'check' or 'render'"}


def register(server) -> None:
    @server.tool(
        name="noctus.dev.redis_acl",
        description=(
            "Prod Redis ACL lockdown, DERIVED (KB § PATTERNS/devops/redis-acl-lockdown.md). Two instances: app Redis "
            "+ a dedicated breaker Redis. Roster = live services loading the root .env (compose x build-scope.txt). "
            "action='check' (default, offline): the host-local compose.redis-auth.prod.yml is consistent. "
            "action='render': plan; write=True writes the gitignored aclfiles (sha256 hashes only), per-service env, "
            "pass files from REDIS_ACL_MASTER_SECRET and, with services='a,b', the override naming exactly the "
            "services to cut over (services='' removes it). Never returns a secret. Never touches the VPS."
        ),
    )
    def _redis_acl(action: str = "check", write: bool = False, services: str | None = None,
                   env_file: str = "", worktree_path: str = "") -> dict:
        return redis_acl(action, write=write, services=services, env_file=env_file or None,
                         worktree_path=worktree_path or None)


__all__ = ["redis_acl", "register", "derive_roster", "derive_password", "render_aclfile", "render_breaker_aclfile",
           "render_service_env", "render_override", "parse_override_services", "APP_KEY_FAMILIES"]
