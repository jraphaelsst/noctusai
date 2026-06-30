#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────────────────────
# prod-pull.sh — VPS-side forced-command target for the CI deploy key.
#
# The deploy key's authorized_keys entry pins:
#   command="/opt/noctus/noctusai/scripts/deploy/prod-pull.sh",no-pty,
#   no-port-forwarding,no-X11-forwarding,no-agent-forwarding <pubkey>
# so the key can run ONLY this script. The client's requested command
# ("<mode> <ref>") arrives in $SSH_ORIGINAL_COMMAND — UNTRUSTED, so we
# whitelist both fields here (defense in depth; the workflow already constrains
# them to `choice` options).
#
# §2a safe-pull drill (KB § GUIDES/production-deploy.md § 2a, mirrors
# noctus.dev.deploy_pull): inspect → refuse non-FF / deploy-local overlap →
# backup (tag + tar OUTSIDE the repo) → `git merge --ff-only`. It NEVER runs
# reset / checkout -f / clean / push / any force — by construction.
#
# Exit codes: 0 ok|up_to_date|dry-run · 2 refused-input · 3 non-FF · 4 overlap.
# ──────────────────────────────────────────────────────────────────────────────
set -euo pipefail

REPO="${NOCTUS_REPO_DIR:-/opt/noctus/noctusai}"
BACKUP_DIR="${NOCTUS_BACKUP_DIR:-/opt/noctus/deploy-backups}"

# ── Parse + whitelist the locked command string ──────────────────────────────
read -r MODE REF _REST <<<"${SSH_ORIGINAL_COMMAND:-dry-run origin/prod}"
MODE="${MODE:-dry-run}"
REF="${REF:-origin/prod}"

case "$MODE" in
  dry-run|apply) ;;
  *) echo "REFUSED: mode '$MODE' not in {dry-run,apply}" >&2; exit 2 ;;
esac
# Allowed refs: origin/prod, origin/main, or a full 40-hex commit sha.
if ! { [[ "$REF" =~ ^origin/(prod|main)$ ]] || [[ "$REF" =~ ^[0-9a-f]{40}$ ]]; }; then
  echo "REFUSED: ref '$REF' not allowed (origin/prod | origin/main | <40-hex-sha>)" >&2
  exit 2
fi

cd "$REPO"
git fetch --quiet origin

CURRENT="$(git rev-parse HEAD)"
TARGET="$(git rev-parse "$REF^{commit}")"

if [[ "$CURRENT" == "$TARGET" ]]; then
  echo "up_to_date: HEAD already at ${TARGET:0:12} ($REF)"
  exit 0
fi

# FF-ability: CURRENT must be an ancestor of TARGET (no divergence / rewrite).
if ! git merge-base --is-ancestor "$CURRENT" "$TARGET"; then
  echo "REFUSED: non-fast-forward — HEAD ${CURRENT:0:12} is not an ancestor of ${TARGET:0:12} ($REF). Manual reconcile required." >&2
  exit 3
fi

# Overlap guard: refuse if any incoming file also has uncommitted local edits.
INCOMING="$(git diff --name-only "$CURRENT" "$TARGET" | sort -u)"
DIRTY="$(git status --porcelain | sed 's/^...//' | sort -u)"
if [[ -n "$DIRTY" ]]; then
  OVERLAP="$(comm -12 <(printf '%s\n' "$INCOMING") <(printf '%s\n' "$DIRTY") | grep -v '^$' || true)"
  if [[ -n "$OVERLAP" ]]; then
    echo "REFUSED: incoming files overlap uncommitted local edits:" >&2
    printf '  %s\n' "$OVERLAP" >&2
    exit 4
  fi
fi

echo "plan: $REF   ${CURRENT:0:12} -> ${TARGET:0:12}"
echo "incoming commits:"
git --no-pager log --oneline "$CURRENT".."$TARGET"

if [[ "$MODE" == "dry-run" ]]; then
  echo "dry-run — no changes made"
  exit 0
fi

# ── apply ── backup BEFORE moving HEAD, then FF-only.
mkdir -p "$BACKUP_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
git tag "deploy-backup-$TS" "$CURRENT"
if ! tar -czf "$BACKUP_DIR/noctusai-$TS.tar.gz" -C "$(dirname "$REPO")" "$(basename "$REPO")" 2>/dev/null; then
  echo "::warning:: tar snapshot failed (tag deploy-backup-$TS still recorded)"
fi
git merge --ff-only "$REF"
echo "deployed: HEAD now $(git rev-parse HEAD | cut -c1-12) (rollback: git reset --hard deploy-backup-$TS)"
