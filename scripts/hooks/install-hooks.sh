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
#   commit-msg — appends `Noc-Branch: <branch>` (ship-consent attribution).
#   pre-push   — client-side branch protection: gates ALL pushes to
#                main/prod behind NOCTUS_ALLOW_MAIN_PUSH=1 (routine work
#                goes to dev; main is deploy-only, § 0), and always refuses
#                force-push + deletion of main/prod. Free equivalent of
#                GitHub branch protection (which needs Pro on a private repo).
#
# Also: `npm ci --prefix mcp/noctusai/node` (the toolkit's pinned PGlite for
# noctus.dev.migration_replay; advisory — a failure warns, never aborts).
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

# ─── commit-msg: ship-consent attribution trailer (Noc-Branch: <branch>).
# Lets `noctus.dev.release stage=manifest` group dev..main riders by
# branch → project, so bless never carries unapproved work to prod.
# KB § PATTERNS/devops/ship-consent-riders.md
rm -f "$HOOKS_DIR/commit-msg"
ln -s "$REPO_ROOT/scripts/hooks/commit-msg" "$HOOKS_DIR/commit-msg"
chmod +x "$REPO_ROOT/scripts/hooks/commit-msg"
echo "  commit-msg: append Noc-Branch trailer (ship-consent attribution)"

# ─── merge drivers (kb-counts, lgpd-warnings): per-repo git config, NOT committable.
# `.gitattributes` maps docs to merge=<driver>; the bodies are registered by the
# shared script (also run by .github/workflows/merge-queue.yml on the runner).
# KB § PATTERNS/common/auto-generated-merge-drivers.md
bash "$REPO_ROOT/scripts/hooks/register-merge-drivers.sh" "$REPO_ROOT"

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

# ─── Toolkit node deps: the pinned PGlite that pre-commit's migration_replay
# gate (step 6i) executes chains on. Without it every migration commit is
# `inconclusive` locally. KB § PATTERNS/backend/migration-chain-replay.md.
if command -v npm >/dev/null 2>&1; then
    if npm ci --prefix "$REPO_ROOT/mcp/noctusai/node" --no-audit --no-fund; then
        echo "  toolkit node deps: installed (mcp/noctusai/node — PGlite for migration_replay)"
    else
        echo "  toolkit node deps: npm ci FAILED — migration_replay stays inconclusive until: npm ci --prefix mcp/noctusai/node" >&2
    fi
else
    echo "  toolkit node deps: npm not on PATH — migration_replay stays inconclusive until: npm ci --prefix mcp/noctusai/node" >&2
fi

echo ""
echo "Done! For full setup (venv + deps + hooks): bash scripts/setup.sh"
