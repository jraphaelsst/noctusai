#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# breaker-trip.sh — VPS-side FORCED COMMAND for the off-host fleet-breaker key.
#
# The key belongs to a dedicated UNPRIVILEGED user `breaker` (never root). Its authorized_keys
# entry (the OWNER installs it; see KB § PATTERNS/devops/prod-watchdog.md § 7b):
#   restrict,command="sudo /opt/noctus/noctusai/deploy/watchdog/breaker-trip.sh" <pubkey> noctus-breaker-trip
# and /etc/sudoers.d/noctus-breaker (deploy/watchdog/noctus-breaker.sudoers) lets `breaker` run exactly
# this script, no arguments, as root (the script needs docker). So the key can run ONLY this script;
# $SSH_ORIGINAL_COMMAND is ignored. This is a DIFFERENT key from the host-probe (read-only) key: a
# read-only key must never gain a write, and a write key must never gain a read.
#
# What it does — exactly one thing: SETNX `noctus:breaker:fleet` in the fleet Redis
# to a JSON read from stdin, after validating it. While that key exists every product's
# background workers/schedulers stay stopped and the APIs keep serving (the seed side:
# feat/supabase-breaker). RE-ARM IS HUMAN, via `noctus.dev.supabase_breaker`: this script
# can never delete the key, never overwrites an existing one (NX keeps the FIRST trip's
# reason), and refuses any payload that is not the exact breaker shape.
#
# stdin JSON (all five keys, nothing else; or exactly {"verify": true}, a read-only EXISTS):
#   {"reason": str<=300, "rate": number|str<=200, "window": str<=64,
#    "tripped_at": str<=40, "by": "offhost-watchdog"}
# stdout: ONE JSON line {"tripped":true,"already":false} | {"tripped":false,"already":true}
# exit: 0 ok (tripped now or already) · 2 invalid payload · 3 redis/tooling failure
# KB § PATTERNS/devops/prod-watchdog.md
# ──────────────────────────────────────────────────────────────────────────────
set -u -o pipefail
cd / || exit 3   # never inherit a caller-controlled working directory

KEY="noctus:breaker:fleet"
MAX_BYTES=2048

# Redis target. Today: the unauthenticated `noctus-redis`. Once the ACL Redis lands
# (redis-acl-lockdown doc §5, branch feat/redis-acl-lockdown) the `trip` credential file exists and we talk to
# `noctus-breaker-redis` as user `trip`, the password coming from that root-owned file through the
# ENVIRONMENT (docker exec -e REDISCLI_AUTH), never a command line.
TRIP_PASS_FILE="${NOCTUS_REDIS_TRIP_PASS_FILE:-/opt/noctus/noctusai/deploy/fleet/redis-auth/trip.pass}"
if [[ -r "$TRIP_PASS_FILE" ]]; then
  REDIS_CONTAINER="${NOCTUS_REDIS_CONTAINER:-noctus-breaker-redis}"
  export REDISCLI_AUTH; REDISCLI_AUTH="$(cat "$TRIP_PASS_FILE")"
  rcli() { timeout 15 docker exec -e REDISCLI_AUTH "$REDIS_CONTAINER" redis-cli --no-auth-warning --user trip "$@" 2>/dev/null; }
else
  REDIS_CONTAINER="${NOCTUS_REDIS_CONTAINER:-noctus-redis}"
  rcli() { timeout 15 docker exec "$REDIS_CONTAINER" redis-cli "$@" 2>/dev/null; }
fi

payload="$(head -c "$MAX_BYTES" 2>/dev/null)"

# Validate + canonicalise in python (stdlib, isolated -I): the value written is re-serialised from the
# parsed object, never the raw stdin. The ONE other accepted payload is {"verify": true}: a READ-ONLY
# EXISTS used by the owner's one-time setup check (it proves ssh + forced command + sudo + redis access
# without tripping the fleet).
canon="$(printf '%s' "$payload" | python3 -I -c '
import json, math, sys
def _refuse(_c):  # NaN / Infinity / -Infinity are not JSON: refuse them at parse time
    raise ValueError(_c)
try:
    d = json.loads(sys.stdin.read(), parse_constant=_refuse)
except Exception:
    sys.exit(2)
if d == {"verify": True}:
    print("VERIFY")
    sys.exit(0)
KEYS = {"reason", "rate", "window", "tripped_at", "by"}
def ok_str(v, n):
    return isinstance(v, str) and 0 < len(v) <= n and "\n" not in v and "\r" not in v
if not (isinstance(d, dict) and set(d) == KEYS):
    sys.exit(2)
if not (ok_str(d["reason"], 300) and ok_str(d["window"], 64) and ok_str(d["tripped_at"], 40)):
    sys.exit(2)
if d["by"] != "offhost-watchdog":
    sys.exit(2)
r = d["rate"]
if not ((isinstance(r, (int, float)) and not isinstance(r, bool) and math.isfinite(r)) or ok_str(r, 200)):
    sys.exit(2)  # 1e999 parses to inf without parse_constant: isfinite catches it
print(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False, allow_nan=False))
' 2>/dev/null)"
rc=$?
if [[ $rc -ne 0 || -z "$canon" ]]; then
  echo '{"error":"invalid payload"}' >&2
  exit 2
fi

if [[ "$canon" == "VERIFY" ]]; then
  exists="$(rcli EXISTS "$KEY")"
  if [[ "$exists" == "0" || "$exists" == "1" ]]; then echo "{\"verify\":true,\"exists\":$exists}"; exit 0; fi
  echo '{"error":"redis unreachable"}' >&2
  exit 3
fi

# SETNX, not `SET ... NX`: the ACL `trip` user holds +setnx only (it can neither overwrite nor expire the key),
# and the legacy path behaves identically. Reply: 1 = we set it, 0 = it already existed (the first trip stands).
out="$(rcli SETNX "$KEY" "$canon")"
case "$out" in
  1)  echo '{"tripped":true,"already":false}' ;;
  0)  echo '{"tripped":false,"already":true}' ;;
  *)  echo '{"error":"redis unreachable or refused"}' >&2; exit 3 ;;
esac
