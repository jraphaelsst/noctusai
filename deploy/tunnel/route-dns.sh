#!/usr/bin/env bash
# route-dns.sh — create the proxied DNS CNAMEs for EVERY hostname in ingress.yml.
#
# WHY THIS EXISTS
# ---------------
# ingress.yml is the declared single-source-of-truth for hostname→service, but
# the matching DNS CNAMEs (`<host> → <TUNNEL_ID>.cfargotunnel.com`) were created
# by a HAND-TYPED list in README.md step 4. That list silently drifted: on
# 2026-06-02 only core / erp / seed / social (+ apex) actually resolved, while
# personal-finance, therapy-platform, daily-life, adconnect and dev-team were
# deployed + healthy in the fleet but had NO DNS record → edge NXDOMAIN.
#
# This script removes the hand-typed-list failure mode: it reads the hostnames
# straight from ingress.yml and routes each one. Driven by the SAME source of
# truth, so "add a hostname to ingress.yml + re-run this" can no longer drift.
#
# IDEMPOTENT: `cloudflared tunnel route dns` confirms/updates an existing CNAME;
# a "record already exists" is treated as success. Safe to re-run any time.
#
# REQUIRES: cloudflared authenticated to the noctusai.com zone (step 1 of the
# README — `cloudflared tunnel login`), run on the VPS (or any host with the
# zone-scoped cert). This is the deliberate, outward-facing step — it mutates
# live Cloudflare DNS, so it is NOT wired into any auto-deploy path.
#
# USAGE:
#   ./route-dns.sh <TUNNEL_NAME>            # route every ingress.yml hostname
#   ./route-dns.sh <TUNNEL_NAME> --dry-run  # print what WOULD be routed, no calls
#
# See deploy/tunnel/README.md → "Apply an ingress change".
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
INGRESS="${HERE}/ingress.yml"

TUNNEL_NAME="${1:-}"
DRY_RUN="${2:-}"

if [[ -z "${TUNNEL_NAME}" ]]; then
  echo "usage: $0 <TUNNEL_NAME> [--dry-run]" >&2
  exit 2
fi
if [[ ! -f "${INGRESS}" ]]; then
  echo "error: ingress.yml not found at ${INGRESS}" >&2
  exit 1
fi

# Extract every `- hostname: <name>` value (strip key, whitespace, comments).
# Portable read loop (no `mapfile` — that is bash-4+; macOS ships bash 3.2).
HOSTS=()
while IFS= read -r host; do
  [[ -n "${host}" ]] && HOSTS+=("${host}")
done < <(
  grep -E '^[[:space:]]*-[[:space:]]*hostname:' "${INGRESS}" \
    | sed -E 's/^[[:space:]]*-[[:space:]]*hostname:[[:space:]]*//' \
    | sed -E 's/[[:space:]]*(#.*)?$//' \
    | awk 'NF'
)

if [[ "${#HOSTS[@]}" -eq 0 ]]; then
  echo "error: no hostnames parsed from ingress.yml" >&2
  exit 1
fi

echo "Tunnel: ${TUNNEL_NAME}"
echo "Source: ${INGRESS} (${#HOSTS[@]} hostnames)"
echo

fail=0
for host in "${HOSTS[@]}"; do
  if [[ "${DRY_RUN}" == "--dry-run" ]]; then
    echo "  [dry-run] would route: ${host}"
    continue
  fi
  printf '  routing %-34s ... ' "${host}"
  if out="$(cloudflared tunnel route dns "${TUNNEL_NAME}" "${host}" 2>&1)"; then
    echo "ok"
  elif grep -qiE 'already exists|already configured|record with that host' <<<"${out}"; then
    echo "ok (already present)"
  else
    echo "FAILED"
    echo "    ${out}" >&2
    fail=1
  fi
done

if [[ "${fail}" -ne 0 ]]; then
  echo >&2
  echo "one or more routes failed — see errors above" >&2
  exit 1
fi

echo
echo "Done. Reload the tunnel if config changed:"
echo "  docker compose -f ${HERE}/compose.tunnel.yml up -d --force-recreate"
