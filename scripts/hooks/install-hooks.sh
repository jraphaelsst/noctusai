#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# install-hooks.sh — Install git hooks only (without full setup)
#
# For the full setup (hooks + venv + deps), use: bash scripts/setup.sh
#
# Hooks installed:
#   pre-commit — 1. Syncs seed → template if products/seed/ is staged.
#                2. Regenerates KB count blocks and stages them.
#                3. Verifies CLAUDE.md ↔ KB INDEX sync (blocking).
#   pre-push   — client-side branch protection: refuses force-push +
#                deletion of main/prod (free equivalent of GitHub branch
#                protection, which needs Pro on a private repo).
#
# Canonical scripts live at scripts/hooks/{pre-commit,pre-push} — the hooks are
# symlinks so edits take effect without re-installing.
# ──────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing git hooks..."

# ─── pre-commit: sync seed+template, refresh KB counts, verify KB sync
rm -f "$HOOKS_DIR/pre-commit"
ln -s "$REPO_ROOT/scripts/hooks/pre-commit" "$HOOKS_DIR/pre-commit"
chmod +x "$REPO_ROOT/scripts/hooks/pre-commit"
echo "  pre-commit: seed→template sync + KB counts + KB sync check"

# ─── pre-push: client-side branch protection (deploy-hardening P3).
# Blocks force-push + deletion of main/prod (the free equivalent of
# GitHub branch protection, which needs Pro on a private repo).
rm -f "$HOOKS_DIR/pre-push"
ln -s "$REPO_ROOT/scripts/hooks/pre-push" "$HOOKS_DIR/pre-push"
chmod +x "$REPO_ROOT/scripts/hooks/pre-push"
echo "  pre-push: refuse force-push/deletion of main + prod"

# ─── Remove legacy post-commit hook (seed sync moved to pre-commit)
if [[ -f "$HOOKS_DIR/post-commit" && ! -L "$HOOKS_DIR/post-commit" ]]; then
    # Only remove if it looks like our seed-sync hook (grep for marker)
    if grep -q "sync-seed-template" "$HOOKS_DIR/post-commit" 2>/dev/null; then
        rm -f "$HOOKS_DIR/post-commit"
        echo "  post-commit: removed (legacy seed sync → moved to pre-commit)"
    fi
fi

echo ""
echo "Done! For full setup (venv + deps + hooks): bash scripts/setup.sh"
