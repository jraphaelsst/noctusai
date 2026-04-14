#!/usr/bin/env bash
# ──────────────────────────────────────────────────────────────
# install-hooks.sh — Install git hooks only (without full setup)
#
# For the full setup (hooks + venv + deps), use: bash scripts/setup.sh
# ──────────────────────────────────────────────────────────────
set -euo pipefail

REPO_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
HOOKS_DIR="$REPO_ROOT/.git/hooks"

echo "Installing git hooks..."

cat > "$HOOKS_DIR/post-commit" << 'HOOK'
#!/usr/bin/env bash
REPO_ROOT="$(git rev-parse --show-toplevel)"
SEED_DIR="$REPO_ROOT/products/seed"
[ ! -d "$SEED_DIR" ] && exit 0
CHANGED_SEED=$(git diff-tree --no-commit-id --name-only -r HEAD -- products/seed/ 2>/dev/null | head -1)
[ -z "$CHANGED_SEED" ] && exit 0
[ -f "$REPO_ROOT/.seed-syncing" ] && rm -f "$REPO_ROOT/.seed-syncing" && exit 0
echo "[hook] Seed product changed — syncing template..."
touch "$REPO_ROOT/.seed-syncing"
bash "$REPO_ROOT/scripts/sync-seed-template.sh" 2>&1 | sed 's/^/[hook] /'
TEMPLATE_CHANGES=$(git status --porcelain -- templates/product-seed/ 2>/dev/null | head -1)
if [ -n "$TEMPLATE_CHANGES" ]; then
    git add templates/product-seed/
    git commit --amend --no-edit --no-verify 2>/dev/null
    echo "[hook] Template synced and included in commit"
else
    echo "[hook] Template already in sync"
fi
rm -f "$REPO_ROOT/.seed-syncing"
HOOK

chmod +x "$HOOKS_DIR/post-commit"
echo "  post-commit: seed → template auto-sync"
echo ""
echo "Done! For full setup (venv + deps + hooks): bash scripts/setup.sh"
