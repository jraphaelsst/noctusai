#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# breaker-trip.sh — VPS-side FORCED COMMAND for the off-host fleet-breaker key.
#
# The breaker key's authorized_keys entry (the OWNER installs it; see
# KB § PATTERNS/devops/prod-watchdog.md § Fleet breaker):
#   restrict,command="/opt/noctus/noctusai/deploy/watchdog/breaker-trip.sh" <pubkey>
# so the key can run ONLY this script. $SSH_ORIGINAL_COMMAND is ignored. This is a
# DIFFERENT key from the host-probe (read-only) key: a read-only key must never gain
# a write, and a write key must never gain a read.
#
# What it does — exactly one thing: SET `noctus:breaker:fleet` (NX) in the fleet Redis
# to a JSON read from stdin, after validating it. While that key exists every product's
# background workers/schedulers stay stopped and the APIs keep serving (the seed side:
# feat/supabase-breaker). RE-ARM IS HUMAN, via `noctus.dev.supabase_breaker`: this script
# can never delete the key, never overwrites an existing one (NX keeps the FIRST trip's
# reason), and refuses any payload that is not the exact breaker shape.
#
# stdin JSON (all five keys, nothing else):
#   {"reason": str<=300, "rate": number|str<=200, "window": str<=64,
#    "tripped_at": str<=40, "by": "offhost-watchdog"}
# stdout: ONE JSON line {"tripped":true,"already":false} | {"tripped":false,"already":true}
# exit: 0 ok (tripped now or already) · 2 invalid payload · 3 redis/tooling failure
# KB § PATTERNS/devops/prod-watchdog.md
# ──────────────────────────────────────────────────────────────────────────────
set -u -o pipefail

KEY="noctus:breaker:fleet"
REDIS_CONTAINER="${NOCTUS_REDIS_CONTAINER:-noctus-redis}"
MAX_BYTES=2048

payload="$(head -c "$MAX_BYTES" 2>/dev/null)"

# Validate + canonicalise in python (stdlib): the value written is re-serialised from the
# parsed object, never the raw stdin — nothing the sender controls reaches redis verbatim.
canon="$(printf '%s' "$payload" | python3 -c '
import json, sys
try:
    d = json.loads(sys.stdin.read())
except Exception:
    sys.exit(2)
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
if not ((isinstance(r, (int, float)) and not isinstance(r, bool)) or ok_str(r, 200)):
    sys.exit(2)
print(json.dumps(d, sort_keys=True, separators=(",", ":"), ensure_ascii=False))
' 2>/dev/null)"
rc=$?
if [[ $rc -ne 0 || -z "$canon" ]]; then
  echo '{"error":"invalid payload"}' >&2
  exit 2
fi

# argv, not a shell string: the JSON is a single docker-exec argument.
out="$(timeout 15 docker exec "$REDIS_CONTAINER" redis-cli SET "$KEY" "$canon" NX 2>/dev/null)"
case "$out" in
  OK)  echo '{"tripped":true,"already":false}' ;;
  "")  # nil reply prints an empty line: the key already exists (an earlier trip stands)
       exists="$(timeout 15 docker exec "$REDIS_CONTAINER" redis-cli EXISTS "$KEY" 2>/dev/null)"
       if [[ "$exists" == "1" ]]; then echo '{"tripped":false,"already":true}'; else echo '{"error":"redis unreachable"}' >&2; exit 3; fi ;;
  *)   echo '{"error":"redis refused"}' >&2; exit 3 ;;
esac
