#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# install-heartbeat.sh — provision the ON-HOST half of the off-host prod watchdog.
# Run as root ON THE VPS, from the repo checkout (/opt/noctus/noctusai):
#
#   bash deploy/watchdog/install-heartbeat.sh                       # units + timer
#   bash deploy/watchdog/install-heartbeat.sh --watchdog-pubkey k.pub  # + restricted key
#   bash deploy/watchdog/install-heartbeat.sh --check [--watchdog-pubkey k.pub]
#
# IDEMPOTENT: a unit file is copied into /etc/systemd/system only when its
# content differs; `daemon-reload` runs only after a change; the timer is
# `enable --now`ed (a no-op when already enabled + active); the authorized_keys
# line is added exactly once (matched on the key BODY).
#
# The key line is `restrict,command="<host-probe.sh>"`: `restrict` drops pty +
# port/agent/X11 forwarding + user-rc in one keyword, and this key needs NO
# forward — so the `restrict`-vs-`permitopen` trap
# (KB § PATTERNS/devops/ssh-deploy-key-restrictions.md) does not apply here.
#
# --check changes NOTHING: it reports units, timer, heartbeat age, the key line
# and one live host-probe run.
# KB § PATTERNS/devops/prod-watchdog.md
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
UNIT_DIR="${NOCTUS_SYSTEMD_DIR:-/etc/systemd/system}"
STATE_DIR="/var/lib/noctus"
FORCED_CMD="/opt/noctus/noctusai/deploy/watchdog/host-probe.sh"
AUTH_KEYS="${NOCTUS_AUTHORIZED_KEYS:-/root/.ssh/authorized_keys}"
KEY_COMMENT="noctus-prod-watchdog"
UNITS=(noctus-heartbeat.service noctus-heartbeat.timer)

MODE="apply"
PUBKEY_FILE=""

usage() {
  sed -n '3,9p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --check) MODE="check"; shift ;;
    --watchdog-pubkey)
      [[ $# -ge 2 ]] || { echo "ERROR: --watchdog-pubkey needs a file" >&2; exit 2; }
      PUBKEY_FILE="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "ERROR: unknown argument '$1'" >&2; usage >&2; exit 2 ;;
  esac
done

# key_line_parts <file> → sets KEY_TYPE / KEY_BODY, or exits 2 on a bad file.
KEY_TYPE=""; KEY_BODY=""
read_pubkey() {
  local f="$1" line n
  [[ -r "$f" ]] || { echo "ERROR: cannot read pubkey file '$f'" >&2; exit 2; }
  n="$(grep -cv '^[[:space:]]*$' "$f" || true)"
  [[ "$n" == "1" ]] || { echo "ERROR: '$f' must hold exactly ONE public key line (found $n)" >&2; exit 2; }
  line="$(grep -v '^[[:space:]]*$' "$f")"
  read -r KEY_TYPE KEY_BODY _rest <<<"$line"
  case "$KEY_TYPE" in
    ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp256|ecdsa-sha2-nistp384|ecdsa-sha2-nistp521|sk-ssh-ed25519@openssh.com) ;;
    *) echo "ERROR: '$f' is not an OpenSSH public key (type '$KEY_TYPE'); options must not be pre-pended — this script writes them" >&2; exit 2 ;;
  esac
  [[ "$KEY_BODY" =~ ^[A-Za-z0-9+/=]+$ ]] || { echo "ERROR: malformed key body in '$f'" >&2; exit 2; }
}

key_present() {
  [[ -f "$AUTH_KEYS" ]] && grep -qF -- "$KEY_BODY" "$AUTH_KEYS"
}

if [[ -n "$PUBKEY_FILE" ]]; then
  read_pubkey "$PUBKEY_FILE"
fi

