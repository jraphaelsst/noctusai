#!/bin/sh
# entrypoint.sh — root:root, PID 1. Fails CLOSED before dropping to
# `noctus` (contract SEC-A/SEC-C, roadmap D1, tech-lead + security-advisor
# review 2026-09-14).
#
# WHY FAIL CLOSED: this image's whole isolation model (julia-cli's uid
# separation, the wrapper's cap-drop) depends on the COMPOSE hardening
# actually being in effect (`cap_drop: ALL` + `cap_add: SETUID,SETGID,
# KILL` + `no-new-privileges:true` + `read_only: true`). A future compose
# edit that silently drops one of those flags (or a bare `docker run`
# with none of them) must not fall back to "starts anyway, just less
# isolated" — every check below is a refusal-to-boot, not a warning.
#
# WHY `--ambient-caps=... +kill`: `noctus` (uid 1000) must be able to
# `kill()` the Julia CLI subprocess (uid 1001, a DIFFERENT uid) on
# turn-timeout / SDK client close — sending a signal across a uid
# boundary needs CAP_KILL (or being the same uid, or root), and `noctus`
# is neither of the other two. Without it, a timed-out/hung CLI process
# leaks for the container's lifetime (the SDK's own `close()` reaps it
# via a signal it can no longer send).
set -eu

fail() {
  echo "entrypoint: refusing to start — $1" >&2
  exit 1
}

# 1. Must be launched as root — the whole point of this entrypoint is the
#    ONE controlled root->noctus privilege drop below; anything else
#    means the image was invoked in a way this design didn't anticipate.
[ "$(id -u)" = "0" ] || fail "must be launched as root (uid 0), got uid $(id -u)"

# 2. NoNewPrivs must already be 1 — compose `security_opt:
#    [no-new-privileges:true]`. Belt-and-suspenders: this entrypoint also
#    passes `--no-new-privs` to its own `setpriv` call below, but that
#    only fires AFTER this gate, and a container that never even asked
#    the kernel for no-new-privs at the OCI level is not the image this
#    was designed for.
NNP="$(awk '/^NoNewPrivs:/ {print $2}' /proc/self/status)"
[ "$NNP" = "1" ] || fail "NoNewPrivs must be 1 (compose security_opt: [no-new-privileges:true]); got '${NNP:-<missing>}'"

# 3. CapBnd must be EXACTLY {SETUID, SETGID, KILL} — compose `cap_drop:
#    [ALL]` + `cap_add: [SETUID, SETGID, KILL]`. Bit 5 = CAP_KILL, bit 6 =
#    CAP_SETGID, bit 7 = CAP_SETUID (linux/capability.h) => mask 0xE0.
#    Anything wider means a broader cap_add than intended (this
#    entrypoint's own privilege-drop guarantee is only as tight as the
#    bounding set it starts from); anything narrower means SETUID/SETGID/
#    KILL are missing and the drop below (or the wrapper's own switch)
#    will fail loudly downstream anyway — better to refuse now with a
#    clear reason than fail obscurely mid-request.
EXPECTED_BND="00000000000000e0"
ACTUAL_BND="$(awk '/^CapBnd:/ {print $2}' /proc/self/status)"
[ "$ACTUAL_BND" = "$EXPECTED_BND" ] || fail "CapBnd must be exactly $EXPECTED_BND / SETUID+SETGID+KILL (compose cap_drop: [ALL] + cap_add: [SETUID, SETGID, KILL]); got '${ACTUAL_BND:-<missing>}'"

# 4. The root filesystem must be read-only — compose `read_only: true`.
#    Probe with a path that cannot collide with a real file and is
#    removed immediately if the write unexpectedly succeeds.
if ( set -e; touch /.d1-readonly-probe ) 2>/dev/null; then
  rm -f /.d1-readonly-probe
  fail "root filesystem is writable (compose read_only: true is missing)"
fi

umask 077

exec /usr/bin/setpriv \
  --reuid=1000 --regid=1000 --init-groups \
  --inh-caps=-all,+setuid,+setgid,+kill --ambient-caps=-all,+setuid,+setgid,+kill \
  --no-new-privs \
  -- \
  uvicorn app.main:app --host 0.0.0.0 --port 8016 --app-dir products/agents/backend --workers 1
