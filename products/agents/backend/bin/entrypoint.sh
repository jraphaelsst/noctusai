#!/bin/sh
# entrypoint.sh — root:root, PID 1. Fails CLOSED before dropping to
# `noctus` (contract §E.11, supersedes §E.5; roadmap D1, per-conversation
# slot isolation, architect review 2026-09-15).
#
# WHY FAIL CLOSED: this image's whole isolation model (each slot uid's
# separation, the wrapper's cap-drop) depends on the COMPOSE hardening
# actually being in effect (`cap_drop: ALL` + `cap_add: SETUID,SETGID,
# KILL` + `no-new-privileges:true` + `read_only: true` + one tmpfs per
# slot plus the shared handoff tmpfs). A future compose edit that
# silently drops one of those flags or mounts (or a bare `docker run`
# with none of them) must not fall back to "starts anyway, just less
# isolated" — every check below is a refusal-to-boot, not a warning.
#
# WHY `--ambient-caps=... +kill`: `noctus` (uid 1000) must be able to
# `kill()` a slot's Julia CLI subprocess (a DIFFERENT uid — one of
# `julia-cli-0`/`julia-cli-1`/`julia-cli-2`) on turn-timeout / SDK client
# close — sending a signal across a uid boundary needs CAP_KILL (or being
# the same uid, or root), and `noctus` is neither of the other two.
# Without it, a timed-out/hung CLI process leaks for the container's
# lifetime (the SDK's own `close()` reaps it via a signal it can no
# longer send).
set -eu

fail() {
  echo "entrypoint: refusing to start — $1" >&2
  exit 1
}

# Returns the fs_mntops (4th /proc/mounts field) for the FIRST mount whose
# mount point EXACTLY matches $1, or nothing if not mounted at all.
_mount_opts() {
  awk -v m="$1" '$2 == m { print $4; exit }' /proc/mounts
}

# $1 = raw comma-separated options string (no leading/trailing comma, as
# /proc/mounts always presents it). $2 = the exact "key=value" (or bare
# flag) token to require. Wrapping both sides in commas turns "is this
# token present" into one substring test regardless of whether the token
# is first, middle, or last (the LAST token has no trailing comma in
# /proc/mounts — verified live: `size=40960k,mode=700,uid=2000,gid=2000`).
_opts_has() {
  case ",$1," in
    *",$2,"*) return 0 ;;
    *) return 1 ;;
  esac
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

# 5. Every slot's tmpfs must be mounted with the correct owner, mode and
#    size (contract §E.11) — a compose edit that drops one slot's tmpfs,
#    or leaves it wrongly owned/sized, must not fall back to "boots
#    anyway, with that one slot silently unusable or under-isolated."
#    $JULIA_CLI_SLOTS itself must resolve — `set -u` would already abort
#    on a genuinely unset var below, but this gives a named reason instead
#    of a bare "unbound variable" shell error.
case "${JULIA_CLI_SLOTS:-}" in
  ''|*[!0-9]*)
    fail "JULIA_CLI_SLOTS must be a positive integer, got '${JULIA_CLI_SLOTS:-<unset>}'"
    ;;
esac

k=0
while [ "$k" -lt "$JULIA_CLI_SLOTS" ]; do
  mnt="/run/julia-$k"
  uid=$((2000 + k))
  opts="$(_mount_opts "$mnt")"
  [ -n "$opts" ] || fail "missing tmpfs mount at $mnt (JULIA_CLI_SLOTS=$JULIA_CLI_SLOTS expects one per slot; compose tmpfs: entry missing or the mount point is wrong)"
  _opts_has "$opts" "uid=$uid" || fail "$mnt: expected uid=$uid; got options '$opts'"
  _opts_has "$opts" "gid=$uid" || fail "$mnt: expected gid=$uid; got options '$opts'"
  _opts_has "$opts" "mode=700" || fail "$mnt: expected mode=700; got options '$opts'"
  _opts_has "$opts" "size=40960k" || fail "$mnt: expected size=40960k (40m); got options '$opts'"
  k=$((k + 1))
done

# 6. The shared handoff tmpfs must be owned by `noctus` (uid/gid 1000)
#    with mode 0711 — a wider mode (e.g. 0777, or group/other read) would
#    let one slot uid LIST another slot's handoff subdirectory, and a
#    different owner would break the "noctus writes, only the matching
#    slot's own primary group can read" guarantee the handoff file's own
#    mode 0640 depends on.
handoff_opts="$(_mount_opts /run/julia-handoff)"
[ -n "$handoff_opts" ] || fail "missing tmpfs mount at /run/julia-handoff (compose tmpfs: entry missing)"
_opts_has "$handoff_opts" "uid=1000" || fail "/run/julia-handoff: expected uid=1000; got options '$handoff_opts'"
_opts_has "$handoff_opts" "gid=1000" || fail "/run/julia-handoff: expected gid=1000; got options '$handoff_opts'"
_opts_has "$handoff_opts" "mode=711" || fail "/run/julia-handoff: expected mode=711; got options '$handoff_opts'"

umask 077

exec /usr/bin/setpriv \
  --reuid=1000 --regid=1000 --init-groups \
  --inh-caps=-all,+setuid,+setgid,+kill --ambient-caps=-all,+setuid,+setgid,+kill \
  --no-new-privs \
  -- \
  uvicorn app.main:app --host 0.0.0.0 --port 8016 --app-dir products/agents/backend --workers 1
