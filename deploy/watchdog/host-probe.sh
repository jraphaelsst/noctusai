#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# host-probe.sh — VPS-side FORCED COMMAND for the off-host prod watchdog key.
#
# The watchdog key's authorized_keys entry (written by install-heartbeat.sh):
#   restrict,command="/opt/noctus/noctusai/deploy/watchdog/host-probe.sh" <pubkey>
# so the key can run ONLY this script. $SSH_ORIGINAL_COMMAND is ignored.
#
# Prints exactly ONE JSON line (consumed by noctus.dev.prod_watchdog):
#   {"journald_last_age_s":N|null,"heartbeat_age_s":N|null,
#    "mem_available_mb":N|null,"swap_used_mb":N|null,"load1":F|null,
#    "load5":F|null,"ncpu":N|null,"uptime_s":N|null,"now":N}
#
# READ-ONLY and never fails hard: `set -u` (not -e) — a probe that cannot read
# something reports null for that field instead of dying, because a missing
# answer is itself the signal (journald silently dead for ~20h before the
# 2026-10-11 freeze is why this exists). Every external read is time-boxed.
# KB § PATTERNS/devops/prod-watchdog.md
# ──────────────────────────────────────────────────────────────────────────────
set -u -o pipefail

HEARTBEAT_FILE="${NOCTUS_HEARTBEAT_FILE:-/var/lib/noctus/heartbeat}"

now="$(date +%s)"

# int_or_null <value> — a non-negative integer, else the JSON literal null.
int_or_null() {
  if [[ "${1:-}" =~ ^[0-9]+$ ]]; then printf '%s' "$1"; else printf 'null'; fi
}
# num_or_null <value> — a non-negative decimal (load averages), else null.
num_or_null() {
  if [[ "${1:-}" =~ ^[0-9]+(\.[0-9]+)?$ ]]; then printf '%s' "$1"; else printf 'null'; fi
}
# age_or_null <epoch> — seconds since <epoch> (clamped at 0), else null.
age_or_null() {
  if [[ "${1:-}" =~ ^[0-9]+$ ]]; then
    local age=$(( now - $1 ))
    (( age < 0 )) && age=0
    printf '%s' "$age"
  else
    printf 'null'
  fi
}

# journald: last entry's timestamp. Empty output (journald dead / no entries)
# → null, which the watchdog reports as DEGRADED.
jline="$(timeout 10 journalctl -n1 -o short-unix --no-pager -q 2>/dev/null)"
jts="${jline%%[ .]*}"
journald_age="$(age_or_null "$jts")"

# heartbeat: mtime of the file the noctus-heartbeat.timer touches every 5 min.
hb_mtime=""
if [[ -f "$HEARTBEAT_FILE" ]]; then
  hb_mtime="$(stat -c %Y "$HEARTBEAT_FILE" 2>/dev/null)"
fi
heartbeat_age="$(age_or_null "$hb_mtime")"

# memory (kB in /proc/meminfo → MB)
mem_avail_kb=""; swap_total_kb=""; swap_free_kb=""
if [[ -r /proc/meminfo ]]; then
  while read -r key val _unit; do
    case "$key" in
      MemAvailable:) mem_avail_kb="$val" ;;
      SwapTotal:) swap_total_kb="$val" ;;
      SwapFree:) swap_free_kb="$val" ;;
    esac
  done < /proc/meminfo
fi
mem_available_mb=null
[[ "$mem_avail_kb" =~ ^[0-9]+$ ]] && mem_available_mb=$(( mem_avail_kb / 1024 ))
swap_used_mb=null
if [[ "$swap_total_kb" =~ ^[0-9]+$ && "$swap_free_kb" =~ ^[0-9]+$ ]]; then
  swap_used_mb=$(( (swap_total_kb - swap_free_kb) / 1024 ))
fi

load1=""; load5=""
if [[ -r /proc/loadavg ]]; then
  read -r load1 load5 _rest < /proc/loadavg
fi

ncpu="$(nproc 2>/dev/null)"

uptime_s=""
if [[ -r /proc/uptime ]]; then
  read -r up _idle < /proc/uptime
  uptime_s="${up%%.*}"
fi

printf '{"journald_last_age_s":%s,"heartbeat_age_s":%s,"mem_available_mb":%s,"swap_used_mb":%s,"load1":%s,"load5":%s,"ncpu":%s,"uptime_s":%s,"now":%s}\n' \
  "$journald_age" "$heartbeat_age" "$mem_available_mb" "$swap_used_mb" \
  "$(num_or_null "$load1")" "$(num_or_null "$load5")" \
  "$(int_or_null "$ncpu")" "$(int_or_null "$uptime_s")" "$(int_or_null "$now")"
exit 0
