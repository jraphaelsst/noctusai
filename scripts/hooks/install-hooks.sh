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
#   pre-push   — client-side branch protection: gates ALL pushes to
#                main/prod behind NOCTUS_ALLOW_MAIN_PUSH=1 (routine work
#                goes to dev; main is deploy-only, § 0), and always refuses
#                force-push + deletion of main/prod. Free equivalent of
#                GitHub branch protection (which needs Pro on a private repo).
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

# ─── pre-push: client-side branch protection.
# Gates ALL pushes to main/prod behind NOCTUS_ALLOW_MAIN_PUSH=1 (routine
# work → dev; main deploy-only, § 0); always refuses force-push + deletion.
rm -f "$HOOKS_DIR/pre-push"
ln -s "$REPO_ROOT/scripts/hooks/pre-push" "$HOOKS_DIR/pre-push"
chmod +x "$REPO_ROOT/scripts/hooks/pre-push"
echo "  pre-push: gate main/prod pushes (NOCTUS_ALLOW_MAIN_PUSH=1 to deploy) + refuse force/delete"

# ─── post-merge: auto-refresh caches after git pull / merge.
# Without this, `git pull` brings in remote KB / code changes but the
# local caches stay stale (no commit boundary means pre-commit doesn't fire).
# KB § PATTERNS/common/cache-auto-freshness.md.
rm -f "$HOOKS_DIR/post-merge"
ln -s "$REPO_ROOT/scripts/hooks/post-merge" "$HOOKS_DIR/post-merge"
chmod +x "$REPO_ROOT/scripts/hooks/post-merge"
echo "  post-merge: auto-refresh caches after git pull / merge"

# ─── post-checkout: auto-refresh caches after branch switch.
# Working tree changes on branch switch; caches must follow.
rm -f "$HOOKS_DIR/post-checkout"
ln -s "$REPO_ROOT/scripts/hooks/post-checkout" "$HOOKS_DIR/post-checkout"
chmod +x "$REPO_ROOT/scripts/hooks/post-checkout"
echo "  post-checkout: auto-refresh caches after branch switch"

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