# ── --check: report only ─────────────────────────────────────────────────────
if [[ "$MODE" == "check" ]]; then
  for u in "${UNITS[@]}"; do
    if [[ ! -f "$UNIT_DIR/$u" ]]; then
      echo "unit $u: NOT INSTALLED"
    elif cmp -s "$SRC_DIR/$u" "$UNIT_DIR/$u"; then
      echo "unit $u: installed, matches repo"
    else
      echo "unit $u: installed, DIFFERS from repo (re-run without --check)"
    fi
  done
  echo "timer enabled: $(systemctl is-enabled noctus-heartbeat.timer 2>/dev/null || echo no)"
  echo "timer active:  $(systemctl is-active noctus-heartbeat.timer 2>/dev/null || echo no)"
  if [[ -f "$STATE_DIR/heartbeat" ]]; then
    echo "heartbeat age: $(( $(date +%s) - $(stat -c %Y "$STATE_DIR/heartbeat") ))s"
  else
    echo "heartbeat: MISSING ($STATE_DIR/heartbeat)"
  fi
  if [[ -x "$FORCED_CMD" ]]; then
    echo "forced command: $FORCED_CMD (executable)"
    echo "host-probe output: $("$FORCED_CMD")"
  else
    echo "forced command: $FORCED_CMD NOT EXECUTABLE / MISSING"
  fi
  if [[ -n "$PUBKEY_FILE" ]]; then
    if key_present; then
      echo "watchdog key: present in $AUTH_KEYS"
      grep -F -- "$KEY_BODY" "$AUTH_KEYS" | grep -qF "command=\"$FORCED_CMD\"" \
        && echo "watchdog key: forced command OK" \
        || echo "watchdog key: present but WITHOUT the forced command — fix by hand"
    else
      echo "watchdog key: NOT in $AUTH_KEYS"
    fi
  fi
  exit 0
fi

# ── apply ────────────────────────────────────────────────────────────────────
[[ "$(id -u)" == "0" ]] || { echo "ERROR: run as root (or pass --check)" >&2; exit 1; }

mkdir -p "$STATE_DIR"
chmod 0755 "$STATE_DIR"

changed=0
for u in "${UNITS[@]}"; do
  if [[ -f "$UNIT_DIR/$u" ]] && cmp -s "$SRC_DIR/$u" "$UNIT_DIR/$u"; then
    echo "unit $u: unchanged"
  else
    install -m 0644 "$SRC_DIR/$u" "$UNIT_DIR/$u"
    echo "unit $u: installed"
    changed=1
  fi
done
if [[ "$changed" == "1" ]]; then
  systemctl daemon-reload
  echo "systemd: daemon-reload"
fi
systemctl enable --now noctus-heartbeat.timer
echo "timer: $(systemctl is-enabled noctus-heartbeat.timer) / $(systemctl is-active noctus-heartbeat.timer)"

[[ -x "$FORCED_CMD" ]] || echo "WARNING: $FORCED_CMD is not executable — the watchdog key will fail until the repo checkout has it (+x is tracked in git)" >&2

if [[ -n "$PUBKEY_FILE" ]]; then
  mkdir -p "$(dirname "$AUTH_KEYS")"
  chmod 0700 "$(dirname "$AUTH_KEYS")"
  touch "$AUTH_KEYS"
  chmod 0600 "$AUTH_KEYS"
  if key_present; then
    echo "watchdog key: already present in $AUTH_KEYS (unchanged)"
  else
    # Guarantee the new entry starts on its own line.
    if [[ -s "$AUTH_KEYS" && -n "$(tail -c1 "$AUTH_KEYS")" ]]; then
      printf '\n' >> "$AUTH_KEYS"
    fi
    printf 'restrict,command="%s" %s %s %s\n' "$FORCED_CMD" "$KEY_TYPE" "$KEY_BODY" "$KEY_COMMENT" >> "$AUTH_KEYS"
    echo "watchdog key: added to $AUTH_KEYS (restrict + forced command)"
  fi
fi
echo "done."
